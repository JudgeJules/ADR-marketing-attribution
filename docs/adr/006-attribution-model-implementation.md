# ADR-006: Attribution Model Implementation

## Status
Proposed

## Context
Attribution models determine which touchpoints receive credit for conversions. For MVP, we're implementing **last-touch attribution** (the final touchpoint before conversion gets 100% credit), with architecture designed to support future models (first-touch, linear, time-decay, algorithmic).

### Requirements
- Implement last-touch attribution for MVP
- Support multiple conversion types (account_created, trial_started, subscription_purchased)
- Handle conversion funnel progression (account → trial → purchase)
- Attribute costs to conversions based on credited touchpoint
- Design for future multi-touch attribution models
- Work with Segment's identity-resolved user journeys

### Attribution Challenge
Users progress through a multi-step funnel:
```
Anonymous touchpoints → Account Created → Trial Started → Purchase (Day 14)
```

Each step is a conversion that needs attribution. We need to decide:
- Does "Trial Started" get attributed to the last touch before trial, or before account creation?
- How do we weigh different conversion types for ROI calculations?

## Decision
We will implement a **last-touch attribution model** with **funnel-aware logic**:

1. **Last touchpoint before each conversion** gets 100% credit for that specific conversion
2. **Each conversion type** is attributed independently
3. **Conversion value weighting** differentiates importance (account < trial < purchase)
4. **Architecture supports future models** through strategy pattern

### Attribution Algorithm

```python
class LastTouchAttributionModel:
    """
    Last-touch attribution: The final marketing touchpoint before conversion
    receives 100% credit for that conversion.
    """
    
    def attribute_conversion(self, conversion: Conversion) -> Attribution:
        """
        Find the last marketing touchpoint before conversion and attribute it.
        """
        # Get user's touchpoint journey before conversion
        touchpoints = db.query(Touchpoint).filter(
            Touchpoint.resolved_user_id == conversion.resolved_user_id,
            Touchpoint.event_timestamp < conversion.conversion_timestamp
        ).order_by(Touchpoint.event_timestamp.desc()).all()
        
        # Filter to marketing touchpoints only (exclude organic/direct)
        marketing_touchpoints = [
            tp for tp in touchpoints
            if self.is_marketing_touchpoint(tp)
        ]
        
        if not marketing_touchpoints:
            # No marketing touchpoints found
            return Attribution(
                conversion_id=conversion.conversion_id,
                attributed_touchpoint_id=None,
                attribution_model='last_touch',
                attributed_cost=None,
                attribution_reason='no_marketing_touchpoints'
            )
        
        # Last marketing touchpoint gets credit
        last_touchpoint = marketing_touchpoints[0]
        
        # Calculate time between touchpoint and conversion
        time_diff = conversion.conversion_timestamp - last_touchpoint.event_timestamp
        time_to_conversion_hours = time_diff.total_seconds() / 3600
        
        return Attribution(
            conversion_id=conversion.conversion_id,
            attributed_touchpoint_id=last_touchpoint.touchpoint_id,
            attribution_model='last_touch',
            attributed_cost=last_touchpoint.estimated_cost,
            attributed_campaign_id=last_touchpoint.campaign_id,
            attributed_utm_source=last_touchpoint.utm_source,
            attributed_utm_medium=last_touchpoint.utm_medium,
            attributed_utm_campaign=last_touchpoint.utm_campaign,
            time_to_conversion_hours=time_to_conversion_hours,
            touchpoints_in_journey=len(touchpoints),
            attribution_reason='last_marketing_touch'
        )
    
    def is_marketing_touchpoint(self, touchpoint: Touchpoint) -> bool:
        """
        Determine if touchpoint is a marketing touchpoint (paid/earned).
        Excludes direct traffic and internal referrals.
        """
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
        
        # Has referrer (organic social, earned media)
        if touchpoint.referrer and not self.is_internal_referrer(touchpoint.referrer):
            return True
        
        return False
    
    def is_internal_referrer(self, referrer: str) -> bool:
        """Check if referrer is internal (own domain)"""
        internal_domains = ['yourdomain.com', 'app.yourdomain.com']
        return any(domain in referrer for domain in internal_domains)
```

### Funnel-Aware Attribution

Each conversion type is attributed to the last touch **before that specific conversion**:

