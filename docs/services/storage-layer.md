# ALPR Storage Layer Documentation

Complete guide to the storage layer implementation for persisting and querying license plate detection events.

## Overview

The storage layer consists of three main components:

1. **TimescaleDB Database** - Time-series optimized PostgreSQL for storing events
2. **Kafka Consumer** - Service that consumes events from Kafka and persists to database
3. **Query API** - REST API for retrieving historical plate detection events

## Architecture

```
ALPR Detection → Event Processor → Kafka Topic → Kafka Consumer → TimescaleDB
                                                                         ↓
                                                                    Query API → Users/Apps
```

## Components

### 1. TimescaleDB Database

**Location**: Docker container `alpr-timescaledb`
**Port**: 5432
**Database**: `alpr_db`
**User**: `alpr`
**Password**: `alpr_secure_pass`

#### Schema

The `plate_events` table stores all validated plate detection events:

```sql
CREATE TABLE plate_events (
    -- Primary identifiers
    event_id UUID NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,

    -- Source information
    camera_id VARCHAR(50) NOT NULL,
    track_id VARCHAR(50) NOT NULL,

    -- Plate information
    plate_text VARCHAR(20) NOT NULL,              -- Original OCR text
    plate_normalized_text VARCHAR(20) NOT NULL,   -- Normalized/cleaned text
    plate_confidence FLOAT NOT NULL,              -- OCR confidence (0.0-1.0)
    plate_region VARCHAR(10) NOT NULL,            -- Region code (US-FL, etc.)

    -- Vehicle information
    vehicle_type VARCHAR(20),
    vehicle_make VARCHAR(50),
    vehicle_model VARCHAR(50),
    vehicle_color VARCHAR(30),

    -- Image references
    plate_image_url TEXT,
    vehicle_image_url TEXT,
    frame_image_url TEXT,

    -- Processing metadata
    latency_ms INTEGER,
    quality_score FLOAT,
    frame_number INTEGER,

    -- Location metadata
    site_id VARCHAR(50),
    host_id VARCHAR(100),
    roi VARCHAR(50),
    direction VARCHAR(20),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Composite primary key (required for TimescaleDB)
    PRIMARY KEY (event_id, captured_at)
);
```

#### Indexes

Optimized for common query patterns:

- `idx_plate_normalized` - Query by plate text
- `idx_camera_time` - Query by camera and time range
- `idx_site_time` - Query by site and time range
- `idx_track_id` - Query by track ID
- `idx_captured_at` - Query by time range

#### Views

- `plate_events_stats` - Aggregate statistics (total events, unique plates, etc.)
- `plate_events_recent` - Events from last 24 hours

### 2. Storage Service

**Location**: `services/storage/storage_service.py`

Python service for database operations with connection pooling.

#### Usage

```python
from services.storage.storage_service import StorageService

# Initialize storage service
storage = StorageService(
    host="localhost",
    port=5432,
    database="alpr_db",
    user="alpr",
    password="alpr_secure_pass",
)

# Insert event
event_dict = {...}  # PlateEvent.to_dict()
success = storage.insert_event(event_dict)

# Query recent events
events = storage.get_recent_events(limit=100)

# Query by plate
events = storage.get_events_by_plate("ABC123", limit=50)

# Query by camera
events = storage.get_events_by_camera(
    camera_id="camera-01",
    start_time=datetime(...),
    end_time=datetime(...),
    limit=100
)

# Get statistics
stats = storage.get_stats()

# Close connections
storage.close()
```

#### Methods

- `insert_event(event_dict)` - Insert single event
- `insert_batch(events)` - Insert multiple events
- `get_event_by_id(event_id)` - Retrieve by UUID
- `get_events_by_plate(plate_text)` - Query by plate text
- `get_events_by_camera(camera_id, start_time, end_time)` - Query by camera
- `get_recent_events(limit)` - Get recent events
- `get_stats()` - Database statistics

### 3. Kafka Consumer

**Location**: `services/storage/kafka_consumer.py`

Background service that consumes events from Kafka and persists to TimescaleDB.

#### Configuration

```python
from services.storage.kafka_consumer import KafkaStorageConsumer

consumer = KafkaStorageConsumer(
    kafka_bootstrap_servers="localhost:9092",
    kafka_topic="alpr.plates.detected",
    kafka_group_id="alpr-storage-consumer",
    db_host="localhost",
    db_port=5432,
    db_name="alpr_db",
    db_user="alpr",
    db_password="alpr_secure_pass",
    auto_offset_reset="latest",  # or "earliest" to replay all messages
)

# Start consuming (blocking)
consumer.start()
```

#### Running as Service

```bash
# Start consumer in foreground
python3 services/storage/kafka_consumer.py

# Start consumer in background
nohup python3 services/storage/kafka_consumer.py > logs/kafka_consumer.log 2>&1 &

# Check logs
tail -f logs/kafka_consumer.log
```

#### Features

- Automatic reconnection on failure
- Graceful shutdown (SIGINT/SIGTERM)
- Offset management (auto-commit)
- Error handling and logging
- Statistics tracking

### 4. Query API

**Location**: `services/api/query_api.py`

FastAPI-based REST API for querying historical plate events.

#### Endpoints

**GET /health**
Health check endpoint

```bash
curl http://localhost:8000/health
```

**GET /stats**
Database statistics

```bash
curl http://localhost:8000/stats
```

Response:
```json
{
  "is_connected": true,
  "total_events": 1234,
  "unique_plates": 567,
  "active_cameras": 3,
  "avg_confidence": 0.89,
  "avg_latency_ms": 45
}
```

