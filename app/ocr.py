import ctypes.util
import os
import re
from datetime import datetime
from pdf2image import convert_from_path
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from PIL import Image
from flask import current_app

class CheckOCR:
    """Handles OCR processing of checks using docTR (deep learning, local, free)"""
    REQUIRED_LIBRARIES = {
        "pango-1.0": "libpango-1.0-0",
        "pangocairo-1.0": "libpangocairo-1.0-0",
    }

    @staticmethod
    def missing_system_dependencies():
        """Return a list of missing system packages required by docTR."""
        missing = []
        for library, package in CheckOCR.REQUIRED_LIBRARIES.items():
            if ctypes.util.find_library(library) is None:
                missing.append(package)
        return missing
    
    def __init__(self):
        """Initialize docTR OCR model - no API keys needed!"""
        try:
            missing = self.missing_system_dependencies()
            if missing:
                missing_list = ", ".join(missing)
                raise ValueError(
                    "Missing system libraries required for docTR: "
                    f"{missing_list}. Install with: sudo apt install -y {missing_list}"
                )
            # Load pretrained docTR model (happens once at startup)
            # Using detection + recognition models
            self.model = ocr_predictor(
                det_arch='db_resnet50',
                reco_arch='crnn_vgg16_bn',
                pretrained=True
            )
            current_app.logger.info("docTR model loaded successfully")
        except Exception as e:
            raise ValueError(f"Failed to load docTR model: {e}")
    
    def split_pdf(self, pdf_path, output_dir):
        """
        Split PDF into individual page images
        Returns: list of image paths
        """
        images = convert_from_path(pdf_path, dpi=300)
        image_paths = []
        
        for i, image in enumerate(images):
            image_path = os.path.join(output_dir, f'page_{i+1:04d}.png')
            image.save(image_path, 'PNG')
            image_paths.append(image_path)
        
        return image_paths
    
    def ocr_image(self, image_path):
        """
        Run OCR on an image using docTR
        Returns: extracted text
        """
        try:
            # Load image with docTR
            doc = DocumentFile.from_images(image_path)
            
            # Run OCR prediction
            result = self.model(doc)
            
            # Extract all text from result
            text_blocks = []
            for page in result.pages:
                for block in page.blocks:
                    for line in block.lines:
                        # Combine words in each line
                        line_text = ' '.join([word.value for word in line.words])
                        text_blocks.append(line_text)
            
            # Join all text with spaces
            full_text = ' '.join(text_blocks)
            return full_text
            
        except Exception as e:
            current_app.logger.error(f"docTR OCR error on {image_path}: {e}")
            return ""
    
    def detect_money_order(self, text):
        """Detect if check is a money order or MoneyGram"""
        money_order_keywords = [
            'money order',
            'moneygram',
            'western union',
            'usps money order',
            'postal money order'
        ]
        
        text_lower = text.lower()
        for keyword in money_order_keywords:
            if keyword in text_lower:
                return True
        return False
    
    def extract_amount(self, text):
        """Extract dollar amount from check text"""
        # Look for patterns like $100.00, $1,234.56
        patterns = [
            r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # $1,234.56
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*dollars',  # 1234.56 dollars
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Clean and convert
                amount_str = matches[0].replace(',', '')
                try:
                    return float(amount_str)
                except ValueError:
                    continue
        
        return None
    
    def extract_date(self, text):
        """Extract date from check"""
        # Common date patterns
        patterns = [
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',  # 12/31/2025 or 12-31-2025
            r'(\d{1,2}\s+\w+\s+\d{2,4})',  # 31 Dec 2025
            r'(\w+\s+\d{1,2},?\s+\d{4})',  # December 31, 2025
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                date_str = matches[0]
                # Try to parse
                for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y', '%m-%d-%y',
                           '%d %b %Y', '%B %d, %Y', '%b %d, %Y']:
                    try:
                        return datetime.strptime(date_str, fmt).date()
                    except ValueError:
                        continue
        
        return None
    
    def extract_check_number(self, text):
        """Extract check number"""
        # Look for 3-5 digit numbers that might be check numbers
        # Usually in format: Check #1234 or just 1234
        patterns = [
            r'check\s*#?\s*(\d{3,5})',
            r'\b(\d{3,5})\b'  # Standalone 3-5 digit number
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return None
    
    def extract_name_address(self, text):
        """
        Extract name and address from text
        Returns: dict with name, address components
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        result = {
            'name': None,
            'address_line1': None,
            'address_line2': None,
            'city': None,
            'state': None,
            'zip_code': None
        }
        
        # Simple heuristic: first non-empty line is usually name
        if len(lines) > 0:
            result['name'] = lines[0]
        
        # Look for address pattern (contains numbers)
        for i, line in enumerate(lines[1:], 1):
            if re.search(r'\d+', line):
                result['address_line1'] = line
                break
        
        # Look for city, state, zip pattern
        zip_pattern = r'([A-Za-z\s]+),?\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)'
        for line in lines:
            match = re.search(zip_pattern, line)
            if match:
                result['city'] = match.group(1).strip()
                result['state'] = match.group(2).strip()
                result['zip_code'] = match.group(3).strip()
                break
        
        return result
    
    def process_check_front(self, image_path):
        """Process check front image and extract all data"""
        text = self.ocr_image(image_path)
        
        return {
            'amount': self.extract_amount(text),
            'check_date': self.extract_date(text),
            'check_number': self.extract_check_number(text),
            'is_money_order': self.detect_money_order(text),
            'raw_text': text
        }
    
    def process_buck_slip(self, image_path):
        """Process buck slip (remittance document) for clean name/address"""
        text = self.ocr_image(image_path)
        
        # Buck slips have cleaner, printed info
        contact_info = self.extract_name_address(text)
        contact_info['amount'] = self.extract_amount(text)  # Confirmation amount
        
        return contact_info
