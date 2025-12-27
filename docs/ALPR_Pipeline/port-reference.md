# ALPR System Port Reference

Complete reference of all ports used by the ALPR pipeline components.

## Port Allocation Table

| Service | Internal Port | External Port | Protocol | Purpose | URL |
|---------|--------------|---------------|----------|---------|-----|
| **Data Infrastructure** |
| ZooKeeper | 2181 | 2181 | TCP | Kafka coordination | - |
| Kafka Broker | 29092 | 9092 | TCP | Message broker (external) | - |
| Kafka JMX | 9101 | 9101 | TCP | Kafka monitoring | - |
| Schema Registry | 8081 | 8081 | HTTP | Avro schema management | http://localhost:8081 |
| Kafka UI | 8080 | 8080 | HTTP | Kafka web interface | http://localhost:8080 |
| TimescaleDB | 5432 | 5432 | TCP | PostgreSQL database | - |
| MinIO API | 9000 | 9000 | HTTP/S3 | Object storage API | http://localhost:9000 |
| MinIO Console | 9001 | 9001 | HTTP | MinIO web UI | http://localhost:9001 |
| **Application Services** |
| Query API | 8000 | 8000 | HTTP | REST API for queries | http://localhost:8000 |
| Query API Metrics | 8000 | 8000 | HTTP | Prometheus metrics | http://localhost:8000/metrics |
| Kafka Consumer Metrics | 8002 | - | HTTP | Prometheus metrics (internal) | - |
| ALPR Pilot Metrics | - | 8001 | HTTP | Edge processing metrics | http://localhost:8001/metrics |
| **Monitoring Stack** |
| Grafana | 3000 | 3000 | HTTP | Metrics visualization | http://localhost:3000 |
| Prometheus | 9090 | 9090 | HTTP | Metrics collection | http://localhost:9090 |
| Loki | 3100 | 3100 | HTTP | Log aggregation | http://localhost:3100 |
| Promtail | 9080 | - | HTTP | Log shipping (internal) | - |
| cAdvisor | 8080 | 8082 | HTTP | Container metrics | http://localhost:8082 |

## Port Groups

### Core Data Infrastructure (Ports 2181, 5432, 9000-9001, 9092, 9101)
Critical services that handle data storage and messaging:
- **ZooKeeper (2181)**: Kafka cluster coordination
- **Kafka (9092)**: Message broker for plate detection events
- **Kafka JMX (9101)**: Kafka performance monitoring
- **TimescaleDB (5432)**: Time-series database for plate records
- **MinIO API (9000)**: S3-compatible storage for plate images
- **MinIO Console (9001)**: Web interface for MinIO management

### Schema & Management (Ports 8080-8081)
Services for schema management and monitoring:
- **Schema Registry (8081)**: Avro schema versioning
- **Kafka UI (8080)**: Kafka cluster management and monitoring

### Application Layer (Ports 8000-8002)
ALPR application services:
- **Query API (8000)**: REST API + Prometheus metrics
- **Kafka Consumer (8002)**: Internal metrics endpoint
- **ALPR Pilot (8001)**: Edge processing metrics

### Monitoring Stack (Ports 3000, 8082, 9090, 3100)
Observability infrastructure:
- **Grafana (3000)**: Main monitoring dashboard
- **Prometheus (9090)**: Metrics database and query engine
- **Loki (3100)**: Log aggregation backend
- **cAdvisor (8082)**: Container resource metrics

## Port Conflicts and Resolutions

### Historical Port Changes

| Original Port | New Port | Service | Reason for Change |
|--------------|----------|---------|-------------------|
| 8080 | 8082 | cAdvisor | Conflict with Kafka UI |

## Service Access URLs

### User-Facing Interfaces

#### Data Management
```
MinIO Console:      http://localhost:9001
  Username: alpr_minio
  Password: alpr_minio_secure_pass_2024

Kafka UI:           http://localhost:8080
  (No authentication)

Query API:          http://localhost:8000
  Health Check:     http://localhost:8000/health
  API Docs:         http://localhost:8000/docs
```

#### Monitoring & Observability
```
Grafana:            http://localhost:3000
  Username: admin
  Password: alpr_admin_2024

Prometheus:         http://localhost:9090
  Targets:          http://localhost:9090/targets
  Alerts:           http://localhost:9090/alerts

cAdvisor:           http://localhost:8082
  (No authentication)
```

### Metrics Endpoints (Prometheus Format)

```bash
# ALPR Pilot (Edge Processing)
curl http://localhost:8001/metrics

# Query API
curl http://localhost:8000/metrics

# Kafka Consumer (internal only - not exposed to host)
# Access via: docker exec alpr-kafka-consumer curl localhost:8002/metrics

# cAdvisor (Container Metrics)
curl http://localhost:8082/metrics

# Prometheus (Self Metrics)
curl http://localhost:9090/metrics
```

### Database Connections

```bash
# TimescaleDB (PostgreSQL)
psql -h localhost -p 5432 -U alpr -d alpr_db
# Password: alpr_secure_pass

# MinIO (S3 API)
aws s3 ls --endpoint-url http://localhost:9000
# Access Key: alpr_minio
# Secret Key: alpr_minio_secure_pass_2024
```

## Firewall & Network Configuration

### Required Open Ports for External Access

If running on a remote server, open these ports:

**Essential (Required for basic operation)**:
- `8000` - Query API
- `3000` - Grafana dashboard

