import os
import threading
from datetime import datetime
from flask import current_app
from app.models import db, Batch, Check
from app.ocr import CheckOCR
from app.hubspot import HubSpotClient

class BatchProcessor:
    """Orchestrates batch processing of checks"""
    
    def __init__(self, batch_id):
        self.batch_id = batch_id
        self.batch = None
        self.ocr = None
        self.hubspot = None
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """Set callback function for progress updates"""
        self.progress_callback = callback
    
    def _emit_progress(self, message, check_number=None, total=None):
        """Emit progress update"""
        if self.progress_callback:
            self.progress_callback({
                'batch_id': self.batch_id,
                'message': message,
                'check_number': check_number,
                'total': total,
                'timestamp': datetime.utcnow().isoformat()
            })
    
    def process_batch(self):
        """Main processing function - runs in background thread"""
        try:
            # Load batch
            self.batch = Batch.query.get(self.batch_id)
            if not self.batch:
                return
            
            # Initialize services
            self.ocr = CheckOCR()
            self.hubspot = HubSpotClient()
            
            # Get PDF path
            pdf_path = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                self.batch.pdf_filename
            )
            
            if not os.path.exists(pdf_path):
                self._emit_progress("Error: PDF file not found")
                return
            
            # Split PDF into images
            self._emit_progress("Splitting PDF into pages...")
            output_dir = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                f'batch_{self.batch_id}_images'
            )
            os.makedirs(output_dir, exist_ok=True)
            
            image_paths = self.ocr.split_pdf(pdf_path, output_dir)
            
            # Determine check pattern based on appeal type
            is_bank_batch = self.batch.appeal_code == "035"
            pages_per_check = 3 if is_bank_batch else 2
            
            # Calculate total checks
            total_checks = len(image_paths) // pages_per_check
            self.batch.total_checks = total_checks
            db.session.commit()
            
            self._emit_progress(
                f"Found {total_checks} checks to process",
                check_number=0,
                total=total_checks
            )
            
            # Process each check
            for check_idx in range(total_checks):
                self._process_single_check(
                    check_idx,
                    image_paths,
                    pages_per_check,
                    is_bank_batch,
                    total_checks
                )
            
            # Update batch status
            self.batch.status = 'completed'
            self.batch.processed_checks = total_checks
            db.session.commit()
            
            self._emit_progress(
                "Batch processing complete!",
                check_number=total_checks,
                total=total_checks
            )
            
        except Exception as e:
            current_app.logger.error(f"Batch processing error: {e}")
            self._emit_progress(f"Error: {str(e)}")
            if self.batch:
                self.batch.status = 'error'
                db.session.commit()
    
    def _process_single_check(self, check_idx, image_paths, pages_per_check, is_bank_batch, total_checks):
        """Process a single check"""
        try:
            check_num = check_idx + 1
            self._emit_progress(
                f"Processing check {check_num}...",
                check_number=check_num,
                total=total_checks
            )
            
            # Calculate page indices
            start_idx = check_idx * pages_per_check
            front_idx = start_idx
            buck_slip_idx = start_idx + 2 if is_bank_batch else None
            
            # OCR check front
            front_path = image_paths[front_idx]
            front_data = self.ocr.process_check_front(front_path)
            
            # Initialize check data
            check_data = {
                'amount': front_data.get('amount'),
                'check_date': front_data.get('check_date'),
                'check_number': front_data.get('check_number'),
                'is_money_order': front_data.get('is_money_order', False),
                'front_image_path': front_path,
            }
            
            # Process buck slip if bank batch
            if is_bank_batch and buck_slip_idx:
                buck_slip_path = image_paths[buck_slip_idx]
                buck_slip_data = self.ocr.process_buck_slip(buck_slip_path)
                
                check_data.update({
                    'payee_name': buck_slip_data.get('name'),
                    'address_line1': buck_slip_data.get('address_line1'),
                    'city': buck_slip_data.get('city'),
                    'state': buck_slip_data.get('state'),
                    'zip_code': buck_slip_data.get('zip_code'),
                    'buck_slip_path': buck_slip_path,
                })
            else:
                # Extract from check front (handwritten)
                name_address = self.ocr.extract_name_address(front_data.get('raw_text', ''))
                check_data.update(name_address)
            
            # Check for missing address
            is_no_address = not check_data.get('address_line1')
            check_data['is_no_address'] = is_no_address
            
            # Attempt HubSpot matching
            if not check_data['is_money_order'] and not is_no_address:
                contact, confidence = self._match_contact(check_data)
                if contact:
                    check_data['hubspot_contact_id'] = contact['id']
                    check_data['hubspot_account_number'] = contact['account_number']
                    check_data['match_confidence'] = confidence
                else:
                    check_data['match_confidence'] = 'none'
            
            # Flag if needed
            is_flagged = (
                check_data['is_money_order'] or
                is_no_address or
                check_data.get('match_confidence') == 'none'
            )
            check_data['is_flagged'] = is_flagged
            
            if check_data['is_money_order']:
                check_data['flag_reason'] = 'Money Order - Manual Review Required'
            elif is_no_address:
                check_data['flag_reason'] = 'No Address Found'
            elif check_data.get('match_confidence') == 'none':
                check_data['flag_reason'] = 'No Contact Match Found'
            
            # Create check record
            check = Check(
                batch_id=self.batch_id,
                sequence_number=check_num,
                **check_data,
                processed=True
            )
            db.session.add(check)
            
            # Update batch totals
            if check_data['amount']:
                self.batch.actual_total += check_data['amount']
            self.batch.processed_checks += 1
            
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Error processing check {check_num}: {e}")
            self._emit_progress(f"Error on check {check_num}: {str(e)}")
    
    def _match_contact(self, check_data):
        """Match check to HubSpot contact"""
        try:
            # Search by address first (more reliable)
            candidates = []
            if check_data.get('address_line1'):
                candidates = self.hubspot.search_contacts_by_address(
                    check_data['address_line1'],
                    check_data.get('city'),
                    check_data.get('state')
                )
            
            # If no address matches, try name
            if not candidates and check_data.get('payee_name'):
                candidates = self.hubspot.search_contacts_by_name(
                    check_data['payee_name']
                )
            
            # Fuzzy match
            if candidates:
                return self.hubspot.fuzzy_match_contacts(
                    check_data.get('payee_name', ''),
                    check_data.get('address_line1', ''),
                    candidates
                )
            
            return None, 'none'
            
        except Exception as e:
            current_app.logger.error(f"Contact matching error: {e}")
            return None, 'none'


def start_batch_processing(batch_id, progress_callback=None):
    """Start batch processing in background thread"""
    processor = BatchProcessor(batch_id)
    if progress_callback:
        processor.set_progress_callback(progress_callback)
    
    thread = threading.Thread(target=processor.process_batch)
    thread.daemon = True
    thread.start()
    
    return thread
