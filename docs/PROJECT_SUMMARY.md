# Attribution System - Project Summary

## What You Have

This package contains a complete set of **Architectural Decision Records (ADRs)** and supporting documentation for building a marketing attribution system that integrates with Segment CDP and ad platforms (starting with Google Ads).

## Document Overview

### Core ADRs
1. **[ADR-001: Event Ingestion Architecture](adr-001-event-ingestion-architecture.md)**
   - Kafka-based streaming ingestion from Segment webhook
   - Event routing and validation
   - Real-time processing pipeline

2. **[ADR-002: Identity Resolution Strategy](adr-002-identity-resolution-strategy.md)**
   - Leverage Segment CDP for identity stitching
   - Anonymous → authenticated user mapping
   - Retroactive touchpoint updates

3. **[ADR-003: Data Storage Design](adr-003-data-storage-design.md)**
   - Hybrid PostgreSQL (hot) + Redshift (cold) architecture
   - Detailed schema for touchpoints, conversions, campaign costs
   - Partitioning and index strategies

4. **[ADR-004: Ad Platform Cost Ingestion](adr-004-ad-platform-cost-ingestion.md)**
   - Daily batch fetching from Google Ads API
   - Plugin architecture for multiple ad platforms
   - Cost metric calculations (CPC, CTR, CPM)

5. **[ADR-005: Cost Calculation Engine](adr-005-cost-calculation-engine.md)**
   - 4-tier cost estimation strategy
   - Median CPC calculations
   - Handling missing/incomplete data

6. **[ADR-006: Attribution Model Implementation](adr-006-attribution-model-implementation.md)**
   - Last-touch attribution (MVP)
   - Extensible design for future multi-touch models
   - Marketing touchpoint filtering logic

7. **[ADR-007: Segment Bidirectional Integration](adr-007-segment-bidirectional-integration.md)**
   - Inbound: Webhook receiver for events
   - Outbound: HTTP API to send attributed conversions
   - Event schema mapping

8. **[ADR-008: Conversion Funnel Modeling](adr-008-conversion-funnel-modeling.md)**
   - Multi-stage funnel tracking (Account → Trial → Purchase)
   - Independent attribution per stage
   - Funnel analytics and cohort analysis

### Supporting Documents
- **[README.md](README.md)** - Index of all ADRs and system overview
- **[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)** - 16-week phased implementation plan
- **[ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)** - Visual system architecture with data flows
- **[CODE_TEMPLATES.md](CODE_TEMPLATES.md)** - Ready-to-use code for key components

## System Architecture at a Glance

```
Segment CDP (Identity & Events)
    ↓ Webhook (Touchpoints & Conversions)
Kafka (Event Streaming)
    ↓ Processors
PostgreSQL (Operational Storage, 90 days)
    ↓ Daily Export
Redshift (Analytical Storage, Forever)

Google Ads API (Daily Batch)
    ↓ Campaign Costs
Cost Calculation Engine
    ↓ Enrich Touchpoints
Attribution Engine (Real-time)
    ↓ Attributed Conversions
Segment CDP (Enriched Profiles)
```

## Key Design Decisions

### 1. CDP-First Approach
- **Decision**: Use Segment as the single source of truth for identity resolution
- **Rationale**: Avoid duplicate identity graphs, leverage Segment's core strength
- **Impact**: Simpler architecture, but dependent on Segment's identity timing

### 2. Streaming Architecture
- **Decision**: Kafka-based event processing instead of direct database writes
- **Rationale**: Scalability, replay capability, decoupled components
- **Trade-off**: Additional operational complexity for better flexibility

### 3. Hybrid Storage
- **Decision**: PostgreSQL for operational queries, Redshift for analytics
- **Rationale**: Right tool for each job - fast lookups vs. complex analysis
- **Trade-off**: Data duplication and sync complexity

### 4. Last-Touch Attribution (MVP)
- **Decision**: Start with simple last-touch model
- **Rationale**: Easier to build and explain, validates system before complexity
- **Future**: Architecture supports multi-touch models

### 5. Multi-Tier Cost Calculation
- **Decision**: 4-tier fallback strategy for cost estimation
- **Rationale**: Handle missing data gracefully while preferring accuracy
- **Trade-off**: Some touchpoints have estimated (not exact) costs

## Implementation Timeline

- **Phase 1 (Weeks 1-6)**: Core infrastructure and data pipeline
- **Phase 2 (Weeks 7-10)**: Attribution engine and Segment integration
- **Phase 3 (Weeks 11-13)**: Analytics and reporting
- **Phase 4 (Weeks 14-16)**: Productionization and optimization

**Total MVP**: ~4 months to fully operational system

## Success Metrics

### Technical
- ✅ 95%+ event ingestion success rate
- ✅ 80%+ touchpoints with cost estimates
- ✅ 90%+ conversions attributed
- ✅ < 5 min lag from conversion to Segment enrichment

