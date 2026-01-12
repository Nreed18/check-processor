from flask import Blueprint, render_template, request, jsonify, current_app, Response, stream_with_context
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import json
from app.models import db, Batch, Check
from app.ocr import CheckOCR
from app.processor import start_batch_processing
from app.hubspot import HubSpotClient

bp = Blueprint('main', __name__)

# Store SSE clients
sse_clients = {}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@bp.route('/')
def index():
    """Homepage - batch list"""
    # Get recent batches (last 7 days)
    cutoff_date = datetime.utcnow() - timedelta(days=7)
    batches = Batch.query.filter(
        Batch.created_at >= cutoff_date
    ).order_by(Batch.created_at.desc()).all()
    
    return render_template('index.html', batches=batches)


@bp.route('/upload', methods=['GET'])
def upload_form():
    """Upload form page"""
    return render_template('upload.html')


@bp.route('/api/batch/create', methods=['POST'])
def create_batch():
    """Create new batch and start processing"""
    try:
        missing_dependencies = CheckOCR.missing_system_dependencies()
        if missing_dependencies:
            missing_list = ", ".join(missing_dependencies)
            return jsonify({
                'error': (
                    "OCR system dependencies are missing. Install with: "
                    f"sudo apt install -y {missing_list}"
                )
            }), 500
        # Validate input
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['pdf_file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only PDF allowed'}), 400
        
        # Get form data
        deposit_date = datetime.strptime(request.form['deposit_date'], '%Y-%m-%d').date()
        batch_number = request.form['batch_number']
        appeal_type = request.form['appeal_type']
        expected_total = float(request.form['expected_total'])
        
        # Extract appeal code
        appeal_code = appeal_type.split(' - ')[-1]  # "General Mail - 020" -> "020"
        
        # Generate unique batch name
        batch_name = f"Batch {datetime.now().strftime('%b %d %I:%M %p')}"
        
        # Save PDF
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = f"{timestamp}_{filename}"
        pdf_path = os.path.join(current_app.config['UPLOAD_FOLDER'], pdf_filename)
        file.save(pdf_path)
        
        # Create batch record
        batch = Batch(
            batch_name=batch_name,
            batch_number=batch_number,
            deposit_date=deposit_date,
            appeal_type=appeal_type,
            appeal_code=appeal_code,
            expected_total=expected_total,
            pdf_filename=pdf_filename,
            status='processing'
        )
        db.session.add(batch)
        db.session.commit()
        
        # Start processing in background
        def progress_callback(data):
            """Send progress updates to SSE clients"""
            if batch.id in sse_clients:
                for queue in sse_clients[batch.id]:
                    queue.put(data)
        
        start_batch_processing(batch.id, progress_callback)
        
        return jsonify({
            'success': True,
            'batch_id': batch.id,
            'batch_name': batch_name
        })
        
    except Exception as e:
        current_app.logger.error(f"Error creating batch: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/batch/<int:batch_id>')
def batch_review(batch_id):
    """Batch review/edit page"""
    batch = Batch.query.get_or_404(batch_id)
    checks = Check.query.filter_by(batch_id=batch_id).order_by(Check.sequence_number).all()
    
    return render_template('review.html', batch=batch, checks=checks)


@bp.route('/api/batch/<int:batch_id>')
def get_batch(batch_id):
    """Get batch details"""
    batch = Batch.query.get_or_404(batch_id)
    return jsonify(batch.to_dict())


@bp.route('/api/batch/<int:batch_id>/checks')
def get_batch_checks(batch_id):
    """Get all checks in batch"""
    checks = Check.query.filter_by(batch_id=batch_id).order_by(Check.sequence_number).all()
    return jsonify([check.to_dict() for check in checks])


@bp.route('/api/check/<int:check_id>', methods=['GET', 'PUT'])
def check_detail(check_id):
    """Get or update check details"""
    check = Check.query.get_or_404(check_id)
    
    if request.method == 'GET':
        return jsonify(check.to_dict())
    
    elif request.method == 'PUT':
        # Update check fields
        data = request.json
        
        # Update editable fields
        if 'amount' in data:
            check.amount = data['amount']
        if 'check_date' in data:
            check.check_date = datetime.fromisoformat(data['check_date']).date()
        if 'check_number' in data:
            check.check_number = data['check_number']
        if 'payee_name' in data:
            check.payee_name = data['payee_name']
        if 'address_line1' in data:
            check.address_line1 = data['address_line1']
        if 'city' in data:
            check.city = data['city']
        if 'state' in data:
            check.state = data['state']
        if 'zip_code' in data:
            check.zip_code = data['zip_code']
        if 'hubspot_contact_id' in data:
            check.hubspot_contact_id = data['hubspot_contact_id']
        if 'excluded' in data:
            check.excluded = data['excluded']
        
        # Recalculate batch total
        batch = check.batch
        batch.actual_total = sum(
            c.amount for c in batch.checks.filter_by(excluded=False) if c.amount
        )
        
        db.session.commit()
        
        return jsonify({'success': True, 'check': check.to_dict()})


@bp.route('/api/contacts/search', methods=['POST'])
def search_contacts():
    """Search HubSpot contacts"""
    try:
        data = request.json
        query = data.get('query', '')
        search_type = data.get('type', 'name')  # 'name' or 'address'
        
        hubspot = HubSpotClient()
        
        if search_type == 'name':
            results = hubspot.search_contacts_by_name(query)
        elif search_type == 'address':
            results = hubspot.search_contacts_by_address(query)
        else:
            results = []
        
        return jsonify({'results': results})
        
    except Exception as e:
        current_app.logger.error(f"Contact search error: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/contacts/create', methods=['POST'])
def create_contact():
    """Create new HubSpot contact"""
    try:
        data = request.json
        
        hubspot = HubSpotClient()
        contact_id = hubspot.create_contact(
            name=data['name'],
            address=data.get('address', ''),
            city=data.get('city', ''),
            state=data.get('state', ''),
            zip_code=data.get('zip_code', ''),
            phone=data.get('phone'),
            email=data.get('email')
        )
        
        return jsonify({'success': True, 'contact_id': contact_id})
        
    except Exception as e:
        current_app.logger.error(f"Contact creation error: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/batch/<int:batch_id>/submit', methods=['POST'])
def submit_batch(batch_id):
    """Submit batch - create deals in HubSpot"""
    try:
        batch = Batch.query.get_or_404(batch_id)
        hubspot = HubSpotClient()
        
        # Get non-excluded checks
        checks = Check.query.filter_by(
            batch_id=batch_id,
            excluded=False
        ).all()
        
        success_count = 0
        error_count = 0
        
        for check in checks:
            try:
                # Skip if already submitted
                if check.submitted:
                    continue
                
                # Create or verify contact
                contact_id = check.hubspot_contact_id
                if not contact_id:
                    # Create new contact
                    contact_id = hubspot.create_contact(
                        name=check.payee_name,
                        address=check.address_line1 or '',
                        city=check.city or '',
                        state=check.state or '',
                        zip_code=check.zip_code or '',
                        email=f"{check.payee_name.replace(' ', '.').lower()}@fakeradio.com" if check.payee_name else None
                    )
                    check.hubspot_contact_id = contact_id
                
                # Create deal
                deal_id = hubspot.create_deal(
                    check_data=check.to_dict(),
                    batch_data=batch.to_dict(),
                    contact_id=contact_id
                )
                
                check.hubspot_deal_id = deal_id
                check.submitted = True
                success_count += 1
                
            except Exception as e:
                current_app.logger.error(f"Error submitting check {check.id}: {e}")
                error_count += 1
        
        # Update batch status
        batch.status = 'submitted'
        batch.submitted_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'submitted': success_count,
            'errors': error_count
        })
        
    except Exception as e:
        current_app.logger.error(f"Batch submission error: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/batch/<int:batch_id>/stream')
def batch_stream(batch_id):
    """Server-Sent Events stream for batch progress"""
    import queue
    
    def event_stream():
        q = queue.Queue()
        
        # Register client
        if batch_id not in sse_clients:
            sse_clients[batch_id] = []
        sse_clients[batch_id].append(q)
        
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        except GeneratorExit:
            # Client disconnected
            sse_clients[batch_id].remove(q)
            if not sse_clients[batch_id]:
                del sse_clients[batch_id]
    
    return Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@bp.route('/api/batch/<int:batch_id>/delete', methods=['DELETE'])
def delete_batch(batch_id):
    """Delete batch and associated data"""
    try:
        batch = Batch.query.get_or_404(batch_id)
        
        # Delete PDF and images
        if batch.pdf_filename:
            pdf_path = os.path.join(current_app.config['UPLOAD_FOLDER'], batch.pdf_filename)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        
        # Delete image directory
        image_dir = os.path.join(
            current_app.config['UPLOAD_FOLDER'],
            f'batch_{batch_id}_images'
        )
        if os.path.exists(image_dir):
            import shutil
            shutil.rmtree(image_dir)
        
        # Delete from database (cascades to checks)
        db.session.delete(batch)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        current_app.logger.error(f"Batch deletion error: {e}")
        return jsonify({'error': str(e)}), 500
