# ADR-002: Identity Resolution Strategy

## Status
Proposed

## Context
The attribution system must handle both anonymous and authenticated users across multiple touchpoints. Identity resolution (stitching anonymous activities to authenticated users) is critical for accurate attribution, but we must avoid creating a duplicate identity graph since Segment CDP is our source of truth.

### Requirements
- Track anonymous user touchpoints before authentication
- Stitch anonymous touchpoints to authenticated users when identity is revealed
- Leverage Segment's identity resolution (not duplicate it)
- Support cost attribution across stitched identities
- Handle identity resolution events from Segment

### Constraints
- **Cannot query Segment Identity Graph API** (not part of MVP scope)
- **Must trust Segment as single source of truth** for identity resolution
- Segment sends resolved identities with events
- Need to handle retroactive stitching when Segment resolves identities

### Identity Flow Example
```
User Journey:
1. Visit landing page (anonymous) → segment_anonymous_id: "anon_123"
2. Click ad (anonymous) → segment_anonymous_id: "anon_123"
3. Sign up → segment_user_id: "user_456", segment_anonymous_id: "anon_123"
4. Segment stitches → All "anon_123" events now linked to "user_456"
5. Start trial → segment_user_id: "user_456"
6. Purchase → segment_user_id: "user_456"
```

## Decision
We will implement a **Segment-driven identity resolution** strategy where:

1. **Store both anonymous and user IDs** with every touchpoint
2. **Trust Segment's identity resolution** as received in events
3. **Use `identify` events** from Segment to trigger retroactive stitching
4. **Maintain lightweight identity mapping** for query performance
5. **Accept eventual consistency** in identity resolution

### Data Model

#### Touchpoints Table (PostgreSQL)
```sql
CREATE TABLE touchpoints (
    touchpoint_id UUID PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    
    -- Identity fields (from Segment)
    segment_anonymous_id VARCHAR(255),
    segment_user_id VARCHAR(255),
    resolved_user_id VARCHAR(255), -- Computed field for queries
    
    -- Event details
    event_type VARCHAR(50),
    event_name VARCHAR(255),
    event_timestamp TIMESTAMPTZ NOT NULL,
    
    -- Campaign tracking
    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),
    utm_content VARCHAR(255),
    utm_term VARCHAR(255),
    campaign_id VARCHAR(255),
    
    -- Additional context
    referrer TEXT,
    url TEXT,
    source_platform VARCHAR(50),
    properties JSONB,
    
    -- Cost attribution
    estimated_cost DECIMAL(10,4),
    cost_calculated_at TIMESTAMPTZ,
    
    -- Metadata
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexes for performance
    INDEX idx_segment_user_id (segment_user_id),
    INDEX idx_segment_anonymous_id (segment_anonymous_id),
    INDEX idx_resolved_user_id (resolved_user_id),
    INDEX idx_event_timestamp (event_timestamp),
    INDEX idx_campaign_id (campaign_id)
);
```

#### Identity Stitching Log (PostgreSQL)
Track when Segment notifies us of identity resolution:
```sql
CREATE TABLE identity_stitches (
    stitch_id UUID PRIMARY KEY,
    segment_anonymous_id VARCHAR(255) NOT NULL,
    segment_user_id VARCHAR(255) NOT NULL,
    stitched_at TIMESTAMPTZ DEFAULT NOW(),
    touchpoints_updated INT DEFAULT 0,
    
    INDEX idx_anonymous_id (segment_anonymous_id),
    INDEX idx_user_id (segment_user_id)
);
```

### Identity Resolution Process

#### 1. Ingest Events with Identity Context
Every event from Segment includes:
```json
{
  "anonymousId": "anon_123",
  "userId": "user_456",  // null if anonymous
  "type": "track",
  "event": "Product Clicked"
}
```

We store both IDs and compute `resolved_user_id`:
- If `segment_user_id` exists → `resolved_user_id = segment_user_id`
- If only `segment_anonymous_id` exists → `resolved_user_id = segment_anonymous_id`

#### 2. Process `identify` Events
When Segment sends an `identify` event (user logs in or signs up):
```json
{
  "type": "identify",
  "anonymousId": "anon_123",
  "userId": "user_456",
  "traits": {
    "email": "user@example.com"
  }
}
```

