# ADR-008: Conversion Funnel Modeling

## Status
Proposed

## Context
Our business has a multi-step conversion funnel where users progress through discrete stages:

1. **Account Created** - User signs up (no payment)
2. **Trial Started** - User begins 14-day trial
3. **Subscription Purchased** - User converts to paid (Day 14 after trial)

Each stage represents a conversion event that needs attribution and cost analysis. We need to:
- Track progression through the funnel
- Attribute each stage independently
- Assign different values/weights to each stage
- Calculate stage-specific conversion rates
- Understand cost-per-acquisition at each stage

### Business Questions
- What's the cost to acquire a trial user vs. a paying subscriber?
- Which campaigns drive account creation but not trial starts?
- What's the trial-to-paid conversion rate by attributed source?
- How long does it take users to progress through the funnel?

## Decision
We will model the funnel as **independent conversion events** with **stage-aware analytics**:

1. Each funnel stage is a separate conversion record
2. Each stage gets attributed independently to the last marketing touch before that stage
3. Stages have different business values assigned
4. Track funnel progression with stage relationships
5. Calculate funnel metrics (conversion rates, drop-off, time between stages)

### Conversion Type Schema

```python
class ConversionType(Enum):
    """Enumeration of conversion types in the funnel"""
    ACCOUNT_CREATED = 'account_created'
    TRIAL_STARTED = 'trial_started'
    SUBSCRIPTION_PURCHASED = 'subscription_purchased'

class ConversionConfig:
    """Configuration for conversion types and their business values"""
    
    CONVERSION_STAGES = {
        ConversionType.ACCOUNT_CREATED: {
            'stage': 1,
            'value': 0.00,  # No immediate revenue
            'weight': 0.33,  # 33% of journey complete
            'display_name': 'Account Created'
        },
        ConversionType.TRIAL_STARTED: {
            'stage': 2,
            'value': 0.00,  # Still no revenue
            'weight': 0.67,  # 67% of journey complete
            'display_name': 'Trial Started'
        },
        ConversionType.SUBSCRIPTION_PURCHASED: {
            'stage': 3,
            'value': 30.00,  # Example: $30/month subscription
            'weight': 1.00,  # 100% - completed funnel
            'display_name': 'Subscription Purchased'
        }
    }
    
    # Expected time ranges between stages (for anomaly detection)
    EXPECTED_STAGE_DURATIONS = {
        (ConversionType.ACCOUNT_CREATED, ConversionType.TRIAL_STARTED): {
            'min_hours': 0,  # Can start trial immediately
            'max_hours': 168,  # Should start within 7 days
            'median_hours': 2
        },
        (ConversionType.TRIAL_STARTED, ConversionType.SUBSCRIPTION_PURCHASED): {
            'min_hours': 336,  # 14-day trial minimum
            'max_hours': 504,  # Should convert within 21 days
            'median_hours': 336  # Exactly 14 days typical
        }
    }
```

### Funnel Stage Tracking

#### Enhanced Conversions Table
```sql
-- Already defined in ADR-003, adding funnel-specific fields
ALTER TABLE conversions ADD COLUMN funnel_stage INT;
ALTER TABLE conversions ADD COLUMN previous_conversion_id UUID REFERENCES conversions(conversion_id);
ALTER TABLE conversions ADD COLUMN next_conversion_id UUID REFERENCES conversions(conversion_id);

-- Index for funnel queries
CREATE INDEX idx_conversions_user_stage 
    ON conversions(resolved_user_id, funnel_stage);
```

