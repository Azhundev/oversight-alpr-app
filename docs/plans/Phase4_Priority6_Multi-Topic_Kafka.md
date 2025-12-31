# Phase 4 Priority 6: Multi-Topic Kafka Architecture - Implementation Plan

**Last Updated**: 2025-12-30

## Executive Summary

This plan outlines the migration from a single-topic Kafka architecture (`alpr.plates.detected`) to a multi-topic architecture with dedicated topics for different event types, system metrics, and dead letter queue (DLQ) handling. The implementation will maintain backward compatibility during migration and support graceful rollback.

**Key Goals**:
- Restructure Kafka topics for better organization (events, metrics, DLQ)
- Implement Dead Letter Queue for failed message handling
- Add system metrics topic for telemetry
- Zero-downtime migration with 7-day rollback window

**Estimated Effort**: 2 weeks

---

## 1. TOPIC ARCHITECTURE DESIGN

### 1.1 Proposed Topic Structure

```
alpr.events.plates          - Plate detection events (primary business events)
alpr.events.vehicles        - Vehicle tracking events (new)
alpr.events.tracking        - Tracking lifecycle events (optional/future)
alpr.metrics               - System health & telemetry
alpr.dlq                   - Dead Letter Queue for failed messages
```

### 1.2 Topic Configuration

**Topic: `alpr.events.plates`**
- **Purpose**: Plate detection events with OCR results
- **Partitions**: 3
- **Retention**: 7 days
- **Partition Key**: `camera_id`
- **Consumers**: Storage, Alert Engine, Elasticsearch

**Topic: `alpr.events.vehicles`**
- **Purpose**: Vehicle tracking events without plates
- **Partitions**: 3
- **Retention**: 7 days
- **Partition Key**: `camera_id`

**Topic: `alpr.metrics`**
- **Purpose**: System health metrics (FPS, latency, GPU)
- **Partitions**: 1
- **Retention**: 24 hours
- **Partition Key**: `host_id`

**Topic: `alpr.dlq`**
- **Purpose**: Dead letter queue for failed messages
- **Partitions**: 1
- **Retention**: 30 days
- **Partition Key**: `original_topic`

---

## 2. AVRO SCHEMA DESIGN

### 2.1 PlateEvent Schema (Enhanced)

**File**: `/home/jetson/OVR-ALPR/schemas/plate_event.avsc` (existing, no changes needed)

Already well-designed with all required fields.

### 2.2 VehicleEvent Schema (New)

**File**: `/home/jetson/OVR-ALPR/schemas/vehicle_event.avsc` (NEW)

```json
{
  "type": "record",
  "name": "VehicleEvent",
  "namespace": "com.alpr.events",
  "doc": "Vehicle tracking event without plate detection",
  "fields": [
    {"name": "event_id", "type": "string"},
    {"name": "captured_at", "type": "string"},
    {"name": "camera_id", "type": "string"},
    {"name": "track_id", "type": "string"},
    {
      "name": "vehicle": {
        "type": "record",
        "name": "VehicleInfo",
        "fields": [
          {"name": "type", "type": ["null", "string"], "default": null},
          {"name": "color", "type": ["null", "string"], "default": null},
          {"name": "bbox", "type": {
            "type": "record",
            "name": "BoundingBox",
            "fields": [
              {"name": "x1", "type": "float"},
              {"name": "y1", "type": "float"},
              {"name": "x2", "type": "float"},
              {"name": "y2", "type": "float"}
            ]
          }},
          {"name": "confidence", "type": "float"}
        ]
      }
    },
    {
      "name": "tracking": {
        "type": "record",
        "name": "TrackingInfo",
        "fields": [
          {"name": "direction", "type": ["null", "string"], "default": null},
          {"name": "speed_kmh", "type": ["null", "float"], "default": null},
          {"name": "dwell_time_seconds", "type": ["null", "float"], "default": null},
          {"name": "first_seen_at", "type": "string"},
          {"name": "last_seen_at", "type": "string"}
        ]
      }
    },
    {"name": "latency_ms", "type": "int", "default": 0},
    {
      "name": "node": {
        "type": "record",
        "name": "NodeInfo",
        "fields": [
          {"name": "site", "type": ["null", "string"], "default": null},
          {"name": "host", "type": ["null", "string"], "default": null}
        ]
      }
    }
  ]
}
```

### 2.3 MetricEvent Schema (New)

