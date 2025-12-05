# Attribution System - Implementation Roadmap

## Overview
This document provides a practical implementation guide for building the attribution system based on the ADRs. It breaks down the work into phases with clear milestones and dependencies.

## System Summary

### Key Components
1. **Event Ingestion** - Kafka-based streaming from Segment webhook
2. **Identity Resolution** - Leverage Segment CDP, track stitching events
3. **Storage** - PostgreSQL (operational) + Redshift (analytical)
4. **Cost Ingestion** - Daily batch from Google Ads API
5. **Cost Calculation** - Multi-tier estimation engine
6. **Attribution** - Last-touch model with funnel awareness
7. **Segment Integration** - Bidirectional flow of enriched data
8. **Funnel Analytics** - Multi-stage conversion tracking

### Tech Stack
- **Streaming**: Kafka (local: Docker Compose)
- **Database**: PostgreSQL 15
- **Data Warehouse**: Redshift (manual sync initially)
- **Language**: Python 3.11+ (FastAPI, Kafka-Python)
- **CDP**: Segment
- **Ad Platform**: Google Ads API

## Phase 1: MVP Foundation (4-6 weeks)

### Week 1-2: Core Infrastructure
**Goal**: Set up local development environment and data pipeline basics

#### Tasks
- [ ] Set up Docker Compose environment
  - Kafka + Zookeeper
  - PostgreSQL
  - PgAdmin
- [ ] Create database schema (ADR-003)
  - `touchpoints` table
  - `conversions` table
  - `campaign_costs` table
  - `identity_stitches` table
- [ ] Build webhook API service (ADR-001, ADR-007)
  - FastAPI application
  - Segment signature verification
  - Basic event validation
  - Publish to Kafka topics
- [ ] Create Kafka topics
  - `touchpoints.raw`
  - `conversions.raw`
  - `identity.raw`

**Deliverable**: Ability to receive events from Segment and store in Kafka

#### Testing
```bash
# Send test Segment event
curl -X POST http://localhost:3000/webhooks/segment \
  -H "Content-Type: application/json" \
  -H "X-Signature: test_signature" \
  -d @test_event.json

# Verify in Kafka
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic touchpoints.raw --from-beginning
```

### Week 3-4: Event Processing & Storage
**Goal**: Process events and store in PostgreSQL

#### Tasks
- [ ] Build Kafka consumers (ADR-001)
  - Touchpoint processor
  - Conversion processor
  - Identity stitch processor
- [ ] Implement Segment event mapping (ADR-007)
  - Map Segment schema to internal models
  - Extract UTM parameters
  - Handle various event types
- [ ] Write to PostgreSQL
  - Insert touchpoints with deduplication
  - Insert conversions
  - Handle identity resolution
- [ ] Basic identity stitching (ADR-002)
  - Process `identify` events
  - Update `resolved_user_id` on touchpoints

**Deliverable**: Events flow from Segment → Kafka → PostgreSQL

#### Testing
```python
# Verify touchpoint creation
def test_touchpoint_created():
    send_segment_event(type='page', anonymousId='anon_123')
    touchpoint = db.query(Touchpoint).filter_by(
        segment_anonymous_id='anon_123'
    ).first()
    assert touchpoint is not None
```

### Week 5: Google Ads Integration
**Goal**: Fetch campaign cost data from Google Ads

#### Tasks
- [ ] Set up Google Ads API access (ADR-004)
  - OAuth2 configuration
  - Test API connection
- [ ] Build Google Ads adapter
  - Fetch campaign performance (spend, clicks, impressions)
  - Transform to internal schema
- [ ] Store in `campaign_costs` table
- [ ] Calculate basic metrics (CPC, CTR, CPM)
- [ ] Create manual fetch script
  ```bash
  python scripts/fetch_costs.py --date yesterday
  ```

**Deliverable**: Daily campaign cost data in database

### Week 6: Cost Calculation
**Goal**: Calculate estimated cost per touchpoint

#### Tasks
- [ ] Implement cost calculation engine (ADR-005)
  - Tier 1: Direct campaign match
  - Tier 2: Fuzzy campaign match
  - Tier 3: Platform median
  - Tier 4: Default estimates
