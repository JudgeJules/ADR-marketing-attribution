# ADR-007: Segment Bidirectional Integration

## Status
Proposed

## Context
The attribution system must integrate bidirectionally with Segment CDP:
- **Inbound**: Receive touchpoint events and conversion events from Segment via webhook
- **Outbound**: Send enriched conversion data with attribution back to Segment via custom source

This creates a closed loop where Segment is the source of truth for identity resolution, and our system enriches conversions with cost attribution data that flows back into Segment for unified customer profiles.

### Requirements
- Receive events from Segment webhook destination (already configured)
- Parse and validate Segment event schema
- Send attributed conversion data back to Segment
- Use Segment as custom source (already configured)
- Include attribution metadata (cost, campaign, touchpoint details)
- Handle authentication and event validation
- Maintain data consistency between systems

### Integration Goals
```
User Touchpoint → Segment → Attribution System → Enrichment → Segment
User Conversion → Segment → Attribution System → Cost Attribution → Segment

Result: Segment profiles enriched with cost and attribution data
```

## Decision
We will implement **bidirectional integration** using:
1. **Segment Webhook Destination** for inbound events (HTTP POST)
2. **Segment Custom Source** via HTTP Tracking API for outbound events
3. **Event schema mapping** to/from Segment's standard format
4. **Kafka topics** as integration buffers for reliability

### Inbound Integration (Segment → Attribution System)

#### Webhook API Endpoint
```python
from fastapi import FastAPI, Request, HTTPException, Header
import hmac
import hashlib

app = FastAPI()

class SegmentWebhookHandler:
    """Handles incoming webhook events from Segment"""
    
    def __init__(self, webhook_secret: str):
        self.webhook_secret = webhook_secret
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Segment webhook signature"""
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha1
        ).hexdigest()
        return hmac.compare_digest(signature, expected_signature)
    
    @app.post("/webhooks/segment")
    async def handle_segment_webhook(
        self,
        request: Request,
        x_signature: str = Header(None)
    ):
        """
        Receive events from Segment webhook destination.
        Validates signature and publishes to Kafka.
        """
        # Read raw body for signature verification
        body = await request.body()
        
        # Verify signature
        if not self.verify_signature(body, x_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse JSON
        event = await request.json()
        
        # Validate event schema
        if not self.validate_segment_event(event):
            raise HTTPException(status_code=400, detail="Invalid event schema")
        
        # Route to appropriate Kafka topic based on event type
        topic = self.route_event(event)
        
        # Publish to Kafka
        kafka_producer.send(topic, value=event)
        
        # Return 200 immediately (async processing)
        return {"status": "received"}
    
    def validate_segment_event(self, event: dict) -> bool:
        """Validate Segment event has required fields"""
        required_fields = ['type', 'messageId', 'timestamp']
        return all(field in event for field in required_fields)
    
    def route_event(self, event: dict) -> str:
        """Route event to appropriate Kafka topic"""
        event_type = event.get('type')
        
        if event_type == 'track':
            event_name = event.get('event', '')
            
            # Conversion events
            if event_name in ['Account Created', 'Trial Started', 'Subscription Purchased']:
                return 'conversions.raw'
            
            # Touchpoint events (page views, clicks, etc.)
            return 'touchpoints.raw'
        
        elif event_type == 'identify':
            # Identity resolution events
            return 'identity.raw'
        
        elif event_type == 'page':
            # Page view touchpoints
            return 'touchpoints.raw'
        
        return 'events.other'
```

