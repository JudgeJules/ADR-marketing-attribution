"""
Calculate costs for touchpoints based on campaign data
"""

import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def calculate_touchpoint_costs():
    """Calculate estimated cost for touchpoints"""
    
    print("\n💰 Calculating touchpoint costs...")
    
    db_path = os.getenv('DATABASE_PATH', './attribution.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get touchpoints without costs
    cursor.execute("""
        SELECT id, campaign_id, utm_campaign, timestamp
        FROM touchpoints
        WHERE estimated_cost IS NULL
        LIMIT 1000
    """)
    
    touchpoints = cursor.fetchall()
    
    if not touchpoints:
        print("✅ No touchpoints to calculate")
        conn.close()
        return
    
    print(f"📊 Processing {len(touchpoints)} touchpoints...")
    
    updated = 0
    
    for tp in touchpoints:
        cost = None
        method = None
        
        # Get date from timestamp
        tp_date = tp['timestamp'].split('T')[0] if 'T' in tp['timestamp'] else tp['timestamp'].split(' ')[0]
        
        # Tier 1: Direct campaign_id match
        if tp['campaign_id']:
            cursor.execute("""
                SELECT cpc FROM campaign_costs
                WHERE campaign_id = ? AND cost_date = ?
            """, (tp['campaign_id'], tp_date))
            
            result = cursor.fetchone()
            if result and result['cpc']:
                cost = result['cpc']
                method = 'campaign_cpc'
        
        # Tier 2: Use default if no match
        if cost is None:
            # Simple default: $1.50 for Google, $0.80 for social
            cost = 1.50  # Default
            method = 'default_estimate'
        
        # Update touchpoint
        cursor.execute("""
            UPDATE touchpoints
            SET estimated_cost = ?,
                cost_method = ?
            WHERE id = ?
        """, (cost, method, tp['id']))
        
        updated += 1
    
    conn.commit()
    conn.close()
    
    print(f"✅ Updated costs for {updated} touchpoints")

if __name__ == "__main__":
    calculate_touchpoint_costs()
