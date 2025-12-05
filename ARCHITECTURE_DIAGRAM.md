# Attribution System - Architecture Diagram

## High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SEGMENT CDP                                     │
│                        (Identity Resolution)                                 │
│                                                                              │
│  User Events: page views, clicks, conversions                               │
│  Identity: anonymousId → userId stitching                                   │
└────────────┬───────────────────────────────────────────────┬────────────────┘
             │                                                │
             │ Webhook (Inbound)                             │ HTTP API (Outbound)
             │ Touchpoints & Conversions                      │ Attributed Conversions
             ▼                                                ▲
┌────────────────────────────────────────────────────────────┴────────────────┐
│                      ATTRIBUTION SYSTEM                                      │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        Webhook API Gateway                            │  │
│  │  - Receive events from Segment                                        │  │
│  │  - Validate signatures                                               │  │
│  │  - Publish to Kafka                                                  │  │
│  └────────────────────────────┬─────────────────────────────────────────┘  │
│                                │                                             │
│                                ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        APACHE KAFKA                                   │  │
│  │                                                                       │  │
│  │  Topics:                                                              │  │
│  │  • touchpoints.raw          - Raw touchpoint events                   │  │
│  │  • conversions.raw          - Raw conversion events                   │  │
│  │  • identity.raw             - Identity stitch events                  │  │
│  │  • segment.outbound         - Events to send back                     │  │
│  └────┬──────────────┬───────────────────┬──────────────────────────────┘  │
│       │              │                   │                                  │
│       ▼              ▼                   ▼                                  │
│  ┌─────────┐   ┌──────────┐   ┌────────────────┐                          │
│  │Touchpoint│   │Conversion│   │Identity Stitch │                          │
│  │Processor │   │Processor │   │Processor       │                          │
│  └────┬────┘   └────┬─────┘   └────────┬───────┘                          │
│       │             │                   │                                  │
│       └─────────────┴───────────────────┘                                  │
│                     │                                                       │
│                     ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      PostgreSQL Database                              │  │
│  │                                                                       │  │
│  │  Tables:                                                              │  │
│  │  • touchpoints          - Marketing touchpoints with costs            │  │
│  │  • conversions          - Conversion events with attribution          │  │
│  │  • campaign_costs       - Daily ad platform costs                     │  │
│  │  • identity_stitches    - Audit log of identity resolution            │  │
│  │                                                                       │  │
│  │  Retention: 90 days (hot data)                                        │  │
│  └──────────────────────────────┬───────────────────────────────────────┘  │
│                                  │                                          │
│                                  │ Daily Export                             │
│                                  ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                       Redshift Data Warehouse                         │  │
│  │                                                                       │  │
│  │  - Same schema as PostgreSQL                                          │  │
│  │  - All historical data                                                │  │
│  │  - Optimized for analytical queries                                   │  │
│  │  - Cohort analysis, long-term trends                                  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      Cost Calculation Engine                          │  │
│  │                                                                       │  │
│  │  Daily Batch Job (3 AM):                                              │  │
│  │  1. Read campaign_costs for yesterday                                 │  │
│  │  2. Match to touchpoints (4-tier strategy)                            │  │
│  │  3. Calculate estimated_cost per touchpoint                           │  │
│  │  4. Update conversions with attributed costs                          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     Attribution Engine                                │  │
│  │                                                                       │  │
│  │  Real-time on Conversion Events:                                      │  │
│  │  1. Receive conversion event                                          │  │
│  │  2. Query user's touchpoint journey                                   │  │
│  │  3. Find last marketing touchpoint                                    │  │
│  │  4. Attribute conversion (cost, campaign)                             │  │
│  │  5. Emit enriched event to segment.outbound topic                     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ Fetch Campaign Costs
                                  │ Daily Batch (2 AM)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AD PLATFORMS                                        │
│                                                                              │
│  ┌────────────────┐   ┌────────────────┐   ┌────────────────┐             │
│  │  Google Ads    │   │   Meta Ads     │   │   TikTok Ads   │             │
│  │                │   │   (Future)     │   │   (Future)     │             │
│  │  Campaign IDs  │   │                │   │                │             │
│  │  Daily Spend   │   │                │   │                │             │
│  │  Clicks        │   │                │   │                │             │
│  │  Impressions   │   │                │   │                │             │
│  └────────────────┘   └────────────────┘   └────────────────┘             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow: User Journey Example