#### Event Schema Mapping (Inbound)
```python
class SegmentEventMapper:
    """Maps Segment events to internal attribution schema"""
    
    def map_touchpoint_event(self, segment_event: dict) -> Touchpoint:
        """Convert Segment event to Touchpoint model"""
        
        return Touchpoint(
            event_id=segment_event['messageId'],
            segment_anonymous_id=segment_event.get('anonymousId'),
            segment_user_id=segment_event.get('userId'),
            resolved_user_id=segment_event.get('userId') or segment_event.get('anonymousId'),
            event_type=segment_event['type'],
            event_name=segment_event.get('event') or segment_event.get('name'),
            event_timestamp=dateutil.parser.parse(segment_event['timestamp']),
            
            # Extract campaign tracking from properties or context
            utm_source=self.extract_utm(segment_event, 'source'),
            utm_medium=self.extract_utm(segment_event, 'medium'),
            utm_campaign=self.extract_utm(segment_event, 'campaign'),
            utm_content=self.extract_utm(segment_event, 'content'),
            utm_term=self.extract_utm(segment_event, 'term'),
            campaign_id=segment_event.get('properties', {}).get('campaign_id'),
            
            # Context
            referrer=segment_event.get('context', {}).get('page', {}).get('referrer'),
            url=segment_event.get('context', {}).get('page', {}).get('url'),
            source_platform=self.extract_platform(segment_event),
            
            # Store full event for debugging
            properties=segment_event.get('properties', {}),
        )
    
    def extract_utm(self, event: dict, param: str) -> Optional[str]:
        """Extract UTM parameter from various possible locations"""
        # Try properties first
        properties = event.get('properties', {})
        if f'utm_{param}' in properties:
            return properties[f'utm_{param}']
        
        # Try context.campaign
        campaign = event.get('context', {}).get('campaign', {})
        if param in campaign:
            return campaign[param]
        
        # Try parsing from URL
        url = event.get('context', {}).get('page', {}).get('url')
        if url:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            if f'utm_{param}' in params:
                return params[f'utm_{param}'][0]
        
        return None
    
    def extract_platform(self, event: dict) -> str:
        """Determine source platform from context"""
        context = event.get('context', {})
        
        if context.get('library', {}).get('name') == 'analytics-ios':
            return 'mobile_ios'
        elif context.get('library', {}).get('name') == 'analytics-android':
            return 'mobile_android'
        elif context.get('library', {}).get('name') == 'analytics.js':
            return 'web'
        
        return 'unknown'
```

### Outbound Integration (Attribution System → Segment)

#### Segment HTTP Tracking API Client
```python
import requests

class SegmentHTTPClient:
    """Send events to Segment via HTTP Tracking API"""
    
    def __init__(self, write_key: str, source_id: str):
        self.write_key = write_key
        self.source_id = source_id
        self.base_url = "https://api.segment.io/v1"
    
    def track(self, user_id: str, event: str, properties: dict, 
              context: dict = None, timestamp: str = None):
        """Send track event to Segment"""
        
        payload = {
            "userId": user_id,
            "event": event,
            "properties": properties,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "context": context or {}
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
    
    def batch_track(self, events: List[dict]):
        """Send multiple events in batch"""
        
        payload = {
            "batch": events
        }
        
        response = requests.post(
            f"{self.base_url}/batch",
            json=payload,
            auth=(self.write_key, ''),
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code != 200:
            raise Exception(f"Segment batch API error: {response.text}")
        
        return response.json()
```

