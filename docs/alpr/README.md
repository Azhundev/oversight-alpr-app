# OVR-ALPR Deployment Guide

This guide covers deploying the OVR-ALPR (Overhead View Recognition - Automatic License Plate Recognition) system in various environments.

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Deployment Options](#deployment-options)
6. [Configuration](#configuration)
7. [Monitoring](#monitoring)
8. [Scaling](#scaling)

## System Overview

OVR-ALPR is a real-time license plate recognition system optimized for NVIDIA Jetson platforms with GPU hardware acceleration. The system uses a hybrid architecture:

- **Edge Processing** (Jetson Device): Real-time camera ingestion with GPU video decode, detection, OCR, and tracking
- **Containerized Services** (Docker): Data storage, event streaming, dual-storage (SQL + NoSQL search), and REST API
- **Dual Storage Strategy**: TimescaleDB for SQL queries + OpenSearch for full-text search and analytics

### Key Components

| Component | Type | Purpose |
|-----------|------|---------|
| **pilot.py** | Python Application | Main ALPR pipeline (runs on host) with multi-topic publisher |
| **Kafka** | Docker Container | Event streaming platform (multi-topic architecture) |
| **Schema Registry** | Docker Container | Avro schema management (Port 8081) |
| **TimescaleDB** | Docker Container | Time-series database for events |
| **Kafka Consumer** | Docker Container | Stores events from Kafka to DB (with DLQ support) |
| **Alert Engine** | Docker Container | Real-time alerting with multi-channel notifications (with DLQ support) |
| **Elasticsearch Consumer** | Docker Container | Indexes events to OpenSearch for search (with DLQ support) |
| **DLQ Consumer** | Docker Container | Monitors Dead Letter Queue for failed messages (Port 8005) |
| **Metrics Consumer** | Docker Container | Aggregates system metrics from Kafka (Port 8006) |
| **OpenSearch** | Docker Container | Full-text search and analytics engine |
| **Query API** | Docker Container | REST API for SQL & search queries |
| **Service Manager** | Docker Container | Web dashboard to start/stop/monitor services |
| **Kafka UI** | Docker Container | Web interface for Kafka |
| **MinIO** | Docker Container | S3-compatible object storage for images |
| **Prometheus** | Docker Container | Metrics collection and storage |
| **Grafana** | Docker Container | Metrics visualization dashboards |
| **Metabase** | Docker Container | Business intelligence and analytics |
| **Loki** | Docker Container | Log aggregation system |
| **Promtail** | Docker Container | Log shipping agent |
| **cAdvisor** | Docker Container | Container resource metrics |
| **Node Exporter** | Docker Container | Host system metrics (Port 9100) |
| **Postgres Exporter** | Docker Container | TimescaleDB metrics (Port 9187) |
| **Kafka Exporter** | Docker Container | Kafka broker metrics (Port 9308) |
| **MLflow** | Docker Container | Model Registry & Experiment Tracking (Port 5000) |
| **Tempo** | Docker Container | Distributed Tracing (Ports 3200, 4317, 4318) |

## Architecture

```
┌────────────────────────────────────────────┐
│       ALPR Pipeline (Host/Jetson)          │
│  ┌────────┐  ┌──────────┐  ┌──────────┐    │
│  │Camera  │→ │Detector  │→ │   OCR    │    │
│  │Manager │  │(YOLOv11) │  │(Paddle)  │    │
│  └────────┘  └──────────┘  └──────────┘    │
│       ↓                                     │
│  ┌──────────┐  ┌──────────────────────┐    │
│  │ Tracker  │→ │  Event Processor     │    │
│  │(ByteTrack)  │ (Avro Publisher)     │    │
│  └──────────┘  └──────────┬───────────┘    │
└────────────────────────────┼────────────────┘
                             │ publishes Avro events
                             ▼
┌────────────────────────────────────────────┐
│      Docker Infrastructure Services         │
│  ┌─────────┐  ┌─────────────┐               │
│  │  Kafka  │←→│   Schema    │               │
│  │(Port    │  │  Registry   │               │
│  │ 9092)   │  │ (Port 8081) │               │
│  └────┬────┘  └─────────────┘               │
│       │                                     │
│       ├──→ ┌─────────────────┐              │
│       │    │ Kafka Consumer  │              │
│       │    │ (Avro→Storage)  │              │
│       │    └────────┬────────┘              │
│       │             ▼                       │
│       │    ┌──────────────────┐             │
│       │    │   TimescaleDB    │             │
│       │    │   (Port 5432)    │             │
│       │    └────────┬─────────┘             │
│       │             │                       │
│       ├──→ ┌─────────────────────┐          │
│       │    │  Alert Engine       │          │
│       │    │  (Notifications)    │          │
│       │    └─────────────────────┘          │
│       │                                     │
│       ├──→ ┌──────────────────────┐         │
│       │    │ Elasticsearch        │         │
│       │    │ Consumer             │         │
│       │    └────────┬─────────────┘         │
│       │             ▼                       │
│       │    ┌──────────────────┐             │
│       │    │   OpenSearch     │             │
│       │    │   (Port 9200)    │             │
│       │    └────────┬─────────┘             │
│       │             │                       │
│       │    ┌────────┴─────────┐             │
│       │    │                  │             │
│       │    ▼                  ▼             │
│       │  ┌──────────────────────────┐       │
│       └─→│     Query API            │       │
│          │   SQL + Search Endpoints │       │
│          │     (Port 8000)          │       │
│          └──────────────────────────┘       │
│                                             │
│          ┌──────────────┐                   │
│          │    MinIO     │                   │
│          │ (Port 9000)  │                   │
│          │  S3 Storage  │                   │
│          └──────────────┘                   │
└─────────────────────────────────────────────┘
```

## Prerequisites

### Hardware Requirements

**Minimum** (Development/Testing):
- NVIDIA Jetson Orin NX 16GB
- 64GB storage
- USB Camera or IP Camera

**Recommended** (Production):
- NVIDIA Jetson Orin NX 16GB or AGX Orin (supports 4-6 RTSP streams with GPU decode)
- 128GB+ NVMe SSD
- Industrial IP Camera with RTSP (H.264/H.265)
- Network bandwidth for multiple RTSP streams

### Software Requirements

- **Operating System**: Ubuntu 20.04 LTS (JetPack 5.x) or Ubuntu 22.04 LTS
- **Docker**: Version 20.10+
- **Docker Compose**: Version 2.0+
- **Python**: 3.8+
- **CUDA**: 11.4+ (included in JetPack)

### Network Requirements

- Open ports:
  - 5432 (TimescaleDB)
  - 8000 (Query API)
  - 8001 (Pilot metrics)
  - 8002 (Kafka Consumer metrics)
  - 8003 (Alert Engine metrics)
  - 8004 (Elasticsearch Consumer metrics)
  - 8005 (DLQ Consumer metrics)
  - 8006 (Metrics Consumer metrics)
  - 8080 (Kafka UI)
  - 9000 (MinIO API)
  - 9001 (MinIO Console)
  - 9092 (Kafka)
  - 9200/9600 (OpenSearch)
  - 3000 (Grafana)
  - 3001 (Metabase)
  - 3200 (Tempo API)
  - 4317 (Tempo OTLP gRPC)
  - 4318 (Tempo OTLP HTTP)
  - 9090 (Prometheus)
  - RTSP camera streams (if using IP cameras)

## Quick Start

### 1. Clone Repository

```bash
cd /home/jetson
git clone <repository-url> OVR-ALPR
cd OVR-ALPR
```

### 2. Start Infrastructure Services

```bash
# Start all Docker services
docker compose up -d

# Verify services are running
docker compose ps

# Check logs
docker compose logs -f
```

Expected output:
```
NAME                  STATUS
alpr-kafka            Up (healthy)
alpr-kafka-consumer   Up
alpr-kafka-ui         Up
alpr-query-api        Up (healthy)
alpr-timescaledb      Up (healthy)
alpr-zookeeper        Up
```

### 3. Configure Cameras

Edit camera configuration:

```bash
nano config/cameras.yaml
```

Example configuration:
```yaml
cameras:
  - id: "cam_01"
    name: "Front Gate"
    source: "rtsp://192.168.1.100:554/stream"
    fps: 30
    resolution: [1920, 1080]
```

### 4. Run ALPR Pipeline

```bash
# Basic usage
python3 pilot.py

# With options
python3 pilot.py --display --enable-ocr --enable-tracking

# Production mode (no display, optimized)
python3 pilot.py --no-display --frame-skip 2
```

### 5. Access Services

- **Query API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Grafana Dashboards**: http://localhost:3000 (user: admin, password: alpr_admin_2024)
- **Metabase Analytics**: http://localhost:3001 (create admin account on first access)
- **Prometheus**: http://localhost:9090
- **Kafka UI**: http://localhost:8080
- **MinIO Console**: http://localhost:9001 (user: alpr_minio, password: alpr_minio_secure_pass_2024)
- **MinIO API**: http://localhost:9000
- **OpenSearch**: http://localhost:9200
- **TimescaleDB**: localhost:5432 (user: alpr, db: alpr_db)
- **MLflow**: http://localhost:5000 (Model Registry & Experiments)
- **Tempo**: http://localhost:3200 (Distributed Tracing API)

### 6. Test the System

```bash
# Query recent events (SQL)
curl "http://localhost:8000/events/recent?limit=10"

# Search for a plate (Full-text search)
curl "http://localhost:8000/search/fulltext?q=ABC123"

# Get faceted search results
curl "http://localhost:8000/search/facets?camera_id=cam1&limit=20"

# Get analytics
curl "http://localhost:8000/search/analytics?metric=top_plates&limit=10"

# Check OpenSearch cluster health
curl "http://localhost:9200/_cluster/health"
```

## Deployment Options

### Option 1: Development Mode

For testing and development on a single Jetson device.

```bash
# Start infrastructure only
docker compose up -d

# Run pipeline manually
python3 pilot.py --display
```

**Pros**: Easy debugging, full control
**Cons**: Manual startup, not persistent

### Option 2: Production Mode (Systemd Service)

For production deployment with automatic startup.

Create systemd service:

```bash
sudo nano /etc/systemd/system/alpr.service
```

```ini
[Unit]
Description=ALPR Pipeline Service
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=jetson
WorkingDirectory=/home/jetson/OVR-ALPR
ExecStartPre=/usr/bin/docker compose up -d
ExecStart=/usr/bin/python3 pilot.py --no-display --frame-skip 2
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable alpr.service
sudo systemctl start alpr.service

# Check status
sudo systemctl status alpr.service

# View logs
sudo journalctl -u alpr.service -f
```

### Option 3: Multiple Cameras/Distributed

For deploying across multiple Jetson devices with centralized storage.

**Setup**:
1. Run infrastructure on a central server
2. Configure each Jetson to connect to central Kafka
3. Each Jetson runs only the ALPR pipeline

See [distributed-deployment.md](distributed-deployment.md) for details.

## Configuration

### Environment Variables

Create `.env` file in project root:

```env
# Database Configuration
DB_HOST=timescaledb
DB_PORT=5432
DB_NAME=alpr_db
DB_USER=alpr
DB_PASSWORD=your_secure_password

# Kafka Configuration (Multi-Topic Architecture)
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_TOPIC_PLATES=alpr.events.plates
KAFKA_TOPIC_VEHICLES=alpr.events.vehicles
KAFKA_TOPIC_METRICS=alpr.metrics
KAFKA_TOPIC_DLQ=alpr.dlq

# API Configuration
API_PORT=8000
API_CORS_ORIGINS=*

# Consumer Configuration (with DLQ Support)
MAX_RETRIES=3
RETRY_DELAY_BASE=2.0
PROCESSING_TIMEOUT=30.0
ENABLE_DLQ=true
```

### Docker Compose Override

For environment-specific settings, create `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  query-api:
    ports:
      - "8080:8000"  # Change external port
    environment:
      LOG_LEVEL: debug
```

### ALPR Pipeline Configuration

Edit `config/cameras.yaml` for camera settings.

Command-line options:

```bash
python3 pilot.py --help
```

Key options:
- `--display`: Show visualization window
- `--save-output`: Save annotated frames
- `--enable-ocr`: Enable license plate OCR
- `--enable-tracking`: Enable vehicle tracking
- `--frame-skip N`: Process every Nth frame
- `--use-tensorrt`: Use TensorRT optimization

## Monitoring

### Observability Stack

The system includes a complete monitoring stack for production deployments:

**Grafana Dashboards** (http://localhost:3000):
- **ALPR Overview** - Real-time FPS, detections, latency metrics
- **System Performance** - CPU, RAM, network usage per container
- **Kafka & Database** - Message consumption, DB writes, API performance
- **Search & Indexing (OpenSearch)** - Indexing rate, bulk performance, search metrics
- **Alert Engine** - Alert processing, notification delivery
- **Logs Explorer** - Centralized log search and filtering

**Metabase Business Intelligence** (http://localhost:3001):
- Executive Overview Dashboard - Total reads, trends, top plates, vehicle types
- Camera Performance Analysis - Reads per camera, confidence scores
- Plate Recognition Quality Reports - Confidence distribution, quality trends
- Time-based Analytics - Peak hours, day-of-week patterns, busiest times
- Custom SQL queries for ad-hoc analysis
- Scheduled email reports for stakeholders

**Distributed Tracing** (Grafana Explore → Tempo):
- End-to-end request tracing across services
- OpenTelemetry instrumentation in Query API
- Trace-to-log correlation (click trace → see related logs)
- Trace-to-metrics correlation (see metrics for traced requests)
- Service dependency visualization

**Access**:
- Grafana: http://localhost:3000 (Login: `admin` / `alpr_admin_2024`)
- Metabase: http://localhost:3001 (Create admin account on first access)

**Key Metrics**:
- Current FPS and processing latency
- Plates detected (last minute and total)
- Kafka publish/consume rates
- Database write performance
- OpenSearch indexing rate and search latency
- Alert processing and delivery stats
- Container resource usage

### Service Health

Check Docker service status:

```bash
# All services
docker compose ps

# Specific service logs
docker compose logs -f query-api
docker compose logs -f kafka-consumer
docker compose logs -f alert-engine
docker compose logs -f elasticsearch-consumer

# Resource usage
docker stats

# Monitoring stack logs
docker compose logs -f prometheus grafana loki
```

### API Health Checks

```bash
# Query API health
curl http://localhost:8000/health

# Database statistics
curl http://localhost:8000/stats

# OpenSearch cluster health
curl http://localhost:9200/_cluster/health

# OpenSearch indices
curl http://localhost:9200/_cat/indices?v

# Prometheus metrics
curl http://localhost:8001/metrics  # pilot.py
curl http://localhost:8002/metrics  # kafka-consumer
curl http://localhost:8003/metrics  # alert-engine
curl http://localhost:8004/metrics  # elasticsearch-consumer
curl http://localhost:8005/metrics  # dlq-consumer
curl http://localhost:8006/metrics  # metrics-consumer
curl http://localhost:8000/metrics  # query-api
curl http://localhost:9090          # Prometheus
```

### Kafka Monitoring

Access Kafka UI: http://localhost:8080

Features:
- Topic message counts
- Consumer lag monitoring
- Broker health
- Message inspection
- Schema Registry integration

### Database Monitoring

Connect to database:

```bash
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db
```

Useful queries:

```sql
-- Recent events
SELECT * FROM plate_events ORDER BY detected_at DESC LIMIT 10;

-- Event count by camera
SELECT camera_id, COUNT(*) FROM plate_events GROUP BY camera_id;

-- Database size
SELECT pg_size_pretty(pg_database_size('alpr_db'));

-- Recent plates
SELECT DISTINCT plate_normalized_text, COUNT(*) as count
FROM plate_events
WHERE detected_at > NOW() - INTERVAL '1 hour'
GROUP BY plate_normalized_text
ORDER BY count DESC;
```

### OpenSearch Monitoring

Check OpenSearch cluster and indices:

```bash
# Cluster health
curl http://localhost:9200/_cluster/health?pretty

# List all indices
curl http://localhost:9200/_cat/indices?v

# Index stats
curl http://localhost:9200/alpr-events-*/_stats?pretty

# Search for recent documents
curl -X GET "http://localhost:9200/alpr-events-*/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "size": 5,
    "sort": [{"captured_at": "desc"}],
    "query": {"match_all": {}}
  }'

# Count documents by index
curl http://localhost:9200/alpr-events-*/_count?pretty

# Get index mapping
curl http://localhost:9200/alpr-events-*/_mapping?pretty
```

### System Monitoring

Monitor Jetson performance:

```bash
# GPU/CPU usage
tegrastats

# Docker container resources
docker stats

# Disk space
df -h

# Memory usage
free -h
```

## Scaling

### Vertical Scaling (Single Device)

Optimize performance on a single Jetson:

1. **Use RTSP streams with GPU decode**: Enables 4-6 concurrent streams (vs 1-2 with video files)
   - Configure RTSP URLs in `config/cameras.yaml`
   - GPU hardware decode (NVDEC) reduces CPU usage by 80-90%
   - Supports H.264 and H.265 codecs

2. **Increase frame skip**: Process fewer frames
   ```bash
   python3 pilot.py --frame-skip 3
   ```

3. **Disable display**: Save GPU resources
   ```bash
   python3 pilot.py --no-display
   ```

4. **Use TensorRT**: Optimize model inference (already enabled by default)
   ```bash
   python3 pilot.py --use-tensorrt
   ```

5. **Adjust batch size**: In detector configuration

### Horizontal Scaling (Multiple Devices)

Deploy across multiple Jetson devices:

1. **Centralized Infrastructure**:
   - Run Docker services on a powerful server
   - Point all Jetson devices to central Kafka

2. **Per-Camera Deployment**:
   - Each Jetson handles 4-6 RTSP cameras (with GPU decode)
   - All publish to central Kafka
   - Centralized storage and API

3. **Load Balancing**:
   - Use multiple Query API instances
   - Load balancer in front of APIs

**Example:** 20 cameras = 4-5 Jetson devices with GPU decode (vs 10+ without)

See [scaling.md](scaling.md) for detailed guide.

## Backup and Recovery

### Database Backup

```bash
# Backup database
docker exec alpr-timescaledb pg_dump -U alpr alpr_db > backup_$(date +%Y%m%d).sql

# Restore database
docker exec -i alpr-timescaledb psql -U alpr -d alpr_db < backup_20241216.sql
```

### Configuration Backup

```bash
# Backup configuration
tar -czf config_backup_$(date +%Y%m%d).tar.gz config/ docker-compose.yml
```

### Automated Backups

Add to crontab:

```bash
# Daily database backup at 2 AM
0 2 * * * docker exec alpr-timescaledb pg_dump -U alpr alpr_db > /backup/alpr_$(date +\%Y\%m\%d).sql
```

## Security Considerations

### Production Checklist

- [ ] Change default database password
- [ ] Configure firewall rules
- [ ] Enable SSL/TLS for API
- [ ] Restrict CORS origins
- [ ] Use secrets management
- [ ] Enable authentication for Query API
- [ ] Regular security updates
- [ ] Monitor access logs

### Securing the API

See [security.md](security.md) for detailed security hardening guide.

## Troubleshooting

Common issues and solutions:

### Services Won't Start

```bash
# Check Docker status
sudo systemctl status docker

# Restart Docker
sudo systemctl restart docker

# Check logs
docker compose logs
```

### Database Connection Failed

```bash
# Verify TimescaleDB is running
docker compose ps timescaledb

# Check database logs
docker compose logs timescaledb

# Test connection
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db
```

### Kafka Consumer Not Processing

```bash
# Check consumer logs
docker compose logs -f kafka-consumer

# Verify Kafka topics
docker exec alpr-kafka kafka-topics --bootstrap-server localhost:9092 --list

# Check consumer group
docker exec alpr-kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group alpr-storage-consumer \
  --describe
```

### OpenSearch Not Indexing

```bash
# Check Elasticsearch Consumer logs
docker compose logs -f elasticsearch-consumer

# Verify OpenSearch is running
docker compose ps opensearch

# Check cluster health
curl http://localhost:9200/_cluster/health

# Check indices
curl http://localhost:9200/_cat/indices?v

# Verify consumer metrics
curl http://localhost:8004/metrics | grep elasticsearch_consumer
```

### Search Queries Not Working

```bash
# Verify OpenSearch connection
curl http://localhost:9200/_cluster/health

# Check if documents exist
curl "http://localhost:9200/alpr-events-*/_count"

# Test direct OpenSearch query
curl -X GET "http://localhost:9200/alpr-events-*/_search?q=*&size=1"

# Check Query API logs
docker compose logs -f query-api
```

For more troubleshooting tips, see [troubleshooting.md](troubleshooting.md).

## Related Documentation

- [Architecture Overview](architecture.md)
- [Services Overview](SERVICES_OVERVIEW.md)
- [OpenSearch Integration Guide](OpenSearch_Integration.md)
- [Docker Setup Guide](../docker-setup.md)
- [Storage Layer Documentation](../storage-layer.md)
- [Kafka Integration Guide](../INTEGRATION_COMPLETE%20Kafka%20+%20Event%20Processing.md)

## Support

For issues and questions:
- Check documentation in `/docs`
- Review logs with `docker compose logs`
- Monitor system with `tegrastats`
- Check GitHub issues (if applicable)
