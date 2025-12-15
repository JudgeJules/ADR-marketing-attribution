# Attribution System - Bare-Bones MVP Deployment Plan

## Overview
This plan creates the **absolute minimum** attribution system that:
1. Receives events from Segment webhook
2. Stores touchpoints and conversions in SQLite (no PostgreSQL needed)
3. Fetches Google Ads costs daily
4. Attributes conversions to last touchpoint
5. Sends attributed conversions back to Segment

**No Kafka. No Docker. No complexity. Just Python + SQLite.**

## What This MVP Does

### Core Flow
```
Segment → Webhook (Flask) → SQLite → Attribution → Segment
                                ↑
                         Google Ads API
```

### Features Included
- ✅ Receive Segment webhook events
- ✅ Store touchpoints and conversions in SQLite
- ✅ Basic identity resolution (handle userId + anonymousId)
- ✅ Fetch Google Ads campaign costs (manual trigger)
- ✅ Calculate touchpoint costs (simple CPC)
- ✅ Last-touch attribution
- ✅ Send attributed conversions back to Segment
- ✅ Basic web UI for monitoring

### Features Excluded (Post-MVP)
- ❌ Kafka event streaming
- ❌ Real-time processing (runs on schedule)
- ❌ Multi-tier cost calculation
- ❌ Advanced attribution models
- ❌ Redshift sync
- ❌ Funnel tracking
- ❌ Production-grade error handling
- ❌ Comprehensive monitoring

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Single Machine (Local)                   │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Flask Web Server (Port 5000)                         │  │
│  │  - /webhooks/segment (receive events)                 │  │
│  │  - /dashboard (monitoring UI)                         │  │
│  │  - /api/stats (API for data)                          │  │
│  └──────────────────────┬────────────────────────────────┘  │
│                         │                                    │
│                         ▼                                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  SQLite Database (attribution.db)                     │  │
│  │  - touchpoints table                                  │  │
│  │  - conversions table                                  │  │
│  │  - campaign_costs table                               │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Background Jobs (APScheduler)                        │  │
│  │  - Fetch Google Ads costs (daily 2 AM)               │  │
│  │  - Calculate touchpoint costs (daily 3 AM)           │  │
│  │  - Run attribution (every 5 minutes)                 │  │
│  │  - Send to Segment (every 5 minutes)                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Required
- Python 3.11+
- Internet connection
- Segment account (free tier OK)
- Google Ads account with API access

### Installation Time
- ~15 minutes for Python dependencies
- ~5 minutes for configuration
- **Total: 20 minutes from scratch to running**

## Installation Steps

### Step 1: Clone/Download Code

```bash
# Create project directory
mkdir attribution-mvp
cd attribution-mvp

# Download MVP code (will be provided separately)
# Or extract from ZIP
```

### Step 2: Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**requirements.txt:**
```txt
flask==3.0.0
flask-cors==4.0.0
apscheduler==3.10.4
google-ads==23.1.0
requests==2.31.0
python-dotenv==1.0.0
```

### Step 3: Interactive Configuration

Run the setup wizard:

```bash
python setup.py
```

**The setup wizard will prompt for:**

1. **Segment Configuration**
   ```
   Enter your Segment Webhook Secret: [from Segment settings]
   Enter your Segment Write Key: [from Segment source settings]
   ```

2. **Google Ads Configuration**
   ```
   Do you have Google Ads API access? (yes/no): yes
   Enter Google Ads Developer Token: [from Google Ads]
   Enter Client ID: [from Google Cloud Console]
   Enter Client Secret: [from Google Cloud Console]
   Enter Refresh Token: [from OAuth flow]
   Enter Customer ID: [your Google Ads account ID]
   
   Test connection? (yes/no): yes
   ✓ Connection successful!
   ```

3. **System Configuration**
   ```
   Enter webhook port (default 5000): 5000
   Enable public access via ngrok? (yes/no): yes
   ```

This creates a `.env` file:
```env
# Segment
SEGMENT_WEBHOOK_SECRET=abc123...
SEGMENT_WRITE_KEY=xyz789...

# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN=...
GOOGLE_ADS_CLIENT_ID=...
GOOGLE_ADS_CLIENT_SECRET=...
GOOGLE_ADS_REFRESH_TOKEN=...
GOOGLE_ADS_CUSTOMER_ID=1234567890

# System
WEBHOOK_PORT=5000
DATABASE_PATH=./attribution.db
```

### Step 4: Initialize Database

```bash
python init_db.py
```

