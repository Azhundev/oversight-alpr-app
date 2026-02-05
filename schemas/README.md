# ALPR Event Schemas

This directory contains Avro schema definitions for ALPR events used with Confluent Schema Registry.

## Overview

The ALPR system uses Apache Kafka with Avro serialization for reliable, schema-validated event streaming. All schemas are registered with Confluent Schema Registry for versioning and compatibility management.

**Schema Registry URL:** http://localhost:8081

## Schema Files

| Schema File | Kafka Topic | Purpose |
|-------------|-------------|---------|
| `plate_event.avsc` | `alpr.events.plates` | License plate detection events |
| `vehicle_event.avsc` | `alpr.events.vehicles` | Vehicle tracking events (no plate) |
| `metric_event.avsc` | `alpr.metrics` | System health and performance metrics |
| `dlq_message.avsc` | `alpr.dlq` | Dead letter queue for failed messages |

## Kafka Topics

```
alpr.events.plates    - Plate detection events (main topic)
alpr.events.vehicles  - Vehicle-only tracking events
alpr.metrics          - System metrics from edge/core services
alpr.dlq              - Dead letter queue for failed processing
```

---

## plate_event.avsc

Avro schema for plate detection events. Primary event type published by the ALPR pipeline.

**Schema Details:**
- **Namespace:** `com.alpr.events`
- **Type:** Record
- **Compatibility:** Backward compatible

**Fields:**
- `event_id` (string): Unique UUID for the event
- `captured_at` (string): ISO 8601 timestamp
- `camera_id` (string): Camera identifier
- `track_id` (string): Vehicle track ID
- `plate` (record): License plate information
  - `text`: Raw OCR text
  - `normalized_text`: Cleaned plate text
  - `confidence`: OCR confidence (0.0-1.0)
  - `region`: Plate region (e.g., US-FL)
- `vehicle` (record): Vehicle information
  - `type`: Vehicle type (car, truck, bus, motorcycle)
  - `make`: Vehicle make (optional)
  - `model`: Vehicle model (optional)
  - `color`: Vehicle color (optional)
- `images` (record): Image URLs
  - `plate_url`: Plate crop image path/URL
  - `vehicle_url`: Vehicle crop image path/URL
  - `frame_url`: Full frame image path/URL
- `latency_ms` (int): Processing latency
- `node` (record): Processing node info
  - `site`: Site identifier
  - `host`: Host identifier
- `extras` (record, optional): Additional metadata
  - `roi`: Region of interest
  - `direction`: Vehicle direction
  - `quality_score`: Image quality
  - `frame_number`: Video frame number

---

## vehicle_event.avsc

Vehicle tracking events for vehicles where no plate was detected.

**Schema Details:**
- **Namespace:** `com.alpr.events`
- **Type:** Record

**Fields:**
- `event_id` (string): Unique event identifier (UUID)
- `captured_at` (string): ISO 8601 timestamp
- `camera_id` (string): Camera identifier
- `track_id` (string): Vehicle track identifier
- `vehicle` (record): Vehicle detection information
  - `type`: Vehicle type (car, truck, bus, motorcycle)
  - `color`: Vehicle color
  - `bbox`: Bounding box coordinates (x1, y1, x2, y2)
  - `confidence`: Detection confidence (0.0-1.0)
- `tracking` (record): Vehicle tracking information
  - `direction`: Vehicle direction (N, S, E, W, NE, NW, SE, SW)
  - `speed_kmh`: Estimated speed in km/h
  - `dwell_time_seconds`: Time vehicle spent in frame
  - `first_seen_at`: ISO 8601 timestamp when track started
  - `last_seen_at`: ISO 8601 timestamp when track last updated
- `latency_ms` (int): Processing latency in milliseconds
- `node` (record): Edge node information
  - `site`: Site identifier
  - `host`: Host identifier

---

## metric_event.avsc

System health and performance metrics published by edge and core services.

**Schema Details:**
- **Namespace:** `com.alpr.metrics`
- **Type:** Record

**Fields:**
- `metric_id` (string): Unique metric event identifier (UUID)
- `timestamp` (string): ISO 8601 timestamp
- `host_id` (string): Host identifier (e.g., jetson-orin-nx)
- `site_id` (string, optional): Site identifier
- `metric_type` (enum): Type of metric
  - `FPS`, `LATENCY`, `GPU_UTIL`, `MEMORY`, `SERVICE_HEALTH`, `KAFKA_LAG`, `CUSTOM`
- `metric_name` (string): Metric name (e.g., pipeline_fps, gpu_utilization)
- `value` (float): Metric value
- `unit` (string): Unit of measurement (fps, ms, percent, bytes, MB)
- `tags` (map): Additional tags for grouping/filtering

---

## dlq_message.avsc

Dead Letter Queue envelope for failed message processing.

**Schema Details:**
- **Namespace:** `com.alpr.dlq`
- **Type:** Record

**Fields:**
- `dlq_id` (string): Unique DLQ entry identifier (UUID)
- `timestamp` (string): ISO 8601 timestamp when message failed
- `original_topic` (string): Original Kafka topic
- `original_partition` (int): Original partition number
- `original_offset` (long): Original offset within partition
- `original_key` (string, optional): Original message key
- `original_message` (string): Original message as JSON string
- `consumer_group_id` (string): Consumer group ID that failed
- `error_type` (enum): Error classification
  - `SCHEMA_VALIDATION`, `PROCESSING_FAILURE`, `TIMEOUT`, `BUSINESS_LOGIC`, `UNKNOWN`