```python
class ConversionFunnelAttributor:
    """
    Attributes each funnel stage independently to the last touch before that stage.
    """
    
    CONVERSION_TYPES = {
        'account_created': {'value': 0, 'stage': 1},
        'trial_started': {'value': 0, 'stage': 2},
        'subscription_purchased': {'value': 30, 'stage': 3}  # Example: $30 LTV
    }
    
    def attribute_user_conversions(self, user_id: str):
        """
        Attribute all conversions for a user through the funnel.
        Each conversion attributed independently.
        """
        conversions = db.query(Conversion).filter(
            Conversion.resolved_user_id == user_id
        ).order_by(Conversion.conversion_timestamp.asc()).all()
        
        model = LastTouchAttributionModel()
        
        for conversion in conversions:
            # Find last touch before THIS conversion
            attribution = model.attribute_conversion(conversion)
            
            # Update conversion with attribution
            conversion.attributed_touchpoint_id = attribution.attributed_touchpoint_id
            conversion.attribution_model = attribution.attribution_model
            conversion.attributed_cost = attribution.attributed_cost
            conversion.attributed_campaign_id = attribution.attributed_campaign_id
            conversion.attributed_utm_source = attribution.attributed_utm_source
            conversion.attributed_utm_medium = attribution.attributed_utm_medium
            conversion.attributed_utm_campaign = attribution.attributed_utm_campaign
            conversion.time_to_conversion_hours = attribution.time_to_conversion_hours
            conversion.touchpoints_in_journey = attribution.touchpoints_in_journey
            conversion.attributed_at = datetime.now()
            
            # Set conversion value from config
            conversion.conversion_value = self.CONVERSION_TYPES.get(
                conversion.conversion_type, {}
            ).get('value', 0)
        
        db.commit()
```

### Real-time Attribution on Conversion Events

When a conversion event arrives from Segment, trigger attribution immediately:

```python
class ConversionEventHandler:
    """
    Handles conversion events from Segment and triggers attribution.
    """
    
    def handle_conversion_event(self, event: SegmentEvent):
        """
        Process conversion event from Segment and run attribution.
        """
        # Create conversion record
        conversion = Conversion(
            event_id=event.message_id,
            segment_user_id=event.user_id,
            resolved_user_id=event.user_id or event.anonymous_id,
            conversion_type=self.map_event_to_conversion_type(event.event),
            conversion_timestamp=event.timestamp,
            properties=event.properties
        )
        db.add(conversion)
        db.commit()
        
        # Run attribution
        model = LastTouchAttributionModel()
        attribution = model.attribute_conversion(conversion)
        
        # Update conversion
        conversion.attributed_touchpoint_id = attribution.attributed_touchpoint_id
        conversion.attributed_cost = attribution.attributed_cost
        # ... (other attribution fields)
        db.commit()
        
        # Emit enriched conversion back to Segment
        self.emit_attributed_conversion_to_segment(conversion, attribution)
    
    def map_event_to_conversion_type(self, event_name: str) -> str:
        """Map Segment event names to conversion types"""
        mapping = {
            'Account Created': 'account_created',
            'Signed Up': 'account_created',
            'Trial Started': 'trial_started',
            'Subscription Purchased': 'subscription_purchased',
            'Order Completed': 'subscription_purchased'
        }
        return mapping.get(event_name, 'unknown')
```

### Attribution Architecture (Strategy Pattern)

Design for future multi-touch models:

```python
class AttributionModel(ABC):
    """Abstract base class for attribution models"""
    
    @abstractmethod
    def attribute_conversion(self, conversion: Conversion) -> Attribution:
        """Attribute conversion to touchpoint(s)"""
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """Return model identifier"""
        pass

class LastTouchAttributionModel(AttributionModel):
    def get_model_name(self) -> str:
        return 'last_touch'
    
    # ... (implementation above)

# Future models
class FirstTouchAttributionModel(AttributionModel):
    def get_model_name(self) -> str:
        return 'first_touch'
    
    def attribute_conversion(self, conversion: Conversion) -> Attribution:
        # Find FIRST marketing touchpoint
        pass

class LinearAttributionModel(AttributionModel):
    def get_model_name(self) -> str:
        return 'linear'
    
    def attribute_conversion(self, conversion: Conversion) -> List[Attribution]:
        # Credit distributed equally across all touchpoints
        pass

class AttributionEngine:
    """Main engine that delegates to specific models"""
    
    def __init__(self):
        self.models = {
            'last_touch': LastTouchAttributionModel(),
            'first_touch': FirstTouchAttributionModel(),
            'linear': LinearAttributionModel()
        }
    
    def attribute_conversion(self, conversion: Conversion, model_name: str = 'last_touch'):
        model = self.models.get(model_name)
        if not model:
            raise ValueError(f"Unknown attribution model: {model_name}")
        
        return model.attribute_conversion(conversion)
```

### Attribution Window

Define how far back to look for touchpoints:

```python
class AttributionConfig:
    """Configuration for attribution behavior"""
    
    # Maximum days to look back for touchpoints
    ATTRIBUTION_WINDOW_DAYS = {
        'account_created': 30,
        'trial_started': 30,
        'subscription_purchased': 90  # Longer window for purchase
    }
    
    # Minimum days between touchpoint and conversion to count
    MIN_TOUCHPOINT_AGE_HOURS = 0  # Immediate effect allowed
    
    # Whether to include organic/direct touchpoints
    INCLUDE_ORGANIC = False
    INCLUDE_DIRECT = False
```