**File**: `/home/jetson/OVR-ALPR/schemas/metric_event.avsc` (NEW)

```json
{
  "type": "record",
  "name": "MetricEvent",
  "namespace": "com.alpr.metrics",
  "fields": [
    {"name": "metric_id", "type": "string"},
    {"name": "timestamp", "type": "string"},
    {"name": "host_id", "type": "string"},
    {"name": "site_id", "type": ["null", "string"], "default": null},
    {"name": "metric_type", "type": {
      "type": "enum",
      "name": "MetricType",
      "symbols": ["FPS", "LATENCY", "GPU_UTIL", "MEMORY", "SERVICE_HEALTH", "CUSTOM"]
    }},
    {"name": "metric_name", "type": "string"},
    {"name": "value", "type": "float"},
    {"name": "unit", "type": "string"},
    {"name": "tags", "type": {"type": "map", "values": "string"}, "default": {}}
  ]
}
```

### 2.4 DLQMessage Schema (New)

**File**: `/home/jetson/OVR-ALPR/schemas/dlq_message.avsc` (NEW)

```json
{
  "type": "record",
  "name": "DLQMessage",
  "namespace": "com.alpr.dlq",
  "fields": [
    {"name": "dlq_id", "type": "string"},
    {"name": "timestamp", "type": "string"},
    {"name": "original_topic", "type": "string"},
    {"name": "original_partition", "type": "int"},
    {"name": "original_offset", "type": "long"},
    {"name": "original_key", "type": ["null", "string"], "default": null},
    {"name": "original_message", "type": "string"},
    {"name": "consumer_group_id", "type": "string"},
    {"name": "error_type", "type": {
      "type": "enum",
      "name": "DLQErrorType",
      "symbols": ["SCHEMA_VALIDATION", "PROCESSING_FAILURE", "TIMEOUT", "BUSINESS_LOGIC", "UNKNOWN"]
    }},
    {"name": "error_message", "type": "string"},
    {"name": "error_stack_trace", "type": ["null", "string"], "default": null},
    {"name": "retry_count", "type": "int", "default": 0},
    {"name": "metadata", "type": {"type": "map", "values": "string"}, "default": {}}
  ]
}
```

---

## 3. PRODUCER MODIFICATIONS

### 3.1 Multi-Topic Publisher

**File**: `/home/jetson/OVR-ALPR/edge-services/event_processor/multi_topic_publisher.py` (NEW)

Implement `MultiTopicAvroPublisher` class with:
- Topic routing based on event type
- Support for multiple schemas
- Dual-publish mode for migration
- Partition key routing (camera_id, host_id)

**Key Methods**:
- `publish_plate_event(event_dict)` → routes to `alpr.events.plates`
- `publish_vehicle_event(event_dict)` → routes to `alpr.events.vehicles`
- `publish_metric_event(event_dict)` → routes to `alpr.metrics`
- `publish_dlq_message(dlq_dict)` → routes to `alpr.dlq`

### 3.2 Pilot.py Integration

**File**: `/home/jetson/OVR-ALPR/pilot.py` (MODIFY lines 196-216)

Add environment variable flag: `KAFKA_USE_MULTI_TOPIC`
- `true`: Use MultiTopicAvroPublisher
- `false`: Use legacy AvroKafkaPublisher

During migration, support dual-publishing to both old and new topics.

---

## 4. CONSUMER MODIFICATIONS

### 4.1 Storage Consumer

**File**: `/home/jetson/OVR-ALPR/core-services/storage/avro_kafka_consumer.py` (MODIFY)

**Changes**:
1. Subscribe to `alpr.events.plates` (update from `alpr.plates.detected`)
2. Add DLQ producer initialization
3. Implement retry logic with exponential backoff (3 attempts, base delay 2s)
4. Add timeout detection (30s max per message)
5. Send to DLQ after exhausting retries

**DLQ Triggers**:
- Database insert failures after 3 retries
- Processing timeout (> 30 seconds)
- Schema validation errors
- Business logic rejections

### 4.2 Alert Engine

**File**: `/home/jetson/OVR-ALPR/core-services/alerting/alert_engine.py` (MODIFY)

**Changes**:
- Update topic: `alpr.events.plates`
- Add DLQ producer
- Send to DLQ on persistent notification failures

### 4.3 Elasticsearch Consumer

**File**: `/home/jetson/OVR-ALPR/core-services/search/elasticsearch_consumer.py` (MODIFY)

