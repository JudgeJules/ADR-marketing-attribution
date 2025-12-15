"""
Run attribution for unattributed conversions
"""

import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def run_attribution():
    """Run last-touch attribution for conversions"""
    
    print("\n🎯 Running attribution...")
    
    db_path = os.getenv('DATABASE_PATH', './attribution.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get unattributed conversions
    cursor.execute("""
        SELECT id, user_id, timestamp
        FROM conversions
        WHERE attributed_at IS NULL
        LIMIT 100
    """)
    
    conversions = cursor.fetchall()
    
    if not conversions:
        print("✅ No conversions to attribute")
        conn.close()
        return
    
    print(f"📊 Processing {len(conversions)} conversions...")
    
    attributed = 0
    
    for conv in conversions:
        # Find last touchpoint before conversion
        cursor.execute("""
            SELECT id, utm_campaign, estimated_cost
            FROM touchpoints
            WHERE resolved_user_id = ?
                AND timestamp < ?
                AND (utm_campaign IS NOT NULL OR campaign_id IS NOT NULL)
            ORDER BY timestamp DESC
            LIMIT 1
        """, (conv['user_id'], conv['timestamp']))
        
        touchpoint = cursor.fetchone()
        
        if touchpoint:
            # Attribute conversion to touchpoint
            cursor.execute("""
                UPDATE conversions
                SET attributed_touchpoint_id = ?,
                    attributed_cost = ?,
                    attributed_campaign = ?,
                    attribution_model = 'last_touch',
                    attributed_at = ?
                WHERE id = ?
            """, (
                touchpoint['id'],
                touchpoint['estimated_cost'],
                touchpoint['utm_campaign'],
                datetime.utcnow().isoformat(),
                conv['id']
            ))
            
            attributed += 1
        else:
            # No touchpoint found - mark as attempted
            cursor.execute("""
                UPDATE conversions
                SET attributed_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), conv['id']))
    
    conn.commit()
    conn.close()
    
    print(f"✅ Attributed {attributed} conversions")

if __name__ == "__main__":
    run_attribution()
