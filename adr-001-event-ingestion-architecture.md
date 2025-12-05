# ADR-001: Event Ingestion Architecture

## Status
Proposed

## Context
We need to ingest marketing touchpoint events from multiple sources (web analytics, AppsFlyer, mobile BFF, web BFF, subscription service) in real-time. All events flow through Segment CDP as JSON payloads via a webhook destination. Expected volume is 200k+ events per day with potential for growth.

### Requirements
- Handle real-time event ingestion from Segment webhook
- Support ~200k events/day (2-3 events/second average, with peaks)
- Process both anonymous and authenticated user touchpoints
- Maintain event ordering per user where possible
- Support future scale to higher volumes
- Local development initially, with corporate tech stack alignment (Kafka, PostgreSQL, Redshift)

### Constraints
- Must integrate with existing Segment infrastructure
- Need to support bidirectional communication with Segment
- Cannot duplicate identity resolution (Segment is source of truth)
- Initial deployment is local/dev environment

## Decision
We will implement a **Kafka-based streaming ingestion architecture** with the following components:

```
Segment Webhook → API Gateway → Kafka Topics → Stream Processors → Storage
```

### Architecture Components

1. **Webhook API Gateway**
   - Lightweight HTTP service (Node.js/Express or Python/FastAPI)
   - Receives POST requests from Segment webhook destination
   - Validates webhook signatures/authentication
   - Basic schema validation
   - Publishes raw events to Kafka topic: `touchpoints.raw`
   - Returns 200 OK immediately (async processing)

2. **Kafka Topics Structure**
   ```
   touchpoints.raw          - Raw events from Segment
   touchpoints.validated    - Schema-validated and enriched events
   conversions.raw          - Raw conversion events
   conversions.attributed   - Conversion events with attribution data
   segment.outbound         - Events to send back to Segment
   ```

3. **Stream Processing Pipeline**
   - Kafka Streams or Python consumer for event processing
   - Validates event schema against known patterns
   - Enriches with metadata (ingestion timestamp, source system)
   - Partitions by `segment_anonymous_id` or `segment_user_id` for ordering
   - Dead letter queue (DLQ) topic for malformed events

4. **Storage Writers**
   - Separate consumers write to PostgreSQL (operational queries)
   - Separate consumers write to Redshift (analytical queries)
   - Dual-write pattern acceptable for MVP (eventual consistency)

### Event Schema Standardization
All touchpoint events will be normalized to:
```json
{
  "event_id": "uuid",
  "segment_anonymous_id": "string",
  "segment_user_id": "string|null",
  "event_type": "page|track|identify",
  "event_name": "string",
  "timestamp": "iso8601",
  "properties": {
    "utm_source": "string",
    "utm_medium": "string", 
    "utm_campaign": "string",
    "utm_content": "string",
    "utm_term": "string",
    "campaign_id": "string",
    "referrer": "string",
    "url": "string"
  },
  "context": {
    "source": "web|mobile|backend",
    "platform": "web|ios|android"
  },
  "ingested_at": "iso8601"
}
```

## Consequences

### Positive
- **Decoupled architecture**: Webhook receiver independent from processing logic
- **Scalability**: Kafka provides horizontal scaling for increased load
- **Reliability**: Event replay capability for debugging and reprocessing
- **Flexibility**: Multiple consumers can process same events for different purposes
- **Corporate alignment**: Uses Kafka (corporate standard)
- **Real-time capable**: Low latency from ingestion to processing

### Negative
- **Complexity**: More components to manage vs direct database writes
- **Operational overhead**: Kafka cluster management (even local dev)
- **Dual writes**: PostgreSQL and Redshift creates consistency challenges
- **Cost**: Kafka infrastructure costs when moving to cloud

### Risks & Mitigations
- **Risk**: Kafka learning curve for team
  - *Mitigation*: Use managed Kafka (Confluent Cloud/MSK) when moving to cloud
  
- **Risk**: Event ordering issues during identity resolution
  - *Mitigation*: Partition by Segment IDs; accept eventual consistency
  
- **Risk**: Webhook delivery failures from Segment
  - *Mitigation*: Implement idempotency using `event_id`; Segment has retry logic

## Alternatives Considered

### Alternative 1: Direct Database Write
Webhook → API → PostgreSQL → CDC to Redshift

**Rejected because**:
- Doesn't align with corporate streaming standards
- Harder to scale for real-time processing
- Couples ingestion with storage
- Less flexible for future streaming use cases

### Alternative 2: Serverless (Lambda/Cloud Functions)
Webhook → Lambda → Kinesis → Storage

**Rejected because**:
- Not applicable for local dev environment
- Would diverge from corporate Kafka standard
- More vendor lock-in

### Alternative 3: Direct Segment API Integration
Poll Segment API instead of webhook

**Rejected because**:
- Not real-time (polling delay)
- More complex to implement
- API rate limits
- Webhook is already configured

## Implementation Notes

### Phase 1 (MVP - Local Dev)
- Single Kafka broker (Docker Compose)
- Python consumers (simpler for prototyping)
- PostgreSQL for operational storage
- Manual Redshift exports initially

### Phase 2 (Production)
- Multi-broker Kafka cluster or managed service
- Kafka Streams for stateful processing
- Automated Redshift sync (Kafka Connect)
- Monitoring and alerting (Prometheus/Grafana)

### Local Development Setup
```yaml
# docker-compose.yml excerpt
services:
  kafka:
    image: confluentinc/cp-kafka:latest
  
  postgres:
    image: postgres:15
  
  webhook-api:
    build: ./services/webhook-api
    ports:
      - "3000:3000"
  
  event-processor:
    build: ./services/event-processor
```

## References
- [Segment Webhooks Documentation](https://segment.com/docs/connections/destinations/catalog/webhooks/)
- [Kafka Streams Documentation](https://kafka.apache.org/documentation/streams/)
- [Event Sourcing Pattern](https://martinfowler.com/eaaDev/EventSourcing.html)

## Related ADRs
- ADR-002: Identity Resolution Strategy
- ADR-003: Data Storage Design
- ADR-007: Segment Bidirectional Integration
