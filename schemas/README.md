# ALPR Event Schemas

This directory contains Avro schema definitions for ALPR events used with Confluent Schema Registry.

## Schema Files

### plate_event.avsc
Avro schema for plate detection events. Defines the structure of events published to Kafka topic `alpr.plates.detected`.

**Schema Details:**
- **Namespace:** `com.alpr.events`
- **Type:** Record
- **Compatibility:** Backward compatible (allows reading old data with new schema)

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

## Schema Registry

### Register Schema

Use the provided script to register the schema:

```bash
python scripts/register_schemas.py
```

### Manual Registration

```bash
curl -X POST \
  http://localhost:8081/subjects/alpr.plates.detected-value/versions \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d @- <<EOF
{
  "schema": $(cat schemas/plate_event.avsc | jq -c .)
}
EOF
```

### List Schemas

```bash
# List all subjects
curl http://localhost:8081/subjects

# Get schema for subject
curl http://localhost:8081/subjects/alpr.plates.detected-value/versions/latest
```

### Delete Schema (Caution!)

```bash
# Soft delete
curl -X DELETE http://localhost:8081/subjects/alpr.plates.detected-value/versions/1

# Hard delete (permanent)
curl -X DELETE http://localhost:8081/subjects/alpr.plates.detected-value?permanent=true
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
  http://localhost:8081/config/alpr.plates.detected-value \
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

producer.produce(topic='alpr.plates.detected', value=event_data)
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

consumer.subscribe(['alpr.plates.detected'])

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue

    event_data = msg.value()  # Automatically deserialized
    print(f"Plate: {event_data['plate']['text']}")
```

## Testing

Test schema validation:

```bash
# Install avro-tools
pip install avro-python3

# Validate schema
python -m avro.tool validate schemas/plate_event.avsc test_event.json
```

## References

- [Confluent Schema Registry Documentation](https://docs.confluent.io/platform/current/schema-registry/index.html)
- [Avro Specification](https://avro.apache.org/docs/current/spec.html)
- [Schema Evolution Best Practices](https://docs.confluent.io/platform/current/schema-registry/avro.html)