- [ ] Build batch cost calculator
  - Process yesterday's touchpoints
  - Update `estimated_cost` field
- [ ] Set up daily cron job
  ```bash
  0 3 * * * cd /project && python scripts/calculate_costs.py --date yesterday
  ```

**Deliverable**: Touchpoints have estimated costs

## Phase 2: Attribution & Segment Integration (3-4 weeks)

### Week 7-8: Attribution Engine
**Goal**: Implement last-touch attribution

#### Tasks
- [ ] Build attribution model (ADR-006)
  - Last-touch attribution algorithm
  - Marketing touchpoint filtering
  - Time-to-conversion calculation
- [ ] Attribution trigger on conversions
  - Listen for conversion events
  - Find last marketing touchpoint
  - Update conversion with attribution
- [ ] Funnel progression tracking (ADR-008)
  - Link conversions via `previous_conversion_id`
  - Track stage-specific attribution

**Deliverable**: Conversions are attributed to touchpoints with costs

#### Testing
```python
def test_last_touch_attribution():
    user_id = 'user_123'
    # Create touchpoints
    create_touchpoint(user_id, timestamp='2024-12-01 10:00', campaign='A')
    create_touchpoint(user_id, timestamp='2024-12-01 14:00', campaign='B')
    
    # Create conversion
    conversion = create_conversion(user_id, timestamp='2024-12-01 15:00')
    
    # Run attribution
    model.attribute_conversion(conversion)
    
    # Assert
    assert conversion.attributed_utm_campaign == 'B'
```

### Week 9-10: Segment Outbound Integration
**Goal**: Send attributed conversions back to Segment

#### Tasks
- [ ] Build Segment HTTP client (ADR-007)
  - Track API implementation
  - Authentication with write key
- [ ] Create attribution enricher
  - Format attributed conversion event
  - Include cost, campaign, ROI
- [ ] Trigger on conversion attribution
  - Emit "Conversion Attributed" event
  - Include touchpoint details
- [ ] Test in Segment debugger

**Deliverable**: Attributed conversions appear in Segment

## Phase 3: Analytics & Optimization (2-3 weeks)

### Week 11-12: Reporting & Dashboards
**Goal**: Enable data analysis and reporting

#### Tasks
- [ ] Create analytical views (ADR-008)
  - `funnel_overview` view
  - Cost per stage queries
  - Campaign performance queries
- [ ] Build basic reports
  - Daily attribution report
  - Campaign ROI report
  - Funnel conversion rates
- [ ] Monitoring dashboard
  - Event processing lag
  - Attribution coverage rate
  - Cost calculation coverage
  - Segment integration health

**Deliverable**: Daily reports on attribution performance

### Week 13: Redshift Sync
**Goal**: Enable historical analytics

#### Tasks
- [ ] Manual Redshift sync process (ADR-003)
  - Export PostgreSQL tables daily
  - Load into Redshift
  - Verify data integrity
- [ ] Create Redshift analytical queries
  - Cohort analysis
  - Long-term trends
  - Advanced funnel metrics

**Deliverable**: Historical data in Redshift for analysis

## Phase 4: Productionization (2-3 weeks)

### Week 14-15: Reliability & Monitoring
**Goal**: Make system production-ready

#### Tasks
- [ ] Error handling & retries
  - Webhook failures
  - Kafka consumer retries
  - Segment API retries
- [ ] Logging & monitoring
  - Structured logging
  - Metrics collection
  - Alerting setup
- [ ] Data quality checks
  - Validation rules
  - Anomaly detection
  - Cost calculation quality metrics
- [ ] Documentation
  - Runbooks
  - Troubleshooting guides
  - API documentation

**Deliverable**: Reliable, monitored production system

### Week 16: Performance Optimization
**Goal**: Ensure system performs at scale

#### Tasks
- [ ] Database optimization
  - Index tuning
  - Query optimization
  - Partition management
- [ ] Kafka optimization
  - Consumer group tuning
  - Partition strategy
- [ ] Cost calculation optimization
  - Batch processing
  - Cache platform medians
- [ ] Load testing
  - Simulate 500k events/day
  - Measure end-to-end latency

**Deliverable**: System handles target load with acceptable latency

## Phase 5: Future Enhancements (Post-MVP)