#### Funnel Progression Tracker
```python
class FunnelProgressionTracker:
    """Track user progression through conversion funnel"""
    
    def link_conversions(self, user_id: str):
        """
        Link conversion events to show funnel progression.
        Called after new conversion is created.
        """
        # Get all conversions for user in chronological order
        conversions = db.query(Conversion).filter(
            Conversion.resolved_user_id == user_id
        ).order_by(Conversion.conversion_timestamp.asc()).all()
        
        # Link conversions sequentially
        for i in range(len(conversions) - 1):
            current = conversions[i]
            next_conv = conversions[i + 1]
            
            # Only link if next stage follows logically
            if self.is_valid_progression(current.conversion_type, next_conv.conversion_type):
                current.next_conversion_id = next_conv.conversion_id
                next_conv.previous_conversion_id = current.conversion_id
        
        db.commit()
    
    def is_valid_progression(self, from_type: str, to_type: str) -> bool:
        """Check if progression is valid (e.g., can't go trial→account)"""
        from_stage = ConversionConfig.CONVERSION_STAGES[from_type]['stage']
        to_stage = ConversionConfig.CONVERSION_STAGES[to_type]['stage']
        return to_stage > from_stage
    
    def get_user_funnel(self, user_id: str) -> FunnelJourney:
        """Get complete funnel journey for a user"""
        conversions = db.query(Conversion).filter(
            Conversion.resolved_user_id == user_id
        ).order_by(Conversion.conversion_timestamp.asc()).all()
        
        journey = {
            'user_id': user_id,
            'stages_completed': [],
            'current_stage': None,
            'total_attributed_cost': 0,
            'funnel_completion_rate': 0
        }
        
        for conv in conversions:
            stage_info = {
                'stage': ConversionConfig.CONVERSION_STAGES[conv.conversion_type]['stage'],
                'conversion_type': conv.conversion_type,
                'timestamp': conv.conversion_timestamp,
                'attributed_cost': conv.attributed_cost,
                'attributed_campaign': conv.attributed_utm_campaign,
                'time_from_previous_stage': None
            }
            
            # Calculate time from previous stage
            if conv.previous_conversion_id:
                prev_conv = db.query(Conversion).get(conv.previous_conversion_id)
                time_diff = conv.conversion_timestamp - prev_conv.conversion_timestamp
                stage_info['time_from_previous_stage'] = time_diff.total_seconds() / 3600
            
            journey['stages_completed'].append(stage_info)
            journey['total_attributed_cost'] += float(conv.attributed_cost or 0)
        
        # Calculate completion rate
        if conversions:
            latest_stage = ConversionConfig.CONVERSION_STAGES[conversions[-1].conversion_type]['stage']
            journey['current_stage'] = latest_stage
            journey['funnel_completion_rate'] = ConversionConfig.CONVERSION_STAGES[
                conversions[-1].conversion_type
            ]['weight']
        
        return journey
```

### Funnel Analytics

#### Stage-Specific Conversion Rates
```python
class FunnelAnalytics:
    """Calculate funnel metrics and conversion rates"""
    
    def calculate_stage_conversion_rates(self, date_range: Tuple[date, date]) -> dict:
        """
        Calculate conversion rates between stages.
        
        Example:
        - Account Created → Trial Started: 40%
        - Trial Started → Subscription Purchased: 60%
        - Overall Account → Purchase: 24%
        """
        start_date, end_date = date_range
        
        # Count conversions at each stage
        stage_counts = {}
        for conv_type in ConversionType:
            count = db.query(func.count(Conversion.conversion_id)).filter(
                Conversion.conversion_type == conv_type.value,
                Conversion.conversion_timestamp.between(start_date, end_date)
            ).scalar()
            stage_counts[conv_type.value] = count
        
        # Calculate conversion rates
        rates = {
            'account_to_trial_rate': self._safe_divide(
                stage_counts['trial_started'],
                stage_counts['account_created']
            ),
            'trial_to_purchase_rate': self._safe_divide(
                stage_counts['subscription_purchased'],
                stage_counts['trial_started']
            ),
            'account_to_purchase_rate': self._safe_divide(
                stage_counts['subscription_purchased'],
                stage_counts['account_created']
            )
        }
        
        return {
            'stage_counts': stage_counts,
            'conversion_rates': rates,
            'date_range': date_range
        }
    
    def calculate_stage_attribution(self, date_range: Tuple[date, date]) -> dict:
        """
        Attribution breakdown by stage.
        Shows which campaigns drive which stages.
        """
        results = {}
        
        for conv_type in ConversionType:
            # Group by attributed campaign
            campaign_stats = db.query(
                Conversion.attributed_utm_campaign,
                func.count(Conversion.conversion_id).label('conversions'),
                func.sum(Conversion.attributed_cost).label('total_cost'),
                func.avg(Conversion.time_to_conversion_hours).label('avg_time_to_conversion')
            ).filter(
                Conversion.conversion_type == conv_type.value,
                Conversion.conversion_timestamp.between(date_range[0], date_range[1]),
                Conversion.attributed_utm_campaign.isnot(None)
            ).group_by(
                Conversion.attributed_utm_campaign
            ).all()
            
            results[conv_type.value] = [
                {
                    'campaign': stat.attributed_utm_campaign,
                    'conversions': stat.conversions,
                    'total_cost': float(stat.total_cost or 0),
                    'avg_cost_per_conversion': float(stat.total_cost or 0) / stat.conversions,
                    'avg_time_to_conversion_hours': float(stat.avg_time_to_conversion or 0)
                }
                for stat in campaign_stats
            ]
        
        return results
    
    def calculate_cost_per_stage(self, date_range: Tuple[date, date]) -> dict:
        """
        Calculate cost to acquire user at each stage.
        
        Example:
        - Cost per Account: $5
        - Cost per Trial: $8 (accounts that started trial)
        - Cost per Purchase: $45 (trials that purchased)
        """
        costs = {}
        
        for conv_type in ConversionType:
            total_cost = db.query(func.sum(Conversion.attributed_cost)).filter(
                Conversion.conversion_type == conv_type.value,
                Conversion.conversion_timestamp.between(date_range[0], date_range[1])
            ).scalar() or 0
            
            conversion_count = db.query(func.count(Conversion.conversion_id)).filter(
                Conversion.conversion_type == conv_type.value,
                Conversion.conversion_timestamp.between(date_range[0], date_range[1])
            ).scalar()
            
            costs[conv_type.value] = {
                'total_cost': float(total_cost),
                'conversions': conversion_count,
                'cost_per_conversion': float(total_cost) / conversion_count if conversion_count > 0 else 0
            }
        
        return costs
    
    def calculate_time_to_convert(self, date_range: Tuple[date, date]) -> dict:
        """
        Calculate median time between funnel stages.
        """
        time_metrics = {}
        
        # Account → Trial
        account_to_trial = db.query(
            func.extract('epoch', 
                Conversion.conversion_timestamp - 
                db.query(Conversion.conversion_timestamp)
                    .filter(Conversion.conversion_id == Conversion.previous_conversion_id)
                    .scalar_subquery()
            ) / 3600  # Convert to hours
        ).filter(
            Conversion.conversion_type == ConversionType.TRIAL_STARTED.value,
            Conversion.previous_conversion_id.isnot(None),
            Conversion.conversion_timestamp.between(date_range[0], date_range[1])
        ).all()
        
        time_metrics['account_to_trial_hours'] = {
            'median': statistics.median([t[0] for t in account_to_trial if t[0]]),
            'p25': statistics.quantiles([t[0] for t in account_to_trial if t[0]], n=4)[0],
            'p75': statistics.quantiles([t[0] for t in account_to_trial if t[0]], n=4)[2]
        }
        
        # Similar for Trial → Purchase
        
        return time_metrics
    
    def _safe_divide(self, numerator: float, denominator: float) -> float:
        """Safe division with zero check"""
        return numerator / denominator if denominator > 0 else 0
```

