# Attribution MVP - Quick Start Guide

## 🎯 What This Is

A **bare-bones marketing attribution system** that:
- Receives events from Segment
- Stores touchpoints and conversions in SQLite
- Fetches Google Ads campaign costs
- Attributes conversions to last touchpoint
- Sends enriched data back to Segment

**Time to deploy: 20 minutes**  
**Cost: $0 (runs locally)**  
**Complexity: Low**

## 📋 Prerequisites

- **Python 3.11+** installed
- **Segment account** (free tier OK)
- **Google Ads account** with API access (optional)
- **Internet connection**

## 🚀 Quick Start

### Step 1: Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### Step 2: Configure System

Run the interactive setup wizard:

```bash
python configure.py
```

This will prompt you for:
- Segment webhook secret
- Segment write key
- Google Ads API credentials (optional)

### Step 3: Initialize Database

```bash
python scripts/init_db.py
```

### Step 4: Start the System

```bash
python -m attribution.app
```

You should see:
```
🚀 Attribution MVP Starting...
✅ Database initialized
✅ Background jobs scheduled
✅ Webhook server starting on port 5000
✅ Dashboard available at http://localhost:5000/dashboard
```

### Step 5: Configure Segment Webhook

1. Go to Segment workspace
2. Navigate to: Connections → Destinations
3. Add "Webhooks" destination
4. Enter webhook URL:
   - Local: `http://localhost:5000/webhooks/segment`
   - With ngrok: `https://[your-id].ngrok.io/webhooks/segment`
5. Add your webhook secret (from .env)
6. Save & enable

### Step 6: Test It!

Send a test event:

```bash
curl -X POST http://localhost:5000/webhooks/segment \
  -H "Content-Type: application/json" \
  -d '{
    "type": "page",
    "userId": "test_user",
    "anonymousId": "anon_123",
    "timestamp": "2024-12-05T12:00:00Z",
    "messageId": "test-123",
    "properties": {
      "utm_source": "google",
      "utm_campaign": "test_campaign"
    }
  }'
```

Check the dashboard:
```bash
open http://localhost:5000/dashboard
```

## 📁 Project Structure

```
attribution-mvp/
├── setup.py                 # Package installation config
├── configure.py             # Interactive setup wizard
├── requirements.txt         # Python dependencies
├── .env                     # Configuration (gitignored)
├── attribution.db           # SQLite database (gitignored)
│
├── src/attribution/
│   ├── app.py              # Main Flask application
│   └── jobs/
│       ├── fetch_costs.py       # Fetch Google Ads costs
│       ├── calculate_costs.py   # Calculate touchpoint costs
│       ├── run_attribution.py   # Run attribution
│       └── send_to_segment.py   # Send to Segment
│
├── scripts/
│   └── init_db.py          # Database initialization
│
└── docs/
    ├── adr/                # Architecture Decision Records
    └── *.md                # Project documentation
```

## 🔧 Manual Job Execution

You can run jobs manually:

```bash
# Fetch Google Ads costs for yesterday
python -m attribution.jobs.fetch_costs

# Calculate costs for touchpoints
python -m attribution.jobs.calculate_costs

# Run attribution
python -m attribution.jobs.run_attribution

# Send to Segment
python -m attribution.jobs.send_to_segment
```

## 📊 Dashboard

Access the dashboard at:
```
http://localhost:5000/dashboard
```

Shows:
- Total touchpoints
- Total conversions
- Attribution rate
- Touchpoints with costs
- Recent events
- System status

Auto-refreshes every 30 seconds.

## 🔄 How It Works

### Data Flow

```
1. User clicks ad → Segment tracks pageview
2. Webhook receives event → Stores touchpoint
3. User converts → Segment tracks conversion
4. Webhook receives event → Stores conversion
5. Background job runs → Finds last touchpoint
6. Attribution complete → Sends back to Segment
```

### Background Jobs

Scheduled automatically:
- **2:00 AM daily** - Fetch Google Ads costs
- **3:00 AM daily** - Calculate touchpoint costs
- **Every 5 minutes** - Run attribution
- **Every 5 minutes** - Send to Segment

## 🧪 Testing

### Test Touchpoint + Conversion Flow

```bash
# 1. Send touchpoint
curl -X POST http://localhost:5000/webhooks/segment \
  -H "Content-Type: application/json" \
  -d '{
    "type": "page",
    "userId": "user_123",
    "anonymousId": "anon_456",
    "timestamp": "2024-12-05T10:00:00Z",
    "messageId": "touchpoint-1",
    "properties": {
      "utm_source": "google",
      "utm_campaign": "winter_sale",
      "campaign_id": "12345"
    }
  }'

# 2. Manually fetch costs (if Google Ads configured)
python -m attribution.jobs.fetch_costs

# 3. Calculate costs
python -m attribution.jobs.calculate_costs

# 4. Send conversion
curl -X POST http://localhost:5000/webhooks/segment \
  -H "Content-Type: application/json" \
  -d '{
    "type": "track",
    "event": "Account Created",
    "userId": "user_123",
    "timestamp": "2024-12-05T11:00:00Z",
    "messageId": "conversion-1"
  }'

# 5. Run attribution
python -m attribution.jobs.run_attribution

# 6. Send to Segment
python -m attribution.jobs.send_to_segment

# 7. Check dashboard
open http://localhost:5000/dashboard
```

