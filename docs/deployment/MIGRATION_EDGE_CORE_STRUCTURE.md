# Migration Guide: Edge/Core Services Structure

**Date**: December 26, 2025
**Type**: Directory Structure Refactoring
**Impact**: File paths, imports, docker-compose.yml

---

## Summary

The ALPR codebase has been reorganized to clearly separate **edge services** (running on Jetson) from **core services** (running in Docker on backend).

### What Changed

```diff
OLD STRUCTURE:
OVR-ALPR/
├── services/
│   ├── camera/          # Edge
│   ├── detector/        # Edge
│   ├── ocr/             # Edge
│   ├── tracker/         # Edge
│   ├── event_processor/ # Edge
│   ├── storage/         # Core
│   └── api/             # Core
└── monitoring/          # Infrastructure
    ├── prometheus/
    ├── grafana/
    └── loki/

NEW STRUCTURE:
OVR-ALPR/
├── edge_services/       ✨ NEW
│   ├── camera/
│   ├── detector/
│   ├── ocr/
│   ├── tracker/
│   └── event_processor/
└── core_services/       ✨ NEW
    ├── storage/
    ├── api/
    └── monitoring/      📦 MOVED
        ├── prometheus/
        ├── grafana/
        └── loki/
```

---

## What Was Changed

### 1. Directory Structure

| Old Path | New Path | Type |
|----------|----------|------|
| `/services/camera/` | `/edge_services/camera/` | Edge |
| `/services/detector/` | `/edge_services/detector/` | Edge |
| `/services/ocr/` | `/edge_services/ocr/` | Edge |
| `/services/tracker/` | `/edge_services/tracker/` | Edge |
| `/services/event_processor/` | `/edge_services/event_processor/` | Edge |
| `/services/storage/` | `/core_services/storage/` | Core |
| `/services/api/` | `/core_services/api/` | Core |
| `/monitoring/` | `/core_services/monitoring/` | Core |

### 2. Docker Compose Changes

**Updated `docker-compose.yml`** to reflect new paths:

```yaml
# OLD
kafka-consumer:
  build:
    dockerfile: services/storage/Dockerfile

# NEW
kafka-consumer:
  build:
    dockerfile: core_services/storage/Dockerfile
```

**Updated Volume Mounts**:

```yaml
# OLD
volumes:
  - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro

# NEW
volumes:
  - ./core_services/monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
```

### 3. Documentation Updates

New README files added:
- ✅ `/edge_services/README.md` - Edge services guide
- ✅ `/core_services/README.md` - Core services guide

Updated documentation:
- Port reference paths
- Service architecture diagrams

---

## Action Required

### ✅ For Users (No Action Needed)

If you're using the system via Docker Compose, **everything still works**. The changes are transparent:

```bash
# These commands work exactly as before
docker compose up -d
docker compose logs kafka-consumer
docker compose ps
```

### ⚠️ For Developers

If you have **custom scripts** or **import statements**, you may need to update paths:

#### Python Imports

**Before**:
```python
from services.detector import PlateDetector
from services.ocr import OCRProcessor
```

**After**:
```python
from edge_services.detector import PlateDetector
from edge_services.ocr import OCRProcessor
```

#### File References

**Before**:
```python
CONFIG_PATH = "services/camera/config.yaml"
MODEL_PATH = "services/detector/model.pt"
```

**After**:
```python
CONFIG_PATH = "edge_services/camera/config.yaml"
MODEL_PATH = "edge_services/detector/model.pt"
```

#### Custom Docker Builds

If you have custom `docker-compose.override.yml` or build scripts:

**Before**:
```yaml
services:
  custom-service:
    build:
      context: ./services/storage
```

**After**:
```yaml
services:
  custom-service:
    build:
      context: ./core_services/storage
```

---

## Verification Steps

### 1. Verify Docker Compose

```bash
# Check configuration is valid
docker compose config --quiet

# Should only show version warning, no errors
```

### 2. Verify Services Start

```bash
# Stop all services
docker compose down

# Start services with new structure
docker compose up -d

# Check all containers are running
docker compose ps
```

### 3. Verify Monitoring Stack

```bash
# Check Grafana loads dashboards
curl -s http://localhost:3000/api/health

# Check Prometheus loads config
curl -s http://localhost:9090/-/healthy
```

### 4. Verify File Structure

