# Kafka Setup for ALPR Event Publishing

## Quick Start

### 1. Install Dependencies

```bash
# Install kafka-python
pip install kafka-python

# Optional: Install with compression support
pip install kafka-python[snappy,lz4,zstd]
```

### 2. Testing Without Kafka (Mock Mode)

You can test the event processor immediately without setting up Kafka:

```bash
cd /home/jetson/OVR-ALPR
python3 services/event-processor/test_kafka.py
```

This uses `MockKafkaPublisher` which logs events to console instead of publishing to Kafka.

---

## Kafka Broker Setup

### Option 1: Local Development (Docker)

**Easiest way to get started:**

```bash
# Create docker-compose.yml
cat > docker-compose.yml <<EOF
version: '3'
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
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
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
EOF

# Start Kafka
docker-compose up -d

# Verify Kafka is running
docker-compose ps
```

**Create topic:**

```bash
docker exec -it $(docker ps -q -f name=kafka) kafka-topics \
  --create \
  --topic alpr.plates.detected \
  --bootstrap-server localhost:9092 \
  --partitions 3 \
  --replication-factor 1
```

**Test publishing:**

```python
# Uncomment the real Kafka test in test_kafka.py
python3 services/event-processor/test_kafka.py
```

---

### Option 2: Cloud Managed Kafka

#### AWS MSK (Managed Streaming for Kafka)

**1. Create MSK cluster:**
```bash
# Via AWS Console or CLI
aws kafka create-cluster \
  --cluster-name alpr-production \
  --kafka-version 2.8.1 \
  --number-of-broker-nodes 3 \
  --broker-node-group-info \
    instanceType=kafka.t3.small,clientSubnets=[subnet-xxx,subnet-yyy,subnet-zzz]
```

**2. Update config/kafka.yaml:**
```yaml
kafka:
  bootstrap_servers: "b-1.alpr-prod.xyz.kafka.us-east-1.amazonaws.com:9092,b-2.alpr-prod.xyz.kafka.us-east-1.amazonaws.com:9092,b-3.alpr-prod.xyz.kafka.us-east-1.amazonaws.com:9092"
```

**3. Create topic:**
```bash
aws kafka create-topic \
  --cluster-arn arn:aws:kafka:us-east-1:123456789012:cluster/alpr-production/... \
  --topic-name alpr.plates.detected \
  --partitions 10 \
  --replication-factor 3
```

**Cost:** ~$300-500/month for 3-broker cluster (t3.small instances)

---

#### Confluent Cloud

**1. Create cluster at https://confluent.cloud**

**2. Get API credentials:**
```
API Key: XXXXXXXXXXXXXXXX
API Secret: YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
Bootstrap Server: pkc-xxxxx.us-east-1.aws.confluent.cloud:9092
```

**3. Update config/kafka.yaml:**
```yaml
kafka:
  bootstrap_servers: "pkc-xxxxx.us-east-1.aws.confluent.cloud:9092"

auth:
  security_protocol: "SASL_SSL"
  sasl_mechanism: "PLAIN"
  sasl_username: "XXXXXXXXXXXXXXXX"
  sasl_password: "YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY"
```

**4. Update kafka_publisher.py to add auth:**
```python
# In KafkaPublisher.__init__, add to config:
if auth_config:
    self.config.update({
        'security_protocol': auth_config['security_protocol'],
        'sasl_mechanism': auth_config['sasl_mechanism'],
        'sasl_plain_username': auth_config['sasl_username'],
        'sasl_plain_password': auth_config['sasl_password'],
    })
```

**Cost:** Pay-as-you-go (~$1/GB ingress + $0.10/GB egress)

---

## Integration with pilot.py

### Step 1: Add Kafka Publisher to pilot.py