**Changes**:
- Update topic: `alpr.events.plates`
- Add DLQ producer
- Add timeout for bulk indexing operations
- Send to DLQ on OpenSearch failures

---

## 5. NEW SERVICES

### 5.1 DLQ Consumer

**File**: `/home/jetson/OVR-ALPR/core-services/dlq/dlq_consumer.py` (NEW)

**Purpose**: Monitor DLQ topic, log failures, expose metrics

**Features**:
- Consume from `alpr.dlq` topic
- Log detailed error information
- Expose Prometheus metrics (port 8005)
- Alert on critical errors (schema validation, timeouts)

**Metrics**:
- `dlq_messages_total{error_type, original_topic}`
- `dlq_oldest_message_age_seconds`

### 5.2 Metrics Consumer (Optional)

**File**: `/home/jetson/OVR-ALPR/core-services/metrics/metrics_consumer.py` (NEW)

**Purpose**: Consume system metrics from Kafka and expose for Prometheus

**Features**:
- Consume from `alpr.metrics` topic
- Dynamically create Prometheus gauges
- Expose metrics (port 8006)

### 5.3 Metrics Publisher (Optional)

**File**: `/home/jetson/OVR-ALPR/edge-services/event_processor/metrics_publisher.py` (NEW)

**Purpose**: Publish system metrics to Kafka

**Metrics to Publish**:
- `pipeline_fps` (FPS)
- `gpu_utilization` (GPU_UTIL)
- `memory_usage` (MEMORY)
- Custom metrics

---

## 6. MIGRATION STRATEGY

### 6.1 Phase-by-Phase Migration

**Phase 1: Schema & Topic Creation** (Day 1, 1 hour)
1. Create new Avro schemas
2. Create Kafka topics:
   ```bash
   docker exec alpr-kafka kafka-topics --create --topic alpr.events.plates --partitions 3
   docker exec alpr-kafka kafka-topics --create --topic alpr.events.vehicles --partitions 3
   docker exec alpr-kafka kafka-topics --create --topic alpr.metrics --partitions 1
   docker exec alpr-kafka kafka-topics --create --topic alpr.dlq --partitions 1
   ```

**Phase 2: Deploy Multi-Topic Producer** (Day 2, 2 hours)
1. Implement MultiTopicAvroPublisher
2. Update pilot.py with `KAFKA_USE_MULTI_TOPIC=false` (default off)
3. Enable dual-publish mode (publish to both old and new topics)

**Phase 3: Deploy New Services** (Day 3, 2 hours)
1. Build and deploy DLQ consumer
2. Build and deploy Metrics consumer (optional)
3. Verify services healthy

**Phase 4: Migrate Storage Consumer** (Day 4, 3 hours)
1. Update code with DLQ support
2. Subscribe to both topics: `alpr.plates.detected,alpr.events.plates`
3. Monitor for 24 hours
4. Switch to new topic only

**Phase 5: Migrate Alert & ES Consumers** (Day 5, 3 hours)
1. Update Alert Engine
2. Update Elasticsearch Consumer
3. Monitor for 24 hours

**Phase 6: Cutover** (Day 7, 1 hour)
1. Disable dual-publishing
2. All consumers on new topics
3. Keep legacy topic for 7-day rollback window

**Phase 7: Cleanup** (Day 14)
1. Delete legacy topic `alpr.plates.detected`

### 6.2 Rollback Plan

**Immediate Rollback** (within 7 days):
1. Stop pilot.py
2. Set `KAFKA_USE_MULTI_TOPIC=false`
3. Restart pilot.py
4. Revert consumers to `KAFKA_TOPICS=alpr.plates.detected`
5. Restart all consumers

**Rollback Window**: 7 days (legacy topic retained with full data)

---

## 7. TESTING STRATEGY

### 7.1 Unit Tests

**Create**:
- `tests/test_multi_topic_publisher.py` - Topic routing logic
- `tests/test_dlq_handling.py` - Retry and DLQ logic
- `tests/test_metrics_publisher.py` - Metrics collection

### 7.2 Integration Tests

**Scenarios**:
1. End-to-end flow (producer → consumers)
2. DLQ routing on failures
3. Dual-topic consumption during migration
4. Timeout detection
5. Retry logic validation

### 7.3 Performance Tests

**Benchmarks**:
- Throughput: > 1000 events/sec
- Latency: < 1 second (p95)
- DLQ overhead: < 5 seconds for full retry cycle

