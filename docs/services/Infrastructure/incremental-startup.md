# Incremental Service Startup Guide

**Purpose**: Development/testing workflow to start pilot.py first with minimal dependencies, then add services incrementally to test features while managing RAM usage.

> **Note**: This is a development/testing approach. Production deployments should start all services together with proper health checks and orchestration.

---

## 🎛️ NEW: Web Dashboard

A visual Service Manager dashboard is now available for controlling services:

**URL**: http://localhost:8000/services/dashboard

Features:
- Toggle switches for each service group
- Real-time memory usage monitoring
- Start/Stop/Restart buttons
- Dependency validation
- Auto-refresh status

**See**: [Service Manager Documentation](service-manager.md) for full API details.

---

## 🚀 Key Features

### Auto-Reconnection (NEW!)

pilot.py now includes **automatic reconnection** to backend services:

| Service | Auto-Reconnect | Reconnect Interval | Fallback Behavior |
|---------|---------------|-------------------|-------------------|
| **Kafka** | ✅ Yes | 30 seconds | MockKafkaPublisher (local logging) |
| **MinIO** | ✅ Yes | 30 seconds | Local file storage only |
| **Prometheus** | ⚠️ No | N/A | Metrics endpoint unavailable |

**Benefits**:
- ✅ Start pilot.py **before** any backend services
- ✅ No restart needed - pilot auto-connects when services become available
- ✅ Graceful degradation - full detection/OCR works offline
- ✅ Saves RAM - start with just pilot (~500 MB), add services incrementally

**How it works**:
1. Start pilot.py first → Runs with MockKafkaPublisher + local storage
2. Start Kafka → Pilot auto-connects within 30 seconds
3. Start MinIO → Pilot auto-connects within 30 seconds
4. No manual intervention needed!

**See**: [Auto-Reconnection Testing Guide](auto-reconnection-test.md) for detailed testing instructions.

---

## Startup Sequence

### Phase 0: Pilot Only (NEW - Recommended for Testing)

**Services**: None
**RAM Usage**: ~500 MB
**What Works**: Detection, tracking, OCR, local logging

```bash
# Start pilot WITHOUT any backend services
python3 pilot.py
```

**Expected output**:
```
⚠️  Kafka/Schema Registry not available, using mock publisher
⚠️  MinIO not available
✅ ALPR Pilot initialized successfully
```

**What you get**:
- ✅ Camera ingestion works
- ✅ Vehicle detection works
- ✅ Plate detection works
- ✅ OCR recognition works
- ✅ ByteTrack tracking works
- ✅ Events logged locally (CSV files in `output/`)
- ✅ Plate crops saved locally (`output/crops/`)
- ⚠️  Events logged with MockKafkaPublisher (not sent to Kafka)
- ❌ No Kafka publishing (yet)
- ❌ No MinIO uploads (yet)
- ❌ No database storage

**When to use**: Testing detection/OCR accuracy, debugging camera issues, RAM-constrained testing

---

### Phase 1: Add Kafka (Auto-Reconnect)

**Services**: Kafka ecosystem
**Additional RAM**: ~1-2 GB
**What Works**: Pilot auto-connects to Kafka, events published

```bash
# With pilot.py ALREADY RUNNING, start Kafka
docker compose up -d zookeeper kafka schema-registry

# Wait for services to be ready (30-60 seconds)
docker logs kafka --tail 50
```

**Expected behavior in pilot.py logs** (within 30 seconds):
```
🔄 Attempting to connect to Kafka...
✅ Connected to Kafka (multi-topic mode)
   Bootstrap: localhost:9092
   Schema Registry: http://localhost:8081
```

**What you get**:
- ✅ Pilot.py auto-connects to Kafka (no restart needed!)
- ✅ Events published to Kafka topics (alpr.events.plates, alpr.events.vehicles)
- ✅ All detection/OCR features continue working
- ❌ Events NOT stored in database (no consumer running)
- ❌ No search, alerts, or monitoring

**Verify**: Check Kafka topics:
```bash
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic alpr.events.plates \
  --from-beginning \
  --max-messages 5
```

---

### Phase 2: Add Storage & API (Database + Query + MinIO Auto-Reconnect)

**Additional Services**: TimescaleDB, MinIO, Kafka Consumer, Query API
**Additional RAM**: ~1.5 GB
**What Works**: Events stored, REST API queries, image storage

```bash
# With pilot.py still running, start storage services
docker compose up -d timescaledb minio kafka-consumer query-api

# Wait for DB initialization (30 seconds)
docker logs alpr-kafka-consumer -f
# Look for: "Subscribed to topics: alpr.events.plates, alpr.events.vehicles"
```

