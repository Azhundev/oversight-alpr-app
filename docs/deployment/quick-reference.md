# Quick Reference Guide

Quick commands and configurations for common OVR-ALPR deployment tasks.

## Table of Contents

1. [Common Commands](#common-commands)
2. [Service Management](#service-management)
3. [Monitoring](#monitoring)
4. [Database Queries](#database-queries)
5. [Configuration](#configuration)
6. [Troubleshooting](#troubleshooting)

## Common Commands

### Starting Services

```bash
# Start all services
docker compose up -d

# Start specific services
docker compose up -d timescaledb kafka query-api

# Start with rebuild
docker compose up -d --build

# View startup logs
docker compose up
```

### Stopping Services

```bash
# Stop all services
docker compose down

# Stop but keep data
docker compose stop

# Stop and remove volumes (deletes all data!)
docker compose down -v

# Stop specific service
docker compose stop query-api
```

### Running ALPR Pipeline

```bash
# Basic run
python3 pilot.py

# Production mode (no display, optimized)
python3 pilot.py --no-display --frame-skip 2 --adaptive-sampling

# Development mode (with visualization)
python3 pilot.py --display --save-output

# Custom configuration
python3 pilot.py \
  --camera-config config/cameras.yaml \
  --detector-model models/yolo11n.pt \
  --plate-model models/yolov11n-plate.pt \
  --frame-skip 2

# View all options
python3 pilot.py --help
```

## Service Management

### Docker Compose

```bash
# Check service status
docker compose ps

# View logs (all services)
docker compose logs

# Follow logs (specific service)
docker compose logs -f query-api
docker compose logs -f kafka-consumer

# Restart service
docker compose restart query-api

# Rebuild and restart
docker compose up -d --build query-api

# Scale service (if configured)
docker compose up -d --scale kafka-consumer=3

# Execute command in container
docker compose exec query-api /bin/bash
docker compose exec timescaledb psql -U alpr -d alpr_db
```

### Individual Containers

```bash
# List running containers
docker ps

# Stop container
docker stop alpr-query-api

# Start container
docker start alpr-query-api

# Remove container
docker rm alpr-query-api

# View container logs
docker logs -f alpr-query-api

# Container resource usage
docker stats

# Execute command
docker exec -it alpr-query-api python --version
```

### Systemd Service (if configured)

```bash
# Start ALPR service
sudo systemctl start alpr.service

# Stop ALPR service
sudo systemctl stop alpr.service

# Restart ALPR service
sudo systemctl restart alpr.service

# Check status
sudo systemctl status alpr.service

# Enable auto-start on boot
sudo systemctl enable alpr.service

# Disable auto-start
sudo systemctl disable alpr.service

# View logs
sudo journalctl -u alpr.service -f

# View last 100 lines
sudo journalctl -u alpr.service -n 100
```

## Monitoring

### Service Health

```bash
# Check all services
docker compose ps

# Check specific service health
curl http://localhost:8000/health

# Check database connection
docker exec alpr-timescaledb pg_isready -U alpr -d alpr_db

# Check Kafka broker
docker exec alpr-kafka kafka-broker-api-versions --bootstrap-server localhost:9092

# Check Tempo (distributed tracing)
curl http://localhost:3200/ready

# Check OpenSearch
curl http://localhost:9200/_cluster/health

# Check MLflow
curl http://localhost:5000/health
```

### Service URLs

```bash
# Core Services
Query API:          http://localhost:8000/docs
Service Manager:    http://localhost:8000/services/dashboard

# Monitoring & Observability
Grafana:            http://localhost:3000  (admin/alpr_admin_2024)
Prometheus:         http://localhost:9090
Tempo:              http://localhost:3200
Loki:               http://localhost:3100

# BI & Analytics
Metabase:           http://localhost:3001

# MLOps
MLflow:             http://localhost:5000

# Data Management
Kafka UI:           http://localhost:8080
MinIO Console:      http://localhost:9001
OpenSearch:         http://localhost:9200
OpenSearch UI:      http://localhost:5601
```

### Resource Usage

```bash
# Jetson GPU/CPU stats
tegrastats

# Docker container stats
docker stats

# Disk usage
df -h

# Memory usage
free -h

# Network connections
sudo netstat -tulpn | grep -E '8000|5432|9092'

# Process tree
pstree -p
```

### Logs

```bash
# Docker service logs
docker compose logs -f --tail=100

# Specific service
docker compose logs -f query-api

# ALPR pipeline logs (if using systemd)
sudo journalctl -u alpr.service -f

# System logs
sudo journalctl -f

# Kernel logs
dmesg -T
```

### Kafka Monitoring

```bash
# List topics
docker exec alpr-kafka kafka-topics --bootstrap-server localhost:9092 --list

# Topic details
docker exec alpr-kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic alpr.events.plates

# Consumer group status
docker exec alpr-kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group alpr-storage-consumer \
  --describe

# Consume messages (for testing)
docker exec alpr-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic alpr.events.plates \
  --from-beginning \
  --max-messages 10
```

## Database Queries

### Connection

```bash
# Connect to database
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db

# Run single query
docker exec alpr-timescaledb psql -U alpr -d alpr_db -c "SELECT COUNT(*) FROM plate_events;"
```

### Common Queries

```sql
-- Recent events
SELECT
    event_id,
    detected_at,
    camera_id,
    plate_normalized_text,
    plate_confidence
FROM plate_events
ORDER BY detected_at DESC
LIMIT 20;

-- Events in last hour
SELECT COUNT(*) as count
FROM plate_events
WHERE detected_at > NOW() - INTERVAL '1 hour';

-- Top plates today
SELECT
    plate_normalized_text,
    COUNT(*) as count,
    AVG(plate_confidence) as avg_confidence
FROM plate_events
WHERE detected_at > NOW() - INTERVAL '1 day'
GROUP BY plate_normalized_text
ORDER BY count DESC
LIMIT 10;

-- Events by camera
SELECT
    camera_id,
    COUNT(*) as total_events,
    COUNT(DISTINCT plate_normalized_text) as unique_plates,
    AVG(plate_confidence) as avg_confidence
FROM plate_events
GROUP BY camera_id
ORDER BY total_events DESC;

-- Hourly event distribution
SELECT
    DATE_TRUNC('hour', detected_at) as hour,
    COUNT(*) as events
FROM plate_events
WHERE detected_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;

-- High confidence reads
SELECT *
FROM plate_events
WHERE plate_confidence > 0.9
ORDER BY detected_at DESC
LIMIT 20;

-- Find specific plate
SELECT *
FROM plate_events
WHERE plate_normalized_text = 'ABC123'
ORDER BY detected_at DESC;

-- Database size
SELECT pg_size_pretty(pg_database_size('alpr_db')) as database_size;

-- Table size
SELECT pg_size_pretty(pg_total_relation_size('plate_events')) as table_size;

-- Row count
SELECT COUNT(*) FROM plate_events;

-- Index usage
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans
FROM pg_stat_user_indexes
WHERE tablename = 'plate_events'
ORDER BY idx_scan DESC;
```

### Database Maintenance

```sql
-- Vacuum table
VACUUM ANALYZE plate_events;

-- Reindex
REINDEX TABLE plate_events;

-- Delete old events (older than 30 days)
DELETE FROM plate_events
WHERE detected_at < NOW() - INTERVAL '30 days';
```

## API Queries

### Using curl

```bash
# API root
curl http://localhost:8000/

# Health check
curl http://localhost:8000/health

# Statistics
curl http://localhost:8000/stats

# Recent events
curl "http://localhost:8000/events/recent?limit=10"

# Events by plate
curl "http://localhost:8000/events/plate/ABC123?limit=10"

# Events by camera
curl "http://localhost:8000/events/camera/cam_01?limit=10"

# Search with filters
curl "http://localhost:8000/events/search?plate=ABC&limit=20"

# Specific event
curl "http://localhost:8000/events/550e8400-e29b-41d4-a716-446655440000"

# Pretty print JSON
curl -s http://localhost:8000/stats | python3 -m json.tool
```

### Using Python

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000"

# Get stats
response = requests.get(f"{BASE_URL}/stats")
stats = response.json()
print(f"Total events: {stats['total_events']}")

# Get recent events
response = requests.get(f"{BASE_URL}/events/recent", params={"limit": 10})
events = response.json()
for event in events['events']:
    print(f"{event['detected_at']}: {event['plate_text']} (camera: {event['camera_id']})")

# Search by plate
response = requests.get(f"{BASE_URL}/events/plate/ABC123")
results = response.json()
print(f"Found {results['count']} events for plate ABC123")
```

## Configuration

### Environment Variables

Create `.env` file:

```bash
# Database
DB_HOST=timescaledb
DB_PORT=5432
DB_NAME=alpr_db
DB_USER=alpr
DB_PASSWORD=your_secure_password

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_TOPIC=alpr.events.plates

# API
API_PORT=8000
```

Load in Docker Compose:

```yaml
services:
  query-api:
    env_file: .env
```

### Camera Configuration

Edit `config/cameras.yaml`:

```yaml
cameras:
  - id: "cam_01"
    name: "Front Gate"
    source: "rtsp://192.168.1.100:554/stream"
    fps: 30
    resolution: [1920, 1080]

  - id: "cam_02"
    name: "Back Exit"
    source: "/dev/video0"  # USB camera
    fps: 30
    resolution: [1280, 720]
```

### Docker Compose Override

Create `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  query-api:
    environment:
      LOG_LEVEL: debug
    ports:
      - "8001:8000"  # Different port

  timescaledb:
    volumes:
      - /mnt/external/db:/var/lib/postgresql/data
```

## Troubleshooting

### Quick Diagnostics

```bash
# Check if Docker is running
sudo systemctl status docker

# Check if services are up
docker compose ps

# Check service logs for errors
docker compose logs --tail=50 | grep -i error

# Check disk space
df -h

# Check memory
free -h

# Check network connectivity
ping google.com

# Check if ports are in use
sudo netstat -tulpn | grep -E '8000|5432|9092'

# Test database connection
docker exec alpr-timescaledb psql -U alpr -d alpr_db -c "SELECT 1;"

# Test Kafka connection
docker exec alpr-kafka kafka-broker-api-versions --bootstrap-server localhost:9092
```

### Common Fixes

```bash
# Restart all services
docker compose restart

# Rebuild and restart specific service
docker compose up -d --build query-api

# Clear Docker cache and rebuild
docker compose down
docker system prune -a
docker compose up -d --build

# Reset database (WARNING: deletes all data)
docker compose down -v
docker compose up -d timescaledb

# Check and fix file permissions
sudo chown -R jetson:jetson /home/jetson/OVR-ALPR
chmod -R 755 /home/jetson/OVR-ALPR

# Free up disk space
docker system prune -a --volumes
sudo apt clean
rm -rf ~/.cache/*
```

### Performance Tuning

```bash
# Increase Docker resources (edit /etc/docker/daemon.json)
sudo nano /etc/docker/daemon.json
# Add: {"default-ulimits": {"nofile": {"hard": 65536, "soft": 65536}}}
sudo systemctl restart docker

# Optimize Jetson power mode
sudo nvpmodel -m 0  # Max performance mode
sudo jetson_clocks  # Max all clocks

# Monitor performance
tegrastats  # Real-time stats

# Reduce logging verbosity
docker compose logs --tail=0 -f  # Only new logs
```

## Backup and Restore

### Database Backup

```bash
# Create backup
docker exec alpr-timescaledb pg_dump -U alpr alpr_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore backup
docker exec -i alpr-timescaledb psql -U alpr -d alpr_db < backup_20241216_120000.sql

# Automated daily backup (add to crontab)
0 2 * * * docker exec alpr-timescaledb pg_dump -U alpr alpr_db > /backup/alpr_$(date +\%Y\%m\%d).sql
```

### Configuration Backup

```bash
# Backup configuration files
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
  config/ \
  docker-compose.yml \
  .env

# Restore configuration
tar -xzf config_backup_20241216.tar.gz
```

## Useful Aliases

Add to `~/.bashrc`:

```bash
# Docker Compose shortcuts
alias dc='docker compose'
alias dcp='docker compose ps'
alias dcl='docker compose logs -f'
alias dcu='docker compose up -d'
alias dcd='docker compose down'

# ALPR shortcuts
alias alpr-start='cd /home/jetson/OVR-ALPR && docker compose up -d'
alias alpr-stop='cd /home/jetson/OVR-ALPR && docker compose down'
alias alpr-logs='cd /home/jetson/OVR-ALPR && docker compose logs -f'
alias alpr-status='cd /home/jetson/OVR-ALPR && docker compose ps'
alias alpr-run='cd /home/jetson/OVR-ALPR && python3 pilot.py'

# Database shortcuts
alias alpr-db='docker exec -it alpr-timescaledb psql -U alpr -d alpr_db'
alias alpr-stats='curl -s http://localhost:8000/stats | python3 -m json.tool'

# Monitoring shortcuts
alias alpr-services='curl -s http://localhost:8000/services/status | python3 -m json.tool'
alias alpr-tempo='curl -s http://localhost:3200/ready'
alias alpr-health='curl -s http://localhost:8000/health && curl -s http://localhost:3200/ready && curl -s http://localhost:9200/_cluster/health'
```

Reload bashrc:

```bash
source ~/.bashrc
```

Now you can use:

```bash
alpr-start    # Start all services
alpr-logs     # View logs
alpr-db       # Connect to database
alpr-stats    # View API stats
```