**Optional (Enhanced monitoring)**:
- `8080` - Kafka UI
- `9001` - MinIO Console
- `9090` - Prometheus
- `8082` - cAdvisor

**Database Access (Use with caution)**:
- `5432` - TimescaleDB (only if remote access needed)
- `9092` - Kafka (only if remote producers needed)

### Internal Docker Network

All services communicate on the `alpr-network` bridge network:
- Services use container names for DNS resolution
- Example: Kafka consumer connects to `kafka:29092` (internal port)
- External clients use `localhost:9092` (mapped port)

## Port Usage by Component

### pilot.py (Edge Processing)
- **Exposes**: 8001 (metrics)
- **Connects to**:
  - Kafka: localhost:9092
  - Schema Registry: http://schema-registry:8081 (if in Docker)

### kafka-consumer (Storage Service)
- **Exposes**: 8002 (metrics, internal only)
- **Connects to**:
  - Kafka: kafka:29092
  - Schema Registry: http://schema-registry:8081
  - TimescaleDB: timescaledb:5432
  - MinIO: minio:9000

### query-api (REST API)
- **Exposes**: 8000 (HTTP + metrics)
- **Connects to**:
  - TimescaleDB: timescaledb:5432
  - MinIO: minio:9000

### Prometheus
- **Exposes**: 9090 (HTTP + metrics)
- **Scrapes from**:
  - pilot.py: host.docker.internal:8001
  - kafka-consumer: kafka-consumer:8002
  - query-api: query-api:8000
  - cAdvisor: cadvisor:8080

### Grafana
- **Exposes**: 3000 (HTTP)
- **Connects to**:
  - Prometheus: http://prometheus:9090
  - Loki: http://loki:3100

## Environment Variable Port Configuration

Services use these environment variables for port configuration:

```yaml
# Kafka Configuration
KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
KAFKA_JMX_PORT: 9101

# Database Configuration
DB_PORT: 5432

# MinIO Configuration
MINIO_ENDPOINT: minio:9000  # or localhost:9000 for host access

# Schema Registry
SCHEMA_REGISTRY_URL: http://schema-registry:8081
```

## Troubleshooting Port Issues

### Check if Port is in Use
```bash
# Check specific port
sudo netstat -tulpn | grep :8080

# Check all ALPR-related ports
sudo netstat -tulpn | grep -E ':(8000|8001|8002|8080|8081|8082|3000|5432|9000|9001|9090|9092)'
```

### Verify Docker Port Mappings
```bash
# List all container port mappings
docker compose ps

# Check specific container
docker port alpr-kafka-ui
```

### Test Port Connectivity
```bash
# Test HTTP endpoints
curl -I http://localhost:3000  # Grafana
curl -I http://localhost:8000/health  # Query API
curl http://localhost:8001/metrics | head  # Pilot metrics

# Test TCP ports
nc -zv localhost 9092  # Kafka
nc -zv localhost 5432  # TimescaleDB
```

### Common Port Conflicts

**Port 8080 (Kafka UI vs cAdvisor)**:
- **Resolution**: cAdvisor moved to 8082
- **Reason**: Kafka UI needs 8080 for web interface

**Port 8000 (Query API vs other services)**:
- Query API uses 8000 by default
- If conflict, change in docker-compose.yml:
  ```yaml
  query-api:
    ports:
      - "8010:8000"  # Map to different external port
  ```

**Port 3000 (Grafana conflicts)**:
- Common conflict with other dev servers
- Change in docker-compose.yml:
  ```yaml
  grafana:
    ports:
      - "3001:3000"  # Alternative Grafana port
  ```

## Security Considerations

### Port Exposure Recommendations

**Publicly Accessible (Behind Authentication)**:
- 3000 (Grafana) - Use strong password, enable HTTPS
- 8000 (Query API) - Implement API authentication

**Internal Network Only**:
- 9090 (Prometheus) - Contains sensitive metrics
- 8082 (cAdvisor) - Exposes container information
- 5432 (TimescaleDB) - Database access
- 9092 (Kafka) - Message broker

**Localhost Only**:
- 8001 (Pilot metrics) - If running on edge device
- 8002 (Consumer metrics) - Internal monitoring only

### Default Credentials to Change

```bash
# Grafana
GF_SECURITY_ADMIN_PASSWORD: alpr_admin_2024  # CHANGE IN PRODUCTION

# TimescaleDB
POSTGRES_PASSWORD: alpr_secure_pass  # CHANGE IN PRODUCTION

# MinIO
MINIO_ROOT_PASSWORD: alpr_minio_secure_pass_2024  # CHANGE IN PRODUCTION
```

## Quick Reference Command

Save this as an alias for quick port reference:

```bash
alias alpr-ports='echo "
ALPR System Ports:
==================
Data:
  Kafka UI:        http://localhost:8080
  MinIO Console:   http://localhost:9001
  Schema Registry: http://localhost:8081

API:
  Query API:       http://localhost:8000
  API Docs:        http://localhost:8000/docs

Monitoring:
  Grafana:         http://localhost:3000
  Prometheus:      http://localhost:9090
  cAdvisor:        http://localhost:8082

Metrics:
  Pilot:           http://localhost:8001/metrics
  Query API:       http://localhost:8000/metrics
"'
```

Then run: `alpr-ports`

## Related Documentation

- [Monitoring Stack Setup](../Services/monitoring-stack-setup.md)
- [Grafana Dashboards Guide](../Services/grafana-dashboards.md)
- [Docker Compose Configuration](../../docker-compose.yml)