```bash
# Should exist
ls edge_services/camera/
ls core_services/storage/
ls core_services/monitoring/

# Should NOT exist
ls services/ 2>/dev/null && echo "❌ Old services/ directory still exists!" || echo "✅ Clean migration"
```

---

## Benefits of New Structure

### 1. Clear Architectural Separation

**Before**: Mixed edge and backend services in `/services`
**After**: Clear distinction between edge and core

### 2. Deployment Clarity

| Directory | Deployment Target | Infrastructure |
|-----------|------------------|----------------|
| `edge_services/` | Jetson Orin NX | GPU, low latency |
| `core_services/` | Docker / Cloud | Scalable, persistent |

### 3. Easier Onboarding

New developers can immediately understand:
- What runs on edge devices
- What runs in backend infrastructure
- Where monitoring components are

### 4. Scalability

- **Edge**: Easy to add new edge devices with same code
- **Core**: Easy to scale backend services independently

---

## Rollback Procedure

If you need to rollback to the old structure:

```bash
# 1. Stop all services
docker compose down

# 2. Move services back
mv edge_services/camera services/
mv edge_services/detector services/
mv edge_services/ocr services/
mv edge_services/tracker services/
mv edge_services/event_processor services/
mv core_services/storage services/
mv core_services/api services/
mv core_services/monitoring ./monitoring

# 3. Restore docker-compose.yml from git
git checkout docker-compose.yml

# 4. Restart services
docker compose up -d
```

---

## Common Issues

### Issue 1: Import Errors

**Error**:
```
ModuleNotFoundError: No module named 'services'
```

**Fix**: Update imports to use `edge_services` or `core_services`

```python
# Change from
from services.detector import PlateDetector

# To
from edge_services.detector import PlateDetector
```

### Issue 2: Docker Build Failures

**Error**:
```
ERROR: failed to solve: failed to read dockerfile: open services/storage/Dockerfile: no such file or directory
```

**Fix**: Already handled in main `docker-compose.yml`. If using custom compose files, update paths:

```yaml
# In docker-compose.override.yml
services:
  kafka-consumer:
    build:
      dockerfile: core_services/storage/Dockerfile  # Updated path
```

### Issue 3: Missing Configuration Files

**Error**:
```
FileNotFoundError: monitoring/prometheus/prometheus.yml not found
```

**Fix**: Configuration files moved to `core_services/monitoring/`. Update any scripts:

```bash
# Change from
PROM_CONFIG="monitoring/prometheus/prometheus.yml"

# To
PROM_CONFIG="core_services/monitoring/prometheus/prometheus.yml"
```

---

## Testing Checklist

After migration, verify:

- [ ] Docker Compose validates: `docker compose config`
- [ ] All containers start: `docker compose up -d`
- [ ] Kafka consumer processes messages
- [ ] Query API responds: `curl http://localhost:8000/health`
- [ ] Grafana dashboards load: http://localhost:3000
- [ ] Prometheus scrapes targets: http://localhost:9090/targets
- [ ] Edge services import correctly (if applicable)
- [ ] No references to old `/services` path in custom code

---

## Questions & Support

### Where should I put new services?

**Edge service** (needs GPU, low latency, runs on Jetson):
- Add to `edge_services/`
- Examples: camera processing, real-time detection, tracking

**Core service** (needs persistence, can scale, runs in Docker):
- Add to `core_services/`
- Examples: data storage, APIs, analytics, monitoring

**Infrastructure** (observability, networking):
- Add to `core_services/monitoring/` if monitoring-related
- Otherwise, create top-level directory (e.g., `/infrastructure`)

### Can I still use `/services` directory?

No. The `/services` directory has been removed. All code moved to:
- `edge_services/` - Edge device services
- `core_services/` - Backend services

### Will this break my existing deployments?

**No**, if you're using the standard `docker-compose.yml`. All paths have been updated.

**Maybe**, if you have:
- Custom build scripts referencing `/services`
- Import statements using `services.` prefix
- Configuration files with hardcoded paths

Check the "Action Required for Developers" section above.

---

## Related Documentation

- [Edge Services README](../edge_services/README.md)
- [Core Services README](../core_services/README.md)
- [Port Reference](alpr_pipeline/port-reference.md)
- [Monitoring Stack Setup](Services/monitoring-stack-setup.md)

---

**Migration completed successfully on December 26, 2025** ✅