Creates `attribution.db` with:
- `touchpoints` table
- `conversions` table
- `campaign_costs` table

### Step 5: Configure Segment Webhook

If using ngrok (for testing without public server):
```bash
# In a separate terminal
ngrok http 5000
```

Then in Segment:
1. Go to Connections → Destinations
2. Add "Webhooks" destination
3. Enter URL: `https://[your-ngrok-url].ngrok.io/webhooks/segment` or `http://localhost:5000/webhooks/segment`
4. Add webhook secret (same as in .env)
5. Save

### Step 6: Start the System

```bash
python app.py
```

Output:
```
🚀 Attribution MVP Starting...
✓ Database initialized
✓ Background jobs scheduled
✓ Webhook server starting on port 5000
✓ Dashboard available at http://localhost:5000/dashboard

📊 System Status:
- Touchpoints: 0
- Conversions: 0
- Attributed: 0

⏰ Scheduled Jobs:
- Fetch Google Ads Costs: Daily at 2:00 AM
- Calculate Costs: Daily at 3:00 AM
- Run Attribution: Every 5 minutes
- Send to Segment: Every 5 minutes
```

### Step 7: Test the System

```bash
# Send a test event
curl -X POST http://localhost:5000/webhooks/segment \
  -H "Content-Type: application/json" \
  -d '{
    "type": "page",
    "userId": "test_user_123",
    "anonymousId": "anon_456",
    "timestamp": "2024-12-05T12:00:00Z",
    "properties": {
      "utm_source": "google",
      "utm_campaign": "test_campaign"
    }
  }'

# Check dashboard
open http://localhost:5000/dashboard
```

## Simplified Database Schema

### SQLite Schema (attribution.db)

```sql
-- Touchpoints (simplified)
CREATE TABLE touchpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    user_id TEXT,
    anonymous_id TEXT,
    resolved_user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    
    -- Campaign data
    utm_source TEXT,
    utm_campaign TEXT,
    campaign_id TEXT,
    
    -- Cost
    estimated_cost REAL,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_touchpoints_user ON touchpoints(resolved_user_id);
CREATE INDEX idx_touchpoints_timestamp ON touchpoints(timestamp);

-- Conversions (simplified)
CREATE TABLE conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    conversion_type TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    
    -- Attribution
    attributed_touchpoint_id INTEGER,
    attributed_cost REAL,
    attributed_campaign TEXT,
    
    -- Status
    attributed_at DATETIME,
    sent_to_segment_at DATETIME,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (attributed_touchpoint_id) REFERENCES touchpoints(id)
);

CREATE INDEX idx_conversions_user ON conversions(user_id);
CREATE INDEX idx_conversions_unattributed ON conversions(attributed_at) WHERE attributed_at IS NULL;

-- Campaign Costs (simplified)
CREATE TABLE campaign_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    cost_date DATE NOT NULL,
    total_spend REAL NOT NULL,
    total_clicks INTEGER NOT NULL,
    cpc REAL,
    
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(campaign_id, cost_date)
);

CREATE INDEX idx_campaign_costs_date ON campaign_costs(cost_date);
```

## Core Application Structure

```
attribution-mvp/
├── app.py                 # Main Flask application
├── setup.py              # Interactive setup wizard
├── init_db.py            # Database initialization
├── requirements.txt      # Python dependencies
├── .env                  # Configuration (created by setup.py)
├── attribution.db        # SQLite database (created by init_db.py)
│
├── models/
│   ├── __init__.py
│   ├── database.py       # SQLAlchemy models
│   └── schemas.py        # Data validation schemas
│
├── services/
│   ├── __init__.py
│   ├── webhook.py        # Segment webhook handler
│   ├── google_ads.py     # Google Ads API client
│   ├── attribution.py    # Attribution logic
│   └── segment_client.py # Segment HTTP API client
│
├── jobs/
│   ├── __init__.py
│   ├── fetch_costs.py    # Fetch Google Ads costs
│   ├── calculate_costs.py # Calculate touchpoint costs
│   ├── run_attribution.py # Run attribution engine
│   └── send_to_segment.py # Send attributed conversions
│
└── templates/
    └── dashboard.html     # Simple monitoring UI
```

## Key Simplifications from Full Design

### 1. SQLite Instead of PostgreSQL
- **Why**: No separate database server needed
- **Limitation**: ~1M rows max before performance degrades
- **Migration path**: Easy to export to PostgreSQL later

### 2. No Kafka
- **Why**: Adds complexity and infrastructure
- **Instead**: Direct database writes from webhook
- **Limitation**: No event replay capability
- **Migration path**: Can add Kafka layer later without data loss

