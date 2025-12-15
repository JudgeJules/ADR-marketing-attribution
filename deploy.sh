#!/bin/bash

# Attribution MVP - One-Click Deploy Script
# This script walks you through the complete installation

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}============================================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

prompt_user() {
    local prompt_text="$1"
    local default_value="$2"
    local user_input
    
    if [ -n "$default_value" ]; then
        read -p "$prompt_text [$default_value]: " user_input
        echo "${user_input:-$default_value}"
    else
        read -p "$prompt_text: " user_input
        while [ -z "$user_input" ]; do
            echo "❌ This field is required" >&2
            read -p "$prompt_text: " user_input
        done
        echo "$user_input"
    fi
}

prompt_yes_no() {
    local prompt_text="$1"
    local default_value="${2:-no}"
    local user_input
    
    read -p "$prompt_text [yes/no] [$default_value]: " user_input
    user_input="${user_input:-$default_value}"
    
    if [[ "$user_input" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        echo "yes"
    else
        echo "no"
    fi
}

# Main deployment
print_header "Attribution MVP - Deployment Wizard"

echo "This script will:"
echo "  1. Check prerequisites"
echo "  2. Set up Python virtual environment"
echo "  3. Install dependencies"
echo "  4. Configure the system"
echo "  5. Initialize the database"
echo "  6. Test the installation"
echo ""
echo "Estimated time: 5-10 minutes"
echo ""

read -p "Ready to begin? [yes/no] [yes]: " START_DEPLOY
START_DEPLOY="${START_DEPLOY:-yes}"
if [[ ! "$START_DEPLOY" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    print_warning "Deployment cancelled"
    exit 0
fi

# Step 1: Check Prerequisites
print_header "Step 1: Checking Prerequisites"

# Check Python
print_info "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION found"
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION found"
    PYTHON_CMD="python"
else
    print_error "Python not found. Please install Python 3.11 or higher"
    exit 1
fi

# Check Python version
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    print_warning "Python 3.11+ recommended (you have $PYTHON_VERSION)"
    read -p "Continue anyway? [yes/no] [no]: " CONTINUE
    CONTINUE="${CONTINUE:-no}"
    if [[ ! "$CONTINUE" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        exit 1
    fi
fi

# Check pip
print_info "Checking pip installation..."
if $PYTHON_CMD -m pip --version &> /dev/null; then
    print_success "pip found"
else
    print_error "pip not found. Please install pip"
    exit 1
fi

# Check if virtual environment exists
if [ -d "venv" ]; then
    print_warning "Virtual environment already exists"
    read -p "Recreate it? [yes/no] [no]: " RECREATE
    RECREATE="${RECREATE:-no}"
    if [[ "$RECREATE" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        rm -rf venv
        print_success "Removed existing virtual environment"
    fi
fi

# Step 2: Create Virtual Environment
print_header "Step 2: Setting Up Virtual Environment"

if [ ! -d "venv" ]; then
    print_info "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    print_success "Virtual environment created"
else
    print_success "Using existing virtual environment"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source venv/bin/activate
print_success "Virtual environment activated"

# Step 3: Install Dependencies
print_header "Step 3: Installing Dependencies"

print_info "Upgrading pip..."
pip install --upgrade pip --quiet

print_info "Installing requirements (this may take a minute)..."
pip install -r requirements.txt --quiet
print_success "Dependencies installed"

print_info "Installing attribution package in editable mode..."
pip install -e . --quiet
print_success "Package installed"

# Step 4: Configuration
print_header "Step 4: System Configuration"

if [ -f ".env" ]; then
    print_warning ".env file already exists"
    read -p "Reconfigure? [yes/no] [no]: " RECONFIGURE
    RECONFIGURE="${RECONFIGURE:-no}"
    if [[ "$RECONFIGURE" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        BACKUP_NAME=".env.backup.$(date +%s)"
        mv .env "$BACKUP_NAME"
        print_success "Backed up to $BACKUP_NAME"
    else
        print_info "Skipping configuration"
        SKIP_CONFIG=true
    fi
fi

if [ "$SKIP_CONFIG" != true ]; then
    echo ""
    print_info "Let's configure your system..."
    echo ""
    
    # Segment Configuration
    echo -e "${YELLOW}=== Segment Configuration ===${NC}"
    echo "Find these in your Segment workspace:"
    echo "  • Webhook Secret: Destinations → Webhooks → Settings"
    echo "  • Write Key: Sources → Your Source → Settings → API Keys"
    echo ""
    
    SEGMENT_WEBHOOK_SECRET=$(prompt_user "Segment Webhook Secret")
    SEGMENT_WRITE_KEY=$(prompt_user "Segment Write Key")
    
    # Google Ads Configuration
    echo ""
    echo -e "${YELLOW}=== Google Ads Configuration ===${NC}"
    read -p "Do you have Google Ads API access? [yes/no] [yes]: " HAS_GOOGLE_ADS
    HAS_GOOGLE_ADS="${HAS_GOOGLE_ADS:-yes}"
    
    if [[ "$HAS_GOOGLE_ADS" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        echo ""
        echo "You'll need OAuth2 credentials from Google Cloud Console"
        echo ""
        GOOGLE_ADS_DEVELOPER_TOKEN=$(prompt_user "Google Ads Developer Token")
        GOOGLE_ADS_CLIENT_ID=$(prompt_user "OAuth2 Client ID")
        GOOGLE_ADS_CLIENT_SECRET=$(prompt_user "OAuth2 Client Secret")
        GOOGLE_ADS_REFRESH_TOKEN=$(prompt_user "OAuth2 Refresh Token")
        GOOGLE_ADS_CUSTOMER_ID=$(prompt_user "Google Ads Customer ID")
    else
        print_warning "Skipping Google Ads configuration"
        GOOGLE_ADS_DEVELOPER_TOKEN=""
        GOOGLE_ADS_CLIENT_ID=""
        GOOGLE_ADS_CLIENT_SECRET=""
        GOOGLE_ADS_REFRESH_TOKEN=""
        GOOGLE_ADS_CUSTOMER_ID=""
    fi
    
    # System Configuration
    echo ""
    echo -e "${YELLOW}=== System Configuration ===${NC}"
    WEBHOOK_PORT=$(prompt_user "Webhook server port" "5000")
    DATABASE_PATH=$(prompt_user "Database file path" "./attribution.db")
    read -p "Enable ngrok for testing? [yes/no] [yes]: " USE_NGROK
    USE_NGROK="${USE_NGROK:-yes}"
    
    # Write .env file
    print_info "Writing configuration..."
    cat > .env << EOF
# Attribution MVP Configuration
# Generated by deploy.sh on $(date)

# Segment
SEGMENT_WEBHOOK_SECRET=$SEGMENT_WEBHOOK_SECRET
SEGMENT_WRITE_KEY=$SEGMENT_WRITE_KEY

# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN=$GOOGLE_ADS_DEVELOPER_TOKEN
GOOGLE_ADS_CLIENT_ID=$GOOGLE_ADS_CLIENT_ID
GOOGLE_ADS_CLIENT_SECRET=$GOOGLE_ADS_CLIENT_SECRET
GOOGLE_ADS_REFRESH_TOKEN=$GOOGLE_ADS_REFRESH_TOKEN
GOOGLE_ADS_CUSTOMER_ID=$GOOGLE_ADS_CUSTOMER_ID

# System
WEBHOOK_PORT=$WEBHOOK_PORT
DATABASE_PATH=$DATABASE_PATH
USE_NGROK=$USE_NGROK
EOF
    
    print_success "Configuration saved to .env"
fi

# Step 5: Initialize Database
print_header "Step 5: Initializing Database"

if [ -f "attribution.db" ]; then
    print_warning "Database already exists"
    read -p "Reinitialize (will delete existing data)? [yes/no] [no]: " REINIT
    REINIT="${REINIT:-no}"
    if [[ "$REINIT" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        rm attribution.db
        print_success "Removed existing database"
    else
        print_info "Keeping existing database"
        SKIP_DB_INIT=true
    fi
fi

if [ "$SKIP_DB_INIT" != true ]; then
    print_info "Creating database schema..."
    $PYTHON_CMD scripts/init_db.py
    print_success "Database initialized"
else
    print_success "Using existing database"
fi

# Step 6: Test Installation
print_header "Step 6: Testing Installation"

print_info "Running quick validation..."

# Test imports
print_info "Testing Python imports..."
$PYTHON_CMD -c "
import flask
import sqlite3
from dotenv import load_dotenv
print('✅ All imports successful')
" || {
    print_error "Import test failed"
    exit 1
}

# Test database
print_info "Testing database connection..."
$PYTHON_CMD -c "
import sqlite3
import os
from dotenv import load_dotenv
load_dotenv()
db_path = os.getenv('DATABASE_PATH', './attribution.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM touchpoints')
print('✅ Database connection successful')
conn.close()
" || {
    print_error "Database test failed"
    exit 1
}

print_success "All tests passed!"

# Final Summary
print_header "Deployment Complete! 🎉"

echo "Your attribution system is ready to use!"
echo ""
echo -e "${GREEN}Next Steps:${NC}"
echo ""
echo "1. Start the system:"
echo -e "   ${YELLOW}source venv/bin/activate${NC}"
echo -e "   ${YELLOW}python -m attribution.app${NC}"
echo ""
echo "2. View the dashboard:"
echo -e "   ${YELLOW}http://localhost:${WEBHOOK_PORT:-5000}/dashboard${NC}"
echo ""
echo "3. Configure Segment webhook:"
echo -e "   ${YELLOW}http://localhost:${WEBHOOK_PORT:-5000}/webhooks/segment${NC}"
echo ""

if [[ "$USE_NGROK" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    echo "4. (Optional) Start ngrok for public access:"
    echo -e "   ${YELLOW}ngrok http ${WEBHOOK_PORT:-5000}${NC}"
    echo ""
fi

echo -e "${YELLOW}Note:${NC} If port ${WEBHOOK_PORT:-5000} is in use, the app will automatically find an available port."
echo ""

echo -e "${BLUE}Documentation:${NC}"
echo "  • Quick Start: docs/QUICK_START.md"
echo "  • Project Summary: docs/PROJECT_SUMMARY.md"
echo "  • Architecture: docs/adr/"
echo ""

read -p "Start the system now? [yes/no] [yes]: " START_NOW
START_NOW="${START_NOW:-yes}"
if [[ "$START_NOW" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    echo ""
    print_info "Starting Attribution MVP..."
    echo ""
    $PYTHON_CMD -m attribution.app
else
    echo ""
    print_success "Run 'python -m attribution.app' when you're ready!"
    echo ""
fi
