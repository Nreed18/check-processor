from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Batch(db.Model):
    """Represents a batch of checks to process"""
    __tablename__ = 'batches'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_name = db.Column(db.String(200), nullable=False, unique=True)
    batch_number = db.Column(db.String(100), nullable=False)
    deposit_date = db.Column(db.Date, nullable=False)
    appeal_type = db.Column(db.String(50), nullable=False)  # "General Mail - 020" or "Bank Check - 035"
    appeal_code = db.Column(db.String(10), nullable=False)  # "020" or "035"
    expected_total = db.Column(db.Numeric(10, 2), nullable=False)
    actual_total = db.Column(db.Numeric(10, 2), default=0)
    
    status = db.Column(db.String(20), default='processing')  # processing, completed, submitted
    pdf_filename = db.Column(db.String(255))
    total_checks = db.Column(db.Integer, default=0)
    processed_checks = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)
    
    # Relationships
    checks = db.relationship('Check', backref='batch', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Batch {self.batch_name}>'
    
    def is_expired(self):
        """Check if batch is older than 48 hours"""
        if not self.submitted_at:
            return False
        expiry_time = self.submitted_at + timedelta(hours=48)
        return datetime.utcnow() > expiry_time
    
    def to_dict(self):
        """Convert batch to dictionary"""
        return {
            'id': self.id,
            'batch_name': self.batch_name,
            'batch_number': self.batch_number,
            'deposit_date': self.deposit_date.isoformat() if self.deposit_date else None,
            'appeal_type': self.appeal_type,
            'appeal_code': self.appeal_code,
            'expected_total': float(self.expected_total),
            'actual_total': float(self.actual_total),
            'status': self.status,
            'total_checks': self.total_checks,
            'processed_checks': self.processed_checks,
            'created_at': self.created_at.isoformat(),
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
        }


class Check(db.Model):
    """Represents an individual check in a batch"""
    __tablename__ = 'checks'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=False)
    sequence_number = db.Column(db.Integer, nullable=False)  # Order in PDF
    
    # OCR extracted data
    amount = db.Column(db.Numeric(10, 2))
    check_date = db.Column(db.Date)
    check_number = db.Column(db.String(50))
    payee_name = db.Column(db.String(255))
    address_line1 = db.Column(db.String(255))
    address_line2 = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    
    # Bank info
    routing_number = db.Column(db.String(20))
    account_number = db.Column(db.String(50))
    
    # HubSpot matching
    hubspot_contact_id = db.Column(db.String(50))
    hubspot_account_number = db.Column(db.String(50))
    hubspot_deal_id = db.Column(db.String(50))
    match_confidence = db.Column(db.String(20))  # exact, fuzzy, manual, none
    
    # Flags
    is_money_order = db.Column(db.Boolean, default=False)
    is_no_address = db.Column(db.Boolean, default=False)
    is_flagged = db.Column(db.Boolean, default=False)
    flag_reason = db.Column(db.String(255))
    excluded = db.Column(db.Boolean, default=False)
    
    # Check images (stored as file paths)
    front_image_path = db.Column(db.String(255))
    buck_slip_path = db.Column(db.String(255))
    
    # Status
    processed = db.Column(db.Boolean, default=False)
    submitted = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Check {self.id} - {self.payee_name}>'
    
    def to_dict(self):
        """Convert check to dictionary"""
        return {
            'id': self.id,
            'sequence_number': self.sequence_number,
            'amount': float(self.amount) if self.amount else None,
            'check_date': self.check_date.isoformat() if self.check_date else None,
            'check_number': self.check_number,
            'payee_name': self.payee_name,
            'address_line1': self.address_line1,
            'address_line2': self.address_line2,
            'city': self.city,
            'state': self.state,
            'zip_code': self.zip_code,
            'hubspot_contact_id': self.hubspot_contact_id,
            'hubspot_deal_id': self.hubspot_deal_id,
            'match_confidence': self.match_confidence,
            'is_money_order': self.is_money_order,
            'is_no_address': self.is_no_address,
            'is_flagged': self.is_flagged,
            'flag_reason': self.flag_reason,
            'excluded': self.excluded,
            'front_image_path': self.front_image_path,
            'processed': self.processed,
            'submitted': self.submitted,
        }
