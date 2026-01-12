#!/bin/bash
# Check Processor Setup Script
# Family Radio - Accounts Receivable Automation

set -e

echo "========================================="
echo "Check Processor Setup"
echo "Family Radio"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
   echo "ERROR: Do not run this script as root"
   echo "Run as: ./setup.sh"
   exit 1
fi

# Get project directory
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

echo "📦 Installing system dependencies..."
sudo apt update
sudo apt install -y postgresql postgresql-contrib python3-pip python3-venv poppler-utils libpango-1.0-0 libpangocairo-1.0-0

echo ""
echo "🐍 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo ""
echo "📚 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "🗄️  Setting up PostgreSQL database..."
sudo -u postgres psql -c "SELECT 1 FROM pg_database WHERE datname = 'check_processor'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE DATABASE check_processor;"

echo ""
echo "⚙️  Creating environment file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Created .env file - EDIT THIS FILE with your credentials!"
else
    echo "✓ .env file already exists"
fi

echo ""
echo "📁 Creating directories..."
mkdir -p uploads
mkdir -p logs

echo ""
echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials:"
echo "   nano .env"
echo ""
echo "2. Update these values:"
echo "   - SECRET_KEY (generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\")"
echo "   - DATABASE_URL (PostgreSQL connection string)"
echo "   - HUBSPOT_API_KEY (HubSpot private app token)"
echo ""
echo "   Note: Using docTR (deep learning OCR) - models download automatically!"
echo ""
echo "3. Initialize database:"
echo "   source venv/bin/activate"
echo "   python3 run.py"
echo "   (Press Ctrl+C after it starts)"
echo ""
echo "4. Run application:"
echo "   source venv/bin/activate"
echo "   python3 run.py"
echo ""
echo "5. Access at: http://localhost:5000"
echo ""
echo "For production deployment, see README.md"
echo ""
