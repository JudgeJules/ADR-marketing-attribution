#!/usr/bin/env python3
"""
Attribution MVP - Main Application
Simple Flask server with background jobs
"""

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import os
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
DATABASE_PATH = os.getenv('DATABASE_PATH', './attribution.db')
SEGMENT_WEBHOOK_SECRET = os.getenv('SEGMENT_WEBHOOK_SECRET')

# ===== Database Helper =====
def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ===== Webhook Endpoint =====
@app.route('/webhooks/segment', methods=['POST'])
@app.route('/events', methods=['POST'])
def segment_webhook():
    """Receive events from Segment"""
    try:
        event = request.json
        
        # Simple validation
        if not event or 'type' not in event:
            return jsonify({'error': 'Invalid event'}), 400
        
        # Route event
        event_type = event.get('type')
        event_name = event.get('event', '')
        
        # Determine if this is a conversion
        conversion_events = ['Account Created', 'Signed Up', 'Trial Started', 
                           'Subscription Purchased', 'Order Completed']
        
        if event_type == 'track' and event_name in conversion_events:
            store_conversion(event)
        else:
            store_touchpoint(event)
        
        return jsonify({'status': 'received'}), 200
        
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({'error': str(e)}), 500

def store_touchpoint(event):
    """Store touchpoint event"""
    db = get_db()
    cursor = db.cursor()
    
    # Extract data
    event_id = event.get('messageId') or event.get('message_id')
    user_id = event.get('userId')
    anonymous_id = event.get('anonymousId')
    resolved_user_id = user_id or anonymous_id
    event_type = event.get('type')
    event_name = event.get('event') or event.get('name', 'page_view')
    timestamp = event.get('timestamp')
    
    # Extract UTM parameters
    properties = event.get('properties', {})
    context = event.get('context', {})
    campaign = context.get('campaign', {})
    
    utm_source = properties.get('utm_source') or campaign.get('source')
    utm_medium = properties.get('utm_medium') or campaign.get('medium')
    utm_campaign = properties.get('utm_campaign') or campaign.get('name')
    utm_content = properties.get('utm_content') or campaign.get('content')
    utm_term = properties.get('utm_term') or campaign.get('term')
    campaign_id = properties.get('campaign_id')
    
    # Extract context
    page = context.get('page', {})
    referrer = page.get('referrer')
    url = page.get('url')
    
    try:
        cursor.execute("""
            INSERT INTO touchpoints (
                event_id, user_id, anonymous_id, resolved_user_id,
                event_type, event_name, timestamp,
                utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                campaign_id, referrer, url, properties
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, user_id, anonymous_id, resolved_user_id,
            event_type, event_name, timestamp,
            utm_source, utm_medium, utm_campaign, utm_content, utm_term,
            campaign_id, referrer, url, json.dumps(properties)
        ))
        
        db.commit()
        print(f"✅ Stored touchpoint: {event_id}")
        
    except sqlite3.IntegrityError:
        print(f"⚠️  Duplicate touchpoint: {event_id}")
    except Exception as e:
        print(f"❌ Error storing touchpoint: {e}")
    finally:
        db.close()

def store_conversion(event):
    """Store conversion event"""
    db = get_db()
    cursor = db.cursor()
    
    event_id = event.get('messageId') or event.get('message_id')
    user_id = event.get('userId')
    event_name = event.get('event')
    timestamp = event.get('timestamp')
    properties = event.get('properties', {})
    
    # Map event name to conversion type
    conversion_type_map = {
        'Account Created': 'account_created',
        'Signed Up': 'account_created',
        'Trial Started': 'trial_started',
        'Subscription Purchased': 'subscription_purchased',
        'Order Completed': 'subscription_purchased'
    }
    conversion_type = conversion_type_map.get(event_name, 'unknown')
    
    # Get conversion value if present
    conversion_value = properties.get('revenue') or properties.get('value')
    
    try:
        cursor.execute("""
            INSERT INTO conversions (
                event_id, user_id, conversion_type, timestamp,
                conversion_value, properties
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            event_id, user_id, conversion_type, timestamp,
            conversion_value, json.dumps(properties)
        ))
        
        db.commit()
        print(f"✅ Stored conversion: {event_id} ({conversion_type})")
        
    except sqlite3.IntegrityError:
        print(f"⚠️  Duplicate conversion: {event_id}")
    except Exception as e:
        print(f"❌ Error storing conversion: {e}")
    finally:
        db.close()