- `error_message` (string): Human-readable error description
- `error_stack_trace` (string, optional): Full stack trace
- `retry_count` (int): Number of retry attempts made
- `metadata` (map): Additional context metadata

---

## Schema Registry

### Register Schemas

Use the provided script to register all schemas:

```bash
python scripts/kafka/register_schemas.py
```

### Manual Registration

```bash
# Register plate_event schema
curl -X POST \
  http://localhost:8081/subjects/alpr.events.plates-value/versions \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d @- <<EOF
{
  "schema": $(cat schemas/plate_event.avsc | jq -c .)
}
EOF

# Register metric_event schema
curl -X POST \
  http://localhost:8081/subjects/alpr.metrics-value/versions \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d @- <<EOF
{
  "schema": $(cat schemas/metric_event.avsc | jq -c .)
}
EOF
```

### List Schemas

```bash
# List all subjects
curl http://localhost:8081/subjects

# Get schema for subject
curl http://localhost:8081/subjects/alpr.events.plates-value/versions/latest

# Get all versions
curl http://localhost:8081/subjects/alpr.events.plates-value/versions
```

### Delete Schema (Caution!)

```bash
# Soft delete
curl -X DELETE http://localhost:8081/subjects/alpr.events.plates-value/versions/1

# Hard delete (permanent)
curl -X DELETE http://localhost:8081/subjects/alpr.events.plates-value?permanent=true
```

## Compatibility Modes

Current mode: **BACKWARD** (default)

- **BACKWARD**: New schema can read old data
- **FORWARD**: Old schema can read new data
- **FULL**: Both backward and forward compatible
- **NONE**: No compatibility checking

Change compatibility mode:

```bash
curl -X PUT \
  http://localhost:8081/config/alpr.events.plates-value \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d '{"compatibility": "FULL"}'
```

## Schema Evolution

### Adding Optional Fields

✅ **Backward Compatible** - Add fields with default values:

```json
{
  "name": "new_field",
  "type": ["null", "string"],
  "default": null
}
```

### Removing Fields

⚠️ **Breaking Change** - Requires compatibility mode change or version bump

### Changing Field Types

❌ **Not Allowed** in BACKWARD mode - Create new field instead

## Python Usage

### Producer (with Schema Registry)

```python
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

# Schema Registry client
schema_registry_client = SchemaRegistryClient({'url': 'http://localhost:8081'})

# Load schema
with open('schemas/plate_event.avsc', 'r') as f:
    schema_str = f.read()

# Create Avro serializer
avro_serializer = AvroSerializer(schema_registry_client, schema_str)

# Create producer
producer = SerializingProducer({
    'bootstrap.servers': 'localhost:9092',
    'value.serializer': avro_serializer
})

# Publish event
event_data = {
    'event_id': 'uuid-here',
    'captured_at': '2025-12-25T12:00:00Z',
    'camera_id': 'CAM1',
    'track_id': 't-42',
    'plate': {
        'text': 'ABC1234',
        'normalized_text': 'ABC1234',
        'confidence': 0.95,
        'region': 'US-FL'
    },
    # ... rest of fields
}

producer.produce(topic='alpr.events.plates', value=event_data)
producer.flush()
```

### Consumer (with Schema Registry)

```python
from confluent_kafka import DeserializingConsumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

# Schema Registry client
schema_registry_client = SchemaRegistryClient({'url': 'http://localhost:8081'})

# Avro deserializer
avro_deserializer = AvroDeserializer(schema_registry_client)

# Create consumer
consumer = DeserializingConsumer({
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'alpr-storage-consumer',
    'value.deserializer': avro_deserializer
})

consumer.subscribe(['alpr.events.plates'])

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue

    event_data = msg.value()  # Automatically deserialized
    print(f"Plate: {event_data['plate']['text']}")
```

## Integration with Monitoring

### Prometheus Metrics
Kafka consumers expose metrics at `/metrics` endpoints showing:
- Messages processed per topic
- Processing latency
- Error rates
- Consumer lag

### Grafana Dashboards
Pre-built dashboards visualize:
- Event throughput by topic
- Processing latency histograms
- DLQ message rates
- Consumer group lag

### OpenSearch Indexing
Plate events are indexed in OpenSearch for:
- Full-text search on plate text
- Time-range queries
- Analytics aggregations

### Distributed Tracing (Tempo)
Query API requests are traced with OpenTelemetry:
- End-to-end request tracing
- Trace-to-log correlation via trace_id
- Service dependency visualization

## Testing

Test schema validation:

```bash
# Install avro-tools
pip install avro-python3

# Validate schema
python -m avro.tool validate schemas/plate_event.avsc test_event.json
```

## Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Schema Registry | http://localhost:8081 | Schema management |
| Kafka UI | http://localhost:8080 | Topic monitoring |
| Query API | http://localhost:8000/docs | Event queries |
| Grafana | http://localhost:3000 | Dashboards |
| Tempo | http://localhost:3200 | Distributed tracing |

## References

- [Confluent Schema Registry Documentation](https://docs.confluent.io/platform/current/schema-registry/index.html)
- [Avro Specification](https://avro.apache.org/docs/current/spec.html)
- [Schema Evolution Best Practices](https://docs.confluent.io/platform/current/schema-registry/avro.html)
