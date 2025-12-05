# ADR-005: Cost Calculation Engine

## Status
Proposed

## Context
To understand marketing ROI, we must attribute costs to individual touchpoints. Since ad platforms report aggregated daily costs (total spend, total clicks) per campaign, we need to estimate the cost of each individual click/impression. This becomes complex when:
- Campaigns are new (no historical data)
- Touchpoints reference campaigns via UTM parameters (imprecise matching)
- Multiple platforms have different cost structures
- Cost data may arrive after touchpoints (1-day lag)

### Requirements
- Calculate cost per touchpoint based on campaign performance data
- Support multiple calculation methods (median CPC, platform CPC, estimated)
- Handle missing/incomplete cost data gracefully
- Recalculate costs when new campaign data arrives
- Extend to multiple ad platforms (Google Ads, Meta, TikTok)
- Accept estimation gaps in MVP (some touchpoints may have no cost)

### Cost Calculation Goals
```
Goal: touchpoints.estimated_cost = f(campaign_cost_data)

Inputs:
- Campaign daily costs (spend, clicks, impressions)
- Touchpoint campaign references (campaign_id, UTM params)
- Historical cost patterns

Output:
- Estimated cost per touchpoint
- Cost calculation method used
- Confidence/quality indicator
```

## Decision
We will implement a **tiered cost calculation engine** that attempts multiple strategies in order of confidence:

```
Tier 1: Direct Campaign Match (Highest Confidence)
  ↓ If no match
Tier 2: Campaign Name Fuzzy Match
  ↓ If no match
Tier 3: Platform Median CPC
  ↓ If no match
Tier 4: Default Estimated CPC (Lowest Confidence)
```

### Cost Calculation Algorithm

