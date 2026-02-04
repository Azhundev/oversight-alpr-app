# Docker Setup and Usage

This document explains how Docker is used in the OVR-ALPR project for managing infrastructure services.

## Overview

The project uses Docker Compose to orchestrate **24+ services** that support the ALPR pipeline:

**Data Infrastructure:**
- **ZooKeeper**: Coordination service for Kafka
- **Kafka**: Message broker for event streaming
- **Schema Registry**: Avro schema management
- **Kafka UI**: Web interface for monitoring Kafka
- **TimescaleDB**: Time-series database for storing plate detections
- **MinIO**: S3-compatible object storage for plate images
- **OpenSearch**: Full-text search and analytics engine

**Application Services:**
- **Kafka Consumer**: Consumes plate events and stores in database
- **Elasticsearch Consumer**: Indexes events in OpenSearch
- **Alert Engine**: Real-time alerting and notifications
- **Query API**: REST API for querying events
- **DLQ Consumer**: Dead letter queue monitoring
- **Metrics Consumer**: System metrics aggregation

**Monitoring & Observability:**
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboards
- **Loki**: Log aggregation
- **Tempo**: Distributed tracing (OTLP)
- **Promtail**: Log shipping
- **cAdvisor**: Container metrics
- **Node Exporter**: Host system metrics
- **Postgres Exporter**: TimescaleDB metrics
- **Kafka Exporter**: Kafka broker metrics

**BI & MLOps:**
- **Metabase**: Business intelligence and analytics
- **MLflow**: Model registry and experiment tracking

## Architecture

```
┌─────────────────┐
│  ALPR Pipeline  │
│   (pilot.py)    │
└────────┬────────┘
         │ publishes events
         ▼
┌─────────────────┐
│     Kafka       │◄──── ZooKeeper
│  (Port 9092)    │
└────────┬────────┘
         │ topic: alpr.events.plates
         ▼
┌─────────────────┐
│ Kafka Consumer  │
│   (Docker)      │
└────────┬────────┘
         │ stores events
         ▼
┌─────────────────┐
│  TimescaleDB    │
│  (Port 5432)    │
└─────────────────┘
```

## Services

### ZooKeeper
- **Container**: `alpr-zookeeper`
- **Port**: 2181
- **Purpose**: Manages Kafka cluster coordination
- **Data**: Persisted in `zookeeper-data` volume

### Kafka
- **Container**: `alpr-kafka`
- **Ports**:
  - 9092 (external access)
  - 29092 (internal Docker network)
  - 9101 (JMX metrics)
- **Purpose**: Message broker for event streaming
- **Topics**: `alpr.events.plates`
- **Data**: Persisted in `kafka-data` volume
- **Retention**: 7 days (168 hours)

### Kafka UI
- **Container**: `alpr-kafka-ui`
- **Port**: 8080
- **Purpose**: Web interface for managing and monitoring Kafka
- **Access**: http://localhost:8080

### TimescaleDB
- **Container**: `alpr-timescaledb`
- **Port**: 5432
- **Purpose**: PostgreSQL database with time-series optimization
- **Database**: `alpr_db`
- **User**: `alpr`
- **Data**: Persisted in `timescaledb-data` volume
- **Schema**: Initialized from `scripts/init_db.sql`

### Kafka Consumer
- **Container**: `alpr-kafka-consumer`
- **Purpose**: Consumes plate events from Kafka and stores in TimescaleDB
- **Built from**: `core-services/storage/Dockerfile`
- **Dependencies**: `core-services/storage/requirements.txt`
- **Depends on**: Kafka and TimescaleDB
- **Logs**: Written to `./logs` directory

### Query API
- **Container**: `alpr-query-api`
- **Purpose**: REST API for querying historical plate detection events
- **Built from**: `core-services/api/Dockerfile`
- **Port**: 8000
- **Depends on**: TimescaleDB
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Getting Started

### Starting All Services

Start all infrastructure services:

```bash
docker compose up -d
```

This will start ZooKeeper, Kafka, Kafka UI, TimescaleDB, and the Kafka Consumer.

### Starting Specific Services

Start only the services you need:

```bash
# Start only Kafka infrastructure (ZooKeeper + Kafka)
docker compose up -d zookeeper kafka

# Start storage layer (TimescaleDB + Consumer)
docker compose up -d timescaledb kafka-consumer
```

### Checking Service Status

```bash
# View running containers
docker compose ps

# View logs for all services
docker compose logs

# View logs for a specific service
docker compose logs kafka-consumer
docker compose logs timescaledb

# Follow logs in real-time
docker compose logs -f kafka-consumer
```

### Stopping Services

```bash
# Stop all services
docker compose down

# Stop but keep volumes (preserves data)
docker compose stop

# Stop and remove volumes (deletes all data)
docker compose down -v
```

## Configuration

### Environment Variables

The Kafka Consumer service is configured via environment variables in `docker-compose.yml`:

```yaml
environment:
  # Kafka configuration
  KAFKA_BOOTSTRAP_SERVERS: kafka:29092
  KAFKA_TOPIC: alpr.events.plates
  KAFKA_GROUP_ID: alpr-storage-consumer
  # Database configuration
  DB_HOST: timescaledb
  DB_PORT: 5432
  DB_NAME: alpr_db
  DB_USER: alpr
  DB_PASSWORD: alpr_secure_pass
```

### Modifying Configuration

To change configuration:

1. Edit `docker-compose.yml`
2. Rebuild and restart the service:

```bash
docker compose up -d --build kafka-consumer
```

## Volumes and Data Persistence

Data is persisted in Docker volumes:

- `zookeeper-data`: ZooKeeper state
- `zookeeper-logs`: ZooKeeper logs
- `kafka-data`: Kafka message logs
- `timescaledb-data`: Database files

### Backing Up Database

```bash
# Backup database to file
docker exec alpr-timescaledb pg_dump -U alpr alpr_db > backup.sql

# Restore from backup
docker exec -i alpr-timescaledb psql -U alpr -d alpr_db < backup.sql
```

### Viewing Database Contents

```bash
# Connect to database
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db

# View tables
\dt

# Query plate events
SELECT * FROM plate_events ORDER BY detected_at DESC LIMIT 10;

# Exit
\q
```

## Rebuilding Services

If you modify the Dockerfile or application code:

```bash
# Rebuild the consumer service
docker compose build kafka-consumer

# Rebuild and restart
docker compose up -d --build kafka-consumer
```

## Troubleshooting

### Kafka Consumer Not Starting

Check if Kafka and TimescaleDB are healthy:

```bash
docker compose ps
```

View consumer logs:

```bash
docker compose logs kafka-consumer
```

### Database Connection Issues

Check if TimescaleDB is running and healthy:

```bash
docker exec alpr-timescaledb pg_isready -U alpr -d alpr_db
```

### Kafka Connection Issues

Check if Kafka is running:

```bash
docker exec alpr-kafka kafka-broker-api-versions --bootstrap-server localhost:9092
```

List topics:

```bash
docker exec alpr-kafka kafka-topics --bootstrap-server localhost:9092 --list
```

### Consumer Lag

Check if consumer is keeping up with message production:

```bash
# Use Kafka UI at http://localhost:8080
# Or check consumer group lag:
docker exec alpr-kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group alpr-storage-consumer \
  --describe
```

### Clearing All Data

To start fresh (WARNING: deletes all data):

```bash
docker compose down -v
docker compose up -d
```

## Development Workflow

### Local Development

For local development without Docker:

1. Start only the infrastructure (Kafka + DB):
   ```bash
   docker compose up -d zookeeper kafka timescaledb
   ```

2. Run the consumer locally:
   ```bash
   python3 core-services/storage/kafka_consumer.py
   ```

### Running in Production

In production, all services run in Docker:

```bash
# Start all services
docker compose up -d

# Monitor logs
docker compose logs -f

# Check health
docker compose ps
```

### Automatic Restart

All services are configured with `restart: unless-stopped`, meaning they will:
- Automatically restart if they crash
- Start automatically when the system boots
- Only stop when explicitly stopped with `docker compose stop`

## Network Configuration

All services communicate on the `alpr-network` bridge network:

- Internal services use container names (e.g., `kafka:29092`)
- External access uses `localhost` (e.g., `localhost:9092`)

### Port Mapping

| Service | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------|
| ZooKeeper | 2181 | 2181 | Coordination |
| Kafka | 29092 | 9092 | Message broker |
| Kafka JMX | 9101 | 9101 | Metrics |
| Schema Registry | 8081 | 8081 | Avro schemas |
| Kafka UI | 8080 | 8080 | Kafka web interface |
| TimescaleDB | 5432 | 5432 | Database |
| MinIO API | 9000 | 9000 | Object storage |
| MinIO Console | 9001 | 9001 | MinIO web UI |
| OpenSearch | 9200 | 9200 | Search engine |
| OpenSearch Dashboards | 5601 | 5601 | Search UI |
| Query API | 8000 | 8000 | REST API |
| Alert Engine | 8003 | 8003 | Alert metrics |
| Elasticsearch Consumer | 8004 | 8004 | Indexer metrics |
| DLQ Consumer | 8005 | 8005 | DLQ metrics |
| Metrics Consumer | 8006 | 8006 | Metrics aggregation |
| Grafana | 3000 | 3000 | Dashboards |
| Metabase | 3000 | 3001 | BI analytics |
| Prometheus | 9090 | 9090 | Metrics DB |
| Loki | 3100 | 3100 | Log aggregation |
| Tempo | 3200 | 3200 | Tracing API |
| Tempo OTLP gRPC | 4317 | 4317 | Trace ingestion |
| Tempo OTLP HTTP | 4318 | 4318 | Trace ingestion |
| cAdvisor | 8080 | 8082 | Container metrics |
| Node Exporter | 9100 | 9100 | Host metrics |
| Postgres Exporter | 9187 | 9187 | DB metrics |
| Kafka Exporter | 9308 | 9308 | Kafka metrics |
| MLflow | 5000 | 5000 | Model registry |

## Best Practices

1. **Monitor Logs**: Regularly check service logs for errors
2. **Backup Data**: Periodically backup the database
3. **Clean Up**: Remove old Kafka messages and database records to save space
4. **Resource Limits**: Consider adding memory/CPU limits for production
5. **Security**: Change default passwords in production
6. **Health Checks**: Monitor service health checks
7. **Updates**: Keep Docker images updated for security patches

## Advanced Usage

### Scaling Consumer

To run multiple consumer instances (for higher throughput):

```bash
docker compose up -d --scale kafka-consumer=3
```

Note: You'll need to modify the container name to support scaling.

### Custom Configuration

Create a `.env` file to override default values:

```env
KAFKA_RETENTION_HOURS=336
POSTGRES_PASSWORD=your_secure_password
```

Reference in `docker-compose.yml`:

```yaml
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-alpr_secure_pass}
```

## Related Documentation

- [Storage Layer Guide](storage-layer.md)
- [Kafka Integration](INTEGRATION_COMPLETE%20Kafka%20+%20Event%20Processing.md)
- [Storage Quickstart](storage-quickstart.md)