```
1. USER JOURNEY STARTS
   └─> User clicks Google Ad
       - UTM params: utm_source=google, utm_campaign=summer_sale, campaign_id=12345
   
2. TOUCHPOINT CREATED (Anonymous)
   Segment (anonymousId: anon_123)
     └─> Webhook → Kafka → PostgreSQL
         touchpoints table:
           - segment_anonymous_id: anon_123
           - utm_campaign: summer_sale
           - campaign_id: 12345
           - estimated_cost: NULL (calculated later)

3. USER CREATES ACCOUNT
   Segment (userId: user_456, anonymousId: anon_123)
     └─> Identify Event
         - Stitches anon_123 → user_456
         - Updates touchpoints.resolved_user_id = user_456
   
   Segment (Track: "Account Created")
     └─> Conversion Event → Attribution
         conversions table:
           - resolved_user_id: user_456
           - conversion_type: account_created
           - attributed_touchpoint_id: [last touch]
           - attributed_campaign: summer_sale
           - attributed_cost: $2.50

4. NIGHTLY COST CALCULATION
   Google Ads API (2 AM)
     └─> Fetch campaign 12345 costs for yesterday
         campaign_costs table:
           - campaign_id: 12345
           - total_spend: $500
           - total_clicks: 200
           - calculated_cpc: $2.50
   
   Cost Calculator (3 AM)
     └─> Match touchpoints to campaigns
         - Update touchpoints.estimated_cost = $2.50
         - Update conversions.attributed_cost = $2.50

5. USER STARTS TRIAL (Day 2)
   Segment (Track: "Trial Started", userId: user_456)
     └─> Conversion Event → Attribution
         - Finds last touch: summer_sale ad
         - Creates conversion record
         - Attributes to same campaign
   
   Attribution Enricher
     └─> Emit to Segment
         Event: "Conversion Attributed"
         Properties:
           - conversion_type: trial_started
           - attributed_cost: $2.50
           - attributed_campaign: summer_sale
           - roi: N/A (no revenue yet)

6. USER PURCHASES (Day 14)
   Segment (Track: "Subscription Purchased", userId: user_456)
     └─> Conversion Event → Attribution
         - Finds last touch: summer_sale ad
         - Creates conversion record
         - Attributed value: $30 (LTV)
   
   Attribution Enricher
     └─> Emit to Segment
         Event: "Conversion Attributed"
         Properties:
           - conversion_type: subscription_purchased
           - conversion_value: $30
           - attributed_cost: $2.50
           - attributed_campaign: summer_sale
           - roi: 1100% ((30-2.5)/2.5 * 100)
   
7. SEGMENT PROFILE ENRICHED
   User Profile (user_456) now has:
     - All original touchpoint events
     - All conversion events
     - "Conversion Attributed" events with cost/ROI data
     - Complete marketing attribution story
```

## Component Details

### 1. Webhook API Gateway
**Technology**: FastAPI (Python)
**Port**: 3000
**Endpoints**:
- `POST /webhooks/segment` - Receive Segment events

**Responsibilities**:
- Validate Segment signatures
- Basic event schema validation
- Route to appropriate Kafka topic
- Return 200 OK immediately (async processing)

### 2. Kafka Topics & Consumers

| Topic | Purpose | Consumer | Output |
|-------|---------|----------|--------|
| `touchpoints.raw` | Raw touchpoint events | Touchpoint Processor | PostgreSQL touchpoints |
| `conversions.raw` | Raw conversion events | Conversion Processor | PostgreSQL conversions + Attribution trigger |
| `identity.raw` | Identity stitch events | Identity Processor | Update resolved_user_id |
| `segment.outbound` | Attributed conversions | Segment Emitter | Segment HTTP API |

### 3. PostgreSQL Tables

#### touchpoints (8M rows/year @ 200k events/day)
```sql
Key Indexes:
- idx_touchpoints_resolved_user_timestamp (attribution lookup)
- idx_touchpoints_campaign_date (cost matching)
- idx_touchpoints_cost_calculated (find uncalculated costs)
```

#### conversions (2M rows/year @ 50k conversions/day)
```sql
Key Indexes:
- idx_conversions_user_timestamp (funnel analysis)
- idx_conversions_attributed_touchpoint (join back to touchpoints)
```

#### campaign_costs (5K rows/year @ 15 campaigns/day)
```sql
Key Indexes:
- idx_campaign_costs_campaign_date (touchpoint matching)
- unique(ad_platform, campaign_id, cost_date) (idempotency)
```