```python
class CostCalculationEngine:
    """
    Calculates estimated cost for touchpoints based on campaign performance data.
    Uses tiered fallback strategy for missing data.
    """
    
    def calculate_touchpoint_cost(self, touchpoint: Touchpoint) -> CostEstimate:
        """
        Calculate cost for a single touchpoint using tiered approach.
        """
        cost_date = touchpoint.event_timestamp.date()
        
        # Tier 1: Direct campaign_id match
        if touchpoint.campaign_id:
            campaign_cost = self.get_campaign_cost(
                campaign_id=touchpoint.campaign_id,
                date=cost_date
            )
            if campaign_cost and campaign_cost.calculated_cpc:
                return CostEstimate(
                    cost=campaign_cost.calculated_cpc,
                    method='campaign_cpc',
                    confidence='high',
                    campaign_id=campaign_cost.campaign_id
                )
            
            # Use median if same-day data not available
            if campaign_cost and campaign_cost.median_cpc:
                return CostEstimate(
                    cost=campaign_cost.median_cpc,
                    method='campaign_median_cpc',
                    confidence='medium',
                    campaign_id=campaign_cost.campaign_id
                )
        
        # Tier 2: Fuzzy match on campaign name via UTM
        if touchpoint.utm_campaign:
            campaign_cost = self.fuzzy_match_campaign(
                campaign_name=touchpoint.utm_campaign,
                platform=self.infer_platform(touchpoint),
                date=cost_date
            )
            if campaign_cost and campaign_cost.calculated_cpc:
                return CostEstimate(
                    cost=campaign_cost.calculated_cpc,
                    method='fuzzy_match_cpc',
                    confidence='medium',
                    campaign_id=campaign_cost.campaign_id
                )
        
        # Tier 3: Platform-level median
        platform = self.infer_platform(touchpoint)
        if platform:
            platform_median = self.get_platform_median_cpc(
                platform=platform,
                date=cost_date,
                window_days=30
            )
            if platform_median:
                return CostEstimate(
                    cost=platform_median,
                    method='platform_median_cpc',
                    confidence='low',
                    campaign_id=None
                )
        
        # Tier 4: Default estimate
        return CostEstimate(
            cost=self.get_default_cpc(touchpoint.utm_source),
            method='default_estimate',
            confidence='very_low',
            campaign_id=None
        )
    
    def infer_platform(self, touchpoint: Touchpoint) -> Optional[str]:
        """Infer ad platform from touchpoint metadata"""
        if touchpoint.ad_platform:
            return touchpoint.ad_platform
        
        # Infer from utm_source
        source_mapping = {
            'google': 'google_ads',
            'facebook': 'meta',
            'instagram': 'meta',
            'tiktok': 'tiktok',
            'linkedin': 'linkedin'
        }
        return source_mapping.get(touchpoint.utm_source.lower())
    
    def get_campaign_cost(self, campaign_id: str, date: date) -> Optional[CampaignCost]:
        """Get campaign cost for specific date"""
        return db.query(CampaignCost).filter(
            CampaignCost.campaign_id == campaign_id,
            CampaignCost.cost_date == date
        ).first()
    
    def fuzzy_match_campaign(self, campaign_name: str, platform: str, date: date) -> Optional[CampaignCost]:
        """Fuzzy match campaign by name"""
        # Use PostgreSQL similarity or Levenshtein distance
        campaigns = db.query(CampaignCost).filter(
            CampaignCost.ad_platform == platform,
            CampaignCost.cost_date == date,
            func.similarity(CampaignCost.campaign_name, campaign_name) > 0.6
        ).order_by(
            func.similarity(CampaignCost.campaign_name, campaign_name).desc()
        ).first()
        
        return campaigns
    
    def get_platform_median_cpc(self, platform: str, date: date, window_days: int = 30) -> Optional[Decimal]:
        """Calculate platform-wide median CPC over rolling window"""
        start_date = date - timedelta(days=window_days)
        
        # Get all CPCs for platform in window
        cpcs = db.query(CampaignCost.calculated_cpc).filter(
            CampaignCost.ad_platform == platform,
            CampaignCost.cost_date.between(start_date, date),
            CampaignCost.calculated_cpc.isnot(None)
        ).all()
        
        if not cpcs:
            return None
        
        # Calculate median
        cpc_values = [cpc[0] for cpc in cpcs]
        return Decimal(str(statistics.median(cpc_values)))
    
    def get_default_cpc(self, utm_source: str) -> Decimal:
        """Fallback CPC estimates by source"""
        defaults = {
            'google': Decimal('1.50'),
            'facebook': Decimal('0.80'),
            'instagram': Decimal('0.80'),
            'tiktok': Decimal('1.20'),
            'linkedin': Decimal('3.00'),
            'unknown': Decimal('1.00')
        }
        return defaults.get(utm_source.lower(), defaults['unknown'])
```

### Batch Cost Calculation Job

Since cost data arrives with 1-day lag, we need to retroactively calculate costs for touchpoints:

```python
class BatchCostCalculator:
    """
    Batch job to calculate costs for touchpoints after campaign data arrives.
    """
    
    def calculate_costs_for_date(self, target_date: date):
        """
        Calculate costs for all touchpoints on a specific date.
        Runs daily after campaign cost data is fetched.
        """
        logger.info(f"Calculating costs for touchpoints on {target_date}")
        
        # Get all touchpoints for date without calculated cost
        touchpoints = db.query(Touchpoint).filter(
            func.date(Touchpoint.event_timestamp) == target_date,
            Touchpoint.estimated_cost.is_(None)
        ).all()
        
        logger.info(f"Found {len(touchpoints)} touchpoints to calculate")
        
        calculator = CostCalculationEngine()
        updated_count = 0
        
        for touchpoint in touchpoints:
            try:
                cost_estimate = calculator.calculate_touchpoint_cost(touchpoint)
                
                # Update touchpoint with cost
                touchpoint.estimated_cost = cost_estimate.cost
                touchpoint.cost_calculation_method = cost_estimate.method
                touchpoint.cost_calculated_at = datetime.now()
                
                # Store in properties for debugging
                touchpoint.properties['cost_confidence'] = cost_estimate.confidence
                if cost_estimate.campaign_id:
                    touchpoint.properties['matched_campaign_id'] = cost_estimate.campaign_id
                
                updated_count += 1
                
            except Exception as e:
                logger.error(f"Failed to calculate cost for touchpoint {touchpoint.touchpoint_id}: {e}")
        
        db.commit()
        logger.info(f"Updated {updated_count} touchpoints with cost estimates")
        
        # Update any conversions that were attributed to these touchpoints
        self.update_conversion_costs(target_date)
    
    def update_conversion_costs(self, target_date: date):
        """Update attributed costs for conversions"""
        conversions = db.query(Conversion).filter(
            Conversion.attributed_touchpoint_id.in_(
                db.query(Touchpoint.touchpoint_id).filter(
                    func.date(Touchpoint.event_timestamp) == target_date,
                    Touchpoint.estimated_cost.isnot(None)
                )
            ),
            Conversion.attributed_cost.is_(None)
        ).all()
        
        for conversion in conversions:
            touchpoint = conversion.attributed_touchpoint
            if touchpoint and touchpoint.estimated_cost:
                conversion.attributed_cost = touchpoint.estimated_cost
        
        db.commit()
        logger.info(f"Updated costs for {len(conversions)} conversions")
```