### 3. Background Jobs via APScheduler
- **Why**: Simple, built into Python
- **Instead of**: Cron jobs or Airflow
- **Limitation**: Single-threaded, not distributed
- **Migration path**: Move to Airflow when scaling

### 4. Single-Tier Cost Calculation
- **Why**: Simpler logic, faster to implement
- **Method**: Campaign ID match only, default CPC if not found
- **Limitation**: Less accurate for some touchpoints
- **Migration path**: Add multi-tier logic incrementally

### 5. Batch Attribution (Every 5 Minutes)
- **Why**: Simpler than real-time
- **Instead of**: Immediate attribution on conversion
- **Limitation**: 5-minute delay in attribution
- **Migration path**: Can make real-time later

### 6. No Redshift
- **Why**: Not needed for MVP
- **Instead**: Query SQLite directly
- **Limitation**: Limited historical analysis
- **Migration path**: Export to Redshift when needed

## Minimal Code Examples

### app.py (Core Application)

```python
from flask import Flask, request, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler
import os
from dotenv import load_dotenv
from services.webhook import handle_segment_event
from services.database import init_db, get_stats
from jobs.fetch_costs import fetch_google_ads_costs
from jobs.calculate_costs import calculate_touchpoint_costs
from jobs.run_attribution import run_attribution
from jobs.send_to_segment import send_attributed_conversions

load_dotenv()

app = Flask(__name__)
scheduler = BackgroundScheduler()

@app.route('/webhooks/segment', methods=['POST'])
def segment_webhook():
    """Receive events from Segment"""
    try:
        event = request.json
        handle_segment_event(event)
        return jsonify({'status': 'received'}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/dashboard')
def dashboard():
    """Simple monitoring dashboard"""
    stats = get_stats()
    return render_template('dashboard.html', stats=stats)

@app.route('/api/stats')
def api_stats():
    """Stats API endpoint"""
    return jsonify(get_stats())

def schedule_jobs():
    """Schedule background jobs"""
    # Daily at 2 AM: Fetch Google Ads costs
    scheduler.add_job(
        fetch_google_ads_costs,
        'cron',
        hour=2,
        minute=0
    )
    
    # Daily at 3 AM: Calculate touchpoint costs
    scheduler.add_job(
        calculate_touchpoint_costs,
        'cron',
        hour=3,
        minute=0
    )
    
    # Every 5 minutes: Run attribution
    scheduler.add_job(
        run_attribution,
        'interval',
        minutes=5
    )
    
    # Every 5 minutes: Send to Segment
    scheduler.add_job(
        send_attributed_conversions,
        'interval',
        minutes=5
    )

if __name__ == '__main__':
    print("🚀 Attribution MVP Starting...")
    
    # Initialize database
    init_db()
    print("✓ Database initialized")
    
    # Schedule jobs
    schedule_jobs()
    scheduler.start()
    print("✓ Background jobs scheduled")
    
    # Start web server
    port = int(os.getenv('WEBHOOK_PORT', 5000))
    print(f"✓ Webhook server starting on port {port}")
    print(f"✓ Dashboard available at http://localhost:{port}/dashboard")
    
    app.run(host='0.0.0.0', port=port)
```

### services/attribution.py (Attribution Logic)

```python
from models.database import get_session, Touchpoint, Conversion
from datetime import datetime

def attribute_conversion(conversion: Conversion):
    """Simple last-touch attribution"""
    db = get_session()
    
    # Find all touchpoints before conversion for this user
    touchpoints = db.query(Touchpoint).filter(
        Touchpoint.resolved_user_id == conversion.user_id,
        Touchpoint.timestamp < conversion.timestamp
    ).order_by(Touchpoint.timestamp.desc()).all()
    
    # Find last marketing touchpoint (has campaign data)
    for tp in touchpoints:
        if tp.utm_campaign or tp.campaign_id:
            # Attribute to this touchpoint
            conversion.attributed_touchpoint_id = tp.id
            conversion.attributed_cost = tp.estimated_cost
            conversion.attributed_campaign = tp.utm_campaign
            conversion.attributed_at = datetime.utcnow()
            
            db.commit()
            return True
    
    # No marketing touchpoint found
    return False
```

## Testing the MVP

### Manual Test Flow

1. **Send a touchpoint event:**
```bash
curl -X POST http://localhost:5000/webhooks/segment \
  -H "Content-Type: application/json" \
  -d '{
    "type": "page",
    "userId": "user_123",
    "timestamp": "2024-12-05T10:00:00Z",
    "properties": {
      "utm_source": "google",
      "utm_campaign": "winter_sale",
      "campaign_id": "12345"
    }
  }'
```

