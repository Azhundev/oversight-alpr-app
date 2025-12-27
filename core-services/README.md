# Core Services

Backend services that run **in Docker** on the server/cloud for data storage, API access, and monitoring.

## Architecture

Core services handle:
- Event storage and persistence
- REST API for querying
- Observability and monitoring

```
┌──────────────────────────────────────────────────────────┐
│                   BACKEND / CLOUD                         │
│                  (Docker Services)                        │
├──────────────────────────────────────────────────────────┤
│                                                            │
│  📥 Kafka Events (from Edge)                              │
│      ↓                                                     │
│  💾 storage/         - Kafka → TimescaleDB + MinIO       │
│      ↓                                                     │
│  🗄️  TimescaleDB     - Time-series plate records          │
│  📦 MinIO            - Plate crop images (S3-compatible)  │
│                                                            │
│  🌐 api/             - REST API for queries               │
│      ↑                                                     │
│      └── HTTP queries from applications                   │
│                                                            │
│  📊 monitoring/      - Observability stack                │
│      ├── Prometheus  - Metrics collection                 │
│      ├── Grafana     - Dashboards & visualization         │
│      ├── Loki        - Log aggregation                    │
│      └── Promtail    - Log shipping                       │
│                                                            │
└──────────────────────────────────────────────────────────┘
```

## Services

### 💾 storage/
**Kafka Consumer & Storage Service**

Consumes plate detection events from Kafka and stores them in TimescaleDB + MinIO.

**Purpose**: Persist detection events for long-term storage and analysis

**Components**:
- `avro_kafka_consumer.py` - Main consumer logic
- `Dockerfile` - Container build configuration
- `requirements.txt` - Python dependencies

**Data Flow**:
```
Kafka → Avro Deserializer → TimescaleDB (metadata)
                          → MinIO (plate images)
```

**Metrics Port**: 8002 (internal)

**Configuration**:
- Kafka broker: `kafka:29092`
- Topic: `alpr.plates.detected`
- Schema Registry: `http://schema-registry:8081`
- Database: `timescaledb:5432`
- Object Storage: `minio:9000`

**Key Features**:
- ✅ Avro schema validation
- ✅ Automatic schema evolution
- ✅ Batch writes for performance
- ✅ Image storage in S3-compatible MinIO
- ✅ Prometheus metrics for monitoring

---

### 🌐 api/
**Query REST API**

FastAPI-based REST API for querying plate detection records.

**Purpose**: Provide HTTP access to stored ALPR data

**Components**:
- `query_api.py` - FastAPI application
- `Dockerfile` - Container build configuration
- `requirements.txt` - Python dependencies (includes FastAPI, uvicorn)

**Port**: 8000 (external)

**Endpoints**:

```python
GET  /health              # Health check
GET  /plates              # List all plates
GET  /plates/{plate_id}   # Get specific plate
GET  /plates/search       # Search by criteria
GET  /metrics             # Prometheus metrics
GET  /docs                # Swagger/OpenAPI docs
```

**Query Examples**:

```bash
# List recent plates
curl http://localhost:8000/plates?limit=10

# Search by plate number
curl http://localhost:8000/plates/search?plate_text=ABC123

# Search by time range
curl "http://localhost:8000/plates?start_time=2025-12-26T00:00:00&end_time=2025-12-26T23:59:59"

# Get plate image
curl http://localhost:8000/plates/12345/image
```

**Key Features**:
- ✅ FastAPI automatic API docs (Swagger UI)
- ✅ Prometheus metrics via instrumentator
- ✅ CORS support for web frontends
- ✅ Pagination for large result sets
- ✅ Full-text search on plate numbers
- ✅ MinIO integration for image retrieval

---

### 📊 monitoring/
**Observability Stack**

Complete monitoring infrastructure for the ALPR system.

**Purpose**: Monitor system health, performance, and troubleshoot issues

**Components**:

#### 📈 Prometheus (`prometheus/`)
- **Metrics collection and storage**
- **Port**: 9090
- **Config**: `prometheus/prometheus.yml`
- **Targets**: pilot.py, kafka-consumer, query-api, cAdvisor
- **Retention**: 30 days

#### 📊 Grafana (`grafana/`)
- **Metrics visualization and dashboards**
- **Port**: 3000
- **Login**: `admin` / `alpr_admin_2024`
- **Dashboards**:
  - ALPR Overview - Main system metrics
  - System Performance - Container resources
  - Kafka & Database - Data pipeline metrics
  - Logs Explorer - Centralized logging

#### 📝 Loki (`loki/`)
- **Log aggregation**
- **Port**: 3100
- **Config**: `loki/loki-config.yaml`
- **Storage**: Filesystem-based TSDB
- **Retention**: 7 days

#### 🚚 Promtail (`promtail/`)
- **Log shipping to Loki**
- **Config**: `promtail/promtail-config.yaml`
- **Sources**: Docker containers, application log files

#### 📦 cAdvisor
- **Container resource metrics**
- **Port**: 8082
- **Metrics**: CPU, memory, network, disk per container

**Access URLs**:
```
Grafana:    http://localhost:3000
Prometheus: http://localhost:9090
cAdvisor:   http://localhost:8082
Loki:       http://localhost:3100
```

**Key Features**:
- ✅ Auto-provisioned dashboards
- ✅ Pre-configured datasources
- ✅ Container-level monitoring
- ✅ Application-level metrics
- ✅ Centralized log search

---

## Running Core Services

### Start All Services

```bash
# From project root
cd /home/jetson/OVR-ALPR

# Start infrastructure (Kafka, DB, MinIO)
docker compose up -d zookeeper kafka schema-registry timescaledb minio

# Start application services
docker compose up -d kafka-consumer query-api

# Start monitoring stack
docker compose up -d prometheus grafana loki promtail cadvisor
```

