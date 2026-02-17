# Gate Control Use Case Documentation

ALPR gate control system deployed as SaaS with edge devices per customer.

## Quick Start

| Goal | Read This |
|------|-----------|
| Understand the product | [use-case-gate-control.md](use-case-gate-control.md) |
| Set up the GitHub repo | [github-setup-guide.md](github-setup-guide.md) |
| Develop without Jetson | [team-development-guide.md](team-development-guide.md) |

## Document Overview

### Architecture & Code

| Document | Purpose |
|----------|---------|
| [project-structure.md](project-structure.md) | Repository layout, module organization, CI/CD |
| [modular-deployment.md](modular-deployment.md) | License validation, feature flags, Docker profiles |
| [github-setup-guide.md](github-setup-guide.md) | Creating the repo, migration from OVR-ALPR |
| [team-development-guide.md](team-development-guide.md) | Testing without Jetson (CPU mode, mocks, remote access) |

### Use Cases

| Document | Purpose |
|----------|---------|
| [use-case-gate-control.md](use-case-gate-control.md) | Gate access control (Basic tier) |
| [use-case-plate-logging.md](use-case-plate-logging.md) | Entry/exit logging with duration tracking (Standard+) |

> **Note:** Plate Logging extends Gate Control - it includes all gate features plus logging.

### Business & Deployment

| Document | Purpose |
|----------|---------|
| [feature-tiers.md](feature-tiers.md) | Feature matrix: Basic ($40) → Enterprise ($200+) |
| [saas-business-model.md](saas-business-model.md) | Edge device per customer, pricing, revenue |
| [deployment-analysis.md](deployment-analysis.md) | Hardware options, cost comparison |
| [hardware-reliability.md](hardware-reliability.md) | 24/7 operation, NVMe, UPS, maintenance |

## Key Concepts

```
alpr-edge (single repo)
├── Core: detector, OCR, tracker, camera (always loaded)
└── Modules: gate, logging, vehicle, alerts, analytics (by license)

Tiers: Basic → Standard → Professional → Enterprise
       $40      $60        $100          $200+
```

## Reading Order

1. **Product:** `use-case-gate-control.md` → `use-case-plate-logging.md`
2. **Code:** `project-structure.md` → `github-setup-guide.md`
3. **Development:** `team-development-guide.md` → `modular-deployment.md`
4. **Business:** `feature-tiers.md` → `saas-business-model.md`