```python
# In pilot.py imports (add after existing imports)
from services.event_processor import EventProcessorService
from services.event_processor.kafka_publisher import KafkaPublisher, MockKafkaPublisher

# In ALPRPilot.__init__, add:
def __init__(self, ...):
    # ... existing init code ...

    # Initialize Event Processor
    self.event_processor = EventProcessorService(
        site_id="DC1",  # Configure based on deployment
        host_id="jetson-orin-nx",
        min_confidence=0.70,
        dedup_similarity_threshold=0.85,
        dedup_time_window_seconds=300,
    )

    # Initialize Kafka Publisher
    try:
        self.kafka_publisher = KafkaPublisher(
            bootstrap_servers="localhost:9092",  # Update for production
            topic="alpr.plates.detected",
            client_id=f"alpr-{camera_id}",
            compression_type="gzip",
            acks="all",
        )
        logger.success("Kafka publisher initialized")
    except Exception as e:
        logger.warning(f"Kafka not available, using mock: {e}")
        self.kafka_publisher = MockKafkaPublisher()
```

### Step 2: Replace CSV saving with Kafka publishing

Replace the `_save_plate_read()` method (lines 271-284):

```python
def _publish_plate_event(self, camera_id: str, track_id: int, plate_detection, vehicle=None):
    """
    Process and publish plate event to Kafka
    Replaces _save_plate_read()
    """
    try:
        # Get vehicle attributes
        vehicle_type = vehicle.vehicle_type if vehicle else "unknown"
        vehicle_color = vehicle.color if vehicle else None
        vehicle_make = vehicle.make if vehicle else None
        vehicle_model = vehicle.model if vehicle else None

        # Get plate image path
        plate_image_path = None
        if track_id in self.track_best_plate_crop:
            date_folder = datetime.now().strftime('%Y-%m-%d')
            plate_image_path = str(self.crops_dir / date_folder / f"{camera_id}_track{track_id}.jpg")

        # Get quality score
        quality_score = self.track_best_plate_quality.get(track_id, 0.0)

        # Process event
        event = self.event_processor.process_detection(
            plate_text=plate_detection.text,
            plate_confidence=plate_detection.confidence,
            camera_id=camera_id,
            track_id=track_id,
            vehicle_type=vehicle_type,
            vehicle_color=vehicle_color,
            vehicle_make=vehicle_make,
            vehicle_model=vehicle_model,
            plate_image_path=plate_image_path,
            region="US-FL",  # Configure based on deployment
            roi=None,  # TODO: Add ROI detection
            direction=None,  # TODO: Add direction detection
            quality_score=quality_score,
            frame_number=self.frame_count,
        )

        if event:
            # Publish to Kafka
            success = self.kafka_publisher.publish_event(event.to_dict())
            if success:
                logger.success(
                    f"📤 Published to Kafka: {event.plate['normalized_text']} "
                    f"(track: {track_id}, event: {event.event_id})"
                )

                # Save best crop to disk
                if track_id in self.track_best_plate_crop:
                    self._save_best_crop_to_disk(track_id, camera_id)
            else:
                logger.error(f"Failed to publish event to Kafka")
        else:
            logger.debug(f"Event rejected by processor (duplicate or invalid)")

    except Exception as e:
        logger.error(f"Failed to publish plate event: {e}")
```

### Step 3: Update OCR processing logic

In `process_frame()`, replace calls to `_save_plate_read()` (around line 835):

```python
# OLD CODE (remove):
# if plate_detection.confidence >= self.ocr_min_confidence and is_new_read:
#     self._save_plate_read(camera_id, track_id, plate_detection.text, plate_detection.confidence, skip_duplicate_check=True)

# NEW CODE (add):
if plate_detection.confidence >= self.ocr_min_confidence and is_new_read:
    vehicle = vehicles[vehicle_idx] if vehicle_idx < len(vehicles) else None
    self._publish_plate_event(camera_id, track_id, plate_detection, vehicle=vehicle)
```

### Step 4: Cleanup on exit

Add to `cleanup()` method:

```python
def cleanup(self):
    """Cleanup resources"""
    logger.info("Cleaning up...")

    # Flush and close Kafka publisher
    if hasattr(self, 'kafka_publisher'):
        self.kafka_publisher.flush()
        self.kafka_publisher.close()

    # ... existing cleanup code ...
```

---

## Topic Design