### Start Individual Services

```bash
# Start only storage service
docker compose up -d kafka-consumer

# Start only API
docker compose up -d query-api

# Start only monitoring
docker compose up -d prometheus grafana loki promtail cadvisor
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f kafka-consumer
docker compose logs -f query-api

# Last 100 lines
docker compose logs --tail=100 kafka-consumer
```

### Stop Services

```bash
# Stop all
docker compose down

# Stop specific service
docker compose stop kafka-consumer

# Stop and remove volumes (DESTROYS DATA!)
docker compose down -v
```

## Configuration

### Environment Variables

Core services use these environment variables (configured in `docker-compose.yml`):

**Storage Service**:
```yaml
KAFKA_BOOTSTRAP_SERVERS: kafka:29092
KAFKA_TOPIC: alpr.plates.detected
SCHEMA_REGISTRY_URL: http://schema-registry:8081
DB_HOST: timescaledb
MINIO_ENDPOINT: minio:9000
```

**Query API**:
```yaml
DB_HOST: timescaledb
DB_PORT: 5432
MINIO_ENDPOINT: minio:9000
```

### Monitoring Configuration

Edit configuration files in `monitoring/`:
- `prometheus/prometheus.yml` - Scrape targets
- `loki/loki-config.yaml` - Log retention, storage
- `promtail/promtail-config.yaml` - Log sources
- `grafana/provisioning/` - Datasources, dashboards

## Data Storage

### TimescaleDB (PostgreSQL)

**Purpose**: Store plate detection metadata

**Schema**:
```sql
CREATE TABLE plate_detections (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    plate_text VARCHAR(20),
    confidence FLOAT,
    camera_id VARCHAR(50),
    track_id INTEGER,
    image_path VARCHAR(500)
);

-- TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('plate_detections', 'timestamp');
```

**Access**:
```bash
# Connect to database
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db

# Query recent detections
SELECT * FROM plate_detections ORDER BY timestamp DESC LIMIT 10;
```

### MinIO (S3 Object Storage)

**Purpose**: Store plate crop images

**Bucket**: `alpr-plate-images`

**Access**:
- Console: http://localhost:9001
- API: http://localhost:9000
- Credentials: `alpr_minio` / `alpr_minio_secure_pass_2024`

**Storage Structure**:
```
alpr-plate-images/
├── 2025/
│   ├── 12/
│   │   ├── 26/
│   │   │   ├── plate_20251226_120530_001.jpg
│   │   │   ├── plate_20251226_120531_002.jpg
│   │   │   └── ...
```

## Metrics & Monitoring

### Storage Service Metrics

```bash
curl http://localhost:8002/metrics
```

**Key Metrics**:
- `alpr_messages_consumed_total` - Kafka messages processed
- `alpr_database_writes_total` - DB write operations
- `alpr_processing_errors_total` - Error count

### Query API Metrics

```bash
curl http://localhost:8000/metrics
```

**Key Metrics**:
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency
- `http_requests_in_progress` - Active requests

### View in Grafana

1. Open http://localhost:3000
2. Login: `admin` / `alpr_admin_2024`
3. Navigate to dashboards:
   - **Kafka & Database** - Storage service metrics
   - **System Performance** - Container resources
   - **ALPR Overview** - End-to-end pipeline metrics

## Troubleshooting

### Storage Service Issues

**Problem**: Kafka consumer not consuming messages

```bash
# Check Kafka connectivity
docker exec alpr-kafka-consumer nc -zv kafka 29092

# Check consumer logs
docker compose logs kafka-consumer | grep -i error

# Verify topic exists
docker exec alpr-kafka kafka-topics --bootstrap-server kafka:9092 --list
```

**Problem**: Database connection failures

```bash
# Check TimescaleDB is running
docker compose ps timescaledb

# Test connection
docker exec alpr-timescaledb pg_isready -U alpr

# Check database logs
docker compose logs timescaledb
```

### API Service Issues

**Problem**: API returning 500 errors

```bash
# Check API logs
docker compose logs query-api

# Test health endpoint
curl http://localhost:8000/health

# Check database connectivity
docker exec alpr-query-api nc -zv timescaledb 5432
```

**Problem**: Slow query performance

```bash
# Check database indexes
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db
\d plate_detections

# Add index if needed
CREATE INDEX idx_timestamp ON plate_detections(timestamp DESC);
CREATE INDEX idx_plate_text ON plate_detections(plate_text);
```

### Monitoring Issues

See [monitoring-stack-test-results.md](../docs/Services/monitoring-stack-test-results.md)

## Scaling & Performance

### Storage Service

**Increase throughput**:
- Scale horizontally: `docker compose up -d --scale kafka-consumer=3`
- Increase batch size in `avro_kafka_consumer.py`
- Optimize database indexes

**Reduce lag**:
- Increase Kafka partitions
- Add more consumer instances
- Optimize database write performance

### Query API

**Handle more traffic**:
- Scale horizontally: `docker compose up -d --scale query-api=3`
- Add load balancer (nginx, traefik)
- Implement Redis caching

**Optimize queries**:
- Add database indexes on frequently queried fields
- Use query result pagination
- Implement query result caching

## Related Documentation

- [Monitoring Stack Setup](../docs/Services/monitoring-stack-setup.md)
- [Grafana Dashboards Guide](../docs/Services/grafana-dashboards.md)
- [Port Reference](../docs/alpr_pipeline/port-reference.md)
- [Edge Services](../edge-services/README.md)

---

**Note**: All core services run in Docker and can be deployed to any server/cloud environment. They do not require GPU access.
