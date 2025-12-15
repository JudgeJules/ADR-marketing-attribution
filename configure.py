#!/usr/bin/env python3
"""
Interactive setup wizard for Attribution MVP
Creates .env file with required configuration
"""

import sys
import os
from pathlib import Path

def print_header(text):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def prompt(text, required=True, default=None):
    """Prompt user for input"""
    if default:
        text += f" [{default}]"
    text += ": "
    
    while True:
        value = input(text).strip()
        if value:
            return value
        elif default:
            return default
        elif not required:
            return None
        else:
            print("❌ This field is required. Please try again.")

def prompt_yes_no(text, default="no"):
    """Prompt for yes/no answer"""
    value = prompt(text + " (yes/no)", required=True, default=default).lower()
    return value in ['yes', 'y', 'true', '1']

def test_google_ads_connection(config):
    """Test Google Ads API connection"""
    try:
        from google.ads.googleads.client import GoogleAdsClient
        
        client_config = {
            'developer_token': config['GOOGLE_ADS_DEVELOPER_TOKEN'],
            'client_id': config['GOOGLE_ADS_CLIENT_ID'],
            'client_secret': config['GOOGLE_ADS_CLIENT_SECRET'],
            'refresh_token': config['GOOGLE_ADS_REFRESH_TOKEN'],
            'use_proto_plus': True
        }
        
        client = GoogleAdsClient.load_from_dict(client_config)
        
        # Try to list campaigns (simple test)
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT campaign.id, campaign.name
            FROM campaign
            LIMIT 1
        """
        
        customer_id = config['GOOGLE_ADS_CUSTOMER_ID'].replace('-', '')
        response = ga_service.search(customer_id=customer_id, query=query)
        
        # If we get here, connection works
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def main():
    print_header("Attribution MVP - Setup Wizard")
    
    print("This wizard will configure your attribution system.")
    print("You'll need:")
    print("  • Segment account credentials")
    print("  • Google Ads API access")
    print("\nLet's get started!\n")
    
    config = {}
    
    # ===== Segment Configuration =====
    print_header("1. Segment Configuration")
    
    print("You can find these values in your Segment workspace:")
    print("  • Webhook Secret: Destinations → Webhooks → Settings")
    print("  • Write Key: Sources → Your Source → Settings → API Keys\n")
    
    config['SEGMENT_WEBHOOK_SECRET'] = prompt("Segment Webhook Secret")
    config['SEGMENT_WRITE_KEY'] = prompt("Segment Write Key")
    
    # ===== Google Ads Configuration =====
    print_header("2. Google Ads Configuration")
    
    has_google_ads = prompt_yes_no("Do you have Google Ads API access?", default="yes")
    
    if has_google_ads:
        print("\nYou'll need OAuth2 credentials from Google Cloud Console:")
        print("  1. Enable Google Ads API")
        print("  2. Create OAuth2 credentials")
        print("  3. Generate refresh token")
        print("  4. Get your Customer ID from Google Ads\n")
        
        config['GOOGLE_ADS_DEVELOPER_TOKEN'] = prompt("Google Ads Developer Token")
        config['GOOGLE_ADS_CLIENT_ID'] = prompt("OAuth2 Client ID")
        config['GOOGLE_ADS_CLIENT_SECRET'] = prompt("OAuth2 Client Secret")
        config['GOOGLE_ADS_REFRESH_TOKEN'] = prompt("OAuth2 Refresh Token")
        config['GOOGLE_ADS_CUSTOMER_ID'] = prompt("Google Ads Customer ID (numbers only)")
        
        # Test connection
        if prompt_yes_no("\nTest Google Ads connection now?", default="yes"):
            print("\n⏳ Testing connection...")
            if test_google_ads_connection(config):
                print("✅ Connection successful!")
            else:
                print("⚠️  Connection failed. You can fix this later in .env file.")
    else:
        print("\n⚠️  Skipping Google Ads configuration.")
        print("You can add it later by editing the .env file.")
        config['GOOGLE_ADS_DEVELOPER_TOKEN'] = ''
        config['GOOGLE_ADS_CLIENT_ID'] = ''
        config['GOOGLE_ADS_CLIENT_SECRET'] = ''
        config['GOOGLE_ADS_REFRESH_TOKEN'] = ''
        config['GOOGLE_ADS_CUSTOMER_ID'] = ''
    
    # ===== System Configuration =====
    print_header("3. System Configuration")
    
    config['WEBHOOK_PORT'] = prompt("Webhook server port", default="5000")
    config['DATABASE_PATH'] = prompt("Database file path", default="./attribution.db")
    
    use_ngrok = prompt_yes_no("\nEnable ngrok for testing? (exposes webhook publicly)", default="yes")
    config['USE_NGROK'] = 'true' if use_ngrok else 'false'
    
    # ===== Write Configuration =====
    print_header("4. Writing Configuration")
    
    env_path = Path('.env')
    
    if env_path.exists():
        backup = prompt_yes_no(f"\n⚠️  {env_path} already exists. Create backup?", default="yes")
        if backup:
            backup_path = env_path.with_suffix('.env.backup')
            env_path.rename(backup_path)
            print(f"✅ Backup created: {backup_path}")
    
    # Write .env file
    with open(env_path, 'w') as f:
        f.write("# Attribution MVP Configuration\n")
        f.write("# Generated by setup wizard\n\n")
        
        f.write("# Segment\n")
        f.write(f"SEGMENT_WEBHOOK_SECRET={config['SEGMENT_WEBHOOK_SECRET']}\n")
        f.write(f"SEGMENT_WRITE_KEY={config['SEGMENT_WRITE_KEY']}\n\n")
        
        f.write("# Google Ads\n")
        f.write(f"GOOGLE_ADS_DEVELOPER_TOKEN={config['GOOGLE_ADS_DEVELOPER_TOKEN']}\n")
        f.write(f"GOOGLE_ADS_CLIENT_ID={config['GOOGLE_ADS_CLIENT_ID']}\n")
        f.write(f"GOOGLE_ADS_CLIENT_SECRET={config['GOOGLE_ADS_CLIENT_SECRET']}\n")
        f.write(f"GOOGLE_ADS_REFRESH_TOKEN={config['GOOGLE_ADS_REFRESH_TOKEN']}\n")
        f.write(f"GOOGLE_ADS_CUSTOMER_ID={config['GOOGLE_ADS_CUSTOMER_ID']}\n\n")
        
        f.write("# System\n")
        f.write(f"WEBHOOK_PORT={config['WEBHOOK_PORT']}\n")
        f.write(f"DATABASE_PATH={config['DATABASE_PATH']}\n")
        f.write(f"USE_NGROK={config['USE_NGROK']}\n")
    
    print(f"✅ Configuration saved to {env_path}")
    
    # ===== Next Steps =====
    print_header("Setup Complete!")
    
    print("Next steps:")
    print("  1. Initialize database: python init_db.py")
    print("  2. Start the system: python app.py")
    print(f"  3. Configure Segment webhook to: http://localhost:{config['WEBHOOK_PORT']}/webhooks/segment")
    
    if use_ngrok:
        print("  4. Start ngrok: ngrok http " + config['WEBHOOK_PORT'])
        print("  5. Update Segment webhook with ngrok URL")
    
    print("\n✨ Happy attributing!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Setup failed: {e}")
        sys.exit(1)
