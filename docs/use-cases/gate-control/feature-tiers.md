# Feature Tiers & Scaling Guide

**Created:** 2026-02-15
**Updated:** 2026-02-17
**Use Case:** Scalable ALPR gate control with modular features
**Related:** [Project Structure](project-structure.md) | [Modular Deployment](modular-deployment.md) | [SaaS Business Model](saas-business-model.md)

---

> **Single Repository:** All tiers use the same **alpr-edge** codebase. Features are enabled by license configuration at runtime. See [Project Structure](project-structure.md) for the repository layout and [Modular Deployment](modular-deployment.md) for how licenses control module loading.

---

## Table of Contents

1. [Overview](#overview)
2. [Feature Matrix](#feature-matrix)
3. [Tier Descriptions](#tier-descriptions)
4. [Hardware Scaling](#hardware-scaling)
5. [Software Modules](#software-modules)
6. [Pricing Strategy](#pricing-strategy)
7. [Implementation Roadmap](#implementation-roadmap)
8. [Upsell Strategies](#upsell-strategies)
9. [Custom Enterprise Options](#custom-enterprise-options)

---

## Overview

The gate control system is designed with a modular architecture that allows scaling based on customer needs. This enables:

- **Flexible pricing** - Charge based on features used
- **Lower entry barrier** - Basic tier is affordable for small properties
- **Growth path** - Customers can upgrade as needs evolve
- **Higher margins** - Premium features have minimal cost to deliver

### Scaling Dimensions

| Dimension | How It Scales |
|-----------|---------------|
| **Cameras** | 1-2 → 4-8 → 16+ |
| **Gates** | Single → Multiple → Multi-site |
| **Users** | Single admin → Team → Enterprise roles |
| **Retention** | 7 days → 30 days → 90 days → 1 year |
| **Alerts** | Dashboard only → Email → SMS → Webhooks |
| **Analytics** | Basic logs → Reports → BI dashboards |
| **Integrations** | None → Webhooks → Custom APIs |

---

## Feature Matrix

### Complete Feature Comparison

| Feature | Basic | Standard | Professional | Enterprise |
|---------|:-----:|:--------:|:------------:|:----------:|
| **CORE FEATURES** |||||
| License plate recognition | ✅ | ✅ | ✅ | ✅ |
| Whitelist management | ✅ | ✅ | ✅ | ✅ |
| Blacklist management | ✅ | ✅ | ✅ | ✅ |
| Auto-enrollment mode | ✅ | ✅ | ✅ | ✅ |
| Gate control (open/deny) | ✅ | ✅ | ✅ | ✅ |
| Basic web dashboard | ✅ | ✅ | ✅ | ✅ |
| Local data storage | ✅ | ✅ | ✅ | ✅ |
| Offline operation | ✅ | ✅ | ✅ | ✅ |
| **CAPACITY** |||||
| Cameras | 1-2 | 2-4 | 4-8 | 8-16+ |
| Gates | 1 | 2 | 4 | Unlimited |
| Plates in whitelist | 500 | 2,000 | 10,000 | Unlimited |
| **USERS & ACCESS** |||||
| Admin users | 1 | 3 | 10 | Unlimited |
| User roles | - | - | ✅ | ✅ |
| Audit logging | Basic | Basic | Detailed | Detailed |
| SSO/LDAP | - | - | - | ✅ |
| **EVIDENCE & RETENTION** |||||
| Plate crop images | ✅ | ✅ | ✅ | ✅ |
| Full frame images | - | ✅ | ✅ | ✅ |
| Retention period | 7 days | 30 days | 90 days | 1 year |
| Export capability | - | CSV | CSV + API | Full API |
| **ALERTS & NOTIFICATIONS** |||||
| Dashboard alerts | ✅ | ✅ | ✅ | ✅ |
| Email notifications | - | ✅ | ✅ | ✅ |
| SMS notifications | - | - | ✅ | ✅ |
| Webhook notifications | - | - | ✅ | ✅ |
| Alert rules (custom) | - | - | 5 rules | Unlimited |
| **ANALYTICS & REPORTING** |||||
| Activity log | ✅ | ✅ | ✅ | ✅ |
| Daily summary | - | ✅ | ✅ | ✅ |
| Weekly/monthly reports | - | - | ✅ | ✅ |
| Peak hours analysis | - | - | ✅ | ✅ |
| Custom reports | - | - | - | ✅ |
| **ADVANCED FEATURES** |||||
| Visitor pre-registration | - | - | ✅ | ✅ |
| Temporary access codes | - | - | ✅ | ✅ |
| Vehicle type logging | - | - | ✅ | ✅ |
| Direction detection | - | - | - | ✅ |
| Speed estimation | - | - | - | ✅ |
| **INTEGRATIONS** |||||
| REST API access | - | - | ✅ | ✅ |
| Webhook events | - | - | ✅ | ✅ |
| Property management sync | - | - | - | ✅ |
| Access control integration | - | - | - | ✅ |
| Custom integrations | - | - | - | ✅ |
| **MULTI-SITE** |||||
| Cloud dashboard sync | - | - | ✅ | ✅ |
| Centralized management | - | - | - | ✅ |
| Cross-site whitelist | - | - | - | ✅ |
| Multi-site analytics | - | - | - | ✅ |
| **SUPPORT & SLA** |||||
| Documentation | ✅ | ✅ | ✅ | ✅ |
| Email support | Best effort | 48h response | 24h response | 4h response |
| Phone support | - | - | Business hours | 24/7 |
| On-site support | - | - | - | ✅ |
| Uptime SLA | - | 99% | 99.5% | 99.9% |
| **MONITORING** |||||
| Device health alerts | - | ✅ | ✅ | ✅ |
| Remote diagnostics | - | - | ✅ | ✅ |
| Prometheus metrics | - | - | - | ✅ |
| Grafana dashboards | - | - | - | ✅ |

---

## Tier Descriptions

### Basic Tier - "Essentials"

**Target Customer:** Small residential properties, single family homes with gates, small parking lots

**What They Get:**
- Core ALPR functionality
- 1-2 cameras, 1 gate
- Basic whitelist/blacklist (up to 500 plates)
- 7-day image retention
- Dashboard-only alerts
- Single admin user

**Use Cases:**
- Gated residential community (small)
- Private driveway with gate
- Small business parking lot

**Limitations:**
- No email/SMS alerts
- No API access
- No advanced analytics
- Single user only

---

### Standard Tier - "Property"

**Target Customer:** Medium residential communities, small commercial properties

**What They Get:**
- Everything in Basic, plus:
- 2-4 cameras, 2 gates
- 2,000 plate whitelist capacity
- 30-day retention with full frame images
- Email notifications
- 3 admin users
- Daily summary reports
- Device health monitoring

**Use Cases:**
- HOA community (50-200 homes)
- Small apartment complex
- Office building parking
- Church or school

**Key Upgrade Drivers:**
- Need email alerts for blacklist hits
- Multiple people need dashboard access
- Longer retention for incident review

---

### Professional Tier - "Business"

**Target Customer:** Large residential communities, commercial properties, multi-gate facilities

**What They Get:**
- Everything in Standard, plus:
- 4-8 cameras, 4 gates
- 10,000 plate capacity
- 90-day retention
- SMS notifications + webhooks
- 10 users with role-based access
- Custom alert rules (5)
- Weekly/monthly reports
- Visitor pre-registration system
- Temporary access codes
- REST API access
- Cloud dashboard sync

**Use Cases:**
- Large HOA/condo (200+ units)
- Corporate campus
- Shopping center
- Industrial park
- Hotel/resort

**Key Upgrade Drivers:**
- Need SMS for security alerts
- API integration with other systems
- Visitor management requirements
- Multiple gates/entrances

---

### Enterprise Tier - "Campus"

**Target Customer:** Large commercial, multi-site deployments, managed security companies

**What They Get:**
- Everything in Professional, plus:
- 8-16+ cameras, unlimited gates
- Unlimited whitelist capacity
- 1-year retention
- Unlimited users with SSO/LDAP
- Unlimited custom alert rules
- Advanced analytics (direction, speed)
- Full API access
- Property management integration
- Cross-site whitelist sharing
- Centralized multi-site management
- Prometheus + Grafana monitoring
- 24/7 phone support
- On-site support available
- 99.9% uptime SLA

**Use Cases:**
- University campus
- Hospital complex
- Multi-property management company
- Government facility
- Large corporate headquarters

**Deployment Model:**
- Dedicated account manager
- Custom implementation
- White-label options available

---

## Hardware Scaling

### Hardware by Tier

| Tier | Recommended Hardware | Cameras | Max FPS | Cost |
|------|---------------------|---------|---------|------|
| **Basic** | Jetson Orin Nano 8GB | 1-2 | 25 FPS | $199 |
| **Standard** | Jetson Orin Nano 8GB | 2-4 | 20 FPS | $199 |
| **Professional** | Jetson Orin NX 16GB | 4-8 | 25 FPS | $599 |
| **Enterprise** | Jetson Orin NX 16GB or AGX | 8-16+ | 30 FPS | $599-$1,999 |

### When to Upgrade Hardware

| Scenario | Current | Upgrade To | Reason |
|----------|---------|------------|--------|
| Adding 3rd camera | Orin Nano | Keep Nano | Still handles 4 cameras |
| Adding 5th camera | Orin Nano | Orin NX | Need more GPU headroom |
| Adding analytics | Any | Consider NX | Analytics uses GPU |
| 8+ cameras | Orin NX | AGX or multi-device | Capacity limit |

### Multi-Device Deployments

For large Enterprise deployments:

```
┌──────────────────────────────────────────────────────────────┐
│                    MULTI-DEVICE ARCHITECTURE                  │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Gate 1-2           Gate 3-4           Gate 5-6              │
│  ┌─────────┐        ┌─────────┐        ┌─────────┐           │
│  │ Jetson  │        │ Jetson  │        │ Jetson  │           │
│  │ NX #1   │        │ NX #2   │        │ NX #3   │           │
│  │ 4 cams  │        │ 4 cams  │        │ 4 cams  │           │
│  └────┬────┘        └────┬────┘        └────┬────┘           │
│       │                  │                  │                 │
│       └──────────────────┼──────────────────┘                 │
│                          │                                    │
│                          ▼                                    │
│               ┌─────────────────────┐                         │
│               │   Central Server    │                         │
│               │   (Cloud or Local)  │                         │
│               │                     │                         │
│               │  • Unified DB       │                         │
│               │  • Cross-site sync  │                         │
│               │  • Analytics        │                         │
│               │  • Management UI    │                         │
│               └─────────────────────┘                         │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Software Modules

### Module Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     SOFTWARE MODULES                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  CORE (All Tiers)                                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ pilot_lite.py    - Main ALPR pipeline                  │ │
│  │ gate_control.py  - Gate relay control                  │ │
│  │ whitelist.py     - List management                     │ │
│  │ dashboard.py     - Basic web UI                        │ │
│  │ database.py      - PostgreSQL storage                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  STANDARD+                                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ email_alerts.py  - SMTP notifications                  │ │
│  │ image_storage.py - Full frame capture                  │ │
│  │ health_monitor.py - Device health checks               │ │
│  │ daily_report.py  - Summary generation                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  PROFESSIONAL+                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ sms_alerts.py    - Twilio SMS                          │ │
│  │ webhook.py       - HTTP webhooks                       │ │
│  │ visitor.py       - Pre-registration system             │ │
│  │ analytics.py     - Reports & trends                    │ │
│  │ api_module.py    - REST API endpoints                  │ │
│  │ cloud_sync.py    - Dashboard sync                      │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ENTERPRISE                                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ multi_site.py    - Cross-site management               │ │
│  │ advanced_analytics.py - Direction, speed, patterns     │ │
│  │ integrations.py  - Property mgmt, access control       │ │
│  │ monitoring.py    - Prometheus + Grafana stack          │ │
│  │ sso_auth.py      - LDAP/SSO integration                │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Module Implementation Effort

| Module | Development Time | Dependencies | Tier |
|--------|-----------------|--------------|------|
| **Core modules** | 3-5 days | None | All |
| email_alerts.py | 2-4 hours | SMTP server | Standard+ |
| image_storage.py | 4-8 hours | Disk space | Standard+ |
| health_monitor.py | 4-8 hours | None | Standard+ |
| daily_report.py | 4-8 hours | Email module | Standard+ |
| sms_alerts.py | 2-4 hours | Twilio account | Professional+ |
| webhook.py | 4-8 hours | None | Professional+ |
| visitor.py | 1-2 days | None | Professional+ |
| analytics.py | 2-3 days | None | Professional+ |
| api_module.py | 1-2 days | None | Professional+ |
| cloud_sync.py | 2-3 days | Cloud portal | Professional+ |
| multi_site.py | 3-5 days | Cloud portal | Enterprise |
| advanced_analytics.py | 1-2 weeks | ML models | Enterprise |
| integrations.py | Variable | Third-party APIs | Enterprise |
| monitoring.py | 1 day | Prometheus/Grafana | Enterprise |
| sso_auth.py | 2-3 days | LDAP/OAuth provider | Enterprise |

### Feature Flags Configuration

```yaml
# config/features.yaml

tier: "professional"  # basic, standard, professional, enterprise

features:
  # Core (always enabled)
  core:
    enabled: true

  # Capacity limits
  limits:
    max_cameras: 8
    max_gates: 4
    max_whitelist: 10000
    max_users: 10
    retention_days: 90

  # Standard features
  email_alerts:
    enabled: true

  full_frame_images:
    enabled: true

  health_monitoring:
    enabled: true

  daily_reports:
    enabled: true

  # Professional features
  sms_alerts:
    enabled: true
    provider: "twilio"

  webhooks:
    enabled: true
    max_endpoints: 5

  visitor_management:
    enabled: true

  analytics:
    enabled: true

  api_access:
    enabled: true
    rate_limit: 1000  # requests per hour

  cloud_sync:
    enabled: true

  # Enterprise features (disabled for Professional)
  multi_site:
    enabled: false

  advanced_analytics:
    enabled: false

  custom_integrations:
    enabled: false

  monitoring_stack:
    enabled: false

  sso:
    enabled: false
```

---

## Pricing Strategy

### Recommended Pricing

| Tier | Setup Fee | Monthly | Annual (10% off) |
|------|-----------|---------|------------------|
| **Basic** | $400 | $40/mo | $432/year |
| **Standard** | $500 | $60/mo | $648/year |
| **Professional** | $800 | $100/mo | $1,080/year |
| **Enterprise** | Custom | $200+/mo | Custom |

### Cost Breakdown (Your Side)

| Tier | Hardware Cost | Your Setup Time | Monthly Cost | Margin |
|------|---------------|-----------------|--------------|--------|
| Basic | $250 | 2 hours | ~$2 | ~90% |
| Standard | $250 | 3 hours | ~$5 | ~88% |
| Professional | $650 | 4 hours | ~$10 | ~85% |
| Enterprise | $700+ | 8+ hours | ~$20+ | ~80% |

### Add-On Pricing

| Add-On | Monthly | Notes |
|--------|---------|-------|
| Extra camera (per cam) | +$10/mo | Beyond tier limit |
| Extra gate (per gate) | +$15/mo | Beyond tier limit |
| SMS credits (100/mo) | +$10/mo | Beyond included |
| Extended retention (+30 days) | +$10/mo | Per 30 days |
| Extra users (5 pack) | +$15/mo | Beyond tier limit |
| Priority support upgrade | +$25/mo | 4h → 1h response |
| API rate limit increase | +$20/mo | 2x rate limit |

### Volume Discounts (Multi-Site)

| Sites | Discount |
|-------|----------|
| 2-5 | 10% |
| 6-10 | 15% |
| 11-25 | 20% |
| 26+ | Custom |

---

## Implementation Roadmap

### Phase 1: Core + Basic (Week 1-2)

```
Week 1:
├── Day 1-2: Core pipeline (pilot_lite.py)
├── Day 3: Gate control module
├── Day 4: Whitelist/blacklist management
└── Day 5: Basic dashboard

Week 2:
├── Day 1-2: Database schema + API
├── Day 3: Basic UI polish
├── Day 4: Testing & bug fixes
└── Day 5: Documentation
```

**Deliverable:** Basic tier ready for customers

### Phase 2: Standard Features (Week 3)

```
Week 3:
├── Day 1: Email alerts module
├── Day 2: Full frame image capture
├── Day 3: Health monitoring
├── Day 4: Daily report generation
└── Day 5: Multi-user support (3 users)
```

**Deliverable:** Standard tier ready

### Phase 3: Professional Features (Week 4-5)

```
Week 4:
├── Day 1: SMS alerts (Twilio)
├── Day 2: Webhook notifications
├── Day 3-4: Visitor management system
└── Day 5: Temporary access codes

Week 5:
├── Day 1-2: Analytics & reporting
├── Day 3: REST API module
├── Day 4: Cloud sync basics
└── Day 5: Role-based access
```

**Deliverable:** Professional tier ready

### Phase 4: Enterprise Features (Week 6-8)

```
Week 6:
├── Multi-site sync foundation
└── Cross-site whitelist sharing

Week 7:
├── Advanced analytics
├── Direction/speed detection
└── Custom integrations framework

Week 8:
├── Prometheus/Grafana stack
├── SSO/LDAP integration
└── Enterprise documentation
```

**Deliverable:** Enterprise tier ready

### Development Priority Matrix

| Feature | Customer Value | Effort | Priority |
|---------|---------------|--------|----------|
| Core ALPR + gate | Critical | High | P0 |
| Basic dashboard | Critical | Medium | P0 |
| Email alerts | High | Low | P1 |
| SMS alerts | High | Low | P1 |
| Visitor management | High | Medium | P1 |
| API access | Medium | Medium | P2 |
| Analytics | Medium | Medium | P2 |
| Multi-site | Medium | High | P3 |
| Advanced analytics | Low | High | P4 |

---

## Upsell Strategies

### Natural Upgrade Triggers

| Trigger | Current Tier | Recommend | Pitch |
|---------|--------------|-----------|-------|
| "Need more cameras" | Basic | Standard | "Standard supports 4 cameras + email alerts" |
| "Want email alerts" | Basic | Standard | "Never miss a blacklist hit again" |
| "Multiple admins" | Basic | Standard | "Let your team access the dashboard" |
| "Need SMS alerts" | Standard | Professional | "Instant SMS for security events" |
| "Want API access" | Standard | Professional | "Integrate with your other systems" |
| "Managing visitors" | Standard | Professional | "Pre-register visitors, issue temp codes" |
| "Multiple properties" | Professional | Enterprise | "Manage all sites from one dashboard" |
| "Need integrations" | Professional | Enterprise | "Connect to property management, access control" |

### Proactive Upsell Opportunities

**In-App Prompts:**
```
"You've used 90% of your whitelist capacity (450/500).
Upgrade to Standard for 2,000 plates → [Upgrade Now]"

"Your images will be deleted in 3 days (7-day retention).
Upgrade to Standard for 30-day retention → [Learn More]"

"You've had 15 blacklist alerts this month.
Get instant SMS notifications with Professional → [Upgrade]"
```

**Quarterly Business Reviews:**
- Review usage metrics
- Identify features they'd benefit from
- Offer upgrade with discount

### Retention Strategies

| Risk Signal | Action |
|-------------|--------|
| Low usage | Proactive check-in, training |
| Support complaints | Prioritize resolution, consider upgrade to better SLA |
| Competitor inquiry | Offer loyalty discount, highlight unique features |
| Contract renewal | Early renewal discount (15%) |

---

## Custom Enterprise Options

### White-Label Program

For security companies and property managers who want to offer ALPR under their brand:

| Feature | Included |
|---------|----------|
| Custom branding (logo, colors) | ✅ |
| Custom domain | ✅ |
| Reseller pricing (40% off) | ✅ |
| Co-branded marketing materials | ✅ |
| Partner portal | ✅ |
| Technical training | ✅ |
| Priority support channel | ✅ |

**Requirements:**
- Minimum 10 sites
- Annual commitment
- Technical capability for installation

### Custom Integration Services

| Integration | Typical Effort | Price Range |
|-------------|----------------|-------------|
| Property management system | 2-4 weeks | $2,000-5,000 |
| Access control (HID, Lenel) | 2-4 weeks | $3,000-8,000 |
| Billing system | 1-2 weeks | $1,500-3,000 |
| Custom reporting | 1-2 weeks | $1,000-3,000 |
| Mobile app (branded) | 4-8 weeks | $10,000-25,000 |

### Managed Services Option

For customers who want hands-off operation:

| Service | Monthly |
|---------|---------|
| 24/7 monitoring | +$100/mo |
| Whitelist management | +$50/mo |
| Monthly reporting | +$25/mo |
| Quarterly reviews | +$50/mo |
| Full managed service | +$200/mo |

---

## Metrics to Track

### Per-Customer Metrics

| Metric | Purpose |
|--------|---------|
| Plates processed/day | Usage level |
| Whitelist size | Capacity usage |
| Alert frequency | Engagement |
| Dashboard logins | Engagement |
| API calls | Integration usage |
| Storage used | Retention needs |

### Business Metrics

| Metric | Target |
|--------|--------|
| MRR (Monthly Recurring Revenue) | Growth |
| Churn rate | <5% monthly |
| Upgrade rate | >10% annually |
| Customer acquisition cost | <3 months MRR |
| Net Promoter Score | >50 |

---

## Related Documentation

- [Project Structure](project-structure.md) - Single repository architecture (alpr-edge)
- [Modular Deployment](modular-deployment.md) - License-based module configuration
- [Model Distribution](model-distribution.md) - MLflow model registry for team
- [SaaS Business Model](saas-business-model.md) - Business model overview
- [Deployment Analysis](deployment-analysis.md) - Technical deployment guide
- [Hardware Reliability](hardware-reliability.md) - 24/7 operation guide
- [Use Case: Gate Control](use-case-gate-control.md) - Access control (Basic tier)
- [Use Case: Plate Logging](use-case-plate-logging.md) - Entry/exit logging (Standard+ tiers)
