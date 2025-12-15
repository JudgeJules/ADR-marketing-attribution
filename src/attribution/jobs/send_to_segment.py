"""
Send attributed conversions back to Segment
"""

import os
import sqlite3
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def send_attributed_conversions():
    """Send attributed conversions to Segment"""
    
    print("\n📤 Sending to Segment...")
    
    # Check if Segment is configured
    write_key = os.getenv('SEGMENT_WRITE_KEY')
    if not write_key:
        print("⚠️  Segment write key not configured. Skipping.")
        return
    
    db_path = os.getenv('DATABASE_PATH', './attribution.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get attributed conversions not yet sent
    cursor.execute("""
        SELECT id, user_id, conversion_type, timestamp,
               conversion_value, attributed_cost, attributed_campaign
        FROM conversions
        WHERE attributed_at IS NOT NULL
            AND sent_to_segment_at IS NULL
        LIMIT 50
    """)
    
    conversions = cursor.fetchall()
    
    if not conversions:
        print("✅ No conversions to send")
        conn.close()
        return
    
    print(f"📊 Sending {len(conversions)} conversions...")
    
    sent = 0
    
    for conv in conversions:
        try:
            # Build Segment event
            event = {
                'userId': conv['user_id'],
                'event': 'Conversion Attributed',
                'properties': {
                    'conversion_type': conv['conversion_type'],
                    'conversion_value': conv['conversion_value'] or 0,
                    'attributed_cost': conv['attributed_cost'] or 0,
                    'attributed_campaign': conv['attributed_campaign'],
                    'attribution_model': 'last_touch'
                },
                'timestamp': conv['timestamp'],
                'context': {
                    'source': 'attribution_mvp'
                }
            }
            
            # Send to Segment
            response = requests.post(
                'https://api.segment.io/v1/track',
                json=event,
                auth=(write_key, ''),
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                # Mark as sent
                cursor.execute("""
                    UPDATE conversions
                    SET sent_to_segment_at = ?
                    WHERE id = ?
                """, (datetime.utcnow().isoformat(), conv['id']))
                
                sent += 1
            else:
                print(f"❌ Failed to send conversion {conv['id']}: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error sending conversion {conv['id']}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"✅ Sent {sent} conversions to Segment")

if __name__ == "__main__":
    send_attributed_conversions()
