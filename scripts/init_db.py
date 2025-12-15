#!/usr/bin/env python3
"""
Initialize SQLite database for Attribution MVP
"""

import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def init_database():
    """Create database and tables"""
    
    db_path = os.getenv('DATABASE_PATH', './attribution.db')
    
    print(f"📁 Creating database: {db_path}")
    
    # Create database connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create touchpoints table
    print("Creating touchpoints table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS touchpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            user_id TEXT,
            anonymous_id TEXT,
            resolved_user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_name TEXT,
            timestamp DATETIME NOT NULL,
            
            -- Campaign data
            utm_source TEXT,
            utm_medium TEXT,
            utm_campaign TEXT,
            utm_content TEXT,
            utm_term TEXT,
            campaign_id TEXT,
            
            -- Context
            referrer TEXT,
            url TEXT,
            
            -- Cost
            estimated_cost REAL,
            cost_method TEXT,
            
            -- Properties (JSON string)
            properties TEXT,
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Indexes for touchpoints
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_touchpoints_user 
        ON touchpoints(resolved_user_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_touchpoints_timestamp 
        ON touchpoints(timestamp)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_touchpoints_campaign 
        ON touchpoints(campaign_id) WHERE campaign_id IS NOT NULL
    """)
    
    # Create conversions table
    print("Creating conversions table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            conversion_type TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            conversion_value REAL,
            
            -- Attribution
            attributed_touchpoint_id INTEGER,
            attributed_cost REAL,
            attributed_campaign TEXT,
            attribution_model TEXT DEFAULT 'last_touch',
            
            -- Status
            attributed_at DATETIME,
            sent_to_segment_at DATETIME,
            
            -- Properties (JSON string)
            properties TEXT,
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (attributed_touchpoint_id) REFERENCES touchpoints(id)
        )
    """)
    
    # Indexes for conversions
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversions_user 
        ON conversions(user_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversions_timestamp 
        ON conversions(timestamp)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversions_unattributed 
        ON conversions(attributed_at) WHERE attributed_at IS NULL
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversions_unsent 
        ON conversions(sent_to_segment_at) WHERE sent_to_segment_at IS NULL
    """)
    
    # Create campaign_costs table
    print("Creating campaign_costs table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL,
            campaign_name TEXT,
            cost_date DATE NOT NULL,
            
            total_spend REAL NOT NULL,
            total_clicks INTEGER NOT NULL,
            total_impressions INTEGER,
            
            cpc REAL,
            ctr REAL,
            
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(campaign_id, cost_date)
        )
    """)
    
    # Indexes for campaign costs
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_costs_campaign 
        ON campaign_costs(campaign_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_costs_date 
        ON campaign_costs(cost_date)
    """)
    
    # Commit changes
    conn.commit()
    conn.close()
    
    print("✅ Database initialized successfully!")
    print(f"📊 Database location: {db_path}")
    
    # Show table counts
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables = ['touchpoints', 'conversions', 'campaign_costs']
    print("\n📈 Table Status:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  • {table}: {count} rows")
    
    conn.close()

if __name__ == "__main__":
    try:
        init_database()
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