### Weighted Attribution Value

For campaigns that drive early-stage conversions, calculate weighted value:

```python
class WeightedAttributionCalculator:
    """
    Calculate attribution value considering funnel stage weights.
    Early-stage conversions have lower value than later stages.
    """
    
    def calculate_campaign_weighted_value(self, campaign_id: str, date_range: Tuple[date, date]) -> dict:
        """
        Calculate total weighted value of conversions for a campaign.
        
        Example:
        - 100 accounts created (weight 0.33) = 33 weighted conversions
        - 40 trials started (weight 0.67) = 26.8 weighted conversions
        - 15 purchases (weight 1.0) = 15 weighted conversions
        - Total weighted value = 74.8
        """
        conversions = db.query(Conversion).filter(
            Conversion.attributed_campaign_id == campaign_id,
            Conversion.conversion_timestamp.between(date_range[0], date_range[1])
        ).all()
        
        weighted_value = 0
        stage_breakdown = {stage.value: 0 for stage in ConversionType}
        
        for conv in conversions:
            weight = ConversionConfig.CONVERSION_STAGES[conv.conversion_type]['weight']
            value = ConversionConfig.CONVERSION_STAGES[conv.conversion_type]['value']
            
            weighted_value += weight
            stage_breakdown[conv.conversion_type] += 1
        
        total_cost = sum(float(c.attributed_cost or 0) for c in conversions)
        
        return {
            'campaign_id': campaign_id,
            'total_conversions': len(conversions),
            'weighted_value': weighted_value,
            'stage_breakdown': stage_breakdown,
            'total_cost': total_cost,
            'cost_per_weighted_conversion': total_cost / weighted_value if weighted_value > 0 else 0
        }
```

### Reporting Views

