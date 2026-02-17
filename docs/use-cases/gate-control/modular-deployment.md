# Modular Deployment for SaaS

**Created:** 2026-02-17
**Updated:** 2026-02-17
**Purpose:** Configure per-customer deployments with only the modules they need
**Related:** [Project Structure](project-structure.md) | [SaaS Business Model](saas-business-model.md) | [Feature Tiers](feature-tiers.md)

---

> **Single Repository:** All deployments use the **alpr-edge** repository with features enabled by license. This document covers how license validation determines which modules load at runtime. See [Project Structure](project-structure.md) for the complete repository layout.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module Registry](#module-registry)
4. [Feature Configuration](#feature-configuration)
5. [Docker Profiles](#docker-profiles)
6. [License Management](#license-management)
7. [Cloud Portal Integration](#cloud-portal-integration)
8. [Deployment Workflow](#deployment-workflow)
9. [Module Implementation](#module-implementation)
10. [Configuration Examples](#configuration-examples)

---

## Overview

Each customer deployment should:
- **Only install** modules they're paying for
- **Only load** features enabled in their license
- **Minimize resources** (RAM, CPU, storage)
- **Receive updates** only for their modules
- **Report usage** to cloud portal for billing

```
Per-Customer Deployment:
══════════════════════════════════════════════════════════════════

Customer A (Basic)              Customer B (Standard)
$40/mo                          $60/mo
┌─────────────────────┐         ┌─────────────────────┐
│ Jetson Device       │         │ Jetson Device       │
│                     │         │                     │
│ ✓ Plate detection   │         │ ✓ Plate detection   │
│ ✓ Gate control      │         │ ✓ Gate control      │
│ ✓ Basic dashboard   │         │ ✓ Basic dashboard   │
│ ✗ Vehicle color     │         │ ✓ Vehicle color     │
│ ✗ Tailgate detect   │         │ ✓ Tailgate detect   │
│ ✗ SMS alerts        │         │ ✓ SMS alerts        │
│ ✗ Make/model        │         │ ✗ Make/model        │
│                     │         │                     │
│ RAM: ~2GB           │         │ RAM: ~3GB           │
│ Containers: 3       │         │ Containers: 4       │
└─────────────────────┘         └─────────────────────┘

Customer C (Professional)       Customer D (Enterprise)
$100/mo                         $200+/mo
┌─────────────────────┐         ┌─────────────────────┐
│ Jetson Device       │         │ Jetson Device       │
│                     │         │                     │
│ ✓ Plate detection   │         │ ✓ Plate detection   │
│ ✓ Gate control      │         │ ✓ Gate control      │
│ ✓ Basic dashboard   │         │ ✓ Basic dashboard   │
│ ✓ Vehicle color     │         │ ✓ Vehicle color     │
│ ✓ Tailgate detect   │         │ ✓ Tailgate detect   │
│ ✓ SMS alerts        │         │ ✓ SMS alerts        │
│ ✓ Make/model        │         │ ✓ Make/model        │
│ ✗ Multi-gate        │         │ ✓ Multi-gate        │
│ ✗ API access        │         │ ✓ API access        │
│                     │         │ ✓ Custom integrations│
│ RAM: ~4GB           │         │                     │
│ Containers: 5       │         │ RAM: ~6GB           │
└─────────────────────┘         │ Containers: 7       │
                                └─────────────────────┘
```

---

## Architecture

### Modular System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                     MODULAR ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  CORE (Always Loaded) - from alpr-edge repo               │  │
│  │  ──────────────────────────────────────                   │  │
│  │  • alpr_edge.core (detector, ocr, camera, tracker)       │  │
│  │  • Base API server                                        │  │
│  │  • PostgreSQL database                                    │  │
│  │  • License validator                                      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  MODULE LOADER                                            │  │
│  │  ─────────────                                            │  │
│  │  Reads license → Loads only enabled modules               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │ MODULE:     │     │ MODULE:     │     │ MODULE:     │       │
│  │ Gate Control│     │ Alerts      │     │ Vehicle     │       │
│  │             │     │             │     │ Attributes  │       │
│  │ • Whitelist │     │ • Email     │     │ • Color     │       │
│  │ • Blacklist │     │ • SMS       │     │ • Make      │       │
│  │ • GPIO      │     │ • Webhook   │     │ • Model     │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │ MODULE:     │     │ MODULE:     │     │ MODULE:     │       │
│  │ Tailgate    │     │ Analytics   │     │ API Access  │       │
│  │ Detection   │     │             │     │             │       │
│  │             │     │ • Reports   │     │ • REST API  │       │
│  │ • Multi-cam │     │ • Export    │     │ • Webhooks  │       │
│  │ • Alerts    │     │ • Dashboard │     │ • OAuth     │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Registry

### Available Modules

| Module ID | Name | Tier | RAM | Description |
|-----------|------|------|-----|-------------|
| `core.detection` | Plate Detection | All | 1.5GB | YOLOv11 + OCR (required) |
| `core.database` | Database | All | 256MB | PostgreSQL (required) |
| `core.api` | Base API | All | 128MB | Health, config endpoints |
| `gate.control` | Gate Control | Basic+ | 64MB | Whitelist, GPIO |
| `gate.enrollment` | Auto Enrollment | Basic+ | 32MB | Learning mode |
| `logging.basic` | Basic Logging | Basic+ | 64MB | Entry/exit records |
| `logging.duration` | Duration Tracking | Standard+ | 32MB | Time calculations |
| `alerts.email` | Email Alerts | Standard+ | 16MB | SMTP notifications |
| `alerts.sms` | SMS Alerts | Standard+ | 16MB | Twilio integration |
| `alerts.webhook` | Webhook Alerts | Standard+ | 16MB | HTTP callbacks |
| `vehicle.color` | Color Detection | Standard+ | 256MB | Vehicle color |
| `vehicle.type` | Vehicle Type | Standard+ | 128MB | Car/truck/motorcycle |
| `security.tailgate` | Tailgate Detection | Standard+ | 64MB | Multi-cam correlation |
| `vehicle.make` | Make Detection | Pro+ | 512MB | Brand recognition |
| `vehicle.model` | Model Detection | Pro+ | 512MB | Model recognition |
| `analytics.reports` | Reports | Pro+ | 128MB | PDF/Excel export |
| `analytics.dashboard` | Advanced Dashboard | Pro+ | 256MB | Charts, trends |
| `integration.api` | External API | Enterprise | 64MB | REST API access |
| `integration.webhook` | Outbound Webhooks | Enterprise | 32MB | Event streaming |
| `integration.custom` | Custom Modules | Enterprise | Varies | Per-customer |

### Module Dependencies

```yaml
# modules/registry.yaml
modules:
  core.detection:
    required: true
    depends: []

  core.database:
    required: true
    depends: []

  gate.control:
    required: false
    depends: [core.detection, core.database]

  security.tailgate:
    required: false
    depends: [gate.control, logging.basic]
    min_cameras: 2

  vehicle.color:
    required: false
    depends: [core.detection]

  vehicle.make:
    required: false
    depends: [core.detection, vehicle.color]
    model_file: vehicle_make_model.pt
    model_size_mb: 450

  alerts.sms:
    required: false
    depends: [core.api]
    requires_config: [twilio_sid, twilio_token, twilio_from]
```

---

## Feature Configuration

### License File Structure

Each device receives a license file from the cloud portal:

```yaml
# /etc/gate-control/license.yaml
# Downloaded from cloud portal, signed and encrypted

license:
  id: "lic_abc123xyz"
  customer_id: "cust_456"
  customer_name: "ABC Properties"
  device_id: "dev_jetson_789"

  tier: "standard"  # basic, standard, professional, enterprise

  # Explicit module list (overrides tier defaults)
  modules:
    - core.detection
    - core.database
    - core.api
    - gate.control
    - gate.enrollment
    - logging.basic
    - logging.duration
    - alerts.email
    - alerts.sms
    - vehicle.color
    - security.tailgate

  # Module-specific limits
  limits:
    max_cameras: 2
    max_whitelist_entries: 500
    log_retention_days: 30
    api_requests_per_day: 0  # 0 = disabled

  # Validity
  issued_at: "2026-02-01T00:00:00Z"
  expires_at: "2027-02-01T00:00:00Z"

  # Signature (verified against cloud public key)
  signature: "base64_encoded_signature..."
```

### Runtime Configuration

```yaml
# /etc/gate-control/config.yaml
# Local configuration (can be updated by cloud portal)

device:
  id: "dev_jetson_789"
  name: "Front Gate - ABC Properties"
  location: "123 Main St"

cameras:
  - id: entry_before
    rtsp_url: "rtsp://192.168.1.10/stream1"
    position: before_gate
    enabled: true

  - id: entry_after
    rtsp_url: "rtsp://192.168.1.11/stream1"
    position: after_gate
    enabled: true

gate:
  controller_type: gpio  # gpio, http, mqtt
  gpio_pin: 18
  open_duration_ms: 5000

alerts:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    recipients: ["admin@abcproperties.com"]

  sms:
    enabled: true
    recipients: ["+1234567890"]

cloud:
  portal_url: "https://portal.yourcompany.com"
  sync_interval_minutes: 5
  report_metrics: true
```

---

## Docker Profiles

### Profile-Based Deployment

```yaml
# docker-compose.yml
version: '3.8'

services:
  # ═══════════════════════════════════════════════════════════════
  # CORE SERVICES (Always running)
  # ═══════════════════════════════════════════════════════════════

  postgres:
    image: postgres:16-alpine
    container_name: gc-postgres
    profiles: ["core"]  # Always included
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASS}
      POSTGRES_DB: gate_control
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M

  alpr-core:
    image: your-registry/gate-control-core:${VERSION}
    container_name: gc-alpr
    profiles: ["core"]
    runtime: nvidia
    environment:
      LICENSE_FILE: /etc/license.yaml
      CONFIG_FILE: /etc/config.yaml
    volumes:
      - /etc/gate-control:/etc/gate-control:ro
      - ./models:/app/models:ro
      - evidence:/app/evidence
    devices:
      - /dev/gpiomem:/dev/gpiomem
    depends_on:
      - postgres
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G

  api:
    image: your-registry/gate-control-api:${VERSION}
    container_name: gc-api
    profiles: ["core"]
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASS}@postgres:5432/gate_control
      LICENSE_FILE: /etc/gate-control/license.yaml
    volumes:
      - /etc/gate-control:/etc/gate-control:ro
    depends_on:
      - postgres
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M

  # ═══════════════════════════════════════════════════════════════
  # OPTIONAL MODULES (Loaded based on license)
  # ═══════════════════════════════════════════════════════════════

  # Standard tier and above
  alerts:
    image: your-registry/gate-control-alerts:${VERSION}
    container_name: gc-alerts
    profiles: ["standard", "professional", "enterprise"]
    environment:
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASS}@postgres:5432/gate_control
      TWILIO_SID: ${TWILIO_SID}
      TWILIO_TOKEN: ${TWILIO_TOKEN}
    volumes:
      - /etc/gate-control:/etc/gate-control:ro
    depends_on:
      - postgres
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 64M

  vehicle-attributes:
    image: your-registry/gate-control-vehicle:${VERSION}
    container_name: gc-vehicle
    profiles: ["standard", "professional", "enterprise"]
    runtime: nvidia
    volumes:
      - /etc/gate-control:/etc/gate-control:ro
      - ./models:/app/models:ro
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M

  # Professional tier and above
  vehicle-make-model:
    image: your-registry/gate-control-make-model:${VERSION}
    container_name: gc-make-model
    profiles: ["professional", "enterprise"]
    runtime: nvidia
    volumes:
      - ./models:/app/models:ro
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G

  analytics:
    image: your-registry/gate-control-analytics:${VERSION}
    container_name: gc-analytics
    profiles: ["professional", "enterprise"]
    environment:
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASS}@postgres:5432/gate_control
    depends_on:
      - postgres
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M

  # Enterprise only
  api-gateway:
    image: your-registry/gate-control-gateway:${VERSION}
    container_name: gc-gateway
    profiles: ["enterprise"]
    ports:
      - "8080:8080"
    environment:
      API_KEYS_ENABLED: "true"
      RATE_LIMIT: "1000"
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 128M

volumes:
  postgres-data:
  evidence:
```

### Deployment Commands by Tier

```bash
# Basic tier (3 containers, ~2GB RAM)
docker compose --profile core up -d

# Standard tier (5 containers, ~3GB RAM)
docker compose --profile core --profile standard up -d

# Professional tier (7 containers, ~5GB RAM)
docker compose --profile core --profile standard --profile professional up -d

# Enterprise tier (8 containers, ~6GB RAM)
docker compose --profile core --profile standard --profile professional --profile enterprise up -d
```

---

## License Management

### License Validation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    LICENSE VALIDATION                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STARTUP                                                        │
│  ───────                                                        │
│  1. Read /etc/gate-control/license.yaml                        │
│  2. Verify signature against cloud public key                   │
│  3. Check expiration date                                       │
│  4. Verify device_id matches hardware                           │
│                                                                  │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────┐                │
│  │  License Valid?                             │                │
│  └─────────────────┬───────────────────────────┘                │
│                    │                                             │
│         ┌──────────┴──────────┐                                 │
│         ▼                     ▼                                 │
│     YES                    NO                                   │
│     ───                    ──                                   │
│  Load enabled           Show error                              │
│  modules only           Safe mode (detection only)              │
│         │                     │                                  │
│         ▼                     ▼                                  │
│  Start services         Alert cloud portal                      │
│                                                                  │
│  RUNTIME                                                        │
│  ───────                                                        │
│  • Check license every hour                                     │
│  • Sync with cloud portal every 5 minutes                      │
│  • Update config if pushed from portal                          │
│  • Report usage metrics                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### License Validator Module

```python
# app/license/validator.py
"""License validation and module loading."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Set

import yaml
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class LicenseError(Exception):
    """License validation failed."""
    pass


class LicenseValidator:
    """Validates license and determines enabled modules."""

    # Cloud portal public key (embedded or fetched)
    PUBLIC_KEY_PATH = "/etc/gate-control/cloud_public_key.pem"

    # Tier to modules mapping
    TIER_MODULES = {
        "basic": {
            "core.detection",
            "core.database",
            "core.api",
            "gate.control",
            "gate.enrollment",
            "logging.basic",
        },
        "standard": {
            "logging.duration",
            "alerts.email",
            "alerts.sms",
            "alerts.webhook",
            "vehicle.color",
            "vehicle.type",
            "security.tailgate",
        },
        "professional": {
            "vehicle.make",
            "vehicle.model",
            "analytics.reports",
            "analytics.dashboard",
        },
        "enterprise": {
            "integration.api",
            "integration.webhook",
            "integration.custom",
        },
    }

    def __init__(self, license_path: str = "/etc/gate-control/license.yaml"):
        self.license_path = Path(license_path)
        self.license_data = None
        self.enabled_modules: Set[str] = set()

    def load_and_validate(self) -> bool:
        """Load and validate the license file."""
        if not self.license_path.exists():
            raise LicenseError("License file not found")

        with open(self.license_path) as f:
            data = yaml.safe_load(f)

        self.license_data = data.get("license", {})

        # Validate signature
        if not self._verify_signature():
            raise LicenseError("Invalid license signature")

        # Check expiration
        expires_at = datetime.fromisoformat(
            self.license_data["expires_at"].replace("Z", "+00:00")
        )
        if datetime.now(expires_at.tzinfo) > expires_at:
            raise LicenseError("License expired")

        # Check device ID
        if not self._verify_device_id():
            raise LicenseError("License not valid for this device")

        # Load enabled modules
        self._load_enabled_modules()

        return True

    def _verify_signature(self) -> bool:
        """Verify license signature against cloud public key."""
        try:
            with open(self.PUBLIC_KEY_PATH, "rb") as f:
                public_key = serialization.load_pem_public_key(f.read())

            # Create payload without signature
            payload = {k: v for k, v in self.license_data.items() if k != "signature"}
            payload_bytes = json.dumps(payload, sort_keys=True).encode()

            # Verify signature
            signature = bytes.fromhex(self.license_data["signature"])
            public_key.verify(
                signature,
                payload_bytes,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    def _verify_device_id(self) -> bool:
        """Verify license matches this device."""
        # Get device serial from Jetson
        try:
            with open("/sys/firmware/devicetree/base/serial-number", "r") as f:
                device_serial = f.read().strip().strip('\x00')
        except FileNotFoundError:
            # Fallback to MAC address
            import uuid
            device_serial = hex(uuid.getnode())

        expected_id = self.license_data.get("device_id", "")
        return expected_id == f"dev_jetson_{device_serial}" or expected_id == "*"

    def _load_enabled_modules(self):
        """Determine which modules are enabled."""
        tier = self.license_data.get("tier", "basic")

        # Start with tier defaults
        for t in ["basic", "standard", "professional", "enterprise"]:
            if t in self.TIER_MODULES:
                self.enabled_modules.update(self.TIER_MODULES[t])
            if t == tier:
                break

        # Override with explicit module list if provided
        explicit_modules = self.license_data.get("modules")
        if explicit_modules:
            self.enabled_modules = set(explicit_modules)

    def is_module_enabled(self, module_id: str) -> bool:
        """Check if a specific module is enabled."""
        return module_id in self.enabled_modules

    def get_enabled_modules(self) -> List[str]:
        """Get list of all enabled modules."""
        return sorted(self.enabled_modules)

    def get_limit(self, limit_name: str, default: int = 0) -> int:
        """Get a specific limit value."""
        limits = self.license_data.get("limits", {})
        return limits.get(limit_name, default)


# Singleton instance
_validator = None


def get_license_validator() -> LicenseValidator:
    """Get the license validator instance."""
    global _validator
    if _validator is None:
        _validator = LicenseValidator()
        _validator.load_and_validate()
    return _validator


def require_module(module_id: str):
    """Decorator to require a specific module."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            validator = get_license_validator()
            if not validator.is_module_enabled(module_id):
                raise LicenseError(
                    f"Module '{module_id}' is not enabled in your license. "
                    f"Please upgrade your plan."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

### Using License in API Routes

```python
# app/api/routes/vehicle.py
"""Vehicle attribute endpoints (requires license)."""

from fastapi import APIRouter, HTTPException, Depends

from app.license.validator import get_license_validator, require_module, LicenseError

router = APIRouter()


def check_vehicle_color_enabled():
    """Dependency to check vehicle.color module."""
    validator = get_license_validator()
    if not validator.is_module_enabled("vehicle.color"):
        raise HTTPException(
            status_code=403,
            detail="Vehicle color detection requires Standard tier or higher"
        )


def check_vehicle_make_enabled():
    """Dependency to check vehicle.make module."""
    validator = get_license_validator()
    if not validator.is_module_enabled("vehicle.make"):
        raise HTTPException(
            status_code=403,
            detail="Vehicle make detection requires Professional tier or higher"
        )


@router.get("/colors")
async def get_color_distribution(
    _: None = Depends(check_vehicle_color_enabled)
):
    """Get vehicle color distribution (Standard+)."""
    # Only runs if module is enabled
    return {"colors": [...]}


@router.get("/makes")
async def get_make_distribution(
    _: None = Depends(check_vehicle_make_enabled)
):
    """Get vehicle make distribution (Professional+)."""
    return {"makes": [...]}


# Or use decorator
@router.get("/search")
@require_module("vehicle.make")
async def search_by_vehicle(color: str = None, make: str = None):
    """Search vehicles by attributes."""
    return {"results": [...]}
```

---

## Cloud Portal Integration

### Device Registration

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEVICE PROVISIONING                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. NEW DEVICE SETUP                                            │
│     ─────────────────                                           │
│     • Flash Jetson with base image                              │
│     • Boot with network connected                                │
│     • Device auto-registers with cloud portal                    │
│                                                                  │
│  2. CLOUD PORTAL                                                │
│     ────────────                                                │
│     • Admin assigns device to customer                          │
│     • Selects tier (Basic/Standard/Pro/Enterprise)              │
│     • Configures cameras, gate settings                         │
│     • Generates license file                                    │
│                                                                  │
│  3. LICENSE PUSH                                                │
│     ────────────                                                │
│     • Portal pushes license to device                           │
│     • Device validates and restarts with new modules            │
│                                                                  │
│  4. ONGOING SYNC                                                │
│     ────────────                                                │
│     • Device reports health metrics every minute                │
│     • Portal can push config updates                            │
│     • Usage data synced for billing                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Cloud Sync Service

```python
# app/services/cloud_sync.py
"""Sync with cloud portal for config and metrics."""

import asyncio
from datetime import datetime
from typing import Dict, Any

import httpx

from app.config import settings
from app.license.validator import get_license_validator


class CloudSyncService:
    """Manages communication with cloud portal."""

    def __init__(self):
        self.portal_url = settings.cloud_portal_url
        self.device_id = settings.device_id
        self.api_key = settings.cloud_api_key
        self._running = False

    async def start(self):
        """Start background sync tasks."""
        self._running = True
        asyncio.create_task(self._health_report_loop())
        asyncio.create_task(self._config_sync_loop())

    async def stop(self):
        """Stop sync tasks."""
        self._running = False

    async def _health_report_loop(self):
        """Report health metrics every minute."""
        while self._running:
            try:
                await self.report_health()
            except Exception as e:
                print(f"Health report failed: {e}")
            await asyncio.sleep(60)

    async def _config_sync_loop(self):
        """Check for config updates every 5 minutes."""
        while self._running:
            try:
                await self.sync_config()
            except Exception as e:
                print(f"Config sync failed: {e}")
            await asyncio.sleep(300)

    async def report_health(self):
        """Send health metrics to cloud portal."""
        metrics = await self._collect_metrics()

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.portal_url}/api/devices/{self.device_id}/health",
                json=metrics,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )

    async def sync_config(self):
        """Check for and apply config updates."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.portal_url}/api/devices/{self.device_id}/config",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )

            if response.status_code == 200:
                new_config = response.json()
                if new_config.get("version") != settings.config_version:
                    await self._apply_config(new_config)

    async def report_usage(self, usage_data: Dict[str, Any]):
        """Report usage data for billing."""
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.portal_url}/api/devices/{self.device_id}/usage",
                json={
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": usage_data,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )

    async def _collect_metrics(self) -> Dict[str, Any]:
        """Collect system metrics."""
        import psutil

        validator = get_license_validator()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "device_id": self.device_id,
            "tier": validator.license_data.get("tier"),
            "enabled_modules": validator.get_enabled_modules(),
            "system": {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage("/").percent,
                "temperature": self._get_temperature(),
            },
            "services": await self._check_services(),
        }

    def _get_temperature(self) -> float:
        """Get Jetson temperature."""
        try:
            with open("/sys/devices/virtual/thermal/thermal_zone0/temp") as f:
                return int(f.read()) / 1000
        except:
            return 0.0

    async def _check_services(self) -> Dict[str, str]:
        """Check status of running services."""
        # Implementation depends on your setup
        return {
            "alpr": "running",
            "api": "running",
            "database": "running",
        }

    async def _apply_config(self, new_config: Dict[str, Any]):
        """Apply new configuration from portal."""
        # Save new config
        # Trigger service restart if needed
        pass
```

---

## Deployment Workflow

### Initial Device Setup

```bash
#!/bin/bash
# scripts/provision_device.sh

set -e

PORTAL_URL="https://portal.yourcompany.com"
PROVISION_TOKEN="$1"

echo "=== Gate Control Device Provisioning ==="

# 1. Get device serial
SERIAL=$(cat /sys/firmware/devicetree/base/serial-number | tr -d '\0')
DEVICE_ID="dev_jetson_${SERIAL}"

echo "Device ID: $DEVICE_ID"

# 2. Register with cloud portal
echo "Registering with cloud portal..."
RESPONSE=$(curl -s -X POST "$PORTAL_URL/api/devices/register" \
    -H "Authorization: Bearer $PROVISION_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"device_id\": \"$DEVICE_ID\", \"hardware\": \"jetson_orin_nano\"}")

# 3. Download license
echo "Downloading license..."
curl -s "$PORTAL_URL/api/devices/$DEVICE_ID/license" \
    -H "Authorization: Bearer $PROVISION_TOKEN" \
    -o /etc/gate-control/license.yaml

# 4. Download config
echo "Downloading configuration..."
curl -s "$PORTAL_URL/api/devices/$DEVICE_ID/config" \
    -H "Authorization: Bearer $PROVISION_TOKEN" \
    -o /etc/gate-control/config.yaml

# 5. Download cloud public key
echo "Downloading cloud public key..."
curl -s "$PORTAL_URL/api/public-key" \
    -o /etc/gate-control/cloud_public_key.pem

# 6. Determine tier and start services
TIER=$(grep "tier:" /etc/gate-control/license.yaml | awk '{print $2}')
echo "License tier: $TIER"

# 7. Start appropriate Docker profile
echo "Starting services for tier: $TIER..."
case $TIER in
    basic)
        docker compose --profile core up -d
        ;;
    standard)
        docker compose --profile core --profile standard up -d
        ;;
    professional)
        docker compose --profile core --profile standard --profile professional up -d
        ;;
    enterprise)
        docker compose --profile core --profile standard --profile professional --profile enterprise up -d
        ;;
esac

echo "=== Provisioning complete ==="
```

### Upgrade/Downgrade Tier

```bash
#!/bin/bash
# scripts/update_tier.sh
# Called by cloud sync when tier changes

set -e

NEW_TIER="$1"

echo "Updating to tier: $NEW_TIER"

# 1. Stop current services
docker compose down

# 2. Download new license
curl -s "$PORTAL_URL/api/devices/$DEVICE_ID/license" \
    -H "Authorization: Bearer $API_KEY" \
    -o /etc/gate-control/license.yaml

# 3. Start with new profile
case $NEW_TIER in
    basic)
        docker compose --profile core up -d
        ;;
    standard)
        docker compose --profile core --profile standard up -d
        ;;
    # ... etc
esac

# 4. Report success
curl -s -X POST "$PORTAL_URL/api/devices/$DEVICE_ID/tier-updated" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"tier\": \"$NEW_TIER\", \"status\": \"success\"}"
```

---

## Configuration Examples

### Basic Tier Customer

```yaml
# /etc/gate-control/license.yaml
license:
  id: "lic_basic_001"
  customer_id: "cust_smith"
  customer_name: "Smith Residence"
  device_id: "dev_jetson_abc123"
  tier: "basic"

  limits:
    max_cameras: 2
    max_whitelist_entries: 100
    log_retention_days: 7

  expires_at: "2027-02-01T00:00:00Z"
  signature: "..."
```

```yaml
# /etc/gate-control/config.yaml
cameras:
  - id: entry
    rtsp_url: "rtsp://192.168.1.10/stream1"
    position: entry_gate

gate:
  controller_type: gpio
  gpio_pin: 18

# No alerts configured (not in tier)
# No vehicle attributes (not in tier)
```

### Professional Tier Customer

```yaml
# /etc/gate-control/license.yaml
license:
  id: "lic_pro_042"
  customer_id: "cust_megacorp"
  customer_name: "MegaCorp Office Park"
  device_id: "dev_jetson_xyz789"
  tier: "professional"

  limits:
    max_cameras: 4
    max_whitelist_entries: 2000
    log_retention_days: 90

  expires_at: "2027-02-01T00:00:00Z"
  signature: "..."
```

```yaml
# /etc/gate-control/config.yaml
cameras:
  - id: entry_before
    rtsp_url: "rtsp://192.168.1.10/stream1"
    position: before_gate
  - id: entry_after
    rtsp_url: "rtsp://192.168.1.11/stream1"
    position: after_gate
  - id: exit
    rtsp_url: "rtsp://192.168.1.12/stream1"
    position: exit_gate

gate:
  controller_type: http
  http_url: "http://192.168.1.100/relay"

alerts:
  email:
    enabled: true
    smtp_host: "smtp.megacorp.com"
    recipients: ["security@megacorp.com"]
  sms:
    enabled: true
    recipients: ["+1555123456", "+1555789012"]

vehicle_detection:
  color: true
  make_model: true

analytics:
  reports_enabled: true
  dashboard_enabled: true
```

---

## Resource Usage by Tier

```
RESOURCE ALLOCATION
══════════════════════════════════════════════════════════════════

Tier          Containers    RAM Usage    GPU Memory    Storage
────────────────────────────────────────────────────────────────
Basic         3             ~2.0 GB      ~1.5 GB       ~2 GB/mo
Standard      5             ~3.0 GB      ~2.0 GB       ~5 GB/mo
Professional  7             ~4.5 GB      ~3.0 GB       ~10 GB/mo
Enterprise    8+            ~6.0 GB      ~4.0 GB       ~20 GB/mo

────────────────────────────────────────────────────────────────
Jetson Orin Nano 8GB:  Basic, Standard (comfortable)
Jetson Orin NX 8GB:    Professional (comfortable)
Jetson Orin NX 16GB:   Enterprise (comfortable)
```

---

## Related Documentation

- [GitHub Setup Guide](github-setup-guide.md) - Step-by-step repository creation
- [Project Structure](project-structure.md) - Repository organization
- [Model Distribution](model-distribution.md) - MLflow model registry for team
- [Feature Tiers](feature-tiers.md) - Feature breakdown by tier
- [SaaS Business Model](saas-business-model.md) - Business model details
- [Hardware Reliability](hardware-reliability.md) - Production reliability

