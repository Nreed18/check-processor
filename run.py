#!/usr/bin/env python3
"""
Check Processor Application
Family Radio - Accounts Receivable Automation
"""

from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Get port from environment or use default
    port = int(os.getenv('PORT', 5000))
    
    # Run the application
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True  # Set to False in production
    )