#### Funnel Overview Report
```sql
-- SQL view for funnel overview
CREATE VIEW funnel_overview AS
SELECT
    DATE(c.conversion_timestamp) as conversion_date,
    c.conversion_type,
    c.attributed_utm_campaign,
    c.attributed_utm_source,
    COUNT(DISTINCT c.conversion_id) as conversions,
    COUNT(DISTINCT c.resolved_user_id) as unique_users,
    SUM(c.attributed_cost) as total_cost,
    AVG(c.attributed_cost) as avg_cost_per_conversion,
    AVG(c.time_to_conversion_hours) as avg_time_to_conversion,
    SUM(c.conversion_value) as total_revenue
FROM conversions c
WHERE c.attributed_at IS NOT NULL
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, 2;
```

#### Cohort Analysis
```python
class CohortAnalyzer:
    """Analyze user cohorts through funnel stages"""
    
    def analyze_monthly_cohorts(self, start_month: date) -> dict:
        """
        Track cohorts by month they created account.
        Show progression through funnel over time.
        
        Example:
        - November 2024 cohort: 1000 accounts → 400 trials → 240 purchases
        - December 2024 cohort: 1200 accounts → 480 trials → ? (still converting)
        """
        cohorts = {}
        
        # Get users who created accounts in target month
        account_conversions = db.query(Conversion).filter(
            Conversion.conversion_type == ConversionType.ACCOUNT_CREATED.value,
            func.date_trunc('month', Conversion.conversion_timestamp) == start_month
        ).all()
        
        cohort_user_ids = [c.resolved_user_id for c in account_conversions]
        
        # Count progression through stages
        for conv_type in ConversionType:
            count = db.query(func.count(Conversion.conversion_id)).filter(
                Conversion.conversion_type == conv_type.value,
                Conversion.resolved_user_id.in_(cohort_user_ids)
            ).scalar()
            
            cohorts[conv_type.value] = count
        
        return {
            'cohort_month': start_month,
            'cohort_size': len(cohort_user_ids),
            'funnel_progression': cohorts,
            'conversion_rates': {
                'account_to_trial': cohorts['trial_started'] / len(cohort_user_ids),
                'trial_to_purchase': cohorts['subscription_purchased'] / cohorts['trial_started'] 
                    if cohorts['trial_started'] > 0 else 0
            }
        }
```

## Consequences

### Positive
- **Independent attribution**: Each stage attributed separately shows full picture
- **Flexible analysis**: Can analyze by stage, campaign, time
- **Progressive value tracking**: Understand value creation at each step
- **Drop-off identification**: See where users leave funnel
- **Campaign optimization**: Identify which campaigns drive which stages
- **Cohort analysis**: Track long-term funnel progression

### Negative
- **Complexity**: More complex than single conversion point
- **Cost allocation**: Summing costs across stages may double-count
- **Data volume**: 3x more conversion records than simple model
- **Reporting complexity**: Stakeholders must understand multi-stage model

### Risks & Mitigations

- **Risk**: Confusion over "which conversion to optimize for"
  - *Mitigation*: Clear documentation; weighted value metric
  
- **Risk**: Double-counting costs (attributing same user multiple times)
  - *Mitigation*: Separate reporting: cost per stage vs. total user acquisition cost
  
- **Risk**: Users skipping stages (trial without account)
  - *Mitigation*: Data validation; acceptable as edge case

## Alternatives Considered

### Alternative 1: Single Conversion (Purchase Only)
Only track final purchase, ignore intermediate stages.

**Rejected because**:
- Loses visibility into funnel performance
- Can't optimize early-stage marketing
- Can't identify drop-off points

### Alternative 2: Last Touch to First Conversion Only
Attribute only account creation, not subsequent stages.

**Rejected because**:
- Doesn't show which campaigns drive trial/purchase
- Incomplete attribution story

### Alternative 3: Cumulative Attribution
First touchpoint gets credit for all downstream conversions.

**Rejected because**:
- Doesn't reflect actual behavior (users may have new touches between stages)
- Over-credits early touchpoints

## Implementation Notes

### Phase 1 (MVP)
- Track all three conversion types
- Independent attribution per stage
- Basic funnel metrics (counts, rates)
- Stage-specific cost reporting

### Phase 2 (Enhanced)
- Cohort analysis dashboards
- Weighted attribution value
- Funnel visualization
- Anomaly detection (unusual stage timing)

### Monitoring
- Daily funnel conversion rates
- Stage-to-stage progression time
- Drop-off rates by stage
- Cost per stage trends

## References
- [Conversion Funnel Analysis](https://www.optimizely.com/optimization-glossary/conversion-funnel/)
- [Multi-Stage Attribution Models](https://www.singular.net/blog/multi-touch-attribution/)

## Related ADRs
- ADR-006: Attribution Model Implementation
- ADR-003: Data Storage Design
- ADR-005: Cost Calculation Engine