### 4. Cost Calculation Pipeline
**Schedule**: Daily at 3 AM (after ad platform fetch at 2 AM)
**Processing Time**: ~5 minutes for 200k touchpoints

**Algorithm**:
1. Tier 1: Direct campaign_id match → campaign CPC
2. Tier 2: Fuzzy UTM campaign match → matched campaign CPC
3. Tier 3: Platform median CPC (30-day window)
4. Tier 4: Default platform estimate

**Success Metrics**:
- Target: 80%+ Tier 1+2 matches
- Acceptable: 15% Tier 3
- Minimize: <5% Tier 4

### 5. Attribution Engine
**Mode**: Real-time (triggered on conversion events)
**Algorithm**: Last-touch (MVP)
**Latency**: <100ms typical

**Process**:
1. Query touchpoints for user (before conversion timestamp)
2. Filter to marketing touchpoints only
3. Sort by timestamp DESC
4. Take first result = attributed touchpoint
5. Copy cost and campaign details to conversion
6. Emit enriched event to Segment

### 6. Ad Platform Adapters
**Current**: Google Ads API
**Future**: Meta, TikTok, LinkedIn

**Interface**:
```python
class AdPlatformAdapter:
    def fetch_campaign_costs(date_range) -> List[CampaignCost]
    def get_campaign_metadata(campaign_ids) -> List[Metadata]
```

## Deployment Architecture

### Phase 1: Local Development
```
Developer Machine:
├── Docker Compose
│   ├── Kafka + Zookeeper
│   ├── PostgreSQL
│   └── PgAdmin
├── Python Services (local processes)
│   ├── webhook-api (uvicorn)
│   ├── event-processor (python script)
│   └── cost-fetcher (cron job)
└── Segment
    ├── Webhook → localhost:3000 (ngrok tunnel)
    └── Custom Source (write key)
```

### Phase 2: Production (Future)
```
AWS/GCP Cloud:
├── Load Balancer → Webhook API (multiple instances)
├── Managed Kafka (Confluent Cloud / MSK)
├── RDS PostgreSQL (Multi-AZ)
├── Redshift Cluster
├── Lambda / Cloud Run
│   ├── Cost Fetcher (scheduled)
│   ├── Cost Calculator (scheduled)
│   └── Segment Emitter
└── Monitoring
    ├── CloudWatch / Stackdriver
    ├── Prometheus + Grafana
    └── PagerDuty alerts
```

## Data Retention Policies

| Storage | Retention | Purpose |
|---------|-----------|---------|
| Kafka | 30 days | Event replay, debugging |
| PostgreSQL | 90 days | Operational queries, real-time attribution |
| Redshift | Unlimited | Historical analysis, long-term trends |
| Segment | Unlimited | CDP source of truth |

## Key Metrics to Monitor

### Operational
- Events received per minute
- Kafka consumer lag
- Attribution latency (conversion → enriched event)
- PostgreSQL query performance
- Disk usage (partition management)

### Data Quality
- Touchpoints with costs (target: 80%+)
- Conversions with attribution (target: 90%+)
- Identity stitch rate
- Campaign match rate (Tier 1+2 vs Tier 3+4)

### Business
- Cost per Account Created
- Cost per Trial Started
- Cost per Purchase
- Trial→Purchase conversion rate
- ROI by campaign
- Funnel drop-off rates

## Security Considerations

1. **Segment Webhook Signature**: Always verify to prevent spoofed events
2. **Google Ads Credentials**: Store OAuth refresh token securely (env vars / secrets manager)
3. **Database Access**: Restrict to application user only
4. **Segment Write Key**: Protect as sensitive credential
5. **API Rate Limits**: Implement rate limiting on webhook endpoint
6. **Data Privacy**: PII handling in compliance with GDPR/CCPA

## Scaling Considerations

| Volume | Changes Needed |
|--------|---------------|
| 500k events/day | Increase Kafka partitions, add PostgreSQL read replicas |
| 1M events/day | Kafka cluster (3+ brokers), PostgreSQL connection pooling |
| 5M events/day | Horizontal scaling of consumers, consider TimescaleDB |
| 10M+ events/day | Distributed processing (Flink/Spark), sharded PostgreSQL |

---

**Note**: This architecture prioritizes simplicity for MVP while maintaining extensibility for future enhancements. Start simple, scale as needed.