### Scheduled Execution

```yaml
# Daily cost calculation workflow
schedule: "0 3 * * *"  # 3 AM, after campaign cost fetch (2 AM)

workflow:
  1. Wait for campaign cost fetch to complete
  2. Calculate costs for yesterday's touchpoints
  3. Update conversion attributed costs
  4. Generate daily cost report
  5. Alert on calculation failures or anomalies
```

### Cost Calculation Metrics & Monitoring

```python
class CostCalculationMetrics:
    """Track quality of cost calculations"""
    
    def generate_daily_metrics(self, target_date: date):
        """Generate metrics for cost calculation quality"""
        
        total_touchpoints = db.query(func.count(Touchpoint.touchpoint_id)).filter(
            func.date(Touchpoint.event_timestamp) == target_date
        ).scalar()
        
        touchpoints_with_cost = db.query(func.count(Touchpoint.touchpoint_id)).filter(
            func.date(Touchpoint.event_timestamp) == target_date,
            Touchpoint.estimated_cost.isnot(None)
        ).scalar()
        
        # Breakdown by calculation method
        method_breakdown = db.query(
            Touchpoint.cost_calculation_method,
            func.count(Touchpoint.touchpoint_id)
        ).filter(
            func.date(Touchpoint.event_timestamp) == target_date,
            Touchpoint.estimated_cost.isnot(None)
        ).group_by(Touchpoint.cost_calculation_method).all()
        
        # Confidence distribution
        confidence_dist = db.query(
            func.jsonb_extract_path_text(Touchpoint.properties, 'cost_confidence'),
            func.count(Touchpoint.touchpoint_id)
        ).filter(
            func.date(Touchpoint.event_timestamp) == target_date,
            Touchpoint.estimated_cost.isnot(None)
        ).group_by(
            func.jsonb_extract_path_text(Touchpoint.properties, 'cost_confidence')
        ).all()
        
        return {
            'date': target_date,
            'total_touchpoints': total_touchpoints,
            'touchpoints_with_cost': touchpoints_with_cost,
            'cost_coverage': touchpoints_with_cost / total_touchpoints if total_touchpoints > 0 else 0,
            'method_breakdown': dict(method_breakdown),
            'confidence_distribution': dict(confidence_dist)
        }
```

### Handling Edge Cases

#### New Campaign (No Historical Data)
```python
# First day of campaign → no calculated_cpc or median_cpc
# Fallback: Use platform median or default estimate
# As data accumulates, accuracy improves
```

#### Campaign Renamed
```python
# Campaign ID remains constant (immutable)
# Cost calculation uses campaign_id (Tier 1)
# UTM matching may break but ID match works
```

#### Multi-platform Campaigns
```python
# Campaign may run on multiple platforms
# Store separate costs per (platform, campaign_id)
# Touchpoint.ad_platform differentiates
```