**GET /events/recent?limit=100**
Get most recent events

```bash
curl http://localhost:8000/events/recent?limit=10
```

**GET /events/{event_id}**
Get event by UUID

```bash
curl http://localhost:8000/events/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
```

**GET /events/plate/{plate_text}?limit=100&offset=0**
Query by plate text

```bash
curl http://localhost:8000/events/plate/ABC123
```

**GET /events/camera/{camera_id}?start_time=...&end_time=...&limit=100**
Query by camera and time range

```bash
curl "http://localhost:8000/events/camera/camera-01?start_time=2025-12-01T00:00:00Z&end_time=2025-12-16T23:59:59Z"
```

#### Running the API

```bash
# Start API in foreground
python3 services/api/query_api.py

# Start API in background
nohup python3 services/api/query_api.py > logs/query_api.log 2>&1 &

# Access API documentation
open http://localhost:8000/docs  # Swagger UI
```

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements-storage.txt
```

Dependencies:
- `psycopg2-binary` - PostgreSQL adapter
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation

### 2. Start TimescaleDB

```bash
# Start TimescaleDB container
docker compose up -d timescaledb

# Wait for database to be ready
docker exec alpr-timescaledb pg_isready -U alpr -d alpr_db

# Initialize schema (first time only)
docker exec -i alpr-timescaledb psql -U alpr -d alpr_db < scripts/init_db.sql
```

### 3. Start All Services

```bash
# Use the startup script
bash scripts/start_storage_layer.sh

# Or start services individually:

# Terminal 1: Start Kafka Consumer
python3 services/storage/kafka_consumer.py

# Terminal 2: Start Query API
python3 services/api/query_api.py
```

## Testing

Run the comprehensive test suite:

```bash
python3 services/storage/test_storage_layer.py
```

Tests include:
1. Database connection and operations
2. Storage insert and query
3. Kafka to storage pipeline (requires running consumer)
4. Query API endpoints (requires running API)
5. Query by plate functionality

## Monitoring

### Database Metrics

```bash
# Connect to database
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db

# Check statistics
SELECT * FROM plate_events_stats;

# Check recent events
SELECT * FROM plate_events_recent LIMIT 10;

# Check table size
SELECT pg_size_pretty(pg_total_relation_size('plate_events'));

# Check index usage
SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public';
```

### Consumer Metrics

Check consumer logs:
```bash
tail -f logs/kafka_consumer.log
```

Statistics logged every 100 messages:
- Total consumed
- Total stored
- Failed stores

### API Metrics

```bash
# Check API stats
curl http://localhost:8000/stats

# Check API health
curl http://localhost:8000/health
```

## Performance Optimization

### Database Tuning

Edit `docker-compose.yml` to add PostgreSQL performance settings:

```yaml
environment:
  # ... existing env vars ...
  # Performance tuning
  POSTGRES_SHARED_BUFFERS: 256MB
  POSTGRES_EFFECTIVE_CACHE_SIZE: 1GB
  POSTGRES_WORK_MEM: 16MB
  POSTGRES_MAINTENANCE_WORK_MEM: 128MB
```

### Connection Pooling

Adjust pool size in `StorageService`:

```python
storage = StorageService(
    min_conn=5,   # Minimum connections
    max_conn=20,  # Maximum connections
)
```

### Batch Inserts

For high-throughput scenarios, use batch inserts:

```python
# Collect events
events = [event1.to_dict(), event2.to_dict(), ...]

# Insert batch
count = storage.insert_batch(events)
```

## Data Retention

Enable automatic data cleanup (uncomment in `init_db.sql`):

```sql
-- Keep data for 90 days
SELECT add_retention_policy('plate_events', INTERVAL '90 days', if_not_exists => TRUE);
```

## Troubleshooting

### Database Connection Issues

```bash
# Check if container is running
docker ps | grep timescaledb

# Check database logs
docker logs alpr-timescaledb

# Restart container
docker compose restart timescaledb
```

### Consumer Not Storing Events

1. Check Kafka is running: `docker ps | grep kafka`
2. Check consumer logs: `tail -f logs/kafka_consumer.log`
3. Verify database connection
4. Check Kafka topic has messages: `docker exec alpr-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic alpr.plates.detected --from-beginning --max-messages 1`

### API Not Responding

```bash
# Check if API is running
ps aux | grep query_api

# Check API logs
tail -f logs/query_api.log

# Test health endpoint
curl http://localhost:8000/health
```

## Integration with ALPR Pipeline

The storage layer integrates seamlessly with the existing ALPR pipeline:

```python
# In pilot.py or main application
from services.event_processor.event_processor_service import EventProcessorService
from services.event_processor.kafka_publisher import KafkaPublisher

# Process and publish event
event = event_processor.process_detection(...)
if event:
    kafka_publisher.publish_event(event.to_dict())
    # Event is now in Kafka and will be persisted by consumer
```

## Next Steps

1. **Analytics Dashboard** - Build web dashboard using Query API
2. **Alert System** - Subscribe to events and trigger alerts
3. **Backup Strategy** - Implement database backups
4. **Replication** - Set up read replicas for scaling
5. **Search Optimization** - Add full-text search capabilities

## References

- [TimescaleDB Documentation](https://docs.timescale.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Kafka Python Documentation](https://kafka-python.readthedocs.io/)
- [PostgreSQL Best Practices](https://wiki.postgresql.org/wiki/Performance_Optimization)