---

## 8. MONITORING & ALERTING

### 8.1 New Prometheus Metrics

**Producer**:
- `alpr_multi_topic_events_published_total{topic}`
- `alpr_multi_topic_publish_errors_total{topic, error_type}`

**Consumers**:
- `alpr_consumer_dlq_messages_sent_total{consumer_group, error_type}`
- `alpr_consumer_retry_attempts_total{consumer_group}`
- `alpr_consumer_processing_timeout_total{consumer_group}`

**DLQ**:
- `alpr_dlq_messages_total{error_type, original_topic}`
- `alpr_dlq_oldest_message_age_seconds`

### 8.2 Grafana Dashboard

**New Dashboard**: "Multi-Topic Kafka Health"

**Panels**:
1. Topic message rate (per topic)
2. Consumer lag
3. DLQ activity and error type breakdown
4. Retry statistics
5. Processing latency (p50, p95, p99)

### 8.3 Prometheus Alerts

**Critical Alerts**:
- `HighDLQRate`: DLQ > 0.1 messages/sec for 5min
- `HighConsumerLag`: Lag > 1000 messages for 10min
- `SchemaValidationFailures`: Any schema validation errors
- `ProcessingTimeouts`: Timeout rate > 5% for 5min

---

## 9. DOCKER COMPOSE UPDATES

**Add to `docker-compose.yml`**:

```yaml
  # DLQ Consumer
  dlq-consumer:
    build:
      context: .
      dockerfile: core-services/dlq/Dockerfile
    container_name: alpr-dlq-consumer
    depends_on:
      - kafka
      - schema-registry
    ports:
      - "8005:8005"  # Prometheus metrics
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      KAFKA_TOPIC: alpr.dlq
      SCHEMA_REGISTRY_URL: http://schema-registry:8081
    networks:
      - alpr-network
    restart: unless-stopped

  # Metrics Consumer (Optional)
  metrics-consumer:
    build:
      context: .
      dockerfile: core-services/metrics/Dockerfile
    container_name: alpr-metrics-consumer
    depends_on:
      - kafka
      - schema-registry
    ports:
      - "8006:8006"  # Prometheus metrics
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      KAFKA_TOPIC: alpr.metrics
      SCHEMA_REGISTRY_URL: http://schema-registry:8081
    networks:
      - alpr-network
    restart: unless-stopped
```

**Update existing consumers**:
```yaml
kafka-consumer:
  environment:
    KAFKA_TOPICS: "alpr.events.plates"  # Update topic name
    MAX_RETRIES: "3"
    RETRY_DELAY_BASE: "2.0"

alert-engine:
  environment:
    KAFKA_TOPIC: "alpr.events.plates"

elasticsearch-consumer:
  environment:
    KAFKA_TOPIC: "alpr.events.plates"
```

---

## 10. CRITICAL FILES FOR IMPLEMENTATION

**Priority: HIGH**
1. `/home/jetson/OVR-ALPR/edge-services/event_processor/multi_topic_publisher.py` (NEW)
2. `/home/jetson/OVR-ALPR/schemas/vehicle_event.avsc` (NEW)
3. `/home/jetson/OVR-ALPR/schemas/metric_event.avsc` (NEW)
4. `/home/jetson/OVR-ALPR/schemas/dlq_message.avsc` (NEW)
5. `/home/jetson/OVR-ALPR/core-services/storage/avro_kafka_consumer.py` (MODIFY)
6. `/home/jetson/OVR-ALPR/core-services/dlq/dlq_consumer.py` (NEW)
7. `/home/jetson/OVR-ALPR/pilot.py` (MODIFY - lines 196-216)

**Priority: MEDIUM**
8. `/home/jetson/OVR-ALPR/docker-compose.yml` (MODIFY)
9. `/home/jetson/OVR-ALPR/core-services/alerting/alert_engine.py` (MODIFY)
10. `/home/jetson/OVR-ALPR/core-services/search/elasticsearch_consumer.py` (MODIFY)

**Priority: LOW (Optional)**
11. `/home/jetson/OVR-ALPR/core-services/metrics/metrics_consumer.py` (NEW)
12. `/home/jetson/OVR-ALPR/edge-services/event_processor/metrics_publisher.py` (NEW)

---

## 11. IMPLEMENTATION CHECKLIST

