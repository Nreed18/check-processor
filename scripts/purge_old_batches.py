#!/usr/bin/env python3
"""
Purge old batches (48 hours after submission)
Run via cron: 0 2 * * * /path/to/this/script.py
"""

from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, Batch
import shutil

def purge_old_batches():
    """Purge batches older than 48 hours"""
    app = create_app()
    
    with app.app_context():
        # Find batches older than 48 hours
        cutoff = datetime.utcnow() - timedelta(hours=48)
        old_batches = Batch.query.filter(
            Batch.submitted_at < cutoff,
            Batch.status == 'submitted'
        ).all()
        
        purged_count = 0
        
        for batch in old_batches:
            try:
                print(f"[{datetime.now()}] Purging batch {batch.id}: {batch.batch_name}")
                
                # Delete PDF file
                if batch.pdf_filename:
                    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], batch.pdf_filename)
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)
                        print(f"  - Deleted PDF: {pdf_path}")
                
                # Delete image directory
                image_dir = os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    f'batch_{batch.id}_images'
                )
                if os.path.exists(image_dir):
                    shutil.rmtree(image_dir)
                    print(f"  - Deleted images: {image_dir}")
                
                # Delete from database (cascades to checks)
                db.session.delete(batch)
                purged_count += 1
                
            except Exception as e:
                print(f"  - ERROR: {e}")
                continue
        
        db.session.commit()
        print(f"\n[{datetime.now()}] Purged {purged_count} batches")
        
        return purged_count

if __name__ == '__main__':
    purge_old_batches()