**Expected behavior in pilot.py logs** (within 30 seconds of MinIO starting):
```
🔄 Attempting to connect to MinIO...
✅ Connected to MinIO
   Endpoint: localhost:9000
   Bucket: alpr-plate-images
```

**What you get**:
- ✅ Events saved to TimescaleDB (queryable SQL database)
- ✅ Images auto-uploaded to MinIO (S3 object storage - no pilot restart!)
- ✅ REST API for querying events
- ✅ Historical data persistence
- ✅ Kafka consumer stores events from backlog (if any queued)
- ❌ No full-text search, alerts, or monitoring

**Verify**:
- Query API: http://localhost:8000/docs
- Check recent events: `curl http://localhost:8000/events/recent?limit=5`
- MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
- Check database:
  ```bash
  docker exec timescaledb psql -U alpr -d alpr_db -c \
    "SELECT COUNT(*) FROM plate_reads;"
  ```
- Check MinIO uploads:
  ```bash
  docker exec minio mc ls minio/alpr-plate-images/
  ```

---

### Phase 3: Add Search (OpenSearch)

**Additional Services**: OpenSearch, OpenSearch Dashboards, Elasticsearch Consumer
**Additional RAM**: ~1.5-2 GB
**What Works**: Full-text search, analytics, faceted queries

```bash
# Start OpenSearch stack
docker compose up -d opensearch opensearch-dashboards elasticsearch-consumer

# Wait for OpenSearch (60+ seconds, it's slow to start)
docker logs alpr-elasticsearch-consumer -f
# Look for: "Consumer started successfully"

# Verify search
curl http://localhost:8000/search/fulltext?query=ABC123
```

**What you get**:
- ✅ Full-text search on plate numbers, locations, colors
- ✅ Faceted search (group by camera, hour, day)
- ✅ Analytics aggregations (top plates, hourly trends)
- ✅ OpenSearch Dashboards for visualization
- ❌ No alerts or monitoring

**Verify**:
- Search API: http://localhost:8000/docs#/default/search_fulltext_search_fulltext_get
- OpenSearch health: `curl http://localhost:9200/_cluster/health`
- OpenSearch Dashboards: http://localhost:5601

---

### Phase 4: Add Alerts (Alert Engine)

**Additional Services**: Alert Engine
**Additional RAM**: ~300 MB
**What Works**: Real-time alerts via email/webhook/Slack

```bash
# Start alert engine
docker compose up -d alert-engine

# Configure alert rules first (if needed)
# Edit: config/alert_rules.yaml

# Restart to reload rules
docker restart alpr-alert-engine

# Check logs
docker logs alpr-alert-engine -f
```

**What you get**:
- ✅ Real-time alerts on suspicious plates
- ✅ Multi-channel notifications (email, webhook, Slack)
- ✅ Configurable alert rules
- ❌ No monitoring dashboards

**Verify**:
- Alert metrics: http://localhost:8003/metrics
- Check logs for triggered alerts
- Test with a plate in your watchlist

---

### Phase 5: Add Monitoring (Prometheus + Grafana)

**Additional Services**: Prometheus, Grafana, Loki, Promtail
**Additional RAM**: ~800 MB
**What Works**: Full observability, dashboards, log aggregation

```bash
# Start monitoring stack
docker compose up -d prometheus grafana loki promtail

# Access Grafana
# http://localhost:3000 (admin/admin)

# Import dashboards (if not auto-loaded)
# Dashboards are in: core_services/monitoring/grafana/dashboards/
```

**What you get**:
- ✅ Prometheus metrics collection from all services
- ✅ Grafana dashboards (system health, ALPR stats, Kafka metrics)
- ✅ Loki log aggregation
- ✅ Promtail log shipping
- ✅ Complete observability

**Verify**:
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Check dashboards:
  - ALPR System Overview
  - Service Status
  - Kafka Metrics

---

### Phase 6: Optional Services

**Kafka UI** (Kafka topic browser):
```bash
docker compose up -d kafka-ui
# Access: http://localhost:8080
```

**Metabase** (Advanced BI and Analytics):
```bash
docker compose up -d metabase
# Access: http://localhost:3001
```

**What you get**:
- ✅ Business intelligence dashboards
- ✅ Custom SQL queries and reports
- ✅ Executive-level analytics
- ✅ Scheduled email reports
- ✅ User-friendly drag-and-drop interface

**Setup required**:
1. Go to http://localhost:3001
2. Create admin account on first access
3. Connect to TimescaleDB (host: `timescaledb`, database: `alpr_db`)
4. Create dashboards and queries

