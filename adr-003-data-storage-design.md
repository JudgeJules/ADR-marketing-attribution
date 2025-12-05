# ADR-003: Data Storage Design

## Status
Proposed

## Context
The attribution system requires different storage patterns for different use cases:
- **Operational queries**: Real-time attribution lookups for conversion events
- **Analytical queries**: Historical analysis, cost reporting, campaign performance
- **Cost data**: Daily aggregated costs from ad platforms
- **Event replay**: Ability to reprocess events for debugging/algorithm changes

Volume: 200k+ events/day (~6M events/month) with potential for growth.

### Requirements
- Fast reads for last-touch attribution lookups (< 100ms)
- Write-heavy for real-time touchpoint ingestion
- Support complex analytical queries (funnel analysis, cohort analysis)
- Store campaign cost data with daily granularity
- Enable historical data analysis (at least 90 days)
- Support both PostgreSQL and Redshift (corporate standards)

### Constraints
- Initial deployment is local (single PostgreSQL, manual Redshift sync)
- Must align with corporate tech stack (PostgreSQL, Redshift, Kafka)
- Budget for cloud storage costs when scaling

## Decision
We will implement a **hybrid storage architecture** with:

1. **PostgreSQL** - Operational data store (hot data, last 90 days)
2. **Redshift** - Analytical data warehouse (all historical data)
3. **Kafka** - Event log and source of truth (retention: 30 days)

Data flows from Kafka → PostgreSQL (real-time) → Redshift (batch sync).

### Storage Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Kafka Topics                          │
│  (Source of Truth, 30-day retention, replay capability)     │
└────────┬────────────────────────────────────────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐  ┌──────────┐
│ Postgres│  │ Redshift │
│  (Hot)  │  │  (Cold)  │
│ 90 days │  │ Forever  │
└─────────┘  └──────────┘
```

### PostgreSQL Schema Design

#### 1. Touchpoints (Operational)
```sql
CREATE TABLE touchpoints (
    touchpoint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id VARCHAR(255) UNIQUE NOT NULL,
    
    -- Identity
    segment_anonymous_id VARCHAR(255),
    segment_user_id VARCHAR(255),
    resolved_user_id VARCHAR(255) NOT NULL, -- Denormalized for query perf
    
    -- Event metadata
    event_type VARCHAR(50) NOT NULL,
    event_name VARCHAR(255) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    
    -- Campaign attribution fields
    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),
    utm_content VARCHAR(255),
    utm_term VARCHAR(255),
    campaign_id VARCHAR(255),
    ad_platform VARCHAR(50), -- 'google_ads', 'meta', etc.
    
    -- Context
    referrer TEXT,
    url TEXT,
    source_platform VARCHAR(50), -- 'web', 'mobile_ios', 'mobile_android'
    page_title VARCHAR(500),
    
    -- Cost attribution
    estimated_cost DECIMAL(10, 4),
    cost_calculation_method VARCHAR(50), -- 'median_cpc', 'platform_cpc', 'estimated'
    cost_calculated_at TIMESTAMPTZ,
    
    -- Flexible storage for platform-specific data
    properties JSONB,
    
    -- Metadata
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Partitioning key for future sharding
    partition_date DATE NOT NULL GENERATED ALWAYS AS (DATE(event_timestamp)) STORED
);

-- Performance indexes
CREATE INDEX idx_touchpoints_resolved_user_timestamp 
    ON touchpoints(resolved_user_id, event_timestamp DESC);

CREATE INDEX idx_touchpoints_campaign_date 
    ON touchpoints(campaign_id, partition_date) 
    WHERE campaign_id IS NOT NULL;

CREATE INDEX idx_touchpoints_timestamp 
    ON touchpoints(event_timestamp DESC);

CREATE INDEX idx_touchpoints_cost_calculated 
    ON touchpoints(cost_calculated_at) 
    WHERE estimated_cost IS NULL; -- Find uncalculated costs

-- GIN index for JSONB queries
CREATE INDEX idx_touchpoints_properties 
    ON touchpoints USING GIN(properties);

-- Partition by month for efficient archival
CREATE TABLE touchpoints_2024_12 PARTITION OF touchpoints
    FOR VALUES FROM ('2024-12-01') TO ('2025-01-01');
