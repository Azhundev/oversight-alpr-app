# Auto-Reconnection Testing Guide

This document describes how to test the auto-reconnection feature in pilot.py, which allows the pilot to start before backend services and automatically connect when they become available.

## Feature Overview

pilot.py now includes **automatic reconnection** for:
- **Kafka + Schema Registry**: Reconnects every 30 seconds if initially unavailable
- **MinIO Object Storage**: Reconnects every 30 seconds if initially unavailable

This allows you to:
1. Start pilot.py first (detection, tracking, OCR work immediately)
2. Start backend services later
3. Pilot automatically connects without restart

---

## Test Scenario 1: Start Pilot Before Kafka

### Step 1: Start pilot.py WITHOUT any services

```bash
# Ensure no services are running
docker compose down

# Start pilot
python3 pilot.py
```

**Expected behavior**:
```
⚠️  Kafka/Schema Registry not available, using mock publisher: ...
⚠️  MinIO not available: ...
✅ Prometheus metrics endpoint started at http://localhost:8001/metrics
✅ ALPR Pilot initialized successfully
```

**What works**:
- ✅ Camera ingestion
- ✅ Vehicle detection
- ✅ Plate detection
- ✅ OCR recognition
- ✅ ByteTrack tracking
- ✅ Local CSV output
- ⚠️  Events logged locally (MockKafkaPublisher)
- ❌ No Kafka publishing
- ❌ No image uploads

### Step 2: Start Kafka (while pilot is running)

```bash
# In another terminal
docker compose up -d zookeeper kafka schema-registry

# Wait for Kafka to be ready (30-60 seconds)
docker logs kafka --tail 50
```

**Expected behavior in pilot.py logs**:
```
🔄 Attempting to connect to Kafka...
✅ Connected to Kafka (multi-topic mode)
   Bootstrap: localhost:9092
   Schema Registry: http://localhost:8081
```

**Wait time**: Up to 30 seconds for first reconnection attempt

**Verify**: Next plate event should show:
```
📤 Published to Kafka: ABC123 (track: 1, event: evt_...)
```

---

## Test Scenario 2: Start MinIO After Pilot

### Step 1: Pilot running with Kafka, but no MinIO

```bash
# Start Kafka only
docker compose up -d zookeeper kafka schema-registry

# Start pilot
python3 pilot.py
```

**Expected**:
```
✅ Connected to Kafka
⚠️  MinIO not available: ...
```

### Step 2: Start MinIO (while pilot is running)

```bash
# Start MinIO
docker compose up -d minio
```

**Expected behavior in pilot.py logs** (within 30 seconds):
```
🔄 Attempting to connect to MinIO...
✅ Connected to MinIO
   Endpoint: localhost:9000
   Bucket: alpr-plate-images
```

**Verify**: Next plate crop should show:
```
💾 Saved plate crop: 2025-01-05/camera_track1_frame123_q0.85.jpg
☁️  Queued upload to MinIO: camera_track1_frame123_q0.85.jpg → s3://...
```

---

## Test Scenario 3: Complete Incremental Startup

### Timeline

**T=0s: Start pilot.py alone**
```bash
python3 pilot.py
```
- Detection/OCR works
- Events logged locally
- Images saved to `output/crops/` only

**T=30s: Start Kafka**
```bash
docker compose up -d zookeeper kafka schema-registry
```
- Wait for Kafka startup (~60s)
- Pilot auto-connects within 30s
- Events now published to Kafka

**T=120s: Start Storage**
```bash
docker compose up -d timescaledb minio kafka-consumer
```
- MinIO auto-connects within 30s
- Images now uploaded to S3
- Events now saved to database

**T=180s: Start Search**
```bash
docker compose up -d opensearch elasticsearch-consumer
```
- Events indexed for search

**T=240s: Start Monitoring**
```bash
docker compose up -d prometheus grafana
```
- Metrics scraped and visualized

---

## Reconnection Intervals

| Service | Reconnection Interval | Trigger |
|---------|----------------------|---------|
| Kafka | 30 seconds | When publishing event |
| MinIO | 30 seconds | When uploading image |

**Note**: These intervals are configurable in pilot.py:
```python
self.kafka_reconnect_interval = 30  # seconds
self.minio_reconnect_interval = 30  # seconds
```

---

## Verification Commands

### Check if pilot connected to Kafka
```bash
# Watch pilot logs
tail -f <pilot_output>

# Check Kafka topics
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Consume recent events
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic alpr.events.plates \
  --from-beginning \
  --max-messages 5
```

### Check if pilot connected to MinIO
```bash
# Check MinIO bucket
docker exec minio mc ls minio/alpr-plate-images/

# Or via web console
# http://localhost:9001 (minioadmin / minioadmin)
```

### Check pilot metrics
```bash
# Prometheus metrics endpoint
curl http://localhost:8001/metrics | grep alpr_
```

---

## Troubleshooting

### Kafka not reconnecting

**Check logs**:
```
Kafka connection failed (will retry in 30s): ...
```

**Possible causes**:
1. Kafka not fully started (check `docker logs kafka`)
2. Port 9092 not accessible
3. Schema Registry not started

**Solution**: Wait for Kafka startup, or restart pilot after Kafka is ready

### MinIO not reconnecting

**Check logs**:
```
MinIO connection failed (will retry in 30s): ...
```

**Possible causes**:
1. MinIO not started
2. Port 9000 not accessible
3. Incorrect credentials

**Solution**: Check MinIO status with `docker logs minio`

### Reconnection attempts too frequent

If you see reconnection attempts every few seconds instead of every 30s:
- Check that `kafka_last_reconnect_attempt` and `minio_last_reconnect_attempt` are being updated
- Verify throttling logic in `_try_reconnect_kafka()` and `_try_reconnect_minio()`

---

## Expected Performance Impact

**Auto-reconnection overhead**:
- **Minimal**: Checks only happen when publishing events or uploading images
- **Throttled**: Maximum 1 attempt every 30 seconds per service
- **No impact** when already connected (fast isinstance check)

**Memory usage**:
- No change (same publishers/storage services)

**CPU usage**:
- Negligible (<0.1% for reconnection attempts)

---

## Production Recommendations

**For production deployments**:

1. **Start services in order** using orchestration (Kubernetes, Docker Swarm)
2. **Use health checks** and readiness probes
3. **Increase reconnection interval** for production:
   ```python
   self.kafka_reconnect_interval = 60  # 1 minute
   self.minio_reconnect_interval = 60  # 1 minute
   ```
4. **Monitor connection state** via Prometheus metrics
5. **Add alerts** for prolonged disconnection

**This auto-reconnection feature is designed for**:
- Development/testing workflows
- Resource-constrained edge devices
- Gradual system startup
- Handling temporary network issues

---

## Related Documentation

- [Incremental Startup Guide](incremental-startup.md)
- [Port Reference](../alpr/port-reference.md)
- [Service Dependencies](../Services/monitoring-stack-setup.md)