## 🔍 Querying Data

### SQLite CLI

```bash
sqlite3 attribution.db

# See touchpoints
SELECT * FROM touchpoints LIMIT 5;

# See conversions
SELECT * FROM conversions LIMIT 5;

# See attribution
SELECT 
  c.conversion_type,
  t.utm_campaign,
  c.attributed_cost
FROM conversions c
LEFT JOIN touchpoints t ON c.attributed_touchpoint_id = t.id
WHERE c.attributed_at IS NOT NULL;

# Exit
.quit
```

## ⚙️ Configuration

All configuration is in `.env`:

```bash
# Segment
SEGMENT_WEBHOOK_SECRET=your_secret
SEGMENT_WRITE_KEY=your_key

# Google Ads (optional)
GOOGLE_ADS_DEVELOPER_TOKEN=...
GOOGLE_ADS_CLIENT_ID=...
GOOGLE_ADS_CLIENT_SECRET=...
GOOGLE_ADS_REFRESH_TOKEN=...
GOOGLE_ADS_CUSTOMER_ID=...

# System
WEBHOOK_PORT=5000
DATABASE_PATH=./attribution.db
```

## 🌐 Using ngrok (Optional)

For testing without a public server:

```bash
# In a separate terminal
ngrok http 5000

# Copy the https URL, e.g.:
# https://abc123.ngrok.io

# Update Segment webhook to:
# https://abc123.ngrok.io/webhooks/segment
```

## ❓ Troubleshooting

### Webhook not receiving events

1. Check Segment webhook is enabled
2. Verify URL is correct
3. Check webhook secret matches
4. Look at Segment debugger for errors

### Attribution not working

1. Verify touchpoints have campaign data
2. Check user IDs match between touchpoint & conversion
3. Run attribution manually: `python -m attribution.jobs.run_attribution`
4. Check dashboard for stats

### Google Ads costs not fetching

1. Verify credentials in .env
2. Test connection: `python -m attribution.jobs.fetch_costs`
3. Check API quota limits in Google Cloud Console
4. Ensure campaigns are ENABLED status

### Database locked errors

SQLite limitation with concurrent writes:
- Reduce job frequency
- Consider PostgreSQL upgrade

## 📈 Scaling Up

When ready to scale:

1. **Add PostgreSQL**: Replace SQLite
2. **Add Kafka**: Insert event streaming layer
3. **Add Docker**: Containerize for deployment
4. **Add monitoring**: Prometheus + Grafana
5. **Add Redshift**: For analytics
6. **Enhance attribution**: Multi-touch models

See `MIGRATION_GUIDE.md` for details.

## 🐛 Known Limitations

- **SQLite**: Max ~1M rows before performance degrades
- **Single process**: No horizontal scaling
- **No authentication**: Don't expose publicly
- **No retry logic**: Failed jobs must be run manually
- **5-minute delay**: Attribution runs on schedule
- **Basic cost calc**: Only direct campaign match

## 📝 API Endpoints

### Webhook
```
POST /webhooks/segment
- Receives Segment events
- Returns 200 OK immediately
```

### Dashboard
```
GET /dashboard
- HTML monitoring interface
```

### Stats API
```
GET /api/stats
- Returns JSON stats
```

### Health Check
```
GET /health
- Returns system status
```

## 🆘 Support

Common issues:

**"Database not found"**
→ Run `python scripts/init_db.py`

**"Module not found"**
→ Run `pip install -r requirements.txt`

**"Permission denied"**
→ Make sure you're in virtual environment

**"Connection refused"**
→ Check port 5000 is not already in use

## 📚 Next Steps

After successful deployment:

1. ✅ Monitor for 1 week
2. ✅ Validate attribution accuracy
3. ✅ Review cost calculation coverage
4. ✅ Plan enhancements
5. ✅ Consider cloud migration

## 🎉 Success Criteria

MVP is working if:
- ✅ Events received from Segment
- ✅ Touchpoints stored in database
- ✅ Conversions attributed
- ✅ Data sent back to Segment
- ✅ Dashboard shows activity

## 📊 What You Get

With this MVP:
- Cost per conversion
- Attribution by campaign
- Conversion tracking
- Last-touch attribution
- Real-time monitoring

**Deploy time: 20 minutes**  
**Monthly cost: $0**  
**Lines of code: ~500**

Ready to scale when you are! 🚀