**See**: [Metabase Setup Guide](metabase-setup.md) for detailed instructions

---

## Quick Reference

### Service Dependencies

```
pilot.py
  ↓ requires
Kafka + Schema Registry
  ↓ consumed by
Kafka Consumer → TimescaleDB
Elasticsearch Consumer → OpenSearch
Alert Engine → (notifications)
  ↓ monitored by
Prometheus → Grafana
```

### Port Reference
- 8000: Query API
- 8001: Pilot metrics
- 8002: Kafka Consumer metrics
- 8003: Alert Engine metrics
- 8004: Elasticsearch Consumer metrics
- 8080: Kafka UI
- 8081: Schema Registry
- 3000: Grafana
- 3001: Metabase
- 5601: OpenSearch Dashboards
- 9000: MinIO API
- 9001: MinIO Console
- 9090: Prometheus
- 9092: Kafka
- 9200: OpenSearch
- 5432: TimescaleDB

### RAM Usage Estimate
- Phase 0 (Pilot only): ~500 MB
- Phase 1 (+Kafka): ~2 GB total
- Phase 2 (+Storage): ~3.5 GB total
- Phase 3 (+Search): ~5.5 GB total
- Phase 4 (+Alerts): ~6 GB total
- Phase 5 (+Monitoring): ~7 GB total
- **All services**: ~7-8 GB total

**NEW**: You can now start with just 500 MB (pilot only) and add services as needed!

---

## Stopping Services

### Recommended: Stop pilot.py first
```bash
# Stop pilot.py
# Press Ctrl+C in pilot terminal
# This ensures graceful shutdown (flushes Kafka, waits for MinIO uploads)
```

### Then stop services in reverse order:
```bash
# Stop monitoring
docker compose stop grafana prometheus loki promtail

# Stop alerts
docker compose stop alert-engine

# Stop search
docker compose stop elasticsearch-consumer opensearch-dashboards opensearch

# Stop storage
docker compose stop query-api kafka-consumer minio timescaledb

# Stop Kafka (last)
docker compose stop schema-registry kafka zookeeper
```

### Or stop everything at once:
```bash
# Stop pilot first (Ctrl+C)
# Then stop all services
docker compose down
```

**Note**: With auto-reconnection, stopping services won't crash pilot.py. It will:
- Switch back to MockKafkaPublisher if Kafka stops
- Disable image uploads if MinIO stops
- Continue detection/tracking/OCR locally
- Auto-reconnect when services restart

---

## Testing Workflow Example

**NEW Recommended Workflow** (with auto-reconnection):

1. **Start pilot.py FIRST** → Verify detection/OCR works → Events logged locally
2. **Add Kafka** (no restart) → Pilot auto-connects → Events published to Kafka
3. **Add Storage** (no restart) → Pilot auto-connects to MinIO → Events saved → Images uploaded
4. **Add Search** → Test full-text search → Verify analytics
5. **Add Alerts** → Configure rules → Test notifications
6. **Add Monitoring** → View Grafana dashboards → Check metrics

**OLD Workflow** (pre-auto-reconnection, still works):
1. **Start Kafka** → Run pilot.py → Verify detection works
2. **Add Storage** → Restart pilot → Check events saved → Test API queries
3. **Add Search** → Test full-text search → Verify analytics
4. **Add Alerts** → Configure rules → Test notifications
5. **Add Monitoring** → View Grafana dashboards → Check metrics

This approach lets you:
- Test each feature independently
- Debug issues in isolation
- Manage RAM on resource-constrained devices
- Understand system architecture incrementally
- **NEW**: No restarts needed when adding Kafka/MinIO!

---

## Production Notes

**This incremental startup approach is for development/testing only**.

Production systems should:
- Start all services together via orchestration (Kubernetes, Docker Swarm)
- Use health checks and readiness probes
- Implement proper service dependencies (init containers, depends_on with health checks)
- Have automatic restart policies
- Use external monitoring and alerting
- **Consider increasing reconnection intervals** to reduce log noise:
  ```python
  # In pilot.py for production:
  self.kafka_reconnect_interval = 60  # 1 minute instead of 30 seconds
  self.minio_reconnect_interval = 60
  ```

**Auto-reconnection benefits for production**:
- ✅ Graceful handling of temporary network issues
- ✅ Resilient to service restarts (updates, maintenance)
- ✅ No manual intervention needed for reconnection
- ⚠️  Monitor connection state via Prometheus metrics

**For more details on auto-reconnection**:
- See [Auto-Reconnection Testing Guide](auto-reconnection-test.md)
