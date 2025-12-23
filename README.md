# OVR-ALPR: Automatic License Plate Recognition System

**Production-ready ALPR system with distributed architecture** for real-time vehicle detection, license plate recognition, and event streaming.

[![Status](https://img.shields.io/badge/status-production--ready-green)]() [![Phase](https://img.shields.io/badge/phase-2-blue)]() [![Cameras](https://img.shields.io/badge/cameras-1--10-orange)]()

---

## 🚀 Quick Start

### Prerequisites

- **Hardware:** NVIDIA Jetson Orin NX (16GB) or better
- **Software:** Ubuntu 20.04/22.04, Docker 20.10+, Python 3.8+
- **Cameras:** RTSP-compatible IP cameras or video files

### 1. Start Backend Services

```bash
# Start Kafka, TimescaleDB, and API services
docker compose up -d

# Verify all services are healthy
docker compose ps
```

### 2. Run ALPR Pipeline

```bash
# Basic usage (with display)
python3 pilot.py

# Production mode (headless, optimized)
python3 pilot.py --no-display --frame-skip 2

# Get help
python3 pilot.py --help
```

### 3. Access Services

- **Query API:** http://localhost:8000/docs (interactive API documentation)
- **Kafka UI:** http://localhost:8080 (message broker monitoring)
- **Database:** `localhost:5432` (TimescaleDB)

---

## 📋 What This System Does

### Edge Processing (pilot.py on Jetson)
1. **Captures** video from RTSP cameras or files
2. **Detects** vehicles and license plates (YOLOv11 + TensorRT)
3. **Tracks** objects across frames (ByteTrack)
4. **Recognizes** plate text (PaddleOCR with per-track optimization)
5. **Validates** and deduplicates events
6. **Publishes** to Kafka message broker

### Backend Services (Docker)
7. **Streams** events via Apache Kafka
8. **Stores** events in TimescaleDB (time-series database)
9. **Provides** REST API for querying events
10. **Monitors** via Kafka UI web interface

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│    EDGE (Jetson)                        │
│  Camera → Detection → Tracking → OCR    │
│         → Event Processing → Kafka      │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│    BACKEND (Docker)                     │
│  Kafka → Consumer → TimescaleDB         │
│                  ↓                      │
│              Query API                  │
└─────────────────────────────────────────┘
```

**See:** [docs/ALPR_Pipeline/SERVICES_OVERVIEW.md](docs/ALPR_Pipeline/SERVICES_OVERVIEW.md) for complete architecture details.

---

## ✨ Key Features

### ✅ Production-Ready
- Complete edge-to-cloud pipeline
- Event persistence with zero data loss
- RESTful API for querying events
- Docker-based deployment
- TensorRT optimization (2-3x faster inference)

### ✅ Intelligent Processing
- **Per-track OCR throttling** (10-30x performance boost)
- Fuzzy deduplication (handles OCR errors)
- Best-shot selection for plate crops
- Spatial deduplication (merges fragmented tracks)
- Quality-based filtering

### ✅ Scalable
- Horizontal scaling (add more Jetsons)
- Distributed deployment (edge + centralized backend)
- Event streaming via Kafka
- Time-series optimized storage

---

## 📊 Performance

### Edge Processing
- **15-25 FPS** per stream (full pipeline with OCR)
- **1-2 cameras** per Jetson Orin NX (16GB)
- **40-90ms** end-to-end latency (capture → Kafka)
- **Sub-20ms** detection (TensorRT FP16)

### Backend Capacity
- **100+ events/second** sustained
- **10,000+ messages/second** Kafka throughput
- **500-1000 inserts/second** TimescaleDB

**See:** [docs/ALPR_Pipeline/Project_Status.md](docs/ALPR_Pipeline/Project_Status.md) for detailed metrics.

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Detection** | YOLOv11 + TensorRT | Vehicle & plate detection |
| **OCR** | PaddleOCR | License plate text recognition |
| **Tracking** | ByteTrack | Multi-object tracking |
| **Messaging** | Apache Kafka | Event streaming |
| **Database** | TimescaleDB (PostgreSQL 16) | Time-series storage |
| **API** | FastAPI | REST endpoints |
| **Deployment** | Docker Compose | Container orchestration |

---

## 📁 Project Structure

```
OVR-ALPR/
├── pilot.py                    # Main ALPR pipeline
├── docker-compose.yml          # Backend services
├── requirements.txt            # Python dependencies
│
├── config/                     # YAML configurations
│   ├── cameras.yaml           # Camera definitions
│   ├── tracking.yaml          # ByteTrack parameters
│   └── ocr.yaml               # PaddleOCR settings
│
├── services/                   # Service implementations
│   ├── camera/                # Video ingestion
│   ├── detector/              # YOLO detection
│   ├── tracker/               # ByteTrack tracking
│   ├── ocr/                   # PaddleOCR service
│   ├── event_processor/       # Event validation & publishing
│   ├── storage/               # Database persistence
│   └── api/                   # Query API (FastAPI)
│
├── scripts/                    # Utility scripts
│   ├── init_db.sql            # Database initialization
│   └── *.py                   # Helper scripts
│
└── docs/                       # Documentation
    └── ALPR_Pipeline/
        ├── SERVICES_OVERVIEW.md      # Complete service reference
        ├── Project_Status.md         # Current implementation status
        ├── ALPR_Next_Steps.md        # Roadmap & next priorities
        └── PIPELINE_COMPARISON.md    # Architecture comparisons
```

---

## 📚 Documentation

### Getting Started
- **[Deployment Guide](docs/ALPR_Pipeline/README.md)** - Complete deployment instructions
- **[Quick Reference](docs/deployment/quick-reference.md)** - Common commands and operations

### Architecture & Design
- **[Services Overview](docs/ALPR_Pipeline/SERVICES_OVERVIEW.md)** - All 10+ services documented
- **[Pipeline Comparison](docs/ALPR_Pipeline/PIPELINE_COMPARISON.md)** - Current vs future architectures
- **[Storage Layer](docs/storage-layer.md)** - TimescaleDB schema and queries

### Status & Roadmap
- **[Project Status](docs/ALPR_Pipeline/Project_Status.md)** - What's implemented vs planned
- **[Next Steps](docs/ALPR_Pipeline/ALPR_Next_Steps.md)** - Detailed roadmap with priorities

### Technical Guides
- **[Kafka Setup](docs/kafka-setup.md)** - Message broker configuration
- **[Jetson Setup](docs/Jetson/JETSON_SETUP.md)** - Hardware platform setup
- **[TensorRT Export](docs/TENSORRT_EXPORT.md)** - Model optimization

---

## 🔧 Configuration

### Camera Setup

Edit `config/cameras.yaml`:

```yaml
cameras:
  - id: "cam_01"
    name: "Front Gate"
    source: "rtsp://192.168.1.100:554/stream"
    fps: 30
    resolution: [1920, 1080]
```

### Environment Variables

Create `.env` file:

```env
# Database
DB_HOST=timescaledb
DB_PORT=5432
DB_NAME=alpr_db
DB_USER=alpr
DB_PASSWORD=your_secure_password

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=alpr.plates.detected
```

---

## 🎯 Use Cases

### Supported Deployments

✅ **Small/Medium** - 1-10 cameras, single or distributed deployment
✅ **Development** - Testing and algorithm development
✅ **Edge Computing** - Jetson-based edge processing
✅ **Multi-Site** - Multiple Jetsons with centralized backend

### Industry Applications

- Parking lot management
- Access control (gates, entrances)
- Traffic monitoring
- Security surveillance
- Fleet management
- Toll collection

---

## 🚦 Current Status

**Phase 2: Production-Ready Distributed Architecture**

| Component | Status | Notes |
|-----------|--------|-------|
| Edge Processing | ✅ Complete | TensorRT optimized |
| Kafka Messaging | ✅ Complete | Event streaming |
| Database Storage | ✅ Complete | TimescaleDB |
| Query API | ✅ Complete | FastAPI with docs |
| Docker Deployment | ✅ Complete | All services containerized |
| Object Storage | 🔄 Planned | MinIO (Phase 3) |
| Monitoring | 🔄 Planned | Prometheus/Grafana (Phase 3) |
| Alerting | 🔄 Planned | Real-time notifications (Phase 3) |

**Overall:** 36% of original vision, 85% of core ALPR features

**See:** [docs/ALPR_Pipeline/Project_Status.md](docs/ALPR_Pipeline/Project_Status.md)

---

## 🛣️ Roadmap

### Phase 3: Production Essentials (1-2 months)
- MinIO object storage for images
- Prometheus + Grafana monitoring
- Alert engine (email, Slack, SMS)
- BI dashboards

### Phase 4: Enterprise Features (2-4 months)
- Elasticsearch for full-text search
- Schema registry for event versioning
- Advanced analytics

### Phase 5: Scale Optimization (4-6 months)
- DeepStream migration (6-8x throughput)
- Triton Inference Server

**See:** [docs/ALPR_Pipeline/ALPR_Next_Steps.md](docs/ALPR_Pipeline/ALPR_Next_Steps.md)

---

## 🔍 API Examples

### Query Recent Events

```bash
# Get last 10 events
curl http://localhost:8000/events/recent?limit=10

# Search by plate
curl http://localhost:8000/events/plate/ABC1234

# Get database statistics
curl http://localhost:8000/stats
```

### Interactive API Documentation

Visit http://localhost:8000/docs for full API documentation with Try-it-out functionality.

---

## 🐛 Troubleshooting

### Services Won't Start

```bash
# Check Docker
sudo systemctl status docker

# View logs
docker compose logs -f

# Restart specific service
docker compose restart kafka-consumer
```

### Database Connection Issues

```bash
# Test database connection
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db

# Check database logs
docker compose logs timescaledb
```

### Kafka Consumer Not Processing

```bash
# Check consumer logs
docker compose logs -f kafka-consumer

# View consumer lag (Kafka UI)
# http://localhost:8080
```

**See:** Full troubleshooting guide in [docs/ALPR_Pipeline/README.md#troubleshooting](docs/ALPR_Pipeline/README.md#troubleshooting)

---

## 📈 Monitoring

### Service Health

```bash
# API health check
curl http://localhost:8000/health

# Kafka UI
http://localhost:8080

# Database queries
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db
```

### System Metrics

```bash
# Jetson performance
tegrastats

# Docker resources
docker stats

# View recent events
curl http://localhost:8000/events/recent?limit=5
```

---

## 🤝 Contributing

This is a private enterprise project. For internal development:

1. Create feature branch from `main`
2. Follow existing code style (Black formatter)
3. Add tests for new features
4. Update documentation
5. Create pull request

---

## 📄 License

Proprietary - Enterprise Use Only

---

## 👥 Authors

- **Project Lead:** Azhundev
- **AI Assistant:** Claude Code (Anthropic)
- **Documentation:** 2025-12-23

---

## 🆘 Support

### Internal Resources
- **Documentation:** See `docs/` folder
- **API Docs:** http://localhost:8000/docs
- **Kafka UI:** http://localhost:8080
- **Project Status:** [docs/ALPR_Pipeline/Project_Status.md](docs/ALPR_Pipeline/Project_Status.md)

### Common Commands

```bash
# Start everything
docker compose up -d && python3 pilot.py

# Stop everything
docker compose down

# View logs
docker compose logs -f

# Restart API
docker compose restart query-api

# Check Jetson GPU
tegrastats
```

---

**Ready to deploy?** See [docs/ALPR_Pipeline/README.md](docs/ALPR_Pipeline/README.md) for complete deployment guide.
