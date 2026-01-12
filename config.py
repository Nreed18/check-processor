import os
from datetime import timedelta

class Config:
    """Application configuration"""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres:postgres@localhost:5432/check_processor'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # HubSpot API
    HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
    HUBSPOT_DEAL_OWNER = os.getenv('HUBSPOT_DEAL_OWNER', '')  # Robin Schuh's ID
    
    # File upload
    UPLOAD_FOLDER = '/home/claude/check-processor/uploads'
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {'pdf'}
    
    # Batch retention
    BATCH_RETENTION_HOURS = 48
    
    # Processing
    MAX_CONCURRENT_OCR = 5  # Process 5 checks in parallel