#### Zero-click Days
```python
# Campaign has spend but zero clicks
# calculated_cpc = None (undefined)
# Fallback to median_cpc or platform median
```

## Consequences

### Positive
- **Flexible calculation**: Multiple fallback strategies handle data gaps
- **Improving accuracy**: System gets better as historical data accumulates
- **Auditable**: Each touchpoint stores calculation method and confidence
- **Extensible**: Easy to add new calculation tiers or methods
- **Tolerates estimation**: Accepts imperfect data for MVP

### Negative
- **Delayed calculation**: 1-day lag for cost data means retroactive updates
- **Estimation errors**: Fallback methods may be inaccurate
- **Complexity**: Multiple calculation tiers add logic complexity
- **Storage overhead**: Store calculation metadata with each touchpoint

### Risks & Mitigations

- **Risk**: Median CPC biased by outlier campaigns
  - *Mitigation*: Use median (not mean); add outlier detection
  
- **Risk**: Fuzzy matching incorrect campaigns
  - *Mitigation*: Set similarity threshold; log low-confidence matches for review
  
- **Risk**: Default estimates wildly inaccurate
  - *Mitigation*: Periodically review and update defaults; use industry benchmarks
  
- **Risk**: Batch job fails, leaving touchpoints without costs
  - *Mitigation*: Idempotent job; retry logic; monitoring alerts

## Alternatives Considered

### Alternative 1: Simple Division (Spend / Total Clicks)
Divide daily spend by daily clicks for campaign-level CPC.

**Rejected because**:
- Doesn't handle new campaigns or zero-click days
- No fallback strategy for missing data
- Doesn't account for temporal variations in CPC

### Alternative 2: Wait for Complete Data
Only calculate costs when perfect data is available.

**Rejected because**:
- Delays attribution by days or weeks
- Incomplete view of marketing effectiveness
- Violates "accept estimation gaps" principle

### Alternative 3: Machine Learning Cost Prediction
Train ML model to predict touchpoint cost based on features.

**Rejected because**:
- Overkill for MVP
- Requires significant training data
- More complex to maintain and explain
- Can revisit in future

### Alternative 4: Manual Cost Entry
Allow manual entry of cost per campaign.

**Rejected because**:
- Not scalable
- Prone to errors
- Defeats purpose of automation
- Useful only as override mechanism

## Implementation Notes

### Phase 1 (MVP)
- Implement Tier 1-4 calculation logic
- Daily batch job at 3 AM
- Simple confidence levels (high/medium/low/very_low)
- Accept ~10-20% of touchpoints with default estimates

### Phase 2 (Enhanced)
- Time-of-day cost adjustments (morning clicks may cost more)
- Device-specific cost estimates (mobile vs desktop)
- Geographic cost variations
- ML-based cost prediction for high-volume campaigns

### Testing Strategy
```python
# Unit tests
def test_campaign_cpc_calculation():
    # Test direct campaign match
    
def test_fuzzy_match():
    # Test campaign name matching with various similarities
    
def test_platform_median():
    # Test median calculation across campaigns
    
def test_fallback_chain():
    # Test full Tier 1→4 fallback

# Integration tests
def test_batch_cost_calculation():
    # Create touchpoints and campaign costs
    # Run batch calculator
    # Verify costs calculated correctly
```

### Monitoring Alerts
- Cost coverage below 80%
- Unusual spike in default estimates (>30%)
- Batch job duration exceeds threshold
- Campaign costs missing for known campaigns
- Outlier costs detected (>10x median)

## References
- [Cost Attribution in Marketing Analytics](https://www.singular.net/glossary/cost-attribution/)
- [CPC vs CPM vs CPA](https://www.wordstream.com/blog/ws/2020/08/27/online-advertising-costs)

## Related ADRs
- ADR-003: Data Storage Design
- ADR-004: Ad Platform Cost Ingestion
- ADR-006: Attribution Model Implementation
