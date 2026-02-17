# ALPR Deployment Analysis

**Created:** 2026-02-14
**Updated:** 2026-02-17
**Purpose:** General deployment guide for small-scale ALPR systems (1-4 cameras)

---

> **Architecture Note:** All deployments use the **alpr-edge** single repository with features enabled by license configuration. See [Project Structure](project-structure.md) for repository layout and [Modular Deployment](modular-deployment.md) for license-based module loading.

---

## Related Documents

| Document | Description |
|----------|-------------|
| [Gate Control Use Case](use-case-gate-control.md) | Access control, whitelist/blacklist, gate integration |
| [Plate Logging Use Case](use-case-plate-logging.md) | Entry/exit logging with timestamps and metadata |
| [Hardware Reliability](hardware-reliability.md) | 24/7 operation, failure points, best practices |
| [SaaS Business Model](saas-business-model.md) | Multi-location business, pricing, revenue |
| [Feature Tiers](feature-tiers.md) | Scaling features based on customer needs |
| [Project Structure](project-structure.md) | Single repository architecture for all use cases |
| [Modular Deployment](modular-deployment.md) | License-based feature loading |

---

## Table of Contents

1. [Overview](#overview)
2. [Minimal System Architecture](#minimal-system-architecture)
3. [Full vs Minimal Stack](#full-vs-minimal-stack)
4. [Architecture Options](#architecture-options)
5. [Cost Analysis](#cost-analysis)
6. [Hardware Recommendations](#hardware-recommendations)
7. [Software Stack](#software-stack)
8. [Implementation Approaches](#implementation-approaches)
9. [Choosing the Right Setup](#choosing-the-right-setup)

---

## Overview

This guide covers deployment options for small-scale ALPR systems:
- 1-4 cameras
- Local gate control or logging applications
- Edge or cloud processing
- Minimal infrastructure requirements

For specific use case implementations, see:
- [Gate Control](use-case-gate-control.md) - Automated access control
- [Plate Logging](use-case-plate-logging.md) - Vehicle tracking with timestamps

---

## Minimal System Architecture

### Components Required

```
┌─────────────────────────────────────────────────────────────────┐
│                    MINIMAL ALPR SYSTEM                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  DETECTION PIPELINE                                       │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │   │
│  │  │  Camera     │───>│  YOLOv11    │───>│  PaddleOCR  │   │   │
│  │  │  Ingestion  │    │  Detection  │    │  Text Read  │   │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘   │   │
│  │                                               │           │   │
│  │                              ┌────────────────┘           │   │
│  │                              ▼                            │   │
│  │                    ┌─────────────────┐                    │   │
│  │                    │  ByteTrack      │                    │   │
│  │                    │  (Deduplication)│                    │   │
│  │                    └────────┬────────┘                    │   │
│  └─────────────────────────────┼────────────────────────────┘   │
│                                │                                 │
│                                ▼                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  APPLICATION LAYER                                        │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │   │
│  │  │  Database   │    │  Dashboard  │    │  Action     │   │   │
│  │  │  Storage    │    │  API        │    │  Handler    │   │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Core Components

| Component | Purpose | Options |
|-----------|---------|---------|
| **Camera Ingestion** | Capture RTSP streams | GStreamer, OpenCV |
| **Plate Detection** | Locate plates in frame | YOLOv11 + TensorRT |
| **OCR** | Read plate text | PaddleOCR |
| **Tracking** | Deduplicate reads | ByteTrack (optional) |
| **Database** | Store events/lists | PostgreSQL, SQLite |
| **API** | Dashboard/integration | FastAPI |
| **Action Handler** | Gate/alerts/logging | Custom logic |

---

## Full vs Minimal Stack

### Current Full System (25 Containers)

The full OVR-ALPR system is designed for enterprise deployments with:
- Multiple cameras (10+)
- Distributed processing
- Full observability
- Time-series analytics
- Model versioning

### Minimal Stack (3-5 Containers)

For 1-4 cameras, most services are unnecessary:

| Category | Full System | Minimal Stack | Why Remove |
|----------|-------------|---------------|------------|
| **Messaging** | Kafka + ZK + Schema Registry | None | Overkill for 2 cameras |
| **Database** | TimescaleDB | PostgreSQL | No time-series needed |
| **Search** | OpenSearch + Consumer | None | Simple list lookup |
| **Monitoring** | Prometheus, Grafana, Loki, etc. | Optional | Basic logging sufficient |
| **Object Storage** | MinIO | Local disk | Small scale |
| **BI** | Metabase | None | Simple reports |
| **MLOps** | MLflow, Tempo | None | No model training |

**Result:** 25 containers → 3-5 containers

### Container Comparison

```
FULL SYSTEM (25 containers)
═══════════════════════════════════════════════════════════════
Kafka │ ZK │ Schema │ TimescaleDB │ OpenSearch │ OSH Dashboard │
Kafka UI │ MinIO │ API │ Consumer │ ES Consumer │ Alert Engine │
Prometheus │ Grafana │ Loki │ Promtail │ cAdvisor │
Node Exp │ PG Exp │ Kafka Exp │ Metabase │ MLflow │
Tempo │ Query API │ ... and more

MINIMAL SYSTEM (3-5 containers)
═══════════════════════════════════════════════════════════════
PostgreSQL │ ALPR Service │ Dashboard │ (Optional: Monitoring)
```

---

## Architecture Options

### Option A: Edge Processing (Recommended)

```
┌─────────────────────────────────────────────────────────────────┐
│                    EDGE DEPLOYMENT (Jetson)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  JETSON DEVICE (On-Premises)                               │ │
│  │                                                             │ │
│  │  ┌──────────────────────┐   ┌──────────────────────┐       │ │
│  │  │ Camera 1             │   │ Camera 2             │       │ │
│  │  └──────────┬───────────┘   └──────────┬───────────┘       │ │
│  │             │                          │                    │ │
│  │             └────────────┬─────────────┘                    │ │
│  │                      ▼                                      │ │
│  │  ┌───────────────────────────────────────────────────────┐ │ │
│  │  │  ALPR Pipeline (YOLOv11 + PaddleOCR + ByteTrack)      │ │ │
│  │  └───────────────────────────┬───────────────────────────┘ │ │
│  │                              │                              │ │
│  │          ┌───────────────────┼───────────────────┐          │ │
│  │          ▼                   ▼                   ▼          │ │
│  │    ┌──────────┐        ┌──────────┐        ┌──────────┐    │ │
│  │    │ Database │        │ Dashboard│        │  Action  │    │ │
│  │    │          │        │   API    │        │ Handler  │    │ │
│  │    └──────────┘        └──────────┘        └──────────┘    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Characteristics:**

| Factor | Value |
|--------|-------|
| **Latency** | 50-100ms |
| **Reliability** | Works offline |
| **Bandwidth** | Local only |
| **Privacy** | Data stays on-site |
| **Cost Model** | One-time hardware |

### Option B: Cloud Processing

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUD DEPLOYMENT                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ON-SITE                           CLOUD (AWS/GCP/Azure)        │
│  ┌──────────────┐                  ┌──────────────────────────┐ │
│  │              │   RTSP/WebRTC    │                          │ │
│  │  IP Cameras  │ ═══════════════► │  GPU VM                  │ │
│  │              │   (Internet)     │  • ALPR Processing       │ │
│  └──────────────┘                  │  • Database              │ │
│                                    │  • Dashboard API         │ │
│  ┌──────────────┐   Commands       │                          │ │
│  │ IoT Relay    │ ◄═══════════════ │                          │ │
│  │ (Gate/Alert) │   (Internet)     │                          │ │
│  └──────────────┘                  └──────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Characteristics:**

| Factor | Value |
|--------|-------|
| **Latency** | 200-500ms |
| **Reliability** | Depends on internet |
| **Bandwidth** | ~$50-100/mo streaming |
| **Privacy** | Data in cloud |
| **Cost Model** | Recurring monthly |

### Option C: Hybrid (Edge + Cloud Sync)

```
┌─────────────────────────────────────────────────────────────────┐
│                    HYBRID DEPLOYMENT                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ON-SITE (Jetson)                  CLOUD (Optional)             │
│  ┌──────────────────────┐          ┌──────────────────────────┐ │
│  │ • Real-time ALPR     │          │ • Centralized dashboard  │ │
│  │ • Local database     │ ──Sync──►│ • Multi-site aggregation │ │
│  │ • Gate/action control│          │ • Backup storage         │ │
│  │ • Works offline      │◄──Sync── │ • Remote list updates    │ │
│  └──────────────────────┘          └──────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Best for:** Multi-site deployments with centralized management.

---

## Cost Analysis

### Edge Deployment (Jetson)

| Item | One-Time | Monthly |
|------|----------|---------|
| Jetson Orin Nano 8GB | $199 | - |
| NVMe SSD (256GB) | $35 | - |
| Enclosure/cooling | $30 | - |
| Power (15W × 24/7) | - | ~$3-5 |
| **Total** | **~$265** | **~$5** |

### Cloud GPU Deployment

| Item | One-Time | Monthly |
|------|----------|---------|
| GPU VM (g4dn.xlarge reserved) | - | ~$150-200 |
| Bandwidth (2 cameras @ 4Mbps) | - | ~$50-100 |
| Storage (100GB) | - | ~$10 |
| **Total** | **$0** | **~$210-310** |

### Cloud CPU Deployment (Budget)

| Item | One-Time | Monthly |
|------|----------|---------|
| CPU VM (4 vCPU, 16GB) | - | ~$60-80 |
| Bandwidth | - | ~$50-100 |
| Storage | - | ~$10 |
| **Total** | **$0** | **~$120-190** |

> **Note:** CPU inference is 3-5x slower but may work for 2 cameras at reduced FPS.

### 3-Year TCO Comparison

```
TOTAL COST OF OWNERSHIP (3 Years)
═══════════════════════════════════════════════════════════════════

Jetson Orin Nano   ████ $530
                   ($265 hardware + $60×3 years power)

Cloud CPU          ████████████████████████████████████████████ $5,400
                   ($150/mo × 36 months)

Cloud GPU          ████████████████████████████████████████████████████████████ $7,200
                   ($200/mo × 36 months)

                   $0        $2,000     $4,000     $6,000     $8,000
```

**Edge is 10-14x cheaper over 3 years.**

---

## Hardware Recommendations

### Compute Options

| Device | Cameras | Price | Use Case |
|--------|---------|-------|----------|
| **Jetson Orin Nano 8GB** | 1-2 | $199 | Basic gate control |
| **Jetson Orin NX 8GB** | 2-4 | $399 | Multiple cameras |
| **Jetson Orin NX 16GB** | 4-6 | $599 | High throughput |
| **Jetson AGX Orin** | 6-10 | $1,999 | Enterprise edge |

### Camera Requirements

| Specification | Minimum | Recommended |
|---------------|---------|-------------|
| Resolution | 720p | 1080p |
| Frame Rate | 15 FPS | 25-30 FPS |
| Codec | H.264 | H.264/H.265 |
| Protocol | RTSP | RTSP |
| Night Vision | Required | IR + WDR |
| Positioning | Capture at 10-30° angle | Dedicated LPR camera |

**Recommended cameras:** $50-100 each (Hikvision, Dahua, Reolink)

### Complete Hardware Stack

| Component | Recommendation | Cost |
|-----------|----------------|------|
| Compute | Jetson Orin Nano 8GB | $199 |
| Storage | Samsung 980 256GB NVMe | $35 |
| Cameras (×2) | 1080p IP with RTSP | $100-200 |
| Gate Controller | Network relay (Shelly) | $15-30 |
| Enclosure | Weatherproof box | $20-30 |
| UPS | CyberPower 425VA | $40 |
| PoE Switch | 4-port | $30 |
| **Total** | | **$440-565** |

> For reliability best practices, see [Hardware Reliability Guide](hardware-reliability.md).

---

## Software Stack

### Minimal Docker Compose

```yaml
# docker-compose.minimal.yml
version: '3.8'

services:
  # Database
  postgres:
    image: postgres:16-alpine
    container_name: alpr-postgres
    environment:
      POSTGRES_USER: alpr
      POSTGRES_PASSWORD: secure_password
      POSTGRES_DB: alpr
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    restart: unless-stopped

  # ALPR + API Service
  alpr-service:
    build:
      context: .
      dockerfile: Dockerfile.minimal
    container_name: alpr-service
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql://alpr:secure_password@postgres:5432/alpr
      CAMERA_1_URL: rtsp://192.168.1.10:554/stream1
      CAMERA_2_URL: rtsp://192.168.1.11:554/stream1
    ports:
      - "8000:8000"
    volumes:
      - ./config:/app/config
      - ./evidence:/app/evidence
    devices:
      - /dev/video0:/dev/video0  # If using USB camera
    runtime: nvidia  # For GPU access
    restart: unless-stopped

  # Web Dashboard (optional - can be served by alpr-service)
  dashboard:
    image: nginx:alpine
    container_name: alpr-dashboard
    volumes:
      - ./dashboard/dist:/usr/share/nginx/html
    ports:
      - "80:80"
    restart: unless-stopped

volumes:
  postgres-data:
```

### Simplified Pipeline (pilot_lite.py)

| Feature | Full System | Minimal |
|---------|-------------|---------|
| Multi-camera | Yes | Yes (2-4) |
| YOLOv11 + TensorRT | Yes | Yes |
| PaddleOCR | Yes | Yes |
| ByteTrack | Yes | Optional |
| Kafka publishing | Yes | No (direct DB) |
| Avro serialization | Yes | No (JSON) |
| MinIO upload | Yes | No (local disk) |
| Prometheus metrics | Yes | Optional |
| Gate/action control | No | Yes |

---

## Implementation Approaches

### Approach A: New Minimal Build

Create a new lightweight system:
- New `pilot_lite.py` - simplified pipeline
- New `api.py` - FastAPI with business logic
- New dashboard - simple web UI
- Reuse: detector, OCR modules

**Effort:** 2-3 days
**Best for:** Clean start, optimized for use case

### Approach B: Strip Down Existing

Disable unnecessary services in current system:

```yaml
# docker-compose.override.yml
services:
  kafka:
    profiles: ["disabled"]
  zookeeper:
    profiles: ["disabled"]
  # ... disable 20+ services
```

**Effort:** 1-2 days
**Best for:** Leveraging existing code

### Approach C: Modular Feature Flags

Keep full system but enable only needed features:

```yaml
# config/features.yaml
features:
  kafka_enabled: false
  opensearch_enabled: false
  monitoring_enabled: false
  gate_control_enabled: true
  logging_enabled: true
```

**Effort:** 1 day
**Best for:** Flexibility, easy upgrade path

---

## Choosing the Right Setup

### Decision Matrix

| Factor | Edge Jetson | Cloud GPU | Cloud CPU |
|--------|-------------|-----------|-----------|
| **Cameras** | 1-6 | 1-20 | 1-4 |
| **Latency** | <100ms | 200-500ms | 300-700ms |
| **Uptime** | 99.9% | 99.9% | 99.9% |
| **Offline** | Yes | No | No |
| **3-Year Cost** | $530 | $7,200 | $5,400 |
| **Setup** | Medium | Easy | Easy |
| **Maintenance** | Medium | Low | Low |

### Recommendations

| Use Case | Best Option | Why |
|----------|-------------|-----|
| **Gate control** | Jetson Edge | Latency critical, offline required |
| **Parking logging** | Jetson Edge | Cost effective, privacy |
| **Multi-site SaaS** | Edge + Cloud Portal | Best of both worlds |
| **Quick prototype** | Cloud GPU | No hardware needed |
| **Budget test** | Cloud CPU | Cheapest start |

---

## Next Steps

1. **Choose use case:** [Gate Control](use-case-gate-control.md) or [Plate Logging](use-case-plate-logging.md)
2. **Select hardware:** Based on camera count and budget
3. **Review reliability:** [Hardware Reliability Guide](hardware-reliability.md)
4. **Plan scaling:** [Feature Tiers](feature-tiers.md)
5. **Consider business model:** [SaaS Business Model](saas-business-model.md)

---

## Related Documentation

- [Project Structure](project-structure.md) - Single repository architecture (alpr-edge)
- [Modular Deployment](modular-deployment.md) - License-based module configuration
- [Model Distribution](model-distribution.md) - MLflow model registry for team
- [Use Case: Gate Control](use-case-gate-control.md) - Access control implementation
- [Use Case: Plate Logging](use-case-plate-logging.md) - Entry/exit logging (extends Gate Control)
- [Feature Tiers](feature-tiers.md) - Scaling features by tier
- [SaaS Business Model](saas-business-model.md) - Multi-location business
- [Hardware Reliability](hardware-reliability.md) - 24/7 operation best practices
- [Full System Overview](../../alpr/services-overview.md) - Complete OVR-ALPR architecture
- [Tech Stack Guide](../../alpr/tech-stack-guide.md) - Technology details