#### Attributed Conversion Event Schema
```python
class AttributionEnricher:
    """Enriches conversions with attribution data and sends back to Segment"""
    
    def __init__(self, segment_client: SegmentHTTPClient):
        self.segment_client = segment_client
    
    def emit_attributed_conversion(self, conversion: Conversion, attribution: Attribution):
        """
        Send conversion with attribution metadata back to Segment.
        This creates a new event type: "Conversion Attributed"
        """
        
        # Get attributed touchpoint details
        touchpoint = None
        if attribution.attributed_touchpoint_id:
            touchpoint = db.query(Touchpoint).get(attribution.attributed_touchpoint_id)
        
        properties = {
            # Original conversion data
            'conversion_type': conversion.conversion_type,
            'conversion_value': float(conversion.conversion_value or 0),
            'conversion_timestamp': conversion.conversion_timestamp.isoformat(),
            
            # Attribution data
            'attribution_model': attribution.attribution_model,
            'attributed_cost': float(attribution.attributed_cost or 0),
            'attributed_campaign_id': attribution.attributed_campaign_id,
            'attributed_utm_source': attribution.attributed_utm_source,
            'attributed_utm_medium': attribution.attributed_utm_medium,
            'attributed_utm_campaign': attribution.attributed_utm_campaign,
            
            # Journey metrics
            'time_to_conversion_hours': float(attribution.time_to_conversion_hours or 0),
            'touchpoints_in_journey': attribution.touchpoints_in_journey,
            
            # ROI calculation
            'roi': self.calculate_roi(conversion, attribution),
            
            # Touchpoint details (if available)
            'attributed_touchpoint': self.serialize_touchpoint(touchpoint) if touchpoint else None
        }
        
        # Send to Segment
        self.segment_client.track(
            user_id=conversion.segment_user_id,
            event='Conversion Attributed',
            properties=properties,
            timestamp=datetime.utcnow().isoformat(),
            context={
                'source': 'attribution_system',
                'version': '1.0'
            }
        )
    
    def calculate_roi(self, conversion: Conversion, attribution: Attribution) -> Optional[float]:
        """Calculate ROI = (Revenue - Cost) / Cost"""
        if not conversion.conversion_value or not attribution.attributed_cost:
            return None
        
        cost = float(attribution.attributed_cost)
        revenue = float(conversion.conversion_value)
        
        if cost == 0:
            return None
        
        return ((revenue - cost) / cost) * 100  # Percentage
    
    def serialize_touchpoint(self, touchpoint: Touchpoint) -> dict:
        """Serialize touchpoint for Segment"""
        return {
            'touchpoint_id': str(touchpoint.touchpoint_id),
            'event_name': touchpoint.event_name,
            'timestamp': touchpoint.event_timestamp.isoformat(),
            'campaign_id': touchpoint.campaign_id,
            'utm_source': touchpoint.utm_source,
            'utm_medium': touchpoint.utm_medium,
            'utm_campaign': touchpoint.utm_campaign,
            'url': touchpoint.url,
            'cost': float(touchpoint.estimated_cost or 0)
        }
```

#### Event Flow with Kafka Buffer
```python
class AttributionEventProcessor:
    """
    Process conversion events from Kafka, run attribution, emit back to Segment.
    Uses Kafka for reliability and retry logic.
    """
    
    def process_conversion_events(self):
        """
        Consume conversion events from Kafka, attribute, and emit to Segment.
        """
        consumer = KafkaConsumer('conversions.raw')
        
        for message in consumer:
            try:
                segment_event = json.loads(message.value)
                
                # Create conversion record
                conversion = self.create_conversion(segment_event)
                
                # Run attribution
                model = LastTouchAttributionModel()
                attribution = model.attribute_conversion(conversion)
                
                # Update conversion with attribution
                self.update_conversion_with_attribution(conversion, attribution)
                
                # Emit enriched event back to Segment
                enricher = AttributionEnricher(segment_client)
                enricher.emit_attributed_conversion(conversion, attribution)
                
                # Commit Kafka offset (processed successfully)
                consumer.commit()
                
            except Exception as e:
                logger.error(f"Failed to process conversion: {e}")
                # Don't commit offset - will retry
```

### Data Consistency & Idempotency

#### Deduplication
```python
class EventDeduplicator:
    """Ensure events are processed only once"""
    
    def is_duplicate(self, event_id: str) -> bool:
        """Check if event already processed"""
        return db.query(Touchpoint).filter(
            Touchpoint.event_id == event_id
        ).first() is not None
    
    def mark_processed(self, event_id: str):
        """Mark event as processed (happens on DB insert)"""
        # event_id is unique constraint in database
        pass
```

### Monitoring & Observability

