# Project Structure for Production Deployment

**Created:** 2026-02-16
**Updated:** 2026-02-17
**Purpose:** Single repository structure for ALPR edge deployments with modular features
**Related:** [Modular Deployment](modular-deployment.md) | [Feature Tiers](feature-tiers.md) | [SaaS Business Model](saas-business-model.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Repository Structure](#repository-structure)
3. [Module Organization](#module-organization)
4. [Use Case Configurations](#use-case-configurations)
5. [Development Setup](#development-setup)
6. [Team Workflow](#team-workflow)
7. [CI/CD Pipeline](#cicd-pipeline)
8. [Deployment Process](#deployment-process)

---

## Overview

A **single repository** contains all ALPR functionality with modular features enabled by license configuration. This approach is simpler than multiple repos while supporting different use case deployments.

```
SINGLE REPOSITORY ARCHITECTURE
══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│  REPO: alpr-edge                                                 │
│  ─────────────────                                               │
│  One codebase, multiple deployment configurations               │
└─────────────────────────────────────────────────────────────────┘
                              │
                    License determines features
                              │
       ┌──────────────────────┼──────────────────────┐
       ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  DEPLOYMENT:    │  │  DEPLOYMENT:    │  │  DEPLOYMENT:    │
│  Gate Control   │  │  Parking Logger │  │  Full System    │
│                 │  │                 │  │                 │
│  Modules:       │  │  Modules:       │  │  Modules:       │
│  • Core         │  │  • Core         │  │  • Core         │
│  • Gate         │  │  • Gate         │  │  • Gate         │
│  • Basic alerts │  │  • Logging      │  │  • Logging      │
│                 │  │  • Vehicle      │  │  • Vehicle      │
│                 │  │  • Analytics    │  │  • Analytics    │
│                 │  │  • Alerts       │  │  • Alerts       │
│                 │  │                 │  │  • Integrations │
└─────────────────┘  └─────────────────┘  └─────────────────┘
     Basic tier         Standard tier       Professional+
```

### Why Single Repo?

| Factor | Single Repo | Multiple Repos |
|--------|-------------|----------------|
| **Code sharing** | ~80% shared naturally | Requires package management |
| **Maintenance** | 1 repo to manage | 3+ repos to sync |
| **PRs** | Atomic changes | Cross-repo coordination |
| **CI/CD** | Single pipeline | Multiple pipelines |
| **Onboarding** | Clone once | Clone multiple |
| **Best for** | Same team, similar use cases | Different teams/products |

---

## Repository Structure

### Complete Directory Layout

```
alpr-edge/
├── src/
│   └── alpr_edge/
│       ├── __init__.py
│       ├── main.py                  # Application entry point
│       ├── config.py                # Settings management
│       ├── license.py               # License validation
│       │
│       ├── core/                    # ALWAYS LOADED
│       │   ├── __init__.py
│       │   ├── detector.py          # YOLOv11 plate detection
│       │   ├── ocr.py               # PaddleOCR text recognition
│       │   ├── tracker.py           # ByteTrack deduplication
│       │   ├── camera.py            # RTSP/GStreamer ingestion
│       │   ├── plate.py             # Plate normalization
│       │   └── pipeline.py          # Main processing loop
│       │
│       ├── modules/                 # LOADED BY LICENSE
│       │   ├── __init__.py
│       │   ├── gate/                # Gate control module
│       │   │   ├── __init__.py
│       │   │   ├── controller.py    # GPIO/HTTP gate trigger
│       │   │   ├── access_list.py   # Whitelist/blacklist
│       │   │   └── enrollment.py    # Auto-enrollment mode
│       │   │
│       │   ├── logging/             # Entry/exit logging
│       │   │   ├── __init__.py
│       │   │   ├── events.py        # Event recording
│       │   │   ├── duration.py      # Time calculations
│       │   │   └── tailgate.py      # Tailgate detection
│       │   │
│       │   ├── vehicle/             # Vehicle attributes
│       │   │   ├── __init__.py
│       │   │   ├── color.py         # Color detection
│       │   │   ├── type.py          # Car/truck/motorcycle
│       │   │   └── make_model.py    # Brand recognition
│       │   │
│       │   ├── alerts/              # Notifications
│       │   │   ├── __init__.py
│       │   │   ├── email.py         # SMTP alerts
│       │   │   ├── sms.py           # Twilio SMS
│       │   │   └── webhook.py       # HTTP callbacks
│       │   │
│       │   ├── analytics/           # Reporting
│       │   │   ├── __init__.py
│       │   │   ├── reports.py       # PDF/Excel export
│       │   │   ├── dashboard.py     # Advanced UI data
│       │   │   └── metrics.py       # Usage statistics
│       │   │
│       │   └── integrations/        # External systems
│       │       ├── __init__.py
│       │       ├── api.py           # REST API access
│       │       ├── cloud_sync.py    # Cloud portal sync
│       │       └── custom.py        # Custom integrations
│       │
│       ├── api/                     # REST API
│       │   ├── __init__.py
│       │   ├── app.py               # FastAPI application
│       │   ├── deps.py              # Dependencies
│       │   └── routes/
│       │       ├── __init__.py
│       │       ├── health.py
│       │       ├── whitelist.py
│       │       ├── blacklist.py
│       │       ├── events.py
│       │       ├── gate.py
│       │       ├── vehicles.py
│       │       └── reports.py
│       │
│       └── db/                      # Database
│           ├── __init__.py
│           ├── database.py          # Connection management
│           ├── models.py            # SQLAlchemy models
│           └── repositories/
│               ├── __init__.py
│               ├── plates.py
│               ├── access_list.py
│               ├── events.py
│               └── vehicles.py
│
├── models/                          # ML models
│   ├── yolo11n-plate.pt
│   ├── yolo11n-plate.engine         # TensorRT optimized
│   └── vehicle_attributes.pt        # Optional
│
├── dashboard/                       # Web UI
│   ├── src/
│   │   ├── components/
│   │   ├── views/
│   │   ├── api/
│   │   └── main.js
│   ├── public/
│   ├── package.json
│   └── vite.config.js
│
├── config/                          # Configuration templates
│   ├── license.example.yaml
│   ├── cameras.example.yaml
│   ├── gate.example.yaml
│   └── alerts.example.yaml
│
├── docker/                          # Docker files
│   ├── Dockerfile                   # Production image
│   ├── Dockerfile.dev               # Development image
│   └── docker-compose.yml           # Full stack with profiles
│
├── scripts/                         # Utility scripts
│   ├── setup.sh                     # Initial setup
│   ├── provision.sh                 # Device provisioning
│   ├── deploy.sh                    # Deployment script
│   └── backup.sh                    # Database backup
│
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_detector.py
│   │   ├── test_ocr.py
│   │   ├── test_gate.py
│   │   └── test_access_list.py
│   ├── integration/
│   │   ├── test_pipeline.py
│   │   └── test_api.py
│   └── e2e/
│       └── test_gate_flow.py
│
├── docs/                            # Documentation
│   ├── deployment.md
│   ├── configuration.md
│   ├── api.md
│   └── troubleshooting.md
│
├── .github/                         # GitHub configuration
│   ├── workflows/
│   │   ├── ci.yml
│   │   ├── build.yml
│   │   └── release.yml
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
│
├── pyproject.toml                   # Python project config
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── LICENSE
├── .env.example
├── .gitignore
└── .pre-commit-config.yaml
```

---

## Module Organization

### Module Dependency Tree

```
CORE (always loaded)
│
├── gate (Basic+)
│   ├── Requires: core
│   └── Provides: whitelist, blacklist, GPIO control, enrollment
│
├── logging (Basic+)
│   ├── Requires: core, gate
│   └── Provides: entry/exit events, timestamps
│
├── logging.duration (Standard+)
│   ├── Requires: logging
│   └── Provides: duration calculation, tailgate detection
│
├── alerts.email (Standard+)
│   ├── Requires: core
│   └── Provides: email notifications
│
├── alerts.sms (Standard+)
│   ├── Requires: core
│   └── Provides: SMS via Twilio
│
├── vehicle.color (Standard+)
│   ├── Requires: core
│   └── Provides: vehicle color detection
│
├── vehicle.make_model (Professional+)
│   ├── Requires: vehicle.color
│   └── Provides: brand/model recognition
│
├── analytics (Professional+)
│   ├── Requires: logging
│   └── Provides: reports, trends, export
│
├── integrations.api (Professional+)
│   ├── Requires: core
│   └── Provides: REST API access
│
└── integrations.cloud (Professional+)
    ├── Requires: core
    └── Provides: cloud portal sync
```

### Module Loading Code

```python
# src/alpr_edge/modules/__init__.py
"""Dynamic module loading based on license."""

from typing import Dict, Any, Set
from importlib import import_module

from alpr_edge.license import get_license


# Module registry
MODULES = {
    "core": {
        "path": "alpr_edge.core",
        "required": True,
        "depends": [],
    },
    "gate": {
        "path": "alpr_edge.modules.gate",
        "required": False,
        "depends": ["core"],
    },
    "logging": {
        "path": "alpr_edge.modules.logging",
        "required": False,
        "depends": ["core", "gate"],
    },
    "logging.duration": {
        "path": "alpr_edge.modules.logging.duration",
        "required": False,
        "depends": ["logging"],
    },
    "alerts.email": {
        "path": "alpr_edge.modules.alerts.email",
        "required": False,
        "depends": ["core"],
    },
    "alerts.sms": {
        "path": "alpr_edge.modules.alerts.sms",
        "required": False,
        "depends": ["core"],
    },
    "vehicle.color": {
        "path": "alpr_edge.modules.vehicle.color",
        "required": False,
        "depends": ["core"],
    },
    "vehicle.make_model": {
        "path": "alpr_edge.modules.vehicle.make_model",
        "required": False,
        "depends": ["vehicle.color"],
    },
    "analytics": {
        "path": "alpr_edge.modules.analytics",
        "required": False,
        "depends": ["logging"],
    },
    "integrations.api": {
        "path": "alpr_edge.modules.integrations.api",
        "required": False,
        "depends": ["core"],
    },
    "integrations.cloud": {
        "path": "alpr_edge.modules.integrations.cloud",
        "required": False,
        "depends": ["core"],
    },
}


class ModuleLoader:
    """Loads modules based on license configuration."""

    def __init__(self):
        self.license = get_license()
        self.loaded_modules: Dict[str, Any] = {}

    def load_all(self) -> Dict[str, Any]:
        """Load all enabled modules in dependency order."""
        enabled = self._get_enabled_modules()
        ordered = self._sort_by_dependencies(enabled)

        for module_id in ordered:
            self._load_module(module_id)

        return self.loaded_modules

    def _get_enabled_modules(self) -> Set[str]:
        """Get list of enabled modules from license."""
        enabled = {"core"}  # Always enabled

        for module_id, config in MODULES.items():
            if config["required"]:
                enabled.add(module_id)
            elif self.license.is_module_enabled(module_id):
                enabled.add(module_id)
                # Add dependencies
                for dep in config["depends"]:
                    enabled.add(dep)

        return enabled

    def _sort_by_dependencies(self, modules: Set[str]) -> list:
        """Sort modules so dependencies load first."""
        result = []
        remaining = modules.copy()

        while remaining:
            for module_id in list(remaining):
                deps = set(MODULES[module_id]["depends"])
                if deps.issubset(set(result)):
                    result.append(module_id)
                    remaining.remove(module_id)

        return result

    def _load_module(self, module_id: str):
        """Import and initialize a module."""
        config = MODULES[module_id]
        module = import_module(config["path"])

        if hasattr(module, "init"):
            module.init()

        self.loaded_modules[module_id] = module
        print(f"Loaded module: {module_id}")


# Singleton
_loader = None


def load_modules() -> Dict[str, Any]:
    """Load all enabled modules."""
    global _loader
    if _loader is None:
        _loader = ModuleLoader()
        _loader.load_all()
    return _loader.loaded_modules


def is_loaded(module_id: str) -> bool:
    """Check if a module is loaded."""
    if _loader is None:
        return False
    return module_id in _loader.loaded_modules
```

---

## Use Case Configurations

### Gate Control Only (Basic Tier)

For customers who only need gate access control.

```yaml
# config/license.yaml
license:
  tier: "basic"
  use_case: "gate_control"

  modules:
    - core
    - gate
    - logging

  limits:
    max_cameras: 2
    max_whitelist: 500
    retention_days: 7
```

**Features enabled:**
- Plate detection + OCR
- Whitelist/blacklist management
- Gate control (GPIO/HTTP)
- Auto-enrollment mode
- Basic event logging
- Dashboard alerts only

### Parking Logger (Standard Tier)

Includes everything from gate control plus logging features.

```yaml
# config/license.yaml
license:
  tier: "standard"
  use_case: "parking_logger"

  modules:
    # Gate control features (included)
    - core
    - gate
    - logging
    # Additional logging features
    - logging.duration
    - vehicle.color
    - alerts.email
    - alerts.sms

  limits:
    max_cameras: 4
    max_whitelist: 2000
    retention_days: 30
```

**Features enabled (everything in Basic plus):**
- Duration tracking (entry → exit)
- Tailgate detection
- Vehicle color detection
- Email notifications
- SMS notifications

### Full System (Professional Tier)

Complete feature set for large deployments.

```yaml
# config/license.yaml
license:
  tier: "professional"
  use_case: "full"

  modules:
    # All previous modules
    - core
    - gate
    - logging
    - logging.duration
    - vehicle.color
    - alerts.email
    - alerts.sms
    # Professional additions
    - vehicle.make_model
    - analytics
    - integrations.api
    - integrations.cloud

  limits:
    max_cameras: 8
    max_whitelist: 10000
    retention_days: 90
```

**Features enabled (everything in Standard plus):**
- Vehicle make/model detection
- Advanced analytics & reports
- REST API access
- Cloud portal sync
- Webhook integrations

---

## Development Setup

### Initial Setup

```bash
# Clone repository
git clone https://github.com/your-org/alpr-edge.git
cd alpr-edge

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Copy example configs
cp config/license.example.yaml config/license.yaml
cp config/cameras.example.yaml config/cameras.yaml
cp .env.example .env

# Run tests
pytest

# Start development server
python -m alpr_edge.main --dev
```

### pyproject.toml

```toml
[project]
name = "alpr-edge"
version = "1.0.0"
description = "ALPR edge processing system with modular features"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "Proprietary"}

dependencies = [
    # Core detection
    "ultralytics>=8.0.0",
    "paddleocr>=2.7.0",
    "paddlepaddle>=2.5.0",
    "opencv-python>=4.6.0",
    "numpy>=1.24.0",

    # Web framework
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",

    # Database
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",

    # Validation
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",

    # Utilities
    "pyyaml>=6.0",
    "httpx>=0.26.0",
    "python-multipart>=0.0.6",
]

[project.optional-dependencies]
# GPU support
gpu = [
    "paddlepaddle-gpu>=2.5.0",
]

# Jetson GPIO
jetson = [
    "Jetson.GPIO>=2.1.0",
]

# Alerts
alerts = [
    "twilio>=8.0.0",
]

# Development
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "black>=23.12.0",
    "ruff>=0.1.9",
    "mypy>=1.8.0",
    "pre-commit>=3.6.0",
]

[project.scripts]
alpr-edge = "alpr_edge.main:run"

[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --cov=alpr_edge --cov-report=term-missing"

[tool.black]
line-length = 88
target-version = ['py310']

[tool.ruff]
line-length = 88
select = ["E", "F", "I", "N", "W", "UP", "B"]
```

---

## Team Workflow

### Branch Strategy

```
main              ●───────●───────●───────●  (production releases)
                  │       │       │       │
                  │       │       │       │
release/*         │   ●───●───●   │       │  (staging/QA)
                  │   │       │   │       │
                  │   │       │   │       │
develop           ●───●───●───●───●───●───●  (integration)
                  │   │   │   │   │   │
                  │   │   │   │   │   │
feature/*         ●───●   ●───●   ●───●      (feature work)
```

### Development Process

```
1. Create feature branch from develop
   git checkout develop
   git pull
   git checkout -b feature/add-sms-alerts

2. Make changes + add tests
   # Edit src/alpr_edge/modules/alerts/sms.py
   # Edit tests/unit/test_sms.py

3. Run tests locally
   pytest tests/

4. Push and create PR
   git push -u origin feature/add-sms-alerts
   # Create PR on GitHub: feature/add-sms-alerts → develop

5. CI runs automatically
   ✓ Tests pass
   ✓ Linting pass
   ✓ Build succeeds

6. Code review + merge to develop

7. When ready for release:
   - Create release/v1.2.0 from develop
   - QA testing on staging
   - Merge to main
   - Tag v1.2.0
```

### Working on Different Modules

```
Developer A: Working on gate module
  └── src/alpr_edge/modules/gate/
  └── tests/unit/test_gate*.py

Developer B: Working on analytics
  └── src/alpr_edge/modules/analytics/
  └── tests/unit/test_analytics*.py

Developer C: Working on core detection
  └── src/alpr_edge/core/
  └── tests/unit/test_detector.py

All changes merged to develop → tested together → released
```

---

## CI/CD Pipeline

### GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test
        run: pytest tests/ -v --cov=alpr_edge --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: pip install ruff black mypy
      - run: ruff check src/
      - run: black --check src/ tests/
      - run: mypy src/

  build:
    needs: [test, lint]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.sha }}
            ghcr.io/${{ github.repository }}:latest
          platforms: linux/amd64,linux/arm64
```

---

## Deployment Process

### Device Provisioning

```bash
#!/bin/bash
# scripts/provision.sh

PORTAL_URL="https://portal.yourcompany.com"
TOKEN="$1"

# Get device serial
SERIAL=$(cat /sys/firmware/devicetree/base/serial-number | tr -d '\0')
DEVICE_ID="dev_${SERIAL}"

# Register with cloud portal
curl -X POST "$PORTAL_URL/api/devices/register" \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"device_id\": \"$DEVICE_ID\"}"

# Download license
curl "$PORTAL_URL/api/devices/$DEVICE_ID/license" \
    -H "Authorization: Bearer $TOKEN" \
    -o /etc/alpr-edge/license.yaml

# Download config
curl "$PORTAL_URL/api/devices/$DEVICE_ID/config" \
    -H "Authorization: Bearer $TOKEN" \
    -o /etc/alpr-edge/config.yaml

# Start services
docker compose up -d
```

### Docker Compose with Profiles

```yaml
# docker/docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    profiles: ["core"]
    environment:
      POSTGRES_USER: ${DB_USER:-alpr}
      POSTGRES_PASSWORD: ${DB_PASS:-secret}
      POSTGRES_DB: ${DB_NAME:-alpr}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: unless-stopped

  alpr:
    image: ghcr.io/your-org/alpr-edge:${VERSION:-latest}
    profiles: ["core"]
    runtime: nvidia
    environment:
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASS}@postgres:5432/${DB_NAME}
      LICENSE_FILE: /etc/alpr-edge/license.yaml
    volumes:
      - /etc/alpr-edge:/etc/alpr-edge:ro
      - evidence:/app/evidence
    devices:
      - /dev/gpiomem:/dev/gpiomem
    depends_on:
      - postgres
    ports:
      - "8000:8000"
    restart: unless-stopped

volumes:
  postgres-data:
  evidence:
```

### Deployment by Use Case

```bash
# Gate Control (Basic)
VERSION=1.0.0 docker compose --profile core up -d

# Parking Logger (Standard) - same image, different license
VERSION=1.0.0 docker compose --profile core up -d

# The license.yaml determines which modules load, not the docker command
```

---

## Related Documentation

- [GitHub Setup Guide](github-setup-guide.md) - Step-by-step repository creation
- [Team Development Guide](team-development-guide.md) - Testing without Jetson hardware
- [Model Distribution](model-distribution.md) - MLflow model registry for team
- [Modular Deployment](modular-deployment.md) - License-based module loading
- [Feature Tiers](feature-tiers.md) - Complete feature breakdown
- [SaaS Business Model](saas-business-model.md) - Business model
- [Deployment Analysis](deployment-analysis.md) - Hardware and costs