### Potential Additions
- [ ] Multi-touch attribution models (linear, time-decay)
- [ ] Additional ad platforms (Meta, TikTok, LinkedIn)
- [ ] Real-time Redshift sync (Kafka Connect)
- [ ] Journey visualization UI
- [ ] Predictive conversion modeling
- [ ] Automated budget optimization
- [ ] Cross-device attribution
- [ ] Attribution model comparison
- [ ] Custom attribution windows
- [ ] Advanced fraud detection

## Key Milestones

| Milestone | Week | Description |
|-----------|------|-------------|
| **M1: Event Pipeline** | 2 | Events flow from Segment to database |
| **M2: Cost Data** | 5 | Campaign costs fetched and stored |
| **M3: Cost Attribution** | 6 | Touchpoints have estimated costs |
| **M4: Attribution** | 8 | Conversions attributed to touchpoints |
| **M5: Segment Loop** | 10 | Attributed conversions sent to Segment |
| **M6: Analytics** | 12 | Reports and dashboards functional |
| **M7: Production Ready** | 15 | System is reliable and monitored |

## Success Metrics

### MVP Success Criteria
- [ ] 95%+ events successfully ingested from Segment
- [ ] 80%+ touchpoints have cost estimates
- [ ] 90%+ conversions have attribution
- [ ] < 5 minute lag from conversion to Segment enrichment
- [ ] 99%+ uptime for webhook endpoint
- [ ] < 100ms p95 response time for webhook

### Business Metrics
- Cost per Account Created
- Cost per Trial Started  
- Cost per Subscription Purchase
- Trial-to-Paid conversion rate by source
- ROI by campaign
- Attribution coverage rate

## Development Environment Setup

### Prerequisites
```bash
# Install Docker & Docker Compose
# Install Python 3.11+
# Install PostgreSQL client tools
```

### Quick Start
```bash
# Clone repository
git clone <repo_url>
cd attribution-system

# Start infrastructure
docker-compose up -d

# Install Python dependencies
pip install -r requirements.txt

# Initialize database
python scripts/init_db.py

# Start services
python services/webhook-api/main.py &
python services/event-processor/main.py &

# Set up Segment webhook
# Point to: http://localhost:3000/webhooks/segment
```

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Segment webhook failures | High | Implement retry logic, idempotency |
| Google Ads API quota | Medium | Monitor usage, request increase |
| Database performance | High | Partitioning, indexes, monitoring |
| Identity resolution delays | Medium | Accept eventual consistency |
| Cost estimation gaps | Medium | Multiple fallback tiers |
| Kafka cluster failure | High | Start simple, plan for managed service |

## Dependencies

### External Services
- Segment CDP (webhooks + HTTP API)
- Google Ads API
- (Future) Redshift cluster

### Internal Dependencies
- Docker/Docker Compose
- Kafka
- PostgreSQL
- Python 3.11+

### Python Packages
```
fastapi
uvicorn
kafka-python
psycopg2-binary
sqlalchemy
pydantic
google-ads
requests
python-dateutil
```

## Questions to Answer During Implementation

1. **Segment webhook authentication**: What signature method is Segment using?
2. **Google Ads credentials**: OAuth2 flow - how to handle refresh tokens?
3. **Identity resolution timing**: How long does Segment take to stitch identities?
4. **Cost data lag**: Is Google Ads data available next day, or 2+ days?
5. **Conversion event names**: Exact event names from Segment for each conversion type?
6. **Campaign ID format**: How are campaign IDs passed in UTM parameters?
7. **Redshift access**: Do we have existing Redshift cluster, or need to provision?

## Recommended Team Structure

### Phase 1-2 (MVP)
- 1 Backend Engineer (lead)
- 1 Data Engineer
- 1 Product Manager (part-time)

### Phase 3-4 (Production)
- Add: 1 DevOps/SRE
- Add: 1 Analytics Engineer

## Next Steps

1. **Review ADRs** with team
2. **Set up development environment**
3. **Configure Segment webhook** (test event generation)
4. **Obtain Google Ads API credentials**
5. **Start Week 1 tasks**
6. **Set up weekly sync meetings**

---

**Document Version**: 1.0  
**Last Updated**: December 5, 2024  
**Status**: Ready for implementation
