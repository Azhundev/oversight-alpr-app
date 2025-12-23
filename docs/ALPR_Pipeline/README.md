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

OVR-ALPR is a real-time license plate recognition system optimized for NVIDIA Jetson platforms. The system uses a hybrid architecture:

- **Edge Processing** (Jetson Device): Real-time camera ingestion, detection, OCR, and tracking
- **Containerized Services** (Docker): Data storage, event streaming, and query API

### Key Components

| Component | Type | Purpose |
|-----------|------|---------|
| **pilot.py** | Python Application | Main ALPR pipeline (runs on host) |
| **Kafka** | Docker Container | Event streaming platform |
| **TimescaleDB** | Docker Container | Time-series database for events |
| **Kafka Consumer** | Docker Container | Stores events from Kafka to DB |
| **Query API** | Docker Container | REST API for querying events |
| **Kafka UI** | Docker Container | Web interface for Kafka |

## Architecture

```
┌──────────────────────────────────────────┐
│       ALPR Pipeline (Host/Jetson)        │
│  ┌────────┐  ┌──────────┐  ┌──────────┐  │
│  │Camera  │→ │Detector  │→ │   OCR    │  │
│  │Manager │  │(YOLOv11) │  │(Paddle)  │  │
│  └────────┘  └──────────┘  └──────────┘  │
│       ↓                                   │
│  ┌──────────┐  ┌────────────────────┐    │
│  │ Tracker  │→ │ Event Processor    │    │
│  │(ByteTrack)  │ (Kafka Publisher)  │    │
│  └──────────┘  └──────────┬─────────┘    │
└────────────────────────────┼──────────────┘
                             │ publishes events
                             ▼
┌──────────────────────────────────────────┐
│      Docker Infrastructure Services       │
│  ┌─────────┐                              │
│  │  Kafka  │ (Port 9092)                  │
│  └────┬────┘                              │
│       │                                   │
│       ├──→ ┌─────────────────┐            │
│       │    │ Kafka Consumer  │            │
│       │    │   (Storage)     │            │
│       │    └────────┬────────┘            │
│       │             ▼                     │
│       │    ┌──────────────────┐           │
│       │    │   TimescaleDB    │           │
│       │    │   (Port 5432)    │           │
│       │    └────────┬─────────┘           │
│       │             │                     │
│       │             ▼                     │
│       └──→ ┌──────────────────┐           │
│            │    Query API     │           │
│            │   (Port 8000)    │           │
│            └──────────────────┘           │
└──────────────────────────────────────────┘
```

## Prerequisites

### Hardware Requirements

**Minimum** (Development/Testing):
- NVIDIA Jetson Orin NX 16GB
- 64GB storage
- USB Camera or IP Camera

**Recommended** (Production):
- NVIDIA Jetson Orin NX 16GB or AGX Orin
- 128GB+ NVMe SSD
- Industrial IP Camera with RTSP

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
  - 8080 (Kafka UI)
  - 9092 (Kafka)
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
- **Kafka UI**: http://localhost:8080
- **TimescaleDB**: localhost:5432 (user: alpr, db: alpr_db)

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

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_TOPIC=alpr.plates.detected

# API Configuration
API_PORT=8000
API_CORS_ORIGINS=*
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

### Service Health

Check Docker service status:

```bash
# All services
docker compose ps

# Specific service logs
docker compose logs -f query-api
docker compose logs -f kafka-consumer

# Resource usage
docker stats
```

### API Health Checks

```bash
# Query API health
curl http://localhost:8000/health

# Database statistics
curl http://localhost:8000/stats
```

### Kafka Monitoring

Access Kafka UI: http://localhost:8080

Features:
- Topic message counts
- Consumer lag monitoring
- Broker health
- Message inspection

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

1. **Increase frame skip**: Process fewer frames
   ```bash
   python3 pilot.py --frame-skip 3
   ```

2. **Disable display**: Save GPU resources
   ```bash
   python3 pilot.py --no-display
   ```

3. **Use TensorRT**: Optimize model inference
   ```bash
   python3 pilot.py --use-tensorrt
   ```

4. **Adjust batch size**: In detector configuration

### Horizontal Scaling (Multiple Devices)

Deploy across multiple Jetson devices:

1. **Centralized Infrastructure**:
   - Run Docker services on a powerful server
   - Point all Jetson devices to central Kafka

2. **Per-Camera Deployment**:
   - Each Jetson handles 1-4 cameras
   - All publish to central Kafka
   - Centralized storage and API

3. **Load Balancing**:
   - Use multiple Query API instances
   - Load balancer in front of APIs

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

For more troubleshooting tips, see [troubleshooting.md](troubleshooting.md).

## Related Documentation

- [Architecture Overview](architecture.md)
- [Docker Setup Guide](../docker-setup.md)
- [Storage Layer Documentation](../storage-layer.md)
- [Kafka Integration Guide](../INTEGRATION_COMPLETE%20Kafka%20+%20Event%20Processing.md)

## Support

For issues and questions:
- Check documentation in `/docs`
- Review logs with `docker compose logs`
- Monitor system with `tegrastats`
- Check GitHub issues (if applicable)