**Identity Stitching Workflow**:
1. Record stitch in `identity_stitches` table
2. Publish event to Kafka topic: `identity.stitched`
3. Background job updates touchpoints:
   ```sql
   UPDATE touchpoints 
   SET resolved_user_id = 'user_456',
       updated_at = NOW()
   WHERE segment_anonymous_id = 'anon_123'
     AND segment_user_id IS NULL;
   ```
4. Recalculate attribution for affected conversions (if any)

#### 3. Query Using Resolved Identity
All attribution queries use `resolved_user_id`:
```sql
-- Get user journey
SELECT * FROM touchpoints
WHERE resolved_user_id = 'user_456'
ORDER BY event_timestamp ASC;

-- Last touch before conversion
SELECT * FROM touchpoints
WHERE resolved_user_id = 'user_456'
  AND event_timestamp < conversion_timestamp
ORDER BY event_timestamp DESC
LIMIT 1;
```

### Handling Edge Cases

#### Case 1: Out-of-Order Events
Segment may send events out of order due to network delays.

**Solution**: Use `event_timestamp` (client-generated) for ordering, not `ingested_at`

#### Case 2: Multiple Anonymous IDs
User switches devices before authenticating (different anonymous IDs).

**Solution**: Trust Segment to resolve this; they'll send `identify` events for each device

#### Case 3: Identity Changes
User changes email or merges accounts.

**Solution**: Segment handles this; we receive new `identify` events and re-stitch

#### Case 4: Historical Data Gaps
When system starts, we don't have previous anonymous touchpoints.

**Solution**: Accept limitation for MVP; future enhancement could backfill from Segment

## Consequences

### Positive
- **Single source of truth**: No duplicate identity graphs
- **Simplified logic**: Delegate complex identity resolution to Segment
- **Consistent with CDP-first approach**: Leverages Segment's core capability
- **Scalable**: Don't need to build sophisticated identity matching
- **Retroactive stitching**: Can update attribution as identities are revealed

### Negative
- **Eventual consistency**: Small delay between identity resolution and attribution updates
- **Dependency on Segment**: Can't perform attribution without Segment events
- **Limited control**: Can't customize identity resolution logic
- **No cross-Segment identity**: If data exists outside Segment, can't correlate

### Risks & Mitigations
- **Risk**: Segment `identify` events delayed or missing
  - *Mitigation*: Monitor `identify` event frequency; alert on anomalies
  
- **Risk**: Identity stitching job fails, leaving touchpoints orphaned
  - *Mitigation*: Idempotent updates; retry logic; monitoring dashboard
  
- **Risk**: Performance issues with retroactive updates
  - *Mitigation*: Batch updates; process asynchronously; index optimization

## Alternatives Considered

### Alternative 1: Build Custom Identity Graph
Implement probabilistic/deterministic matching using emails, device IDs, etc.

**Rejected because**:
- Duplicates Segment's core functionality
- Requires significant engineering effort
- Risk of inconsistent identity resolution
- Violates "CDP-first" principle

### Alternative 2: Query Segment Profile API
Query Segment for resolved identity on-demand.

**Rejected because**:
- Not available in MVP scope
- Adds latency to real-time processing
- API rate limits
- Unnecessary if we trust events

### Alternative 3: Store Only Authenticated User Data
Ignore anonymous touchpoints until user authenticates.

**Rejected because**:
- Loses critical pre-authentication touchpoint data
- Can't attribute top-of-funnel marketing effectiveness
- Incomplete user journey

## Implementation Notes

### Phase 1 (MVP)
- Store both IDs with every touchpoint
- Process `identify` events asynchronously
- Simple UPDATE query for stitching
- Accept small delay in attribution accuracy

### Phase 2 (Future)
- Real-time stitching using Kafka Streams
- Materialize pre-joined views for faster queries
- Backfill historical touchpoints from Segment replay
- Add monitoring for identity resolution metrics

### Monitoring Metrics
- `identify` events received per hour
- Touchpoints updated per stitch
- Time lag between `identify` and stitch completion
- Percentage of touchpoints with resolved identity
- Conversions with vs without pre-auth touchpoints

## References
- [Segment Identity Resolution](https://segment.com/docs/unify/identity-resolution/)
- [Event Ordering in Distributed Systems](https://www.confluent.io/blog/handling-out-of-order-events-in-kafka/)

## Related ADRs
- ADR-001: Event Ingestion Architecture
- ADR-003: Data Storage Design
- ADR-006: Attribution Model Implementation
