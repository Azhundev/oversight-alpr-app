# Multi-Location SaaS Business Model

**Created:** 2026-02-15
**Updated:** 2026-02-17
**Use Case:** ALPR gate control as a service for multiple companies
**Related:** [Deployment Analysis](deployment-analysis.md) | [Hardware Reliability](hardware-reliability.md) | [Project Structure](project-structure.md)

---

> **Architecture Note:** All deployments use the **alpr-edge** single repository. Each customer device runs the same codebase with features controlled by license configuration. See [Project Structure](project-structure.md) for repository details and [Modular Deployment](modular-deployment.md) for license-based loading.

---

## Table of Contents

1. [Business Context](#business-context)
2. [Option A: Shared Cloud GPU](#option-a-shared-cloud-gpu-multi-tenant)
3. [Option B: Edge Device per Customer](#option-b-edge-device-per-customer-recommended)
4. [Business Model Comparison](#business-model-comparison)
5. [Pricing Strategy](#pricing-strategy)
6. [Scaling the Business](#scaling-the-business)
7. [Cloud Portal Features](#cloud-portal-features)
8. [Revenue Projections](#revenue-projections)

---

## Business Context

If you're planning to offer ALPR gate control as a service to multiple companies/properties:

- Each location is a **separate company/customer**
- Complete data isolation between tenants
- Each customer gets their own dashboard
- You provide the service and charge monthly

---

## Option A: Shared Cloud GPU (Multi-tenant)

All customers share your cloud infrastructure. You manage one system that serves multiple tenants.

```
┌─────────────────────────────────────────────────────────────────┐
│                    YOUR CLOUD GPU VM                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │   Company A      Company B      Company C      ...          ││
│  │   (2 cams)       (2 cams)       (2 cams)                    ││
│  │   ┌────────┐     ┌────────┐     ┌────────┐                  ││
│  │   │Isolated│     │Isolated│     │Isolated│                  ││
│  │   │Database│     │Database│     │Database│                  ││
│  │   └────────┘     └────────┘     └────────┘                  ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Shared: GPU Processing, API Server, Dashboard Platform         │
└─────────────────────────────────────────────────────────────────┘
```

### Capacity per VM

- 1× g4dn.xlarge (T4 GPU) handles ~10-20 camera streams
- With 2 cameras per site = **5-10 customers per VM**

### Cost Structure

| Customers | Bandwidth Cost | GPU VM | Your Cost | Revenue @$75/mo | Margin |
|-----------|---------------|--------|-----------|-----------------|--------|
| 5 sites | $175-250/mo | $150-200/mo | ~$400/mo | $375/mo | -$25 |
| 10 sites | $350-500/mo | $150-200/mo | ~$600/mo | $750/mo | +$150 |
| 20 sites | $700-1000/mo | $300-400/mo (2 VMs) | ~$1,200/mo | $1,500/mo | +$300 |

### Pros

- You manage one infrastructure
- Easy customer onboarding (just add cameras + credentials)
- No hardware to ship or install
- Higher margin per customer

### Cons

- Customer pays bandwidth (or you absorb it)
- Gate latency: 300-500ms (acceptable but not ideal)
- Single point of failure: Your VM down = ALL customers down
- Customer concern: "Cloud controls my gate"

---

## Option B: Edge Device per Customer (Recommended)

Each customer gets their own Jetson device. You maintain a central cloud portal for management.

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│    Company A     │  │    Company B     │  │    Company C     │
│  ┌────────────┐  │  │  ┌────────────┐  │  │  ┌────────────┐  │
│  │  Jetson    │  │  │  │  Jetson    │  │  │  │  Jetson    │  │
│  │  $250      │  │  │  │  $250      │  │  │  │  $250      │  │
│  │  On-site   │  │  │  │  On-site   │  │  │  │  On-site   │  │
│  │            │  │  │  │            │  │  │  │            │  │
│  │ • Gate ctrl│  │  │  │ • Gate ctrl│  │  │  │ • Gate ctrl│  │
│  │ • Local DB │  │  │  │ • Local DB │  │  │  │ • Local DB │  │
│  │ • Offline  │  │  │  │ • Offline  │  │  │  │ • Offline  │  │
│  └─────┬──────┘  │  │  └─────┬──────┘  │  │  └─────┬──────┘  │
└────────┼─────────┘  └────────┼─────────┘  └────────┼─────────┘
         │                     │                     │
         │      Sync lists     │      Sync lists     │
         │      + analytics    │      + analytics    │
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ▼
              ┌────────────────────────────────┐
              │     YOUR CLOUD PORTAL ($50/mo) │
              │                                │
              │  • Multi-tenant Dashboard      │
              │  • Customer Management         │
              │  • Whitelist/Blacklist Sync    │
              │  • Analytics & Reporting       │
              │  • Remote Device Management    │
              │  • Billing Integration         │
              │                                │
              └────────────────────────────────┘
```

### Cost Structure

| Item | One-Time | Monthly |
|------|----------|---------|
| Jetson per customer | $250-350 | - |
| Your cloud portal | - | $50-100 (fixed) |
| Per-customer cloud cost | - | ~$2-5 (minimal sync) |

### Revenue Model

| Component | Amount | Notes |
|-----------|--------|-------|
| **Setup Fee** | $400-600 | Covers Jetson + cameras + installation |
| **Monthly Fee** | $30-75/mo | Dashboard access + support + updates |
| **Optional Add-ons** | $10-25/mo | SMS alerts, extended retention, API access |

### Margin Analysis (20 customers)

| | Cloud Multi-tenant | Edge + Portal |
|-|-------------------|---------------|
| Your monthly cost | ~$1,200 | ~$150 |
| Revenue @$50/mo each | $1,000 | $1,000 |
| Revenue @$75/mo each | $1,500 | $1,500 |
| **Monthly profit** | $300-$300 | **$850-$1,350** |
| Hardware revenue | $0 | $3,000-6,000 (one-time) |

### Pros

- Each customer isolated physically (better security story)
- Gate works even if cloud/internet fails
- Low latency (<100ms) - critical for gate control
- Lower ongoing costs = higher margin
- Hardware sale provides upfront revenue

### Cons

- Hardware logistics (shipping, installation)
- On-site support may be needed occasionally
- Higher upfront investment per customer

---

## Business Model Comparison

| Factor | Cloud Multi-tenant | Edge + Cloud Portal |
|--------|-------------------|---------------------|
| **Reliability** | Single point of failure | Independent per site |
| **Gate Latency** | 300-500ms (acceptable) | <100ms (ideal) |
| **Offline Operation** | No (gate fails) | Yes (gate works) |
| **Your Monthly Cost** | High (scales with customers) | Low (fixed portal cost) |
| **Customer Trust** | "Cloud controls my gate" | "I own my device" |
| **Scalability** | Easy (just add streams) | Requires logistics |
| **Upfront Revenue** | None | Hardware sale |
| **Monthly Margin** | ~20-30% | ~80-90% |
| **Break-even** | ~8-10 customers | ~3-5 customers |

---

## Pricing Strategy

### Recommended Pricing (Edge Model)

| Tier | Setup Fee | Monthly | Includes |
|------|-----------|---------|----------|
| **Basic** | $400 | $40/mo | 1-2 cameras, 1 gate, dashboard only |
| **Standard** | $500 | $60/mo | + Email alerts, 30-day retention, 3 users |
| **Professional** | $800 | $100/mo | + SMS, API access, 90-day retention, visitor mgmt |
| **Enterprise** | Custom | $200+/mo | + Multi-site, integrations, unlimited |

> For full feature breakdown by tier, see [Feature Tiers](feature-tiers.md)

### Pricing Considerations

1. **Setup fee** should cover hardware cost + installation time + small margin
2. **Monthly fee** is mostly profit after cloud portal costs are split
3. **Add-ons** increase ARPU (Average Revenue Per User) without much cost
4. **Tier upgrades** - most customers start Basic, upgrade within 6 months

### Add-On Pricing

| Add-On | Monthly | Notes |
|--------|---------|-------|
| Extra camera | +$10/mo | Beyond tier limit |
| Extra gate | +$15/mo | Beyond tier limit |
| SMS credits (100/mo) | +$10/mo | Beyond included |
| Extended retention | +$10/mo | Per extra 30 days |

### Competitive Positioning

| Competitor Type | Their Price | Your Advantage |
|-----------------|-------------|----------------|
| Traditional gate systems | $2,000-5,000 setup | ALPR adds plate recognition |
| Cloud ALPR services | $100-200/mo | Lower cost, works offline |
| DIY solutions | Free (but complex) | Turnkey, supported |

---

## Scaling the Business

### Phase 1: Launch (1-10 customers)

- Deploy Jetsons manually
- Basic cloud portal (single VM, $50/mo)
- Handle support directly
- Focus on local market

**Goals:**
- Validate product-market fit
- Refine installation process
- Build case studies

### Phase 2: Growth (10-50 customers)

- Partner with local installers
- Automated provisioning portal
- Tiered support (self-service + premium)
- Expand to nearby regions

**Investment Needed:**
- Better cloud infrastructure (~$200/mo)
- Part-time support person
- Marketing budget

### Phase 3: Scale (50+ customers)

- White-label option for installers
- Regional support partners
- Enterprise API for integrations
- National expansion

**Investment Needed:**
- Full-time support team
- Sales team or channel partners
- Enterprise features development

---

## Cloud Portal Features

### Feature Roadmap

| Feature | MVP | Phase 2 | Phase 3 |
|---------|-----|---------|---------|
| Customer dashboard | ✅ | ✅ | ✅ |
| Whitelist/blacklist sync | ✅ | ✅ | ✅ |
| Device health monitoring | ✅ | ✅ | ✅ |
| Usage analytics | - | ✅ | ✅ |
| Billing integration | - | ✅ | ✅ |
| White-label branding | - | - | ✅ |
| API for integrations | - | - | ✅ |
| Multi-site customer view | - | ✅ | ✅ |

### MVP Portal Requirements

**Customer-Facing:**
- Login/authentication
- View plate read history
- Manage whitelist/blacklist
- View gate events
- Basic reports (daily/weekly)

**Admin-Facing:**
- Customer management
- Device status monitoring
- Push updates to devices
- Usage/billing reports

### Technology Stack (Portal)

| Component | Recommendation | Cost |
|-----------|----------------|------|
| Backend | FastAPI (Python) or Node.js | - |
| Frontend | React or Vue.js | - |
| Database | PostgreSQL | - |
| Hosting | DigitalOcean or AWS Lightsail | $50-100/mo |
| Auth | Auth0 or Firebase Auth | Free tier |

---

## Revenue Projections

### Conservative Scenario (Edge Model)

| Year | New Customers | Total Customers | Hardware Rev | Monthly MRR | Annual Rev |
|------|---------------|-----------------|--------------|-------------|------------|
| Year 1 | 20 | 20 | $10,000 | $1,000 | **$22,000** |
| Year 2 | 30 | 50 | $15,000 | $2,500 | **$45,000** |
| Year 3 | 50 | 100 | $25,000 | $5,000 | **$85,000** |

### Optimistic Scenario (Edge Model)

| Year | New Customers | Total Customers | Hardware Rev | Monthly MRR | Annual Rev |
|------|---------------|-----------------|--------------|-------------|------------|
| Year 1 | 30 | 30 | $15,000 | $1,500 | **$33,000** |
| Year 2 | 50 | 80 | $25,000 | $4,000 | **$73,000** |
| Year 3 | 70 | 150 | $35,000 | $7,500 | **$125,000** |

### Cost Structure (Your Side)

| Item | Monthly Cost | Notes |
|------|--------------|-------|
| Cloud portal hosting | $50-100 | Fixed regardless of customers |
| Domain + SSL | $5 | - |
| Monitoring (UptimeRobot) | $0-10 | Free tier available |
| SMS alerts (Twilio) | Variable | Pass through to customers |
| Your time | Variable | Biggest "cost" initially |

**Key insight:** Your costs remain ~$100-200/mo regardless of customer count, making this highly scalable.

---

## Key Success Factors

1. **Reliable hardware** - Use NVMe, UPS, proper setup (see [Hardware Reliability](hardware-reliability.md))
2. **Fast installation** - Streamline the on-site process
3. **Self-service portal** - Reduce support burden
4. **Good documentation** - For customers and installers
5. **Proactive monitoring** - Fix issues before customers notice

---

## Related Documentation

- [Project Structure](project-structure.md) - Single repository architecture (alpr-edge)
- [Modular Deployment](modular-deployment.md) - License-based module configuration
- [Model Distribution](model-distribution.md) - MLflow model registry for team
- [Feature Tiers](feature-tiers.md) - Complete feature breakdown by tier
- [Deployment Analysis](deployment-analysis.md) - Technical deployment guide
- [Hardware Reliability](hardware-reliability.md) - 24/7 operation best practices
- [Use Case: Gate Control](use-case-gate-control.md) - Access control implementation
- [Use Case: Plate Logging](use-case-plate-logging.md) - Entry/exit logging (extends Gate Control)
- [Services Overview](../../alpr/services-overview.md) - Full OVR-ALPR system architecture