### Business
- 📊 Cost per Account Created
- 📊 Cost per Trial Started
- 📊 Cost per Purchase
- 📊 ROI by campaign/source/medium
- 📊 Funnel conversion rates

## Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Event Ingestion | Kafka | Corporate standard, scalable streaming |
| Webhook API | FastAPI (Python) | Fast, modern, async-capable |
| Operational DB | PostgreSQL 15 | Reliable, feature-rich, indexes |
| Analytics DB | Redshift | Corporate standard, optimized for OLAP |
| CDP | Segment | Existing infrastructure |
| Ad Platform | Google Ads API | Starting point, extensible |
| Language | Python 3.11+ | Team expertise, rich ecosystem |

## What Makes This Different

### 1. CDP Integration
Most attribution systems are standalone. This one integrates bidirectionally with your existing Segment CDP, enriching customer profiles with attribution data.

### 2. Funnel-Aware
Tracks multi-stage conversions (Account → Trial → Purchase) with independent attribution per stage, not just final purchase.

### 3. Cost-First
Built around cost attribution from day one, not just touchpoint tracking. Every conversion knows its acquisition cost.

### 4. Extensible by Design
Plugin architecture for ad platforms, strategy pattern for attribution models. Easy to add new capabilities.

### 5. Handles Reality
Designed for incomplete data, delayed cost reporting, identity resolution timing. The real world isn't perfect.

## Quick Start

1. **Review the ADRs** (start with README.md)
2. **Set up development environment** (Docker Compose from CODE_TEMPLATES.md)
3. **Follow IMPLEMENTATION_ROADMAP.md** week by week
4. **Use CODE_TEMPLATES.md** for starter implementations
5. **Reference ARCHITECTURE_DIAGRAM.md** when understanding data flows

## Critical Questions to Answer

Before implementation, clarify these with your team:

1. **Segment Configuration**
   - Webhook URL and authentication method
   - Event names for each conversion type
   - How campaign IDs appear in events

2. **Google Ads Access**
   - OAuth2 credentials and refresh tokens
   - Customer ID(s) to fetch
   - API quota limits

3. **Business Logic**
   - Exact conversion event definitions
   - Revenue/value for each conversion type
   - Attribution window preferences

4. **Infrastructure**
   - Redshift cluster availability
   - Preferred deployment environment
   - Monitoring/alerting tools

## Common Pitfalls to Avoid

1. **Don't** build your own identity graph (use Segment's)
2. **Don't** expect perfect cost data immediately (estimates are OK)
3. **Don't** over-engineer attribution models in MVP (start simple)
4. **Don't** forget idempotency (events can arrive multiple times)
5. **Don't** ignore data quality monitoring (watch for gaps)

## Next Steps

1. **Share ADRs** with engineering team for review
2. **Schedule kickoff meeting** to discuss architecture
3. **Provision infrastructure** (dev environment first)
4. **Configure Segment webhook** and test event flow
5. **Obtain Google Ads credentials**
6. **Begin Week 1 tasks** from IMPLEMENTATION_ROADMAP.md

## Questions or Concerns?

This is a comprehensive system design, but it's meant to be adapted to your specific needs. The ADRs document **decisions**, not dictates. Feel free to:

- Challenge assumptions
- Propose alternatives
- Adjust for your constraints
- Scale up or down based on volume

## Document Maintenance

These ADRs should be treated as living documents:

- **Update** when decisions change
- **Add new ADRs** for new architectural decisions
- **Mark as superseded** when approach changes
- **Reference** in code and discussions

## Attribution System Values

This system design embodies these principles:

1. **Pragmatic over Perfect** - Ship MVP, iterate based on learnings
2. **Simple over Clever** - Prefer straightforward solutions
3. **Extensible over Complete** - Build for future needs without over-engineering
4. **Observable over Opaque** - Monitor everything, hide nothing
5. **CDP-First over Build-Your-Own** - Leverage existing tools

---

## File Checklist

- ✅ README.md - System overview and ADR index
- ✅ ADR-001 - Event ingestion architecture
- ✅ ADR-002 - Identity resolution strategy
- ✅ ADR-003 - Data storage design
- ✅ ADR-004 - Ad platform cost ingestion
- ✅ ADR-005 - Cost calculation engine
- ✅ ADR-006 - Attribution model implementation
- ✅ ADR-007 - Segment bidirectional integration
- ✅ ADR-008 - Conversion funnel modeling
- ✅ IMPLEMENTATION_ROADMAP.md - Phased execution plan
- ✅ ARCHITECTURE_DIAGRAM.md - Visual system architecture
- ✅ CODE_TEMPLATES.md - Starter code implementations

## Total Documentation

- **8 ADRs** covering all major architectural decisions
- **4 supporting documents** for implementation guidance
- **~100 pages** of detailed technical documentation
- **Ready-to-use code templates** for rapid development

---

**Version**: 1.0  
**Created**: December 5, 2024  
**Status**: Ready for Implementation  
**Estimated Effort**: 16 weeks to production-ready MVP

Good luck building your attribution system! 🚀
