"""
Fetch campaign costs from Google Ads API
"""

import os
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def fetch_google_ads_costs():
    """Fetch campaign costs from Google Ads"""
    
    print("\n🔍 Fetching Google Ads costs...")
    
    # Check if Google Ads is configured
    if not os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN'):
        print("⚠️  Google Ads not configured. Skipping.")
        return
    
    try:
        from google.ads.googleads.client import GoogleAdsClient
        
        # Build client config
        client_config = {
            'developer_token': os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN'),
            'client_id': os.getenv('GOOGLE_ADS_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_ADS_CLIENT_SECRET'),
            'refresh_token': os.getenv('GOOGLE_ADS_REFRESH_TOKEN'),
            'use_proto_plus': True
        }
        
        client = GoogleAdsClient.load_from_dict(client_config)
        customer_id = os.getenv('GOOGLE_ADS_CUSTOMER_ID').replace('-', '')
        
        # Query for yesterday's data
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        ga_service = client.get_service("GoogleAdsService")
        
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                metrics.cost_micros,
                metrics.clicks,
                metrics.impressions,
                segments.date
            FROM campaign
            WHERE segments.date = '{yesterday}'
                AND campaign.status = 'ENABLED'
        """
        
        response = ga_service.search(customer_id=customer_id, query=query)
        
        # Store costs in database
        db_path = os.getenv('DATABASE_PATH', './attribution.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        count = 0
        for row in response:
            campaign_id = str(row.campaign.id)
            campaign_name = row.campaign.name
            cost_date = row.segments.date
            
            # Convert micros to dollars
            total_spend = row.metrics.cost_micros / 1_000_000
            total_clicks = row.metrics.clicks
            total_impressions = row.metrics.impressions
            
            # Calculate CPC
            cpc = total_spend / total_clicks if total_clicks > 0 else None
            ctr = (total_clicks / total_impressions) if total_impressions > 0 else None
            
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO campaign_costs (
                        campaign_id, campaign_name, cost_date,
                        total_spend, total_clicks, total_impressions,
                        cpc, ctr
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    campaign_id, campaign_name, cost_date,
                    total_spend, total_clicks, total_impressions,
                    cpc, ctr
                ))
                count += 1
            except Exception as e:
                print(f"❌ Error storing campaign {campaign_id}: {e}")
        
        conn.commit()
        conn.close()
        
        print(f"✅ Fetched costs for {count} campaigns on {yesterday}")
        
    except ImportError:
        print("❌ google-ads library not installed")
        print("   Install with: pip install google-ads")
    except Exception as e:
        print(f"❌ Error fetching Google Ads costs: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fetch_google_ads_costs()