### Handling Edge Cases

#### Multiple Conversions Same Touchpoint
```python
# User clicks ad → creates account → starts trial same day
# Both conversions attributed to same touchpoint (allowed)
# This is accurate: one ad click drove two conversion events
```

#### Conversion Before Any Touchpoints
```python
# User converts but we have no touchpoint data (new user in system)
# Attribution: None
# attributed_touchpoint_id = NULL
# attribution_reason = 'no_touchpoints_found'
```

#### Identity Stitching After Attribution
```python
# Anonymous touchpoints → attributed conversion → identity stitch
# Need to re-attribute after stitch to find previously anonymous touchpoints
# Trigger: Listen for identity.stitched Kafka events
# Action: Re-run attribution for affected conversions
```

## Consequences

### Positive
- **Simple to understand**: Last-touch is intuitive for stakeholders
- **Fast to compute**: Single query to find last touchpoint
- **Deterministic**: Same inputs always produce same output
- **Real-time capable**: Can attribute on conversion event arrival
- **Funnel-aware**: Each conversion stage attributed independently
- **Extensible architecture**: Easy to add new attribution models

### Negative
- **Oversimplifies journey**: Ignores earlier touchpoints that influenced decision
- **Recency bias**: Over-credits late-stage tactics (e.g., retargeting)
- **Channel bias**: May under-value upper-funnel awareness campaigns
- **Not suitable for complex journeys**: Multi-touch would be more accurate

### Risks & Mitigations

- **Risk**: Stakeholders want to know "first touch" impact
  - *Mitigation*: Store full journey; can run first-touch reports separately
  
- **Risk**: Attribution changes after identity stitching
  - *Mitigation*: Accept eventual consistency; log re-attribution events
  
- **Risk**: No touchpoint data for new users
  - *Mitigation*: Track "unattributed" conversions; acceptable for MVP
  
- **Risk**: Gaming the system (last-click hijacking)
  - *Mitigation*: Monitor attribution patterns; add fraud detection later

## Alternatives Considered

### Alternative 1: Multi-Touch Attribution (Linear)
Distribute credit equally across all touchpoints.

**Deferred (not rejected)**: Planned for Phase 2 after MVP validates system

### Alternative 2: Data-Driven Attribution
Use ML to learn optimal credit distribution.

**Deferred**: Requires significant historical data; Phase 3 consideration

### Alternative 3: Position-Based Attribution
40% first touch, 40% last touch, 20% distributed middle.

**Deferred**: More complex; defer until MVP validated

### Alternative 4: Time-Decay Attribution
More recent touchpoints get more credit (exponential decay).

**Deferred**: Phase 2 consideration after last-touch validated

## Implementation Notes

### Phase 1 (MVP)
- Last-touch only
- Real-time attribution on conversion events
- Funnel-aware (each conversion attributed independently)
- No attribution window (look back unlimited)
- Accept ~5-10% unattributed conversions

### Phase 2 (Multi-Touch)
- Implement first-touch and linear models
- Run multiple models simultaneously for comparison
- Add attribution window enforcement
- Journey visualization in analytics

### Phase 3 (Advanced)
- Data-driven/algorithmic attribution
- Cross-device attribution (if Segment supports)
- Attribution decay models
- A/B test attribution models

### Testing Strategy
```python
def test_last_touch_attribution():
    # Create user journey
    user_id = 'user_123'
    create_touchpoint(user_id, timestamp='2024-12-01 10:00', utm_campaign='campaign_a')
    create_touchpoint(user_id, timestamp='2024-12-01 14:00', utm_campaign='campaign_b')
    create_touchpoint(user_id, timestamp='2024-12-01 18:00', utm_campaign='campaign_c')
    
    # Create conversion
    conversion = create_conversion(user_id, timestamp='2024-12-01 19:00')
    
    # Run attribution
    model = LastTouchAttributionModel()
    attribution = model.attribute_conversion(conversion)
    
    # Assert last touchpoint (campaign_c) gets credit
    assert attribution.attributed_utm_campaign == 'campaign_c'
    assert attribution.time_to_conversion_hours == 1.0
```

### Monitoring Metrics
- Attribution rate (% conversions with attributed touchpoint)
- Time-to-conversion distribution
- Touchpoints per conversion (journey length)
- Top attributed campaigns/sources/mediums
- Cost per attributed conversion by type
- ROI by conversion type

## References
- [Attribution Models Explained](https://support.google.com/analytics/answer/1662518)
- [Last-Click Attribution Bias](https://www.marketingevolution.com/knowledge-center/last-click-attribution)
- [Multi-Touch Attribution Guide](https://www.singular.net/glossary/multi-touch-attribution/)

## Related ADRs
- ADR-002: Identity Resolution Strategy
- ADR-003: Data Storage Design
- ADR-005: Cost Calculation Engine
- ADR-008: Conversion Funnel Modeling
