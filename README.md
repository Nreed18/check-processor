# Check Processor - Family Radio

Automated check processing system for accounts receivable. Processes remote deposit PDFs, extracts check data via OCR, matches contacts in HubSpot, and creates deals automatically.

## Features

- **PDF Processing**: Automatically splits remote deposit PDFs into individual checks
- **OCR Extraction**: Azure Computer Vision extracts check data (amount, date, check #, name, address)
- **HubSpot Integration**: Fuzzy matching to existing contacts, automatic deal creation
- **Dual Workflow Support**:
  - **Bank Check batches (035)**: Uses clean buck slips for contact info
  - **General Mail batches (020)**: OCRs handwritten checks
- **Smart Flagging**: Automatically flags money orders, missing addresses, and unmatched contacts
- **Real-time Progress**: Live updates during batch processing
- **Manual Review**: Edit any field before submitting to HubSpot
- **48-Hour Retention**: Batch data auto-purges after submission

## System Requirements

- Ubuntu 24 (or similar Linux)
- Python 3.10+
- PostgreSQL 12+
- docTR OCR (free, local, deep learning)
- HubSpot API key (with CRM permissions)

## Installation

### 1. Clone Repository

```bash
cd /home/claude
# (Repository should already be in /home/claude/check-processor)
```

### 2. Install System Dependencies

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib python3-pip python3-venv poppler-utils
```

**Note:** docTR is a Python package and will be installed via pip (no system packages needed)

### 3. Create Virtual Environment

```bash
cd /home/claude/check-processor
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Set Up PostgreSQL Database

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create database and user
CREATE DATABASE check_processor;
CREATE USER check_user WITH PASSWORD 'secure-password-here';
GRANT ALL PRIVILEGES ON DATABASE check_processor TO check_user;
\q
```

### 6. Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

**Required settings:**
- `SECRET_KEY`: Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `DATABASE_URL`: Update with your PostgreSQL credentials
- `HUBSPOT_API_KEY`: Your HubSpot private app token

**Note:** Using docTR (deep learning OCR) - no API keys needed! Models download automatically on first run (~200MB).

### 7. Initialize Database

```bash
source venv/bin/activate
python3 run.py
# Press Ctrl+C after it starts (creates tables)
```

## Running the Application

### Development Mode

```bash
source venv/bin/activate
python3 run.py
```

Access at: `http://localhost:5000`

### Production Deployment (systemd)

Create service file:

```bash
sudo nano /etc/systemd/system/check-processor.service
```

```ini
[Unit]
Description=Family Radio Check Processor
After=network.target postgresql.service

[Service]
Type=simple
User=claude
WorkingDirectory=/home/claude/check-processor
Environment="PATH=/home/claude/check-processor/venv/bin"
ExecStart=/home/claude/check-processor/venv/bin/python3 /home/claude/check-processor/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable check-processor
sudo systemctl start check-processor
sudo systemctl status check-processor
```

### Cloudflare Zero Trust Tunnel

```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Authenticate and create tunnel
cloudflared tunnel login
cloudflared tunnel create check-processor
cloudflared tunnel route dns check-processor checks.familyradio.org

# Create config
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

```yaml
tunnel: <tunnel-id>
credentials-file: /home/claude/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: checks.familyradio.org
    service: http://localhost:5000
  - service: http_status:404
```

```bash
# Run tunnel as service
sudo cloudflared service install
sudo systemctl start cloudflared
```

## Usage

### 1. Upload New Batch

1. Navigate to "New Batch"
2. Upload remote deposit PDF
3. Enter deposit date, batch number, expected total
4. Select appeal type:
   - **General Mail - 020**: Mail checks (OCRs handwritten info)
   - **Bank Check - 035**: Bank batch (uses buck slips)
5. Click "Start Processing"

### 2. Live Processing

- System splits PDF into individual checks
- OCR runs on each check (2-3 sec per check)
- First check appears immediately while others process
- Automatic contact matching in HubSpot
- Flags special cases (money orders, no address, etc.)

### 3. Review & Edit

- Review all checks in batch
- Edit any field (amount, date, name, address)
- Search HubSpot contacts via typeahead
- Exclude checks from batch if needed
- Running total updates live

### 4. Submit to HubSpot

- Verify totals match expected amount
- Click "Submit to HubSpot"
- System creates deals for all non-excluded checks
- Associates deals with matched contacts
- Generates annotated PDF with deal IDs

### 5. Data Retention

- Batch data retained for 48 hours after submission
- Can re-edit and resubmit if needed
- After 48 hours: automatic purge via cron job

## API Endpoints

### Batch Management

- `POST /api/batch/create` - Create new batch and start processing
- `GET /api/batch/<id>` - Get batch details
- `GET /api/batch/<id>/checks` - Get all checks in batch
- `GET /api/batch/<id>/stream` - SSE stream for progress updates
- `POST /api/batch/<id>/submit` - Submit batch to HubSpot
- `DELETE /api/batch/<id>/delete` - Delete batch

### Check Management

- `GET /api/check/<id>` - Get check details
- `PUT /api/check/<id>` - Update check fields

### HubSpot Integration

- `POST /api/contacts/search` - Search HubSpot contacts
- `POST /api/contacts/create` - Create new contact

## HubSpot Field Mapping

**Auto-filled Deal Fields:**
- Deal name: Contact name
- Pipeline: "Gifts"
- Deal stage: "Closed Won"
- Amount: OCR extracted
- Close date: Submission timestamp
- Payment Method: "Check"
- Check Date: From check
- Check Number: OCR extracted
- Batch Number: User entered
- Appeal: User selected
- Appeal Code: Auto-set (20 or 35)
- Account Number: From matched contact
- Deal owner: Auto-assigns to logged-in user
- Postmark Year: Year from check date

## Troubleshooting

### OCR Issues

**Problem**: docTR models not downloading
```bash
# Manually download models (if behind firewall)
python3 -c "from doctr.models import ocr_predictor; ocr_predictor(pretrained=True)"
# Models cache in ~/.cache/doctr/models/
```

**Problem**: Amounts not detected
- Check image quality in PDF
- Verify DPI is 300 (set in code)
- Look for errors in logs: `journalctl -u check-processor -f`

**Problem**: Dates parsing incorrectly
- Common formats supported: MM/DD/YYYY, MM-DD-YY, "December 31, 2025"
- Edit manually in review screen

**Problem**: Slow processing on first run
- docTR downloads models on first run (~200MB)
- Subsequent runs are much faster
- Models cache in ~/.cache/doctr/models/

**Problem**: Out of memory errors
- docTR requires ~2GB RAM for processing
- Reduce concurrent processing in config: `MAX_CONCURRENT_OCR = 2`
- Or upgrade to cloud OCR (Azure/Google) for lower memory usage

### HubSpot Matching

**Problem**: No contacts found
- Verify HubSpot API key has read permissions
- Check that contacts have addresses populated
- Use typeahead search to manually select

**Problem**: Deals not creating
- Verify API key has deal write permissions
- Check HubSpot pipeline/stage names match config
- Review error logs

### Database Issues

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# View logs
sudo journalctl -u postgresql -n 50

# Reset database
sudo -u postgres psql
DROP DATABASE check_processor;
CREATE DATABASE check_processor;
\q
python3 run.py  # Recreates tables
```

### Performance

**docTR OCR processing**:
- Local processing: ~2-3 sec per check (depends on CPU)
- No API rate limits (runs locally)
- Accuracy: ~90-95% for printed text, ~80-85% for handwriting
- Much better than Tesseract, close to cloud OCR

**To improve performance**:
- Use GPU acceleration (if available): Install `python-doctr[tf]` or keep `[torch]`
- Increase DPI for better accuracy (300 recommended)
- Use SSD storage for faster image processing
- Consider cloud OCR (Azure/Google) only if handwriting accuracy still insufficient

## Cron Job - Data Purge

Create cron job to purge old batches:

```bash
crontab -e
```

```bash
# Run daily at 2 AM
0 2 * * * /home/claude/check-processor/venv/bin/python3 /home/claude/check-processor/scripts/purge_old_batches.py
```

Create purge script:

```bash
mkdir -p /home/claude/check-processor/scripts
```

```python
# scripts/purge_old_batches.py
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/home/claude/check-processor')

from app import create_app
from app.models import db, Batch
import os
import shutil

app = create_app()

with app.app_context():
    # Find batches older than 48 hours
    cutoff = datetime.utcnow() - timedelta(hours=48)
    old_batches = Batch.query.filter(
        Batch.submitted_at < cutoff,
        Batch.status == 'submitted'
    ).all()
    
    for batch in old_batches:
        print(f"Purging batch {batch.id}: {batch.batch_name}")
        
        # Delete files
        if batch.pdf_filename:
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], batch.pdf_filename)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        
        image_dir = os.path.join(app.config['UPLOAD_FOLDER'], f'batch_{batch.id}_images')
        if os.path.exists(image_dir):
            shutil.rmtree(image_dir)
        
        # Delete from database
        db.session.delete(batch)
    
    db.session.commit()
    print(f"Purged {len(old_batches)} batches")
```

## Monitoring

### Application Logs

```bash
# View live logs
sudo journalctl -u check-processor -f

# View recent errors
sudo journalctl -u check-processor -p err -n 50
```

### Database Size

```bash
sudo -u postgres psql check_processor -c "SELECT pg_size_pretty(pg_database_size('check_processor'));"
```

### File Storage

```bash
du -sh /home/claude/check-processor/uploads
```

## Security Considerations

- API keys stored in `.env` (not committed to git)
- Simple password auth (not tied to HubSpot)
- Cloudflare Zero Trust for secure external access
- Files auto-purge after 48 hours
- Checks already deposited before upload (low risk)

## Cost Analysis

**docTR OCR**:
- **FREE** (runs locally)
- No API costs
- No usage limits
- No cloud dependencies
- Better accuracy than Tesseract

**HubSpot API**:
- Included with most HubSpot tiers
- No additional cost

**Total**: **COMPLETELY FREE!** 🎉

**Comparison to alternatives**:
- **docTR**: FREE, 90-95% accuracy (printed), 80-85% (handwriting)
- **Azure Computer Vision**: FREE tier (5,000/month) then $1/1,000, 95%+ accuracy
- **Google Cloud Vision**: FREE tier (1,000/month) then $1.50/1,000, 95%+ accuracy

docTR gives you near-cloud accuracy without any costs!

## Support

For issues or questions:
1. Check logs: `sudo journalctl -u check-processor -f`
2. Review this README
3. Contact IT team

## Future Enhancements

- [ ] Multi-user authentication (LDAP/SSO)
- [ ] Email notifications on batch completion
- [ ] Export batch summary to Excel
- [ ] Mobile-responsive review interface
- [ ] Advanced duplicate detection
- [ ] Batch analytics dashboard
- [ ] Integration with accounting software

## License

Internal use only - Family Radio