```

#### 2. Conversions (Operational)
```sql
CREATE TABLE conversions (
    conversion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id VARCHAR(255) UNIQUE NOT NULL,
    
    -- Identity
    segment_user_id VARCHAR(255) NOT NULL, -- Conversions always authenticated
    resolved_user_id VARCHAR(255) NOT NULL,
    
    -- Conversion metadata
    conversion_type VARCHAR(50) NOT NULL, -- 'account_created', 'trial_started', 'subscription_purchased'
    conversion_timestamp TIMESTAMPTZ NOT NULL,
    conversion_value DECIMAL(10, 2), -- Revenue value if applicable
    
    -- Attribution
    attributed_touchpoint_id UUID REFERENCES touchpoints(touchpoint_id),
    attribution_model VARCHAR(50) NOT NULL DEFAULT 'last_touch',
    attributed_cost DECIMAL(10, 4),
    attributed_campaign_id VARCHAR(255),
    attributed_utm_source VARCHAR(255),
    attributed_utm_medium VARCHAR(255),
    attributed_utm_campaign VARCHAR(255),
    
    -- Time to conversion metrics
    time_to_conversion_hours DECIMAL(10, 2),
    touchpoints_in_journey INT,
    
    -- Metadata
    properties JSONB,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attributed_at TIMESTAMPTZ,
    
    partition_date DATE NOT NULL GENERATED ALWAYS AS (DATE(conversion_timestamp)) STORED
);

CREATE INDEX idx_conversions_user_timestamp 
    ON conversions(resolved_user_id, conversion_timestamp DESC);

CREATE INDEX idx_conversions_type_timestamp 
    ON conversions(conversion_type, conversion_timestamp DESC);

CREATE INDEX idx_conversions_attributed_touchpoint 
    ON conversions(attributed_touchpoint_id);
```

#### 3. Campaign Costs (Operational & Reference)
```sql
CREATE TABLE campaign_costs (
    cost_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Campaign identification
    ad_platform VARCHAR(50) NOT NULL, -- 'google_ads', 'meta', etc.
    campaign_id VARCHAR(255) NOT NULL,
    campaign_name VARCHAR(500),
    
    -- Date aggregation
    cost_date DATE NOT NULL,
    
    -- Cost metrics from platform
    total_spend DECIMAL(10, 2) NOT NULL,
    total_impressions BIGINT,
    total_clicks BIGINT,
    total_conversions BIGINT, -- Platform-reported conversions
    
    -- Calculated metrics
    platform_cpc DECIMAL(10, 4), -- From platform
    calculated_cpc DECIMAL(10, 4), -- Our calculation: spend / clicks
    median_cpc DECIMAL(10, 4), -- Rolling median for estimation
    
    -- Additional platform metrics
    ctr DECIMAL(5, 4), -- Click-through rate
    cpm DECIMAL(10, 2), -- Cost per mille (thousand impressions)
    
    -- Metadata
    raw_data JSONB, -- Store full platform response
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(ad_platform, campaign_id, cost_date)
);

CREATE INDEX idx_campaign_costs_platform_date 
    ON campaign_costs(ad_platform, cost_date DESC);

CREATE INDEX idx_campaign_costs_campaign_date 
    ON campaign_costs(campaign_id, cost_date DESC);
```

#### 4. Identity Stitches (Audit Log)
```sql
CREATE TABLE identity_stitches (
    stitch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    segment_anonymous_id VARCHAR(255) NOT NULL,
    segment_user_id VARCHAR(255) NOT NULL,
    stitched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    touchpoints_updated INT DEFAULT 0,
    processing_duration_ms INT,
    
    INDEX idx_identity_stitches_anonymous (segment_anonymous_id),
    INDEX idx_identity_stitches_user (segment_user_id),
    INDEX idx_identity_stitches_timestamp (stitched_at DESC)
);
```

### Redshift Schema Design

Similar schema to PostgreSQL but optimized for analytical queries:

```sql
-- Optimized for analytical queries with sort/dist keys
CREATE TABLE touchpoints (
    -- Same columns as PostgreSQL
    ...
)
DISTKEY(resolved_user_id)
SORTKEY(event_timestamp, resolved_user_id);

CREATE TABLE conversions (
    -- Same columns as PostgreSQL
    ...
)
DISTKEY(resolved_user_id)
SORTKEY(conversion_timestamp, resolved_user_id);

