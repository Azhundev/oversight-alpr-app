# GitHub Repository Setup Guide

**Created:** 2026-02-17
**Purpose:** Step-by-step guide to create and configure the alpr-edge repository
**Related:** [Project Structure](project-structure.md) | [Modular Deployment](modular-deployment.md) | [SaaS Business Model](saas-business-model.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Repository Strategy](#repository-strategy)
3. [Creating the Repository](#creating-the-repository)
4. [Initial Project Setup](#initial-project-setup)
5. [Migrating from OVR-ALPR](#migrating-from-ovr-alpr)
6. [Branch Protection & Workflows](#branch-protection--workflows)
7. [CI/CD Configuration](#cicd-configuration)
8. [Cloud Portal Repository](#cloud-portal-repository)
9. [Development Workflow](#development-workflow)
10. [Release Process](#release-process)
11. [Next Steps Checklist](#next-steps-checklist)

---

## Overview

This guide walks through creating the **alpr-edge** repository for production deployments. The repository contains all ALPR functionality with modular features enabled by license configuration.

```
REPOSITORY LANDSCAPE
══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│  CURRENT STATE                                                   │
│  ─────────────                                                   │
│  OVR-ALPR (monolith)                                            │
│  • Full 25-container system                                     │
│  • Development/learning project                                 │
│  • Contains reusable components                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Extract & simplify
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  TARGET STATE                                                    │
│  ────────────                                                    │
│                                                                  │
│  ┌─────────────────────────────┐  ┌─────────────────────────┐  │
│  │  alpr-edge                  │  │  alpr-portal            │  │
│  │  (Edge Deployments)         │  │  (Cloud Management)     │  │
│  │                             │  │                         │  │
│  │  • Gate Control             │  │  • Customer dashboard   │  │
│  │  • Plate Logging            │  │  • Device management    │  │
│  │  • License validation       │  │  • License generation   │  │
│  │  • Local processing         │  │  • Billing integration  │  │
│  │  • Offline capable          │  │  • Multi-tenant         │  │
│  └─────────────────────────────┘  └─────────────────────────┘  │
│              │                              │                    │
│              └──────────────────────────────┘                    │
│                    Cloud sync (optional)                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Repository Strategy

### Two-Repository Approach

| Repository | Purpose | Priority |
|------------|---------|----------|
| **alpr-edge** | Edge device software (runs on Jetson) | **Phase 1** (Now) |
| **alpr-portal** | Cloud management portal | Phase 2 (Later) |

### Why Two Repos?

| Factor | Reason |
|--------|--------|
| **Different deployment targets** | Edge runs on Jetson, Portal runs on cloud |
| **Different tech stacks** | Edge: Python + TensorRT, Portal: Python/Node + React |
| **Different release cycles** | Edge: careful updates, Portal: rapid iteration |
| **Access control** | Portal may have different team members |
| **Simpler CI/CD** | Each repo has focused pipelines |

### What Stays in OVR-ALPR?

OVR-ALPR remains as:
- Development sandbox
- Reference implementation
- Full enterprise system (Kafka, OpenSearch, etc.)
- Training ground for learning the stack

---

## Creating the Repository

### Step 1: Create GitHub Repository

```bash
# Option A: Using GitHub CLI
gh repo create your-org/alpr-edge \
  --private \
  --description "ALPR edge processing system with modular features" \
  --clone

# Option B: Create on GitHub.com
# 1. Go to github.com/your-org
# 2. Click "New repository"
# 3. Name: alpr-edge
# 4. Private repository
# 5. Add README, .gitignore (Python), License
```

### Step 2: Clone and Initialize

```bash
# Clone the new repository
git clone git@github.com:your-org/alpr-edge.git
cd alpr-edge

# Create initial directory structure
mkdir -p src/alpr_edge/{core,modules,api,db}
mkdir -p src/alpr_edge/modules/{gate,logging,vehicle,alerts,analytics,integrations}
mkdir -p models config docker scripts tests/{unit,integration,e2e} docs dashboard

# Create initial files
touch src/alpr_edge/__init__.py
touch src/alpr_edge/main.py
touch src/alpr_edge/config.py
touch src/alpr_edge/license.py
```

### Step 3: Create Essential Files

**pyproject.toml:**
```bash
cat > pyproject.toml << 'EOF'
[project]
name = "alpr-edge"
version = "0.1.0"
description = "ALPR edge processing system with modular features"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "Proprietary"}

dependencies = [
    "ultralytics>=8.0.0",
    "paddleocr>=2.7.0",
    "paddlepaddle>=2.5.0",
    "opencv-python>=4.6.0",
    "numpy>=1.24.0",
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "pyyaml>=6.0",
    "httpx>=0.26.0",
    "python-multipart>=0.0.6",
]

[project.optional-dependencies]
jetson = ["Jetson.GPIO>=2.1.0"]
alerts = ["twilio>=8.0.0"]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
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

[tool.black]
line-length = 88

[tool.ruff]
line-length = 88
select = ["E", "F", "I", "N", "W", "UP", "B"]
EOF
```

**.gitignore:**
```bash
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
env/
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment
.env
.env.local
*.env

# Secrets
license.yaml
config/license.yaml
*.pem
*.key

# Models (large files)
models/*.pt
models/*.engine
models/*.onnx
!models/.gitkeep

# Evidence/logs
evidence/
logs/
*.log

# Database
*.db
*.sqlite

# OS
.DS_Store
Thumbs.db

# Testing
.coverage
htmlcov/
.pytest_cache/

# Docker
docker-compose.override.yml
EOF
```

**README.md:**
```bash
cat > README.md << 'EOF'
# ALPR Edge

Edge-based Automatic License Plate Recognition system with modular features.

## Features

- **Plate Detection**: YOLOv11 + TensorRT for fast, accurate detection
- **OCR**: PaddleOCR for text recognition
- **Gate Control**: Whitelist/blacklist with GPIO/HTTP gate triggers
- **Modular**: Features enabled by license configuration
- **Offline**: Works without internet connection

## Quick Start

```bash
# Clone and setup
git clone git@github.com:your-org/alpr-edge.git
cd alpr-edge
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
cp config/license.example.yaml config/license.yaml
cp config/cameras.example.yaml config/cameras.yaml

# Run
python -m alpr_edge.main
```

## Documentation

- [Project Structure](docs/project-structure.md)
- [Configuration Guide](docs/configuration.md)
- [API Reference](docs/api.md)
- [Deployment Guide](docs/deployment.md)

## License

Proprietary - See LICENSE file
EOF
```

---

## Initial Project Setup

### Step 4: Create Core Module Structure

```bash
# Core module files
cat > src/alpr_edge/core/__init__.py << 'EOF'
"""Core ALPR functionality - always loaded."""

from .detector import PlateDetector
from .ocr import OCREngine
from .tracker import PlateTracker
from .camera import CameraManager
from .pipeline import Pipeline

__all__ = [
    "PlateDetector",
    "OCREngine",
    "PlateTracker",
    "CameraManager",
    "Pipeline",
]
EOF

# Create placeholder files
touch src/alpr_edge/core/detector.py
touch src/alpr_edge/core/ocr.py
touch src/alpr_edge/core/tracker.py
touch src/alpr_edge/core/camera.py
touch src/alpr_edge/core/pipeline.py
touch src/alpr_edge/core/plate.py
```

### Step 5: Create Module Structure

```bash
# Gate module
cat > src/alpr_edge/modules/gate/__init__.py << 'EOF'
"""Gate control module - whitelist, blacklist, GPIO control."""

def init():
    """Initialize gate control module."""
    print("Gate control module loaded")
EOF

touch src/alpr_edge/modules/gate/controller.py
touch src/alpr_edge/modules/gate/access_list.py
touch src/alpr_edge/modules/gate/enrollment.py

# Logging module
cat > src/alpr_edge/modules/logging/__init__.py << 'EOF'
"""Logging module - entry/exit events, duration tracking."""

def init():
    """Initialize logging module."""
    print("Logging module loaded")
EOF

touch src/alpr_edge/modules/logging/events.py
touch src/alpr_edge/modules/logging/duration.py
touch src/alpr_edge/modules/logging/tailgate.py

# Create other module placeholders
for module in vehicle alerts analytics integrations; do
    touch src/alpr_edge/modules/$module/__init__.py
done
```

### Step 6: Create Configuration Templates

```bash
# License example
cat > config/license.example.yaml << 'EOF'
# ALPR Edge License Configuration
# Copy to license.yaml and update with your actual license

license:
  id: "lic_example_001"
  customer_id: "cust_example"
  customer_name: "Example Company"
  device_id: "dev_jetson_*"  # * = any device (dev only)

  tier: "basic"  # basic, standard, professional, enterprise

  modules:
    - core
    - gate
    - logging

  limits:
    max_cameras: 2
    max_whitelist_entries: 500
    log_retention_days: 7

  expires_at: "2027-01-01T00:00:00Z"

  # For production, this would be a real signature
  signature: "development_mode"
EOF

# Cameras example
cat > config/cameras.example.yaml << 'EOF'
# Camera Configuration
# Copy to cameras.yaml and update with your camera URLs

cameras:
  - id: entry_before
    name: "Main Entrance - Approach"
    rtsp_url: "rtsp://192.168.1.10:554/stream1"
    position: before_gate
    gate_id: gate_1
    enabled: true

  - id: entry_after
    name: "Main Entrance - Inside"
    rtsp_url: "rtsp://192.168.1.11:554/stream1"
    position: after_gate
    gate_id: gate_1
    enabled: true

  - id: exit_cam
    name: "Main Exit"
    rtsp_url: "rtsp://192.168.1.12:554/stream1"
    position: exit_gate
    enabled: true
EOF

# Gate example
cat > config/gate.example.yaml << 'EOF'
# Gate Controller Configuration

gate_controller:
  type: gpio  # gpio, http, mqtt

  gpio:
    pin: 18
    active_high: true
    open_duration_ms: 5000

  http:
    url: "http://192.168.1.100/relay/0"
    method: GET
    open_params:
      turn: "on"
      timer: 5
EOF
```

### Step 7: Initial Commit

```bash
# Add all files
git add .

# Initial commit
git commit -m "Initial project structure

- Core module structure (detector, ocr, tracker, camera, pipeline)
- Feature modules (gate, logging, vehicle, alerts, analytics, integrations)
- Configuration templates (license, cameras, gate)
- pyproject.toml with dependencies
- Basic documentation structure

Co-Authored-By: Claude <noreply@anthropic.com>"

# Push to main
git push -u origin main
```

---

## Migrating from OVR-ALPR

### Components to Migrate

| Component | Source (OVR-ALPR) | Target (alpr-edge) | Priority |
|-----------|-------------------|-------------------|----------|
| Plate Detector | `edge_services/detector/` | `src/alpr_edge/core/detector.py` | P0 |
| PaddleOCR | `edge_services/ocr/` | `src/alpr_edge/core/ocr.py` | P0 |
| ByteTrack | `edge_services/tracker/` | `src/alpr_edge/core/tracker.py` | P0 |
| Camera Ingest | `edge_services/camera/` | `src/alpr_edge/core/camera.py` | P0 |
| YOLO Models | `models/*.pt` | `models/*.pt` | P0 |
| FastAPI Base | `core_services/api/` | `src/alpr_edge/api/` | P1 |
| Config Loading | `config/` | `src/alpr_edge/config.py` | P1 |

### Migration Script

```bash
#!/bin/bash
# scripts/migrate_from_ovr.sh
# Run from alpr-edge directory

OVR_ALPR_PATH="../OVR-ALPR"

echo "=== Migrating from OVR-ALPR ==="

# 1. Copy detector code
echo "Copying detector..."
cp "$OVR_ALPR_PATH/edge_services/detector/plate_detector.py" \
   src/alpr_edge/core/detector.py

# 2. Copy OCR code
echo "Copying OCR..."
cp "$OVR_ALPR_PATH/edge_services/ocr/ocr_engine.py" \
   src/alpr_edge/core/ocr.py

# 3. Copy tracker
echo "Copying tracker..."
cp "$OVR_ALPR_PATH/edge_services/tracker/byte_tracker.py" \
   src/alpr_edge/core/tracker.py

# 4. Copy models
echo "Copying models..."
cp "$OVR_ALPR_PATH/models/yolo11n-plate.pt" models/
cp "$OVR_ALPR_PATH/models/yolo11n-plate.engine" models/ 2>/dev/null || true

# 5. Copy camera code
echo "Copying camera manager..."
cp "$OVR_ALPR_PATH/edge_services/camera/camera_manager.py" \
   src/alpr_edge/core/camera.py

echo "=== Migration complete ==="
echo "Review and refactor copied files to match new structure"
```

### Refactoring Guidelines

After copying, refactor each file:

1. **Update imports** - Change to new package structure
2. **Remove Kafka** - Replace with direct database/local processing
3. **Remove MinIO** - Replace with local file storage
4. **Simplify config** - Use pydantic-settings
5. **Add type hints** - Full typing for new code
6. **Add tests** - Unit tests for each module

---

## Branch Protection & Workflows

### Configure Branch Protection

```bash
# Using GitHub CLI
gh api repos/your-org/alpr-edge/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["test","lint"]}' \
  --field enforce_admins=false \
  --field required_pull_request_reviews='{"required_approving_review_count":1}' \
  --field restrictions=null
```

Or via GitHub UI:
1. Settings → Branches → Add rule
2. Branch name pattern: `main`
3. Enable:
   - Require pull request reviews (1 approval)
   - Require status checks (test, lint)
   - Require branches to be up to date

### Branch Naming Convention

```
main                    Production releases
├── develop             Integration branch
├── feature/*           New features
├── bugfix/*            Bug fixes
├── hotfix/*            Urgent production fixes
└── release/*           Release preparation
```

---

## CI/CD Configuration

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
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test
        run: |
          pytest tests/ -v --cov=alpr_edge --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: coverage.xml

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install linters
        run: pip install ruff black mypy

      - name: Run ruff
        run: ruff check src/

      - name: Run black
        run: black --check src/ tests/

      - name: Run mypy
        run: mypy src/

  build:
    needs: [test, lint]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
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
          platforms: linux/arm64
```

### Release Workflow

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: |
          docker buildx build \
            --platform linux/arm64 \
            --tag ghcr.io/${{ github.repository }}:${{ github.ref_name }} \
            --push \
            -f docker/Dockerfile .

      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          generate_release_notes: true
          files: |
            docker/docker-compose.yml
            config/*.example.yaml
```

---

## Cloud Portal Repository

### Phase 2: Create alpr-portal

When ready for cloud management:

```bash
# Create portal repository
gh repo create your-org/alpr-portal \
  --private \
  --description "ALPR cloud management portal"

# Initialize with web stack
npx create-next-app@latest alpr-portal --typescript --tailwind
cd alpr-portal

# Or use Python backend
mkdir -p alpr-portal/{backend,frontend}
cd alpr-portal/backend
# FastAPI backend for API
# React/Vue frontend for dashboard
```

### Portal Features (Phase 2)

| Feature | Description | Priority |
|---------|-------------|----------|
| Device registration | Register new Jetson devices | P0 |
| License generation | Create signed license files | P0 |
| Customer management | Add/edit customers | P0 |
| Device monitoring | Health status dashboard | P1 |
| Config push | Remote configuration updates | P1 |
| Billing integration | Stripe/payment processing | P2 |
| Analytics | Usage metrics across devices | P2 |

---

## Development Workflow

### Daily Development

```bash
# 1. Start from develop branch
git checkout develop
git pull

# 2. Create feature branch
git checkout -b feature/add-email-alerts

# 3. Make changes
# Edit src/alpr_edge/modules/alerts/email.py
# Add tests/unit/test_email_alerts.py

# 4. Run tests locally
pytest tests/unit/test_email_alerts.py -v

# 5. Commit with conventional commits
git add .
git commit -m "feat(alerts): add email notification module

- SMTP configuration support
- Template-based email formatting
- Queue for async sending

Closes #42"

# 6. Push and create PR
git push -u origin feature/add-email-alerts
gh pr create --base develop --title "Add email alerts module"

# 7. After approval, merge to develop
gh pr merge --squash
```

### Testing on Jetson

```bash
# On development machine
git push origin feature/test-on-jetson

# On Jetson device
cd ~/alpr-edge
git fetch origin
git checkout feature/test-on-jetson
pip install -e .
python -m alpr_edge.main --dev
```

---

## Release Process

### Creating a Release

```bash
# 1. Ensure develop is stable
git checkout develop
pytest tests/

# 2. Create release branch
git checkout -b release/v1.0.0

# 3. Update version
# Edit pyproject.toml: version = "1.0.0"
# Update CHANGELOG.md

# 4. Final testing
pytest tests/

# 5. Merge to main
git checkout main
git merge release/v1.0.0 --no-ff
git tag -a v1.0.0 -m "Release v1.0.0"

# 6. Push
git push origin main --tags

# 7. Merge back to develop
git checkout develop
git merge main
git push origin develop

# 8. CI/CD builds and pushes Docker image automatically
```

---

## Next Steps Checklist

### Phase 1: Repository Setup (Week 1)

- [ ] Create `alpr-edge` repository on GitHub
- [ ] Initialize project structure
- [ ] Set up pyproject.toml and dependencies
- [ ] Configure .gitignore and README
- [ ] Set up branch protection rules
- [ ] Create CI workflow (test + lint)
- [ ] Create initial configuration templates

### Phase 2: Core Migration (Week 2)

- [ ] Migrate plate detector from OVR-ALPR
- [ ] Migrate OCR engine
- [ ] Migrate ByteTrack tracker
- [ ] Migrate camera manager
- [ ] Create simplified pipeline (no Kafka)
- [ ] Copy and optimize YOLO models
- [ ] Add unit tests for core modules

### Phase 3: Gate Control Module (Week 3)

- [ ] Implement whitelist/blacklist management
- [ ] Implement GPIO gate controller
- [ ] Implement HTTP gate controller
- [ ] Add auto-enrollment mode
- [ ] Create basic dashboard API
- [ ] Add integration tests

### Phase 4: License System (Week 4)

- [ ] Implement license validation
- [ ] Implement module loader
- [ ] Create license generation script (for portal)
- [ ] Test tier-based feature loading
- [ ] Document license format

### Phase 5: Docker & Deployment (Week 5)

- [ ] Create Dockerfile for Jetson
- [ ] Create docker-compose.yml with profiles
- [ ] Create provisioning script
- [ ] Test deployment on Jetson device
- [ ] Document deployment process

### Phase 6: First Customer (Week 6+)

- [ ] Deploy to test customer
- [ ] Gather feedback
- [ ] Iterate on features
- [ ] Begin Phase 2 (Portal) planning

---

## Commands Quick Reference

```bash
# Create repo
gh repo create your-org/alpr-edge --private --clone

# Development setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# Testing
pytest tests/                    # All tests
pytest tests/unit/              # Unit only
pytest -k "test_detector"       # Specific tests

# Linting
ruff check src/                 # Check issues
ruff check src/ --fix           # Auto-fix
black src/ tests/               # Format code

# Git workflow
git checkout -b feature/name    # New feature
gh pr create --base develop     # Create PR
gh pr merge --squash            # Merge PR

# Release
git tag -a v1.0.0 -m "Release"  # Tag release
git push origin main --tags     # Push with tags
```

---

## Related Documentation

- [Team Development Guide](team-development-guide.md) - Testing without Jetson hardware
- [Model Distribution](model-distribution.md) - MLflow model registry for team
- [Project Structure](project-structure.md) - Detailed directory layout
- [Modular Deployment](modular-deployment.md) - License-based features
- [Feature Tiers](feature-tiers.md) - Feature breakdown by tier
- [SaaS Business Model](saas-business-model.md) - Business model
- [Deployment Analysis](deployment-analysis.md) - Hardware and costs
