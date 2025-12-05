# Code Templates & Starter Implementations

This document provides ready-to-use code templates for key components of the attribution system.

## Table of Contents
1. [Docker Compose Setup](#docker-compose-setup)
2. [Database Models (SQLAlchemy)](#database-models)
3. [Webhook API (FastAPI)](#webhook-api)
4. [Kafka Consumer](#kafka-consumer)
5. [Attribution Engine](#attribution-engine)
6. [Cost Calculator](#cost-calculator)
7. [Segment Client](#segment-client)
8. [Configuration Management](#configuration-management)

---

## Docker Compose Setup

**File**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    ports:
      - "2181:2181"
    volumes:
      - zookeeper-data:/var/lib/zookeeper/data
      - zookeeper-logs:/var/lib/zookeeper/log

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    volumes:
      - kafka-data:/var/lib/kafka/data

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: attribution
      POSTGRES_USER: attribution_user
      POSTGRES_PASSWORD: attribution_pass
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql

  pgadmin:
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@attribution.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - postgres

volumes:
  zookeeper-data:
  zookeeper-logs:
  kafka-data:
  postgres-data:
```

**Usage**:
```bash
docker-compose up -d
docker-compose ps  # Check status
docker-compose logs -f kafka  # View Kafka logs
```

---

## Database Models

**File**: `models/database.py`

```python
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, DECIMAL, JSON, Index, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import sessionmaker, relationship
import uuid
from datetime import datetime

Base = declarative_base()

class Touchpoint(Base):
    __tablename__ = 'touchpoints'
    
    touchpoint_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # Identity
    segment_anonymous_id = Column(String(255), index=True)
    segment_user_id = Column(String(255), index=True)
    resolved_user_id = Column(String(255), nullable=False, index=True)
    
    # Event metadata
    event_type = Column(String(50), nullable=False)
    event_name = Column(String(255), nullable=False)
    event_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Campaign attribution
    utm_source = Column(String(255))
    utm_medium = Column(String(255))
    utm_campaign = Column(String(255))
    utm_content = Column(String(255))
    utm_term = Column(String(255))
    campaign_id = Column(String(255), index=True)
    ad_platform = Column(String(50))
    
    # Context
    referrer = Column(String(2000))
    url = Column(String(2000))
    source_platform = Column(String(50))
    page_title = Column(String(500))
    
    # Cost attribution
    estimated_cost = Column(DECIMAL(10, 4))
    cost_calculation_method = Column(String(50))
    cost_calculated_at = Column(DateTime(timezone=True))
    
    # Properties
    properties = Column(JSONB)
    
    # Metadata
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_touchpoints_resolved_user_timestamp', 'resolved_user_id', 'event_timestamp'),
        Index('idx_touchpoints_campaign_date', 'campaign_id', 'event_timestamp'),
    )

class Conversion(Base):
    __tablename__ = 'conversions'
    
    conversion_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # Identity
    segment_user_id = Column(String(255), nullable=False, index=True)
    resolved_user_id = Column(String(255), nullable=False, index=True)
    
    # Conversion metadata
    conversion_type = Column(String(50), nullable=False)
    conversion_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    conversion_value = Column(DECIMAL(10, 2))
    funnel_stage = Column(Integer)
    
    # Attribution
    attributed_touchpoint_id = Column(UUID(as_uuid=True), ForeignKey('touchpoints.touchpoint_id'))
    attribution_model = Column(String(50), default='last_touch')
    attributed_cost = Column(DECIMAL(10, 4))
    attributed_campaign_id = Column(String(255))
    attributed_utm_source = Column(String(255))
    attributed_utm_medium = Column(String(255))
    attributed_utm_campaign = Column(String(255))
    
    # Journey metrics
    time_to_conversion_hours = Column(DECIMAL(10, 2))
    touchpoints_in_journey = Column(Integer)
    
    # Funnel progression
    previous_conversion_id = Column(UUID(as_uuid=True), ForeignKey('conversions.conversion_id'))
    next_conversion_id = Column(UUID(as_uuid=True), ForeignKey('conversions.conversion_id'))
    
    # Properties
    properties = Column(JSONB)
    
    # Metadata
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    attributed_at = Column(DateTime(timezone=True))
    
    # Relationships
    attributed_touchpoint = relationship("Touchpoint", foreign_keys=[attributed_touchpoint_id])
    
    # Indexes
    __table_args__ = (
        Index('idx_conversions_user_timestamp', 'resolved_user_id', 'conversion_timestamp'),
        Index('idx_conversions_type_timestamp', 'conversion_type', 'conversion_timestamp'),
    )

class CampaignCost(Base):
    __tablename__ = 'campaign_costs'
    
    cost_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Campaign identification
    ad_platform = Column(String(50), nullable=False)
    campaign_id = Column(String(255), nullable=False)
    campaign_name = Column(String(500))
    cost_date = Column(DateTime(timezone=True), nullable=False)
    
    # Cost metrics
    total_spend = Column(DECIMAL(10, 2), nullable=False)
    total_impressions = Column(Integer)
    total_clicks = Column(Integer)
    total_conversions = Column(Integer)
    
    # Calculated metrics
    platform_cpc = Column(DECIMAL(10, 4))
    calculated_cpc = Column(DECIMAL(10, 4))
    median_cpc = Column(DECIMAL(10, 4))
    ctr = Column(DECIMAL(5, 4))
    cpm = Column(DECIMAL(10, 2))
    
    # Raw data
    raw_data = Column(JSONB)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Unique constraint
    __table_args__ = (
        Index('idx_campaign_costs_platform_date', 'ad_platform', 'cost_date'),
        Index('idx_campaign_costs_campaign_date', 'campaign_id', 'cost_date'),
        Index('idx_unique_campaign_cost', 'ad_platform', 'campaign_id', 'cost_date', unique=True),
    )

class IdentityStitch(Base):
    __tablename__ = 'identity_stitches'
    
    stitch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    segment_anonymous_id = Column(String(255), nullable=False, index=True)
    segment_user_id = Column(String(255), nullable=False, index=True)
    stitched_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    touchpoints_updated = Column(Integer, default=0)
    processing_duration_ms = Column(Integer)

# Database connection
DATABASE_URL = "postgresql://attribution_user:attribution_pass@localhost:5432/attribution"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully")

if __name__ == "__main__":
    init_db()
```

---

## Webhook API

**File**: `services/webhook_api/main.py`

```python
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from kafka import KafkaProducer
import hmac
import hashlib
import json
import os
from datetime import datetime
from typing import Optional

app = FastAPI(title="Attribution Webhook API")

# Configuration
SEGMENT_WEBHOOK_SECRET = os.getenv("SEGMENT_WEBHOOK_SECRET", "your_secret_here")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Kafka producer
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def verify_segment_signature(body: bytes, signature: str) -> bool:
    """Verify Segment webhook signature"""
    expected_signature = hmac.new(
        SEGMENT_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha1
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)

def route_event_to_topic(event: dict) -> str:
    """Determine which Kafka topic to route event to"""
    event_type = event.get('type')
    event_name = event.get('event', '')
    
    # Conversion events
    if event_type == 'track' and event_name in [
        'Account Created', 'Signed Up',
        'Trial Started',
        'Subscription Purchased', 'Order Completed'
    ]:
        return 'conversions.raw'
    
    # Identity events
    if event_type == 'identify':
        return 'identity.raw'
    
    # Touchpoint events
    if event_type in ['page', 'track']:
        return 'touchpoints.raw'
    
    return 'events.other'

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.post("/webhooks/segment")
async def handle_segment_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None)
):
    """
    Receive events from Segment webhook destination.
    Validates signature and publishes to Kafka.
    """
    # Read raw body
    body = await request.body()
    
    # Verify signature
    if not x_signature:
        raise HTTPException(status_code=401, detail="Missing signature header")
    
    if not verify_segment_signature(body, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse JSON
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Validate required fields
    required_fields = ['type', 'messageId', 'timestamp']
    if not all(field in event for field in required_fields):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    # Route to appropriate topic
    topic = route_event_to_topic(event)
    
    # Add ingestion metadata
    event['_ingested_at'] = datetime.utcnow().isoformat()
    
    # Publish to Kafka
    try:
        producer.send(topic, value=event)
        producer.flush()
    except Exception as e:
        print(f"Failed to publish to Kafka: {e}")
        raise HTTPException(status_code=500, detail="Failed to process event")
    
    return {"status": "received", "topic": topic}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
```

**Run**:
```bash
python services/webhook_api/main.py
```

---

## Kafka Consumer

**File**: `services/event_processor/touchpoint_consumer.py`

```python
from kafka import KafkaConsumer
import json
from datetime import datetime
from models.database import SessionLocal, Touchpoint
from sqlalchemy.exc import IntegrityError

# Configuration
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
TOPIC = "touchpoints.raw"

# Create consumer
consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    group_id='touchpoint-processor',
    auto_offset_reset='earliest'
)

def extract_utm(event: dict, param: str) -> str:
    """Extract UTM parameter from various locations in event"""
    # Try properties
    properties = event.get('properties', {})
    if f'utm_{param}' in properties:
        return properties[f'utm_{param}']
    
    # Try context.campaign
    campaign = event.get('context', {}).get('campaign', {})
    if param in campaign:
        return campaign[param]
    
    return None

def process_touchpoint_event(event: dict):
    """Process touchpoint event and store in database"""
    db = SessionLocal()
    
    try:
        # Check for duplicate
        existing = db.query(Touchpoint).filter_by(event_id=event['messageId']).first()
        if existing:
            print(f"Duplicate event: {event['messageId']}")
            return
        
        # Create touchpoint
        touchpoint = Touchpoint(
            event_id=event['messageId'],
            segment_anonymous_id=event.get('anonymousId'),
            segment_user_id=event.get('userId'),
            resolved_user_id=event.get('userId') or event.get('anonymousId'),
            event_type=event['type'],
            event_name=event.get('event') or event.get('name', 'page_view'),
            event_timestamp=datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')),
            
            # Extract UTM parameters
            utm_source=extract_utm(event, 'source'),
            utm_medium=extract_utm(event, 'medium'),
            utm_campaign=extract_utm(event, 'campaign'),
            utm_content=extract_utm(event, 'content'),
            utm_term=extract_utm(event, 'term'),
            campaign_id=event.get('properties', {}).get('campaign_id'),
            
            # Context
            referrer=event.get('context', {}).get('page', {}).get('referrer'),
            url=event.get('context', {}).get('page', {}).get('url'),
            source_platform='web',  # TODO: Detect from context
            
            properties=event.get('properties', {}),
        )
        
        db.add(touchpoint)
        db.commit()
        print(f"Processed touchpoint: {touchpoint.touchpoint_id}")
        
    except IntegrityError:
        db.rollback()
        print(f"Duplicate event (integrity): {event['messageId']}")
    except Exception as e:
        db.rollback()
        print(f"Error processing event: {e}")
    finally:
        db.close()

def main():
    """Main consumer loop"""
    print(f"Starting touchpoint consumer on topic: {TOPIC}")
    
    for message in consumer:
        try:
            event = message.value
            process_touchpoint_event(event)
        except Exception as e:
            print(f"Failed to process message: {e}")

if __name__ == "__main__":
    main()
```

**Run**:
```bash
python services/event_processor/touchpoint_consumer.py
```

---

## Attribution Engine

**File**: `services/attribution/engine.py`

```python
from models.database import SessionLocal, Conversion, Touchpoint
from sqlalchemy import and_
from datetime import datetime
from typing import Optional

class LastTouchAttributionModel:
    """Last-touch attribution model"""
    
    def __init__(self):
        self.db = SessionLocal()
    
    def is_marketing_touchpoint(self, touchpoint: Touchpoint) -> bool:
        """Determine if touchpoint is from marketing (not organic/direct)"""
        # Has campaign tracking
        if touchpoint.campaign_id or touchpoint.utm_campaign:
            return True
        
        # Has paid source/medium
        paid_sources = ['google', 'facebook', 'instagram', 'tiktok', 'linkedin']
        paid_mediums = ['cpc', 'cpm', 'paid', 'paidsocial', 'ppc']
        
        if touchpoint.utm_source and touchpoint.utm_source.lower() in paid_sources:
            return True
        
        if touchpoint.utm_medium and touchpoint.utm_medium.lower() in paid_mediums:
            return True
        
        return False
    
    def attribute_conversion(self, conversion: Conversion) -> dict:
        """
        Find last marketing touchpoint and attribute conversion.
        Returns attribution data.
        """
        # Get all touchpoints before conversion
        touchpoints = self.db.query(Touchpoint).filter(
            and_(
                Touchpoint.resolved_user_id == conversion.resolved_user_id,
                Touchpoint.event_timestamp < conversion.conversion_timestamp
            )
        ).order_by(Touchpoint.event_timestamp.desc()).all()
        
        # Filter to marketing touchpoints
        marketing_touchpoints = [
            tp for tp in touchpoints
            if self.is_marketing_touchpoint(tp)
        ]
        
        if not marketing_touchpoints:
            return {
                'attributed_touchpoint_id': None,
                'attribution_model': 'last_touch',
                'attribution_reason': 'no_marketing_touchpoints'
            }
        
        # Last marketing touchpoint gets credit
        last_touchpoint = marketing_touchpoints[0]
        
        # Calculate time to conversion
        time_diff = conversion.conversion_timestamp - last_touchpoint.event_timestamp
        time_to_conversion_hours = time_diff.total_seconds() / 3600
        
        # Update conversion
        conversion.attributed_touchpoint_id = last_touchpoint.touchpoint_id
        conversion.attribution_model = 'last_touch'
        conversion.attributed_cost = last_touchpoint.estimated_cost
        conversion.attributed_campaign_id = last_touchpoint.campaign_id
        conversion.attributed_utm_source = last_touchpoint.utm_source
        conversion.attributed_utm_medium = last_touchpoint.utm_medium
        conversion.attributed_utm_campaign = last_touchpoint.utm_campaign
        conversion.time_to_conversion_hours = time_to_conversion_hours
        conversion.touchpoints_in_journey = len(touchpoints)
        conversion.attributed_at = datetime.utcnow()
        
        self.db.commit()
        
        return {
            'attributed_touchpoint_id': last_touchpoint.touchpoint_id,
            'attributed_cost': float(last_touchpoint.estimated_cost or 0),
            'attributed_campaign': last_touchpoint.utm_campaign,
            'time_to_conversion_hours': time_to_conversion_hours,
            'attribution_model': 'last_touch'
        }
    
    def __del__(self):
        self.db.close()

# Example usage
if __name__ == "__main__":
    db = SessionLocal()
    
    # Find unattributed conversions
    conversions = db.query(Conversion).filter(
        Conversion.attributed_touchpoint_id.is_(None)
    ).limit(10).all()
    
    model = LastTouchAttributionModel()
    
    for conversion in conversions:
        print(f"Attributing conversion: {conversion.conversion_id}")
        result = model.attribute_conversion(conversion)
        print(f"Result: {result}")
```

---

## Cost Calculator

**File**: `scripts/calculate_costs.py`

```python
import argparse
from datetime import datetime, timedelta, date
from models.database import SessionLocal, Touchpoint, CampaignCost
from sqlalchemy import func, and_
from decimal import Decimal
import statistics

class CostCalculationEngine:
    """Calculate costs for touchpoints"""
    
    def __init__(self):
        self.db = SessionLocal()
    
    def get_campaign_cost(self, campaign_id: str, target_date: date):
        """Get campaign cost for specific date"""
        return self.db.query(CampaignCost).filter(
            and_(
                CampaignCost.campaign_id == campaign_id,
                func.date(CampaignCost.cost_date) == target_date
            )
        ).first()
    
    def calculate_touchpoint_cost(self, touchpoint: Touchpoint) -> dict:
        """Calculate cost using tiered strategy"""
        cost_date = touchpoint.event_timestamp.date()
        
        # Tier 1: Direct campaign match
        if touchpoint.campaign_id:
            campaign_cost = self.get_campaign_cost(touchpoint.campaign_id, cost_date)
            if campaign_cost and campaign_cost.calculated_cpc:
                return {
                    'cost': campaign_cost.calculated_cpc,
                    'method': 'campaign_cpc'
                }
        
        # Tier 2: Platform median (simplified for template)
        # Tier 3: Default estimate
        default_cpc = Decimal('1.50')  # $1.50 default
        return {
            'cost': default_cpc,
            'method': 'default_estimate'
        }
    
    def calculate_costs_for_date(self, target_date: date):
        """Calculate costs for all touchpoints on a date"""
        touchpoints = self.db.query(Touchpoint).filter(
            and_(
                func.date(Touchpoint.event_timestamp) == target_date,
                Touchpoint.estimated_cost.is_(None)
            )
        ).all()
        
        print(f"Found {len(touchpoints)} touchpoints to calculate")
        
        updated = 0
        for tp in touchpoints:
            try:
                result = self.calculate_touchpoint_cost(tp)
                tp.estimated_cost = result['cost']
                tp.cost_calculation_method = result['method']
                tp.cost_calculated_at = datetime.utcnow()
                updated += 1
            except Exception as e:
                print(f"Error calculating cost for {tp.touchpoint_id}: {e}")
        
        self.db.commit()
        print(f"Updated {updated} touchpoints with costs")
    
    def __del__(self):
        self.db.close()

def main():
    parser = argparse.ArgumentParser(description='Calculate touchpoint costs')
    parser.add_argument('--date', type=str, default='yesterday',
                       help='Date to process (YYYY-MM-DD or "yesterday")')
    args = parser.parse_args()
    
    if args.date == 'yesterday':
        target_date = (datetime.utcnow() - timedelta(days=1)).date()
    else:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    
    print(f"Calculating costs for: {target_date}")
    
    engine = CostCalculationEngine()
    engine.calculate_costs_for_date(target_date)

if __name__ == "__main__":
    main()
```

**Run**:
```bash
python scripts/calculate_costs.py --date yesterday
```

---

## Segment Client

**File**: `services/segment_client/client.py`

```python
import requests
import os
from datetime import datetime
from typing import Dict, Any

class SegmentHTTPClient:
    """Send events to Segment via HTTP Tracking API"""
    
    def __init__(self):
        self.write_key = os.getenv("SEGMENT_WRITE_KEY", "your_write_key")
        self.base_url = "https://api.segment.io/v1"
    
    def track(self, user_id: str, event: str, properties: Dict[str, Any],
              timestamp: str = None):
        """Send track event to Segment"""
        
        payload = {
            "userId": user_id,
            "event": event,
            "properties": properties,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "context": {
                "source": "attribution_system"
            }
        }
        
        response = requests.post(
            f"{self.base_url}/track",
            json=payload,
            auth=(self.write_key, ''),
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code != 200:
            raise Exception(f"Segment API error: {response.text}")
        
        return response.json()
    
    def emit_attributed_conversion(self, conversion, attribution):
        """Send attributed conversion event to Segment"""
        
        properties = {
            'conversion_type': conversion.conversion_type,
            'conversion_value': float(conversion.conversion_value or 0),
            'attributed_cost': float(attribution['attributed_cost']),
            'attributed_campaign': attribution['attributed_campaign'],
            'time_to_conversion_hours': float(attribution['time_to_conversion_hours']),
            'attribution_model': attribution['attribution_model']
        }
        
        return self.track(
            user_id=conversion.segment_user_id,
            event='Conversion Attributed',
            properties=properties
        )

# Example usage
if __name__ == "__main__":
    from models.database import SessionLocal, Conversion
    
    db = SessionLocal()
    client = SegmentHTTPClient()
    
    # Get recent conversion
    conversion = db.query(Conversion).filter(
        Conversion.attributed_touchpoint_id.isnot(None)
    ).first()
    
    if conversion:
        attribution = {
            'attributed_cost': float(conversion.attributed_cost or 0),
            'attributed_campaign': conversion.attributed_utm_campaign,
            'time_to_conversion_hours': float(conversion.time_to_conversion_hours or 0),
            'attribution_model': conversion.attribution_model
        }
        
        result = client.emit_attributed_conversion(conversion, attribution)
        print(f"Sent to Segment: {result}")
```

---

## Configuration Management

**File**: `.env.example`

```bash
# Database
DATABASE_URL=postgresql://attribution_user:attribution_pass@localhost:5432/attribution

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Segment
SEGMENT_WEBHOOK_SECRET=your_webhook_secret_here
SEGMENT_WRITE_KEY=your_write_key_here

# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN=your_dev_token
GOOGLE_ADS_CLIENT_ID=your_client_id
GOOGLE_ADS_CLIENT_SECRET=your_client_secret
GOOGLE_ADS_REFRESH_TOKEN=your_refresh_token
GOOGLE_ADS_CUSTOMER_ID=1234567890
```

**File**: `config/config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    
    # Segment
    SEGMENT_WEBHOOK_SECRET = os.getenv("SEGMENT_WEBHOOK_SECRET")
    SEGMENT_WRITE_KEY = os.getenv("SEGMENT_WRITE_KEY")
    
    # Google Ads
    GOOGLE_ADS_CONFIG = {
        'developer_token': os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
        'client_id': os.getenv("GOOGLE_ADS_CLIENT_ID"),
        'client_secret': os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
        'refresh_token': os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
        'customer_id': os.getenv("GOOGLE_ADS_CUSTOMER_ID"),
    }

config = Config()
```

---

## Requirements

**File**: `requirements.txt`

```
fastapi==0.104.1
uvicorn==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
kafka-python==2.0.2
requests==2.31.0
python-dotenv==1.0.0
google-ads==23.1.0
pydantic==2.5.0
```

**Install**:
```bash
pip install -r requirements.txt
```

---

## Quick Start Script

**File**: `scripts/start_local.sh`

```bash
#!/bin/bash

echo "Starting Attribution System..."

# Start Docker services
echo "Starting Docker services..."
docker-compose up -d

# Wait for services
echo "Waiting for services to be ready..."
sleep 10

# Initialize database
echo "Initializing database..."
python models/database.py

# Start webhook API
echo "Starting webhook API..."
python services/webhook_api/main.py &

# Start touchpoint consumer
echo "Starting touchpoint consumer..."
python services/event_processor/touchpoint_consumer.py &

echo "Attribution system started!"
echo "Webhook API: http://localhost:3000"
echo "PgAdmin: http://localhost:5050"
```

**Usage**:
```bash
chmod +x scripts/start_local.sh
./scripts/start_local.sh
```

---

These templates provide a solid foundation to start building. Customize as needed for your specific requirements!
