# Kafka Quick Start Guide

## Test Event Processing Right Now (No Kafka Required)

```bash
cd /home/jetson/OVR-ALPR

# Test with mock publisher
python3 services/event-processor/test_kafka.py
```

You'll see output like:
```
✅ Event published: 91ee2923-d604-46f0-9470-6e2a99fb1bb9 | ABC123
📤 [MOCK] Would publish to Kafka:
  Topic: alpr.events.plates
  Key: west_gate_cam_03
  Event ID: 91ee2923-d604-46f0-9470-6e2a99fb1bb9
  Plate: ABC123
```

---

## Set Up Real Kafka (5 minutes)

### 1. Start Kafka with Docker

```bash
cd /home/jetson/OVR-ALPR

# Create docker-compose.yml
cat > docker-compose.yml <<'EOF'
version: '3'
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
    ports:
      - "2181:2181"

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
EOF

# Start Kafka
docker-compose up -d

# Wait 30 seconds for startup
sleep 30
```

### 2. Install Python Client

```bash
pip install kafka-python
```

### 3. Create Topic

```bash
docker exec -it $(docker ps -q -f name=kafka) kafka-topics \
  --create \
  --topic alpr.events.plates \
  --bootstrap-server localhost:9092 \
  --partitions 3 \
  --replication-factor 1
```

### 4. Test Real Publishing

Edit `services/event-processor/test_kafka.py` and uncomment line 195:

```python
# Change from:
# test_with_real_kafka()

# To:
test_with_real_kafka()
```

Then run:
```bash
python3 services/event-processor/test_kafka.py
```

### 5. Consume Messages

In another terminal:

```bash
docker exec -it $(docker ps -q -f name=kafka) kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic alpr.events.plates \
  --from-beginning
```

You should see JSON events:
```json
{
  "event_id": "...",
  "captured_at": "2025-12-04T20:15:12.431Z",
  "camera_id": "west_gate_cam_03",
  "plate": {
    "text": "ABC123",
    "normalized_text": "ABC123",
    "confidence": 0.91
  }
}
```

---

## Files Created

```
services/event-processor/
├── event_processor_service.py   # Main service
├── kafka_publisher.py            # Kafka integration
├── test_kafka.py                 # Test suite
└── example_usage.py              # Usage examples

config/
└── kafka.yaml                    # Kafka configuration

docs/
├── event-processor-service.md    # Service documentation
├── kafka-setup.md                # Full setup guide
└── kafka-quickstart.md           # This file
```

---

## What You Have Now

✅ **EventProcessorService** - Normalizes, validates, deduplicates plates
✅ **KafkaPublisher** - Publishes events to Kafka topics
✅ **MockKafkaPublisher** - Test without Kafka broker
✅ **Event Schema** - Structured JSON for Kafka/MQTT
✅ **Configuration** - YAML config for all settings
✅ **Documentation** - Complete guides and examples

---

## Next Steps

1. **Test locally** with mock publisher (done above)
2. **Set up Kafka** with Docker (done above)
3. **Integrate with pilot.py** - See [kafka-setup.md](./kafka-setup.md#integration-with-pilotpy)
4. **Build consumers** - Storage, analytics, alerts
5. **Deploy to cloud** - AWS MSK or Confluent Cloud

---

## Quick Integration Example

```python
# In pilot.py
from services.event_processor import EventProcessorService
from services.event_processor.kafka_publisher import KafkaPublisher

# Initialize
event_processor = EventProcessorService()
kafka_publisher = KafkaPublisher(
    bootstrap_servers="localhost:9092",
    topic="alpr.events.plates"
)

# When OCR succeeds
event = event_processor.process_detection(
    plate_text=plate_detection.text,
    plate_confidence=plate_detection.confidence,
    camera_id=camera_id,
    track_id=track_id,
    # ... other fields
)

if event:
    kafka_publisher.publish_event(event.to_dict())
```

---

## Help

- **Full documentation**: [kafka-setup.md](./kafka-setup.md)
- **Event processor**: [event-processor-service.md](./event-processor-service.md)
- **Issues**: Check logs with `logger.debug()` enabled
