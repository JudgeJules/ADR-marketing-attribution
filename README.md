# Attribution System - Marketing Attribution MVP

## Overview
A marketing attribution system that ingests real-time touchpoint data, performs cost attribution calculations, and integrates bidirectionally with Segment CDP.

## System Goals
- Ingest real-time marketing touchpoints from multiple sources via Segment
- Store and process anonymous and authenticated user journeys
- Calculate cost per touchpoint based on ad platform performance data
- Enrich conversion events with attribution data and emit back to Segment
- Support last-touch attribution model (MVP) with extensibility for future models

## Quick Start

### One-Command Deploy

```bash
./deploy.sh
```

The deploy script will walk you through:
- Prerequisites check
- Virtual environment setup
- Dependency installation
- System configuration
- Database initialization
- Installation testing

### Manual Installation

See [Quick Start Guide](docs/QUICK_START.md) for detailed manual setup instructions.

```bash
# Install dependencies
pip install -r requirements.txt

# Configure system
python configure.py

# Initialize database
python scripts/init_db.py

# Start the system
python -m attribution.app
```

## Project Structure

```
attribution-mvp/
├── src/attribution/         # Main application code
│   ├── app.py              # Flask web server & webhook receiver
│   └── jobs/               # Background job modules
│       ├── fetch_costs.py
│       ├── calculate_costs.py
│       ├── run_attribution.py
│       └── send_to_segment.py
│
├── scripts/                # Standalone scripts
│   └── init_db.py         # Database initialization
│
├── docs/                   # Documentation
│   ├── adr/               # Architecture Decision Records
│   ├── QUICK_START.md     # Quick start guide
│   ├── PROJECT_SUMMARY.md # Comprehensive project overview
│   └── *.md               # Additional documentation
│
├── setup.py               # Package installation config
├── configure.py           # Interactive setup wizard
├── requirements.txt       # Python dependencies
└── .env.example          # Configuration template
```

## Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](docs/adr/001-event-ingestion-architecture.md) | Event Ingestion Architecture | Proposed |
| [ADR-002](docs/adr/002-identity-resolution-strategy.md) | Identity Resolution Strategy | Proposed |
| [ADR-003](docs/adr/003-data-storage-design.md) | Data Storage Design | Proposed |
| [ADR-004](docs/adr/004-ad-platform-cost-ingestion.md) | Ad Platform Cost Data Ingestion | Proposed |
| [ADR-005](docs/adr/005-cost-calculation-engine.md) | Cost Calculation Engine | Proposed |
| [ADR-006](docs/adr/006-attribution-model-implementation.md) | Attribution Model Implementation | Proposed |
| [ADR-007](docs/adr/007-segment-bidirectional-integration.md) | Segment Bidirectional Integration | Proposed |
| [ADR-008](docs/adr/008-conversion-funnel-modeling.md) | Conversion Funnel Modeling | Proposed |

## Key Technologies
- **Streaming**: Kafka (corporate standard)
- **Data Warehouse**: Redshift (corporate standard)
- **OLTP Database**: PostgreSQL (SQLite for MVP)
- **CDP**: Segment
- **Ad Platforms**: Google Ads (initially)
- **Language**: Python 3.11+

## Key Design Principles
1. **CDP-First**: Leverage Segment for identity resolution; don't create duplicate identity graphs
2. **Stream-First**: Prefer streaming architecture for real-time processing where feasible
3. **Extensibility**: Design for future attribution models and additional ad platforms
4. **Estimation Tolerance**: Accept gaps in cost data for MVP; improve over time

## Event Flow
```
Marketing Touchpoints (Segment) 
    → Webhook Receiver
    → Storage (SQLite/PostgreSQL)
    
Ad Platform APIs (Google Ads)
    → Daily Batch Job
    → Cost Calculation Engine
    → Storage
    
Conversion Events (Segment)
    → Webhook Receiver
    → Attribution Lookup (last-touch)
    → Cost Enrichment
    → Emit to Segment (custom source)
```

## Documentation

- [Quick Start Guide](docs/QUICK_START.md) - Get up and running in 20 minutes
- [Project Summary](docs/PROJECT_SUMMARY.md) - Comprehensive system overview
- [Implementation Roadmap](docs/IMPLEMENTATION_ROADMAP.md) - 16-week phased plan
- [Architecture Diagram](docs/ARCHITECTURE_DIAGRAM.md) - Visual system architecture
- [Code Templates](docs/CODE_TEMPLATES.md) - Ready-to-use code snippets
- [Deployment Summary](docs/DEPLOYMENT_SUMMARY.md) - Deployment guide
- [MVP Deployment Plan](docs/MVP_DEPLOYMENT_PLAN.md) - MVP-specific deployment

## API Endpoints

- `POST /webhooks/segment` - Receive events from Segment
- `GET /dashboard` - Monitoring dashboard
- `GET /api/stats` - System statistics (JSON)
- `GET /health` - Health check

## Background Jobs

Scheduled automatically:
- **2:00 AM daily** - Fetch Google Ads costs
- **3:00 AM daily** - Calculate touchpoint costs
- **Every 5 minutes** - Run attribution
- **Every 5 minutes** - Send to Segment

## Contributing

When adding new ADRs, please follow the template structure and update this index.

## Document Status
- **Proposed**: Decision is proposed but not yet accepted
- **Accepted**: Decision has been accepted and is being implemented
- **Deprecated**: Decision has been superseded by a later decision
- **Superseded**: Decision has been replaced (with link to replacement)

---

**Version**: 0.1.0  
**Status**: MVP Ready  
**Deployment Time**: 20 minutes  
**Monthly Cost**: $0 (local) / varies (cloud)
