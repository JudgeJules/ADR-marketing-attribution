# ADR-004: Ad Platform Cost Data Ingestion

## Status
Proposed

## Context
To attribute costs to marketing touchpoints, we need to ingest campaign performance data from ad platforms (starting with Google Ads). This data includes total spend, clicks, impressions, and other metrics aggregated by campaign and date. Unlike touchpoint events, this is **batch data** fetched daily from platform APIs.

### Requirements
- Fetch daily campaign cost data from Google Ads API
- Store spend, clicks, impressions, conversions per campaign per day
- Calculate cost-per-click (CPC) metrics for touchpoint attribution
- Support extensibility for future platforms (Meta, TikTok, LinkedIn)
- Handle API rate limits, authentication, and failures gracefully
- Run automatically on a daily schedule

### Constraints
- Google Ads API requires OAuth2 authentication
- API rate limits vary by platform
- Data may be revised/updated after initial fetch (platform adjustments)
- Cost data does not contain PII or user-level information
- Initial deployment is local (manual runs, then cron/scheduler)

### Data Mapping Challenge
Ad platform campaigns must be matched to touchpoint `campaign_id` or UTM parameters:
```
Google Ads Campaign ID → touchpoints.campaign_id
Campaign Name → touchpoints.utm_campaign
```

## Decision
We will implement a **scheduled batch ingestion pipeline** with the following architecture:

```
Scheduler (cron/Airflow) → API Fetcher → Data Transformer → PostgreSQL
                                                            ↓
                                                        Campaign Costs Table
```

### Architecture Components

#### 1. Ad Platform Adapters (Plugin Architecture)
Create abstracted adapters for each ad platform to enable extensibility:

```python
# Base interface
class AdPlatformAdapter(ABC):
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with platform API"""
        pass
    
    @abstractmethod
    def fetch_campaign_costs(self, start_date: date, end_date: date) -> List[CampaignCost]:
        """Fetch campaign cost data for date range"""
        pass
    
    @abstractmethod
    def get_campaign_metadata(self, campaign_ids: List[str]) -> List[CampaignMetadata]:
        """Fetch campaign names and metadata"""
        pass

# Implementation for Google Ads
class GoogleAdsAdapter(AdPlatformAdapter):
    def __init__(self, config: GoogleAdsConfig):
        self.client = GoogleAdsClient(
            developer_token=config.developer_token,
            client_id=config.client_id,
            client_secret=config.client_secret,
            refresh_token=config.refresh_token
        )
    
    def fetch_campaign_costs(self, start_date: date, end_date: date):
        # Query Google Ads API
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                metrics.cost_micros,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                segments.date
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """
        # Execute and transform results
```

Future adapters: `MetaAdsAdapter`, `TikTokAdsAdapter`, etc.

#### 2. Data Fetcher Service
```python
class CostDataFetcher:
    def __init__(self, adapters: List[AdPlatformAdapter], storage: CostStorage):
        self.adapters = adapters
        self.storage = storage
    
    def fetch_daily_costs(self, target_date: date):
        """Fetch costs for all platforms for a given date"""
        for adapter in self.adapters:
            try:
                costs = adapter.fetch_campaign_costs(target_date, target_date)
                self.storage.upsert_costs(costs)
                logger.info(f"Fetched {len(costs)} campaigns from {adapter.platform_name}")
            except Exception as e:
                logger.error(f"Failed to fetch from {adapter.platform_name}: {e}")
                # Continue with other platforms
    
    def backfill_costs(self, start_date: date, end_date: date):
        """Backfill historical cost data"""
        for single_date in daterange(start_date, end_date):
            self.fetch_daily_costs(single_date)
```

#### 3. Cost Calculation Logic
```python
class CostCalculator:
    def calculate_metrics(self, raw_cost: RawCampaignCost) -> CampaignCost:
        """Calculate derived metrics from raw platform data"""
        
        # Platform-reported CPC (if available)
        platform_cpc = None
        if raw_cost.total_clicks > 0:
            platform_cpc = raw_cost.total_spend / raw_cost.total_clicks
        
        # Calculate CTR
        ctr = None
        if raw_cost.total_impressions > 0:
            ctr = raw_cost.total_clicks / raw_cost.total_impressions
        
        # Calculate CPM
        cpm = None
        if raw_cost.total_impressions > 0:
            cpm = (raw_cost.total_spend / raw_cost.total_impressions) * 1000
        
        # Calculate median CPC (rolling 7-day median for this campaign)
        median_cpc = self._calculate_median_cpc(
            raw_cost.campaign_id, 
            raw_cost.cost_date,
            window_days=7
        )
        
        return CampaignCost(
            ad_platform=raw_cost.platform,
            campaign_id=raw_cost.campaign_id,
            campaign_name=raw_cost.campaign_name,
            cost_date=raw_cost.cost_date,
            total_spend=raw_cost.total_spend,
            total_clicks=raw_cost.total_clicks,
            total_impressions=raw_cost.total_impressions,
            platform_cpc=platform_cpc,
            calculated_cpc=platform_cpc,  # Same for now
            median_cpc=median_cpc,
            ctr=ctr,
            cpm=cpm,
            raw_data=raw_cost.to_dict()
        )
    
    def _calculate_median_cpc(self, campaign_id: str, target_date: date, window_days: int = 7):
        """Calculate rolling median CPC for estimation when no current data"""
        # Query last N days of CPC data
        # Return median value
```