CREATE TABLE campaign_costs (
    -- Same columns as PostgreSQL
    ...
)
DISTKEY(campaign_id)
SORTKEY(cost_date, campaign_id);
```

### Data Lifecycle & Sync Strategy

#### PostgreSQL (Hot Storage)
- **Retention**: 90 days of touchpoints and conversions
- **Partitioning**: Monthly partitions, drop old partitions automatically
- **Use case**: Real-time attribution lookups

#### Redshift (Cold Storage)
- **Retention**: All historical data
- **Sync frequency**: Daily batch job (initially manual, then automated)
- **Use case**: Historical analysis, reporting, data science

#### Kafka (Event Log)
- **Retention**: 30 days
- **Use case**: Event replay, debugging, reprocessing

### Sync Process (PostgreSQL → Redshift)

**Initial MVP (Manual)**:
```bash
# Daily export from PostgreSQL
pg_dump --table touchpoints --where "partition_date = '2024-12-04'" \
    | aws s3 cp - s3://bucket/touchpoints/2024-12-04.sql

# Load into Redshift
COPY touchpoints FROM 's3://bucket/touchpoints/2024-12-04.sql' 
    IAM_ROLE 'arn:aws:iam::...' FORMAT CSV;
```

**Future (Automated)**:
- Kafka Connect with Redshift sink connector
- Real-time CDC (Change Data Capture) from PostgreSQL
- Scheduled ETL job (Airflow/Prefect)

## Consequences

### Positive
- **Fast operational queries**: PostgreSQL optimized for low-latency lookups
- **Scalable analytics**: Redshift handles complex analytical queries
- **Event replay capability**: Kafka retention enables reprocessing
- **Cost-efficient**: Hot/cold storage split reduces costs
- **Corporate alignment**: Uses standard tech stack
- **Partition pruning**: Date-based partitions improve query performance

### Negative
- **Dual-write complexity**: Must sync PostgreSQL → Redshift
- **Eventual consistency**: Redshift may lag behind PostgreSQL
- **Storage duplication**: Same data in multiple stores
- **Operational overhead**: More systems to manage and monitor
- **Manual sync initially**: Requires automation investment later

### Risks & Mitigations

- **Risk**: PostgreSQL disk fills up if partitions not dropped
  - *Mitigation*: Automated partition management; monitoring alerts
  
- **Risk**: Redshift sync fails, creating data gaps
  - *Mitigation*: Kafka replay capability; idempotent sync jobs; monitoring
  
- **Risk**: Query performance degrades with volume growth
  - *Mitigation*: Index optimization; partition pruning; query caching
  
- **Risk**: Cost overruns with Redshift
  - *Mitigation*: Right-size cluster; use Redshift Spectrum for archival; monitor queries

## Alternatives Considered

### Alternative 1: PostgreSQL Only
Use only PostgreSQL for all storage needs.

**Rejected because**:
- Limited analytical query performance at scale
- PostgreSQL not ideal for complex OLAP queries
- Doesn't leverage corporate Redshift investment

### Alternative 2: Redshift Only
Use only Redshift for all storage needs.

**Rejected because**:
- Higher latency for operational queries
- More expensive for high-frequency writes
- Overkill for real-time attribution lookups

### Alternative 3: NoSQL (e.g., MongoDB, DynamoDB)
Use document database for flexible schema.

**Rejected because**:
- Not corporate standard
- Harder to perform relational queries
- Team lacks expertise
- SQL better for attribution logic

### Alternative 4: Time-Series Database (TimescaleDB, InfluxDB)
Optimize for time-series event data.

**Rejected because**:
- Adds new technology to stack
- PostgreSQL with partitioning sufficient for MVP
- Can consider later if needed

## Implementation Notes

### Phase 1 (MVP - Local)
```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:15
    volumes:
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql
    environment:
      POSTGRES_DB: attribution
  
  pgadmin:
    image: dpage/pgadmin4
```

### Phase 2 (Production)
- Managed PostgreSQL (RDS/Cloud SQL)
- Managed Redshift cluster
- Automated sync pipeline (Kafka Connect or Airflow)
- Connection pooling (PgBouncer)
- Read replicas for analytical queries

### Monitoring & Observability
- Table sizes and growth rates
- Query performance (slow query log)
- Partition health (old partitions dropped on time)
- Sync lag (PostgreSQL → Redshift)
- Index usage statistics
- Connection pool utilization

### Backup & Recovery
- PostgreSQL: Automated daily backups (pg_dump or managed service)
- Redshift: Automated snapshots
- Kafka: 30-day retention allows event replay
- Disaster recovery: Replay events from Kafka to rebuild PostgreSQL

## References
- [PostgreSQL Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [Redshift Best Practices](https://docs.aws.amazon.com/redshift/latest/dg/best-practices.html)
- [Lambda Architecture](https://en.wikipedia.org/wiki/Lambda_architecture)

## Related ADRs
- ADR-001: Event Ingestion Architecture
- ADR-002: Identity Resolution Strategy
- ADR-005: Cost Calculation Engine