# ===== Dashboard Endpoint =====
@app.route('/dashboard')
def dashboard():
    """Simple monitoring dashboard"""
    stats = get_stats()
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Attribution MVP Dashboard</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            h1 { color: #333; }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }
            .stat-card {
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .stat-value {
                font-size: 32px;
                font-weight: bold;
                color: #2563eb;
            }
            .stat-label {
                color: #666;
                margin-top: 5px;
            }
            .section {
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin: 20px 0;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid #e5e5e5;
            }
            th {
                background: #f9fafb;
                font-weight: 600;
            }
            .status-ok { color: #10b981; }
            .status-warning { color: #f59e0b; }
            .refresh {
                background: #2563eb;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }
            .refresh:hover { background: #1d4ed8; }
        </style>
        <script>
            function refreshPage() {
                location.reload();
            }
            // Auto-refresh every 30 seconds
            setTimeout(refreshPage, 30000);
        </script>
    </head>
    <body>
        <h1>📊 Attribution MVP Dashboard</h1>
        <button class="refresh" onclick="refreshPage()">🔄 Refresh</button>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{{ stats.touchpoints }}</div>
                <div class="stat-label">Touchpoints</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.conversions }}</div>
                <div class="stat-label">Conversions</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.attributed }}</div>
                <div class="stat-label">Attributed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.attribution_rate }}%</div>
                <div class="stat-label">Attribution Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.with_costs }}</div>
                <div class="stat-label">With Costs</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.campaigns }}</div>
                <div class="stat-label">Campaigns</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Recent Events (Last 10)</h2>
            <table>
                <tr>
                    <th>Time</th>
                    <th>Type</th>
                    <th>User</th>
                    <th>Campaign</th>
                    <th>Cost</th>
                </tr>
                {% for event in stats.recent_events %}
                <tr>
                    <td>{{ event.timestamp }}</td>
                    <td>{{ event.type }}</td>
                    <td>{{ event.user_id }}</td>
                    <td>{{ event.campaign or '-' }}</td>
                    <td>{{ event.cost or '-' }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        
        <div class="section">
            <h2>System Status</h2>
            <p class="status-ok">✅ System running</p>
            <p>Database: {{ stats.database_path }}</p>
            <p>Last updated: {{ stats.last_updated }}</p>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(html, stats=stats)

@app.route('/api/stats')
def api_stats():
    """Stats API endpoint"""
    return jsonify(get_stats())

def get_stats():
    """Get system statistics"""
    db = get_db()
    cursor = db.cursor()
    
    # Count touchpoints
    cursor.execute("SELECT COUNT(*) FROM touchpoints")
    touchpoints_count = cursor.fetchone()[0]
    
    # Count conversions
    cursor.execute("SELECT COUNT(*) FROM conversions")
    conversions_count = cursor.fetchone()[0]
    
    # Count attributed conversions
    cursor.execute("SELECT COUNT(*) FROM conversions WHERE attributed_at IS NOT NULL")
    attributed_count = cursor.fetchone()[0]
    
    # Attribution rate
    attribution_rate = 0
    if conversions_count > 0:
        attribution_rate = round((attributed_count / conversions_count) * 100, 1)
    
    # Count touchpoints with costs
    cursor.execute("SELECT COUNT(*) FROM touchpoints WHERE estimated_cost IS NOT NULL")
    with_costs = cursor.fetchone()[0]
    
    # Count campaigns
    cursor.execute("SELECT COUNT(DISTINCT campaign_id) FROM campaign_costs")
    campaigns_count = cursor.fetchone()[0]
    
    # Get recent events
    cursor.execute("""
        SELECT timestamp, 'touchpoint' as type, resolved_user_id as user_id, 
               utm_campaign as campaign, estimated_cost as cost
        FROM touchpoints
        ORDER BY created_at DESC
        LIMIT 10
    """)
    recent_events = [dict(row) for row in cursor.fetchall()]
    
    db.close()
    
    return {
        'touchpoints': touchpoints_count,
        'conversions': conversions_count,
        'attributed': attributed_count,
        'attribution_rate': attribution_rate,
        'with_costs': with_costs,
        'campaigns': campaigns_count,
        'recent_events': recent_events,
        'database_path': DATABASE_PATH,
        'last_updated': datetime.utcnow().isoformat()
    }

# ===== Health Check =====
@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })

# ===== Background Jobs =====
def schedule_jobs():
    """Schedule background jobs"""
    scheduler = BackgroundScheduler()
    
    # Import job functions
    from attribution.jobs.fetch_costs import fetch_google_ads_costs
    from attribution.jobs.calculate_costs import calculate_touchpoint_costs
    from attribution.jobs.run_attribution import run_attribution
    from attribution.jobs.send_to_segment import send_attributed_conversions
    
    # Daily at 2 AM: Fetch Google Ads costs
    scheduler.add_job(
        fetch_google_ads_costs,
        'cron',
        hour=2,
        minute=0,
        id='fetch_costs'
    )
    
    # Daily at 3 AM: Calculate touchpoint costs
    scheduler.add_job(
        calculate_touchpoint_costs,
        'cron',
        hour=3,
        minute=0,
        id='calculate_costs'
    )
    
    # Every 5 minutes: Run attribution
    scheduler.add_job(
        run_attribution,
        'interval',
        minutes=5,
        id='run_attribution'
    )
    
    # Every 5 minutes: Send to Segment
    scheduler.add_job(
        send_attributed_conversions,
        'interval',
        minutes=5,
        id='send_to_segment'
    )
    
    scheduler.start()
    return scheduler

# ===== Main =====
if __name__ == '__main__':
    print("\n" + "="*60)
    print("  🚀 Attribution MVP Starting...")
    print("="*60 + "\n")
    
    # Check database exists
    if not os.path.exists(DATABASE_PATH):
        print("❌ Database not found!")
        print("   Run: python init_db.py")
        exit(1)
    
    print("✅ Database initialized")
    
    # Schedule background jobs
    try:
        scheduler = schedule_jobs()
        print("✅ Background jobs scheduled")
    except Exception as e:
        print(f"⚠️  Warning: Could not schedule jobs: {e}")
        print("   Jobs will not run automatically")
    
    # Get stats
    stats = get_stats()
    
    # Start web server
    port = int(os.getenv('WEBHOOK_PORT', 5000))
    
    # Check if port is available
    import socket
    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
    
    if is_port_in_use(port):
        print(f"⚠️  Port {port} is already in use")
        if port == 5000:
            print("   (This is often macOS AirPlay Receiver)")
        
        # Try to find an available port
        alternative_ports = [8000, 8080, 3000, 5001, 8888]
        found_port = None
        
        for alt_port in alternative_ports:
            if not is_port_in_use(alt_port):
                found_port = alt_port
                break
        
        if found_port:
            print(f"✅ Using alternative port: {found_port}")
            port = found_port
        else:
            print("❌ No available ports found. Please free up a port and try again.")
            print("   To disable AirPlay Receiver: System Settings → General → AirDrop & Handoff")
            exit(1)
    
    print(f"✅ Webhook server starting on port {port}")
    print(f"✅ Dashboard available at http://localhost:{port}/dashboard")
    
    print(f"\n📊 Current Status:")
    print(f"   • Touchpoints: {stats['touchpoints']}")
    print(f"   • Conversions: {stats['conversions']}")
    print(f"   • Attributed: {stats['attributed']}")
    
    print(f"\n⏰ Scheduled Jobs:")
    print(f"   • Fetch Google Ads Costs: Daily at 2:00 AM")
    print(f"   • Calculate Costs: Daily at 3:00 AM")
    print(f"   • Run Attribution: Every 5 minutes")
    print(f"   • Send to Segment: Every 5 minutes")
    
    print("\n" + "="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)