#### 4. Storage Layer
```python
class CostStorage:
    def upsert_costs(self, costs: List[CampaignCost]):
        """Insert or update campaign costs (idempotent)"""
        for cost in costs:
            # Use UPSERT (ON CONFLICT) for idempotency
            query = """
                INSERT INTO campaign_costs (
                    ad_platform, campaign_id, campaign_name, cost_date,
                    total_spend, total_clicks, total_impressions,
                    platform_cpc, calculated_cpc, median_cpc,
                    ctr, cpm, raw_data, fetched_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (ad_platform, campaign_id, cost_date)
                DO UPDATE SET
                    campaign_name = EXCLUDED.campaign_name,
                    total_spend = EXCLUDED.total_spend,
                    total_clicks = EXCLUDED.total_clicks,
                    total_impressions = EXCLUDED.total_impressions,
                    platform_cpc = EXCLUDED.platform_cpc,
                    calculated_cpc = EXCLUDED.calculated_cpc,
                    median_cpc = EXCLUDED.median_cpc,
                    ctr = EXCLUDED.ctr,
                    cpm = EXCLUDED.cpm,
                    raw_data = EXCLUDED.raw_data,
                    fetched_at = NOW()
            """
```

### Campaign Matching Strategy

#### Touchpoint → Campaign Cost Mapping
Touchpoints contain campaign identifiers in multiple forms:
1. `campaign_id` (direct platform ID, e.g., Google Ads Campaign ID)
2. `utm_campaign` (campaign name from UTM parameter)
3. `utm_source` + `utm_medium` (channel identification)

**Matching hierarchy**:
```python
def find_campaign_cost(touchpoint: Touchpoint, cost_date: date) -> Optional[CampaignCost]:
    """Find matching campaign cost for a touchpoint"""
    
    # 1. Exact campaign_id match (highest confidence)
    if touchpoint.campaign_id:
        cost = db.query(CampaignCost).filter(
            campaign_id=touchpoint.campaign_id,
            cost_date=cost_date
        ).first()
        if cost:
            return cost
    
    # 2. UTM campaign name match (fuzzy)
    if touchpoint.utm_campaign:
        cost = db.query(CampaignCost).filter(
            campaign_name.ilike(f"%{touchpoint.utm_campaign}%"),
            cost_date=cost_date
        ).first()
        if cost:
            return cost
    
    # 3. Default/fallback: Use platform-level median
    if touchpoint.utm_source == 'google':
        return get_platform_median_cost('google_ads', cost_date)
    
    return None
```

### Scheduling Strategy

#### Daily Job (Primary)
```yaml
# Cron expression: Run at 2 AM daily
schedule: "0 2 * * *"

job:
  - Fetch yesterday's cost data (ad platforms typically have 1-day lag)
  - Calculate metrics (CPC, CTR, median CPC)
  - Upsert into campaign_costs table
  - Trigger touchpoint cost recalculation for affected campaigns
```

#### Backfill Job (One-time or Manual)
```bash
python cost_fetcher.py backfill \
    --platform google_ads \
    --start-date 2024-11-01 \
    --end-date 2024-11-30
```

### Error Handling & Resilience

#### API Failures
```python
class APIRetryStrategy:
    def fetch_with_retry(self, fetch_fn, max_retries=3):
        for attempt in range(max_retries):
            try:
                return fetch_fn()
            except RateLimitError as e:
                wait_time = exponential_backoff(attempt)
                logger.warning(f"Rate limited, waiting {wait_time}s")
                time.sleep(wait_time)
            except AuthenticationError as e:
                logger.error("Authentication failed, refresh token needed")
                raise
            except APIError as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"API error, retrying: {e}")
        
        raise MaxRetriesExceeded()
```