2. **Manually fetch costs:**
```bash
python jobs/fetch_costs.py
```

3. **Calculate costs:**
```bash
python jobs/calculate_costs.py
```

4. **Send a conversion:**
```bash
curl -X POST http://localhost:5000/webhooks/segment \
  -H "Content-Type: application/json" \
  -d '{
    "type": "track",
    "event": "Account Created",
    "userId": "user_123",
    "timestamp": "2024-12-05T11:00:00Z"
  }'
```

5. **Run attribution:**
```bash
python jobs/run_attribution.py
```

6. **Check dashboard:**
```bash
open http://localhost:5000/dashboard
```

## Dashboard Features

Simple HTML page showing:
- Total touchpoints stored
- Total conversions
- Attributed conversions
- Attribution rate (%)
- Recent events (last 10)
- Campaign costs fetched
- System status

## Success Criteria

MVP is successful if:
- ✅ Can receive events from Segment
- ✅ Events stored in SQLite
- ✅ Can fetch Google Ads costs
- ✅ Conversions attributed to touchpoints
- ✅ Attributed conversions sent back to Segment
- ✅ Dashboard shows basic stats

## Limitations & Known Issues

### Limitations
1. **SQLite**: Max ~1M rows before slow
2. **Single process**: No horizontal scaling
3. **No authentication**: Don't expose to public internet
4. **No event replay**: Lost events are lost
5. **5-minute delay**: Attribution runs on schedule
6. **Basic cost calculation**: Only direct campaign match

### Known Issues
1. If webhook receives events faster than processing, queue builds up
2. No retry logic for failed Google Ads fetches
3. Identity resolution is immediate (no retroactive stitching)

## Migration Path to Full System

When ready to scale:

1. **Add PostgreSQL**: Export SQLite data, update connection string
2. **Add Kafka**: Insert Kafka layer between webhook and database
3. **Add Docker**: Containerize for easier deployment
4. **Add monitoring**: Prometheus + Grafana
5. **Add Redshift**: Set up daily sync
6. **Enhance attribution**: Add multi-tier cost calculation
7. **Real-time processing**: Remove 5-minute delay

## Troubleshooting

### Webhook not receiving events
- Check Segment webhook destination is enabled
- Verify webhook URL is correct
- Check ngrok is running (if using)
- Look at Segment debugger for delivery failures

### Attribution not working
- Verify touchpoints have campaign data
- Check conversion user_id matches touchpoint resolved_user_id
- Run attribution manually: `python jobs/run_attribution.py`

### Google Ads costs not fetching
- Verify API credentials in .env
- Test connection: `python services/google_ads.py`
- Check API quota limits

### Database locked errors
- SQLite issue with concurrent writes
- Reduce background job frequency
- Consider PostgreSQL upgrade

## Deployment Checklist

- [ ] Python 3.11+ installed
- [ ] Virtual environment created
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Setup wizard completed (`python setup.py`)
- [ ] Database initialized (`python init_db.py`)
- [ ] Segment webhook configured
- [ ] Google Ads API credentials tested
- [ ] Application started (`python app.py`)
- [ ] Test event received successfully
- [ ] Dashboard accessible
- [ ] Background jobs running

## Estimated Costs

### MVP Costs (Local Development)
- **Infrastructure**: $0 (runs on local machine)
- **Segment**: $0 (free tier: 1,000 MTUs)
- **Google Ads API**: $0 (free, but need existing ad spend)
- **Total**: **$0/month**

### Scaling Costs (Cloud Production)
- **Server**: $10-50/month (small VM)
- **Database**: $20-100/month (managed PostgreSQL)
- **Kafka**: $50-200/month (managed service)
- **Monitoring**: $0-50/month
- **Total**: **$80-400/month**

## Support & Next Steps

After successful MVP deployment:

1. Monitor for 1 week
2. Collect feedback on accuracy
3. Review attribution coverage
4. Plan enhancements (multi-tier costs, funnel tracking, etc.)
5. Consider cloud migration if scaling needed

## Summary

This MVP provides:
- ✅ Working attribution system in 20 minutes
- ✅ No complex infrastructure required
- ✅ Easy to test and iterate
- ✅ Clear migration path to full system
- ✅ $0 cost for development

**Total Time to Deploy: ~30 minutes**
**Total Cost: $0**
**Complexity: Low**

Ready to scale when you are!