### Recommended Topic Structure

```
alpr.plates.detected         # Main event stream
  └─ Partitions: 10          # Scale based on camera count
  └─ Retention: 7 days       # For ML retraining
  └─ Replication: 3          # High availability

alpr.vehicles.tracked        # Vehicle tracking events (optional)
  └─ Partitions: 5
  └─ Retention: 2 days

alpr.system.health          # System telemetry (optional)
  └─ Partitions: 1
  └─ Retention: 1 day
```

### Partitioning Strategy

**Use `camera_id` as partition key:**
- Ensures ordering per camera
- Scales horizontally as cameras are added
- Allows parallel processing by camera

```python
# Automatic in KafkaPublisher:
publisher.publish_event(event.to_dict())  # Uses camera_id as key
```

---

## Consuming Events

### Python Consumer Example

```python
from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    'alpr.plates.detected',
    bootstrap_servers='localhost:9092',
    auto_offset_reset='earliest',
    enable_auto_commit=True,
    group_id='alpr-storage-service',
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

for message in consumer:
    event = message.value
    print(f"Received plate: {event['plate']['normalized_text']}")

    # Store to database
    # store_to_postgres(event)

    # Trigger alert if watchlist match
    # check_watchlist(event)
```

### Stream Processing (Kafka Streams)

For real-time analytics:

```java
// Aggregate plate reads by camera (Java example)
StreamsBuilder builder = new StreamsBuilder();

KStream<String, PlateEvent> plates = builder.stream("alpr.plates.detected");

// Count plates per camera (1-minute windows)
KTable<Windowed<String>, Long> plateCounts = plates
    .groupBy((key, value) -> value.getCameraId())
    .windowedBy(TimeWindows.of(Duration.ofMinutes(1)))
    .count();

plateCounts.toStream().to("alpr.analytics.camera-counts");
```

---

## Monitoring

### View messages in topic

```bash
# Consumer from beginning
docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic alpr.plates.detected \
  --from-beginning

# Consumer with formatting
docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic alpr.plates.detected \
  --from-beginning \
  --property print.key=true \
  --property print.value=true
```

### Check topic lag

```bash
docker exec -it kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group alpr-storage-service \
  --describe
```

---

## Troubleshooting

### Connection errors

```
ERROR: Failed to connect to Kafka
```

**Solution:**
1. Check Kafka is running: `docker-compose ps`
2. Verify broker address in config/kafka.yaml
3. Check network connectivity: `telnet localhost 9092`

### Authentication errors (Cloud)

```
ERROR: Authentication failed
```

**Solution:**
1. Verify credentials in config/kafka.yaml
2. Check security_protocol matches broker config
3. Ensure API key has write permissions

### Message too large

```
ERROR: MessageSizeTooLargeError
```

**Solution:**
1. Reduce max_request_size in kafka.yaml
2. Don't embed large images in events (use S3 URLs instead)
3. Increase broker `message.max.bytes` setting

---

## Production Checklist

- [ ] Kafka cluster has 3+ brokers (HA)
- [ ] Topics have replication factor ≥ 2
- [ ] Enable authentication (SASL/SSL)
- [ ] Set retention policy based on storage limits
- [ ] Configure monitoring (Prometheus + Grafana)
- [ ] Set up log aggregation (ELK stack)
- [ ] Test failover scenarios
- [ ] Document disaster recovery plan
- [ ] Enable compression (gzip/snappy)
- [ ] Tune batch_size and linger_ms for throughput

---

## Next Steps

1. **Start with mock mode** - Test event processor without Kafka
2. **Set up local Kafka** - Use Docker for development
3. **Integrate with pilot.py** - Replace CSV with Kafka publishing
4. **Build consumers** - Storage service, analytics, alerts
5. **Deploy to cloud** - Use managed Kafka (MSK/Confluent)
6. **Monitor and scale** - Add partitions as camera count grows

## Related Documentation

- [Event Processor Service](./event-processor-service.md)
- [REST API Design](./rest-api-design.md) (to be created)
- [Database Schema](./database-schema.md) (to be created)