#### Data Quality Checks
```python
def validate_cost_data(cost: CampaignCost) -> bool:
    """Validate cost data before storage"""
    
    # Check for negative values
    if cost.total_spend < 0 or cost.total_clicks < 0:
        logger.error(f"Negative values detected: {cost}")
        return False
    
    # Check for outliers (spend > 10x historical average)
    avg_spend = get_campaign_avg_spend(cost.campaign_id, days=30)
    if cost.total_spend > avg_spend * 10:
        logger.warning(f"Unusually high spend detected: {cost}")
        # Still store but flag for review
    
    # Check for missing required fields
    if not cost.campaign_id or not cost.cost_date:
        logger.error(f"Missing required fields: {cost}")
        return False
    
    return True
```

## Consequences

### Positive
- **Extensible design**: Plugin architecture supports multiple ad platforms
- **Idempotent**: Can safely re-run for same date without duplication
- **Automated**: Daily schedule reduces manual effort
- **Resilient**: Retry logic handles transient failures
- **Auditable**: Stores raw API responses for debugging
- **Cost-aware**: Calculates multiple CPC metrics for flexibility

### Negative
- **Batch latency**: 1-day lag in cost data (ad platform limitation)
- **API complexity**: Each platform has unique API structure
- **Authentication management**: OAuth tokens need refresh
- **Data revisions**: Platforms may update historical data
- **Matching ambiguity**: UTM-based matching may be imprecise

### Risks & Mitigations

- **Risk**: Google Ads API quota exceeded
  - *Mitigation*: Implement rate limiting; request quota increase
  
- **Risk**: Campaign renamed, breaking historical linkage
  - *Mitigation*: Store campaign ID (immutable) as primary key
  
- **Risk**: Missing cost data for new campaigns
  - *Mitigation*: Use platform-level median CPC as fallback
  
- **Risk**: OAuth token expires
  - *Mitigation*: Automated token refresh; alerting on auth failures

## Alternatives Considered

### Alternative 1: Real-time API Polling
Poll ad platform APIs in real-time for each touchpoint.

**Rejected because**:
- Extreme API rate limit consumption
- Most platforms don't provide real-time cost data
- Unnecessary complexity and cost
- Batch aggregation is platform standard

### Alternative 2: Manual CSV Uploads
Download cost reports manually and upload via UI.

**Rejected because**:
- Not scalable
- Prone to human error
- Delays in data availability
- Doesn't support automation

### Alternative 3: Third-party ETL Tool (Fivetran, Stitch)
Use commercial ETL service for ad platform integration.

**Rejected because**:
- Additional cost
- Less control over transformation logic
- Overkill for single data source initially
- Can reconsider for future if managing many platforms

### Alternative 4: Event-driven via Webhooks
Receive cost updates via platform webhooks.

**Rejected because**:
- Most ad platforms don't support cost webhooks
- Batch aggregation is standard for cost data
- Would still need polling for historical data

## Implementation Notes

### Phase 1 (MVP - Local)
```bash
# Manual daily run
python cost_fetcher.py fetch --date yesterday

# Setup cron for automation
0 2 * * * cd /path/to/project && python cost_fetcher.py fetch --date yesterday
```

### Phase 2 (Production)
- Orchestration tool (Airflow, Prefect) for scheduling
- Centralized secrets management (AWS Secrets Manager)
- Monitoring and alerting (failed fetches, quota warnings)
- Support for multiple ad accounts per platform
- Delta detection (only fetch changed campaigns)

### Configuration Management
```yaml
# config/ad_platforms.yaml
google_ads:
  enabled: true
  developer_token: ${GOOGLE_ADS_DEV_TOKEN}
  client_id: ${GOOGLE_ADS_CLIENT_ID}
  client_secret: ${GOOGLE_ADS_CLIENT_SECRET}
  refresh_token: ${GOOGLE_ADS_REFRESH_TOKEN}
  customer_id: "1234567890"
  
meta_ads:
  enabled: false  # Future
  access_token: ${META_ACCESS_TOKEN}
  ad_account_id: "act_123456"
```

### Monitoring Metrics
- API fetch success/failure rate
- Campaigns fetched per day
- Data latency (fetch time vs cost_date)
- API quota usage
- Cost data completeness (% campaigns with data)
- Data revisions detected

## References
- [Google Ads API Documentation](https://developers.google.com/google-ads/api/docs/start)
- [Google Ads Reporting Guide](https://developers.google.com/google-ads/api/docs/reporting/overview)
- [OAuth 2.0 Best Practices](https://oauth.net/2/)

## Related ADRs
- ADR-003: Data Storage Design
- ADR-005: Cost Calculation Engine
- ADR-006: Attribution Model Implementation