### Phase 1: Foundation
- [ ] Create Avro schemas (vehicle, metric, dlq)
- [ ] Register schemas with Schema Registry
- [ ] Create Kafka topics (alpr.events.plates, alpr.events.vehicles, alpr.metrics, alpr.dlq)
- [ ] Verify topics in Kafka UI

### Phase 2: Producer
- [ ] Implement MultiTopicAvroPublisher class
- [ ] Add topic routing logic
- [ ] Add dual-publish mode
- [ ] Update pilot.py integration
- [ ] Add KAFKA_USE_MULTI_TOPIC environment variable
- [ ] Write unit tests for publisher

### Phase 3: DLQ Infrastructure
- [ ] Add DLQ producer to storage consumer
- [ ] Add DLQ producer to alert engine
- [ ] Add DLQ producer to Elasticsearch consumer
- [ ] Implement DLQ consumer service
- [ ] Create DLQ Dockerfile
- [ ] Add DLQ service to docker-compose.yml

### Phase 4: Retry & Timeout
- [ ] Add retry logic to storage consumer (3 attempts, exponential backoff)
- [ ] Add timeout detection (30s max)
- [ ] Add retry logic to alert engine
- [ ] Add retry logic to Elasticsearch consumer
- [ ] Test retry scenarios

### Phase 5: Testing
- [ ] Write unit tests for MultiTopicAvroPublisher
- [ ] Write unit tests for DLQ handling
- [ ] Write integration tests (end-to-end flow)
- [ ] Write integration tests (DLQ routing)
- [ ] Perform load testing (> 1000 events/sec)
- [ ] Test failure scenarios

### Phase 6: Monitoring
- [ ] Add new Prometheus metrics
- [ ] Create Grafana dashboard (Multi-Topic Kafka Health)
- [ ] Add Prometheus alerts (DLQ, lag, timeouts)
- [ ] Test alert triggering

### Phase 7: Documentation
- [ ] Update event publishing documentation
- [ ] Create multi-topic architecture documentation
- [ ] Create DLQ handling guide
- [ ] Update README.md
- [ ] Update CLAUDE.md (new ports 8005, 8006)

### Phase 8: Migration
- [ ] Enable dual-publish mode
- [ ] Migrate storage consumer (subscribe to both topics)
- [ ] Migrate alert engine
- [ ] Migrate Elasticsearch consumer
- [ ] Monitor for 24 hours
- [ ] Disable dual-publish mode
- [ ] Deprecate legacy topic after 7 days

### Phase 9: Validation
- [ ] Verify message flow through new topics
- [ ] Verify no consumer lag
- [ ] Verify DLQ is empty (no errors)
- [ ] Performance benchmarking (compare to baseline)
- [ ] Stakeholder sign-off

---

## 12. SUCCESS CRITERIA

**Implementation is successful when**:

1. ✅ **Zero Message Loss**: All events published to new topics
2. ✅ **No Consumer Lag**: Lag < 100 messages across all consumers
3. ✅ **DLQ Rate < 0.1%**: < 1 in 1000 messages goes to DLQ
4. ✅ **Latency < 1s**: End-to-end latency < 1 second (p95)
5. ✅ **Uptime > 99.9%**: System uptime maintained during migration
6. ✅ **Rollback Capability**: Successful rollback test within 5 minutes
7. ✅ **Documentation Complete**: All docs updated and reviewed
8. ✅ **Tests Pass**: 100% unit test coverage, integration tests pass

---

## 13. RISK ASSESSMENT

| Risk | Probability | Impact | Mitigation |
|------|-------------|---------|------------|
| Schema incompatibility | Low | High | Pre-register schemas, validate with tests |
| Message loss during migration | Medium | Critical | Dual-publish mode, 7-day rollback window |
| Consumer lag spike | Medium | Medium | Monitor lag, scale consumers if needed |
| DLQ flooding | Low | Medium | Alert on high DLQ rate, investigate root cause |
| Performance degradation | Low | Medium | Benchmark before/after, optimize configs |

---

## 14. POST-IMPLEMENTATION

### 14.1 Immediate Actions
- Monitor DLQ topic for unexpected errors
- Review Grafana dashboards daily for 1 week
- Collect performance metrics
- Gather team feedback

### 14.2 Future Enhancements (Phase 4b)
- Implement TrackingEvent topic for debugging
- Add DLQ replay capability
- Multi-site Kafka replication
- Kafka Streams for real-time analytics
- Schema evolution testing

---

**End of Implementation Plan**
