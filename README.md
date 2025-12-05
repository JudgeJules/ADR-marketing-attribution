# Attribution System - Architectural Decision Records

## Overview
This directory contains the architectural decision records (ADRs) for the Marketing Attribution System that ingests real-time touchpoint data, performs cost attribution calculations, and integrates bidirectionally with Segment CDP.

## System Goals
- Ingest real-time marketing touchpoints from multiple sources via Segment
- Store and process anonymous and authenticated user journeys
- Calculate cost per touchpoint based on ad platform performance data
- Enrich conversion events with attribution data and emit back to Segment
- Support last-touch attribution model (MVP) with extensibility for future models

## ADR Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](adr-001-event-ingestion-architecture.md) | Event Ingestion Architecture | Proposed |
| [ADR-002](adr-002-identity-resolution-strategy.md) | Identity Resolution Strategy | Proposed |
| [ADR-003](adr-003-data-storage-design.md) | Data Storage Design | Proposed |
| [ADR-004](adr-004-ad-platform-cost-ingestion.md) | Ad Platform Cost Data Ingestion | Proposed |
| [ADR-005](adr-005-cost-calculation-engine.md) | Cost Calculation Engine | Proposed |
| [ADR-006](adr-006-attribution-model-implementation.md) | Attribution Model Implementation | Proposed |
| [ADR-007](adr-007-segment-bidirectional-integration.md) | Segment Bidirectional Integration | Proposed |
| [ADR-008](adr-008-conversion-funnel-modeling.md) | Conversion Funnel Modeling | Proposed |

## Quick Reference

### Key Technologies
- **Streaming**: Kafka (corporate standard)
- **Data Warehouse**: Redshift (corporate standard)
- **OLTP Database**: PostgreSQL
- **CDP**: Segment
- **Ad Platforms**: Google Ads (initially)

### Key Design Principles
1. **CDP-First**: Leverage Segment for identity resolution; don't create duplicate identity graphs
2. **Stream-First**: Prefer streaming architecture for real-time processing where feasible
3. **Extensibility**: Design for future attribution models and additional ad platforms
4. **Estimation Tolerance**: Accept gaps in cost data for MVP; improve over time

### Event Flow
```
Marketing Touchpoints (Segment) 
    → Kafka Topic (touchpoints)
    → Attribution Service (process & enrich)
    → Storage (PostgreSQL + Redshift)
    
Ad Platform APIs (Google Ads)
    → Daily Batch Job
    → Cost Calculation Engine
    → Storage (PostgreSQL)
    
Conversion Events (Segment)
    → Kafka Topic (conversions)
    → Attribution Lookup (last-touch)
    → Cost Enrichment
    → Emit to Segment (custom source)
```

## Document Status
- **Proposed**: Decision is proposed but not yet accepted
- **Accepted**: Decision has been accepted and is being implemented
- **Deprecated**: Decision has been superseded by a later decision
- **Superseded**: Decision has been replaced (with link to replacement)

## Contributing
When adding new ADRs, please follow the template structure and update this index.