```python
class IntegrationMonitoring:
    """Monitor Segment integration health"""
    
    def track_metrics(self):
        """Track integration metrics"""
        
        metrics = {
            # Inbound
            'events_received_per_hour': self.count_events_received(),
            'webhook_failures': self.count_webhook_errors(),
            'invalid_events': self.count_validation_failures(),
            
            # Outbound
            'events_sent_to_segment': self.count_events_sent(),
            'segment_api_errors': self.count_segment_errors(),
            'segment_api_latency_ms': self.measure_segment_latency(),
            
            # End-to-end
            'event_processing_lag_seconds': self.measure_processing_lag(),
            'attributed_conversions_sent': self.count_attributed_conversions()
        }
        
        return metrics
```

## Consequences

### Positive
- **Closed-loop integration**: Data flows both ways for complete view
- **Segment as source of truth**: No duplicate identity graphs
- **Enriched profiles**: Segment profiles include cost and attribution data
- **Unified analytics**: All customer data in one place (Segment)
- **Kafka buffering**: Reliability and retry capability
- **Idempotent processing**: Safe to replay events

### Negative
- **Dual integration complexity**: Maintain both inbound and outbound
- **Event schema dependencies**: Changes to Segment schema require updates
- **Latency added**: Round-trip adds processing time
- **API costs**: Segment charges per API call for outbound events
- **Eventual consistency**: Small delay in data appearing in Segment

### Risks & Mitigations

- **Risk**: Segment webhook delivery failures
  - *Mitigation*: Segment has automatic retry; idempotent processing
  
- **Risk**: Segment API rate limits on outbound
  - *Mitigation*: Batch API; rate limiting; exponential backoff
  
- **Risk**: Schema drift between systems
  - *Mitigation*: Version event schemas; automated testing
  
- **Risk**: Circular event loops
  - *Mitigation*: Add source context; don't process our own outbound events

## Alternatives Considered

### Alternative 1: Segment Functions (Cloud-side processing)
Run attribution logic inside Segment Functions.

**Rejected because**:
- Limited compute resources in Segment
- Can't access our PostgreSQL database
- No control over cost calculation logic
- Less flexible for complex attribution

### Alternative 2: Unidirectional (Outbound Only)
Store all data locally, don't send back to Segment.

**Rejected because**:
- Doesn't enrich Segment profiles
- Creates data silos
- Violates "CDP-first" principle

### Alternative 3: Real-time Segment API Queries
Query Segment API for identity resolution on each event.

**Rejected because**:
- Too high latency
- API rate limits
- Segment already provides resolved IDs in events

### Alternative 4: CSV Exports to Segment
Batch export attributed conversions as CSV uploads.

**Rejected because**:
- Not real-time
- Manual process
- No event-level granularity

## Implementation Notes

### Phase 1 (MVP)
- Webhook receiver for inbound events
- HTTP Tracking API for outbound events
- Single "Conversion Attributed" event type
- Manual monitoring of integration health

### Phase 2 (Production)
- Batch API for outbound (reduce API calls)
- Multiple attributed event types
- Automated integration testing
- Real-time monitoring dashboard
- Alert on integration failures

### Configuration
```yaml
# config/segment.yaml
segment:
  inbound:
    webhook_secret: ${SEGMENT_WEBHOOK_SECRET}
    endpoint: /webhooks/segment
  
  outbound:
    write_key: ${SEGMENT_WRITE_KEY}
    source_id: attribution_system
    batch_size: 100
    batch_interval_seconds: 60
```

### Testing Strategy
```python
def test_inbound_webhook():
    # Mock Segment webhook event
    # POST to webhook endpoint
    # Verify event published to Kafka
    
def test_outbound_tracking():
    # Create attributed conversion
    # Call emit_attributed_conversion
    # Verify Segment API called with correct payload

def test_idempotency():
    # Send same event twice
    # Verify only processed once
```

## References
- [Segment Webhooks](https://segment.com/docs/connections/destinations/catalog/webhooks/)
- [Segment HTTP Tracking API](https://segment.com/docs/connections/sources/catalog/libraries/server/http-api/)
- [Segment Event Spec](https://segment.com/docs/connections/spec/)

## Related ADRs
- ADR-001: Event Ingestion Architecture
- ADR-002: Identity Resolution Strategy
- ADR-006: Attribution Model Implementation
