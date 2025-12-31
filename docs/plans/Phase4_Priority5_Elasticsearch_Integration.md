# Phase 4 Priority 5: Elasticsearch Integration - Implementation Plan

## Executive Summary

**Goal:** Integrate OpenSearch (Elasticsearch-compatible) into the ALPR system for advanced full-text search, real-time analytics, and faceted queries on plate detection events.

**Technology Choice:** OpenSearch 2.11.0 (Apache 2.0 license, fully open-source)

**Estimated Effort:** 2 weeks (10 working days)

**Key Benefits:**
- Full-text search on plate numbers with fuzzy matching
- Real-time analytics and aggregations
- Faceted search for building drill-down UIs
- Advanced query capabilities beyond SQL
- Horizontal scaling for future growth

---

## Architecture Overview

```
Kafka Topic: alpr.plates.detected (Avro)
  │
  ├──> TimescaleDB Consumer (existing - historical queries)
  ├──> Alert Engine (existing - notifications)
  └──> NEW: Elasticsearch Consumer
           │
           └──> OpenSearch Cluster
                 │
                 ├──> Index: alpr-events-YYYY.MM
                 ├──> 90-day retention
                 └──> Monthly rollover

Query API (FastAPI)
  │
  ├──> /events/* (existing - TimescaleDB)
  └──> NEW: /search/* (OpenSearch)
           ├──> /search/fulltext - Full-text search
           ├──> /search/facets - Faceted search
           ├──> /search/analytics - Aggregations
           └──> /search/query - Advanced DSL
```

---

## 1. Docker Infrastructure

### Add to `/home/jetson/OVR-ALPR/docker-compose.yml`

**OpenSearch Service:**
```yaml
opensearch:
  image: opensearchproject/opensearch:2.11.0
  container_name: alpr-opensearch
  environment:
    discovery.type: single-node
    DISABLE_SECURITY_PLUGIN: "true"
    OPENSEARCH_JAVA_OPTS: "-Xms512m -Xmx1g"  # Critical for Jetson
    plugins.security.disabled: "true"
    bootstrap.memory_lock: "false"
  ports:
    - "9200:9200"
    - "9600:9600"
  volumes:
    - opensearch-data:/usr/share/opensearch/data
  networks:
    - alpr-network
  restart: unless-stopped
  healthcheck:
    test: ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health || exit 1"]
    interval: 30s
    timeout: 10s
    retries: 5
    start_period: 60s
```

**OpenSearch Dashboards (Optional):**
```yaml
opensearch-dashboards:
  image: opensearchproject/opensearch-dashboards:2.11.0
  container_name: alpr-opensearch-dashboards
  depends_on:
    opensearch:
      condition: service_healthy
  ports:
    - "5601:5601"
  environment:
    OPENSEARCH_HOSTS: '["http://opensearch:9200"]'
    DISABLE_SECURITY_DASHBOARDS_PLUGIN: "true"
  networks:
    - alpr-network
  restart: unless-stopped
  profiles:
    - analytics  # Only start with: docker compose --profile analytics up
```

**Elasticsearch Consumer Service:**
```yaml
elasticsearch-consumer:
  build:
    context: .
    dockerfile: core-services/search/Dockerfile
  container_name: alpr-elasticsearch-consumer
  depends_on:
    kafka:
      condition: service_healthy
    schema-registry:
      condition: service_healthy
    opensearch:
      condition: service_healthy
  ports:
    - "8004:8004"  # Prometheus metrics
  environment:
    KAFKA_BOOTSTRAP_SERVERS: kafka:29092
    KAFKA_TOPIC: alpr.plates.detected
    KAFKA_GROUP_ID: alpr-elasticsearch-consumer
    SCHEMA_REGISTRY_URL: http://schema-registry:8081
    OPENSEARCH_HOSTS: http://opensearch:9200
    OPENSEARCH_INDEX_PREFIX: alpr-events
    OPENSEARCH_BULK_SIZE: "50"
    OPENSEARCH_FLUSH_INTERVAL: "5"
    AUTO_OFFSET_RESET: latest
  volumes:
    - ./logs:/app/logs
  networks:
    - alpr-network
  restart: unless-stopped
```

**Add Volume:**
```yaml
volumes:
  opensearch-data:
    driver: local
```

---

## 2. Index Design

### Strategy: Monthly Time-Based Indices

**Pattern:** `alpr-events-YYYY.MM` (e.g., `alpr-events-2025.01`)

**Benefits:**
- Easy retention management (delete old months)
- Better query performance (smaller indices)
- Aligns with 90-day retention (3 indices max)

### Index Template

**File:** `core-services/search/opensearch/templates/alpr-events-template.json`

```json
{
  "index_patterns": ["alpr-events-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0,
      "refresh_interval": "5s",
      "codec": "best_compression"
    },
    "mappings": {
      "properties": {
        "event_id": {"type": "keyword"},
        "captured_at": {"type": "date"},
        "camera_id": {"type": "keyword"},
        "track_id": {"type": "keyword"},
        "plate": {
          "properties": {
            "text": {
              "type": "text",
              "fields": {"keyword": {"type": "keyword"}}
            },
            "normalized_text": {"type": "keyword"},
            "confidence": {"type": "float"},
            "region": {"type": "keyword"}
          }
        },
        "vehicle": {
          "properties": {
            "type": {"type": "keyword"},
            "make": {"type": "keyword"},
            "model": {"type": "keyword"},
            "color": {"type": "keyword"}
          }
        },
        "images": {
          "properties": {
            "plate_url": {"type": "keyword", "index": false},
            "vehicle_url": {"type": "keyword", "index": false},
            "frame_url": {"type": "keyword", "index": false}
          }
        },
        "latency_ms": {"type": "integer"},
        "node": {
          "properties": {
            "site": {"type": "keyword"},
            "host": {"type": "keyword"}
          }
        },
        "extras": {
          "properties": {
            "roi": {"type": "keyword"},
            "direction": {"type": "keyword"},
            "quality_score": {"type": "float"},
            "frame_number": {"type": "long"}
          }
        },
        "indexed_at": {"type": "date"}
      }
    }
  }
}
```

### Field Type Decisions

| Field | Type | Rationale |
|-------|------|-----------|
| `plate.text` | text + keyword | Full-text search + exact match |
| `plate.normalized_text` | keyword | Exact match only |
| `camera_id` | keyword | Filtering/aggregations |
| `vehicle.type` | keyword | Categorical faceting |
| `captured_at` | date | Time-series queries |
| `images.*` | keyword (not indexed) | Storage only, no search |

---

## 3. ElasticsearchConsumer Service

### Directory Structure

```
core-services/search/
├── Dockerfile
├── requirements.txt
├── elasticsearch_consumer.py  # Main consumer
├── bulk_indexer.py           # Bulk API handler
├── opensearch_client.py      # OpenSearch wrapper
├── index_manager.py          # Index lifecycle
├── opensearch/
│   ├── templates/
│   │   └── alpr-events-template.json
│   └── policies/
│       └── alpr-retention-policy.json
└── config/
    └── elasticsearch.yaml
```

### Service Architecture

**Pattern:** Follows existing `avro_kafka_consumer.py` and `alert_engine.py`

**Key Components:**
- Avro deserialization with Schema Registry
- Bulk indexing with adaptive batching (50 docs or 5 seconds)
- Prometheus metrics on port 8004
- Graceful shutdown with signal handlers
- Error handling with retry logic

### Dockerfile

**File:** `core-services/search/Dockerfile`

```dockerfile
FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y gcc libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY core-services/search/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY core-services/search/ /app/services/search/
COPY schemas/ /app/schemas/

RUN mkdir -p /app/logs

ENV PYTHONPATH=/app/services/search

EXPOSE 8004

CMD ["python", "-u", "/app/services/search/elasticsearch_consumer.py"]
```

### Requirements

**File:** `core-services/search/requirements.txt`

```
opensearch-py>=2.4.0
confluent-kafka[avro]>=2.12.0
prometheus-client>=0.19.0
loguru>=0.7.2
pyyaml>=6.0.1
```

### Bulk Indexing Strategy

**Adaptive Batching:**
- **Size trigger:** Flush when 50 documents accumulated
- **Time trigger:** Flush every 5 seconds
- **Whichever comes first**

**Error Handling:**
1. **Transient errors** (network, timeout): Retry with exponential backoff (3 attempts)
2. **Mapping errors**: Log and skip (or send to DLQ)
3. **Partial failures**: Retry only failed documents from bulk response

### Prometheus Metrics (Port 8004)

```
# Consumption
elasticsearch_consumer_messages_consumed_total
elasticsearch_consumer_messages_indexed_total
elasticsearch_consumer_messages_failed_total

# Bulk performance
elasticsearch_consumer_bulk_requests_total
elasticsearch_consumer_bulk_size_documents (histogram)
elasticsearch_consumer_bulk_duration_seconds (histogram)

# OpenSearch health
elasticsearch_consumer_opensearch_available (gauge)
```

---

## 4. Query API Extensions

### New Endpoints

Add to `core-services/api/query_api.py`:

1. **`GET /search/fulltext`** - Full-text search with fuzzy matching
   - Parameters: `q` (query), `start_time`, `end_time`, `camera_id`, `limit`, `offset`
   - Returns: Matching events with total count and search time

2. **`GET /search/facets`** - Faceted search with drill-down
   - Parameters: `camera_id`, `vehicle_type`, `vehicle_color`, `limit`
   - Returns: Events + aggregations (cameras, vehicle types, colors, sites)

3. **`GET /search/analytics`** - Aggregations for dashboards
   - Parameters: `metric` (plates_per_hour, avg_confidence, top_plates), `interval`, `start_time`, `end_time`
   - Returns: Time-series data or rankings

4. **`POST /search/query`** - Advanced DSL queries
   - Body: OpenSearch query DSL
   - Returns: Raw OpenSearch response

### Implementation Pattern

**Add to startup:**
```python
from opensearchpy import AsyncOpenSearch

opensearch_client: Optional[AsyncOpenSearch] = None

@app.on_event("startup")
async def startup_event():
    global opensearch_client

    # ... existing code ...

    # Initialize OpenSearch client
    opensearch_host = os.getenv("OPENSEARCH_HOSTS", "http://opensearch:9200")
    try:
        opensearch_client = AsyncOpenSearch(
            hosts=[opensearch_host],
            use_ssl=False,
            verify_certs=False,
            timeout=30
        )
        info = await opensearch_client.info()
        logger.success(f"✅ Connected to OpenSearch: {info['version']['number']}")
    except Exception as e:
        logger.warning(f"⚠️  OpenSearch not available: {e}")
        opensearch_client = None
```

**Example endpoint:**
```python
@app.get("/search/fulltext")
async def fulltext_search(
    q: str = Query(..., description="Search query"),
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    camera_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    if not opensearch_client:
        raise HTTPException(status_code=503, detail="Search service unavailable")

    # Build query with filters
    query = {
        "bool": {
            "must": [{
                "multi_match": {
                    "query": q,
                    "fields": ["plate.text", "plate.normalized_text", "vehicle.make"],
                    "fuzziness": "AUTO"
                }
            }],
            "filter": []
        }
    }

    # Add time range filter
    if start_time or end_time:
        time_filter = {"range": {"captured_at": {}}}
        if start_time:
            time_filter["range"]["captured_at"]["gte"] = start_time
        if end_time:
            time_filter["range"]["captured_at"]["lte"] = end_time
        query["bool"]["filter"].append(time_filter)

    # Add camera filter
    if camera_id:
        query["bool"]["filter"].append({"term": {"camera_id": camera_id}})

    # Execute search
    results = await opensearch_client.search(
        index="alpr-events-*",
        body={
            "query": query,
            "from": offset,
            "size": limit,
            "sort": [{"captured_at": "desc"}]
        }
    )

    return {
        "total": results["hits"]["total"]["value"],
        "results": [hit["_source"] for hit in results["hits"]["hits"]],
        "took_ms": results["took"]
    }
```

---

## 5. Configuration

### Config File

**File:** `config/elasticsearch.yaml`

```yaml
opensearch:
  hosts:
    - "http://localhost:9200"
  use_ssl: false
  verify_certs: false

  index:
    prefix: "alpr-events"
    rollover_age: "30d"
    retention_days: 90
    shards: 1
    replicas: 0
    refresh_interval: "5s"
    codec: "best_compression"

  bulk:
    size: 50
    flush_interval: 5
    max_retries: 3

kafka:
  bootstrap_servers: "localhost:9092"
  topic: "alpr.plates.detected"
  group_id: "alpr-elasticsearch-consumer"
  schema_registry:
    url: "http://localhost:8081"
```

---

## 6. Monitoring & Observability

### Prometheus Integration

**Add to:** `core-services/monitoring/prometheus/prometheus.yml`

```yaml
scrape_configs:
  - job_name: 'elasticsearch-consumer'
    static_configs:
      - targets: ['elasticsearch-consumer:8004']
    metrics_path: '/metrics'
    scrape_interval: 10s
```

### Grafana Dashboard

**Create:** `core-services/monitoring/grafana/dashboards/elasticsearch-search.json`

**Panels:**
1. **Indexing Rate:** `rate(elasticsearch_consumer_messages_indexed_total[1m])`
2. **Bulk Duration (p95):** `histogram_quantile(0.95, rate(elasticsearch_consumer_bulk_duration_seconds_bucket[5m]))`
3. **Consumer Lag:** `elasticsearch_consumer_lag_seconds`
4. **Error Rate:** `rate(elasticsearch_consumer_messages_failed_total[5m])`
5. **OpenSearch Cluster Health**
6. **Search Query Latency**

---

## 7. Implementation Phases

### Phase 1: Infrastructure (Days 1-2)

**Tasks:**
- [ ] Add OpenSearch, OpenSearch Dashboards, elasticsearch-consumer to docker-compose.yml
- [ ] Add opensearch-data volume
- [ ] Start services: `docker compose up -d opensearch`
- [ ] Verify health: `curl http://localhost:9200/_cluster/health`
- [ ] Create index template using curl or Python script
- [ ] Test manual document indexing

**Critical Files:**
- `docker-compose.yml`
- `core-services/search/opensearch/templates/alpr-events-template.json`

---

### Phase 2: Consumer Development (Days 3-5)

**Tasks:**
- [ ] Create directory structure: `core-services/search/`
- [ ] Implement `elasticsearch_consumer.py` (follow `avro_kafka_consumer.py` pattern)
- [ ] Implement `bulk_indexer.py` (adaptive batching logic)
- [ ] Implement `opensearch_client.py` (connection wrapper)
- [ ] Implement `index_manager.py` (monthly index creation)
- [ ] Create `Dockerfile` and `requirements.txt`
- [ ] Write unit tests for bulk batching and Avro deserialization
- [ ] Test locally with sample Kafka messages

**Critical Files:**
- `core-services/search/elasticsearch_consumer.py`
- `core-services/search/bulk_indexer.py`
- `core-services/search/Dockerfile`
- `core-services/search/requirements.txt`

**References:**
- `/home/jetson/OVR-ALPR/core-services/storage/avro_kafka_consumer.py` (Avro pattern)
- `/home/jetson/OVR-ALPR/core-services/alerting/alert_engine.py` (consumer pattern)

---

### Phase 3: Docker Integration (Days 6-7)

**Tasks:**
- [ ] Build elasticsearch-consumer Docker image
- [ ] Start service: `docker compose up -d elasticsearch-consumer`
- [ ] Monitor logs: `docker logs -f alpr-elasticsearch-consumer`
- [ ] Verify events flow: Kafka → Consumer → OpenSearch
- [ ] Check OpenSearch indices: `curl http://localhost:9200/_cat/indices?v`
- [ ] Query sample documents from OpenSearch
- [ ] Create `config/elasticsearch.yaml`
- [ ] Run integration tests

**Validation:**
- Consumer service healthy and processing messages
- Events indexed to OpenSearch with correct mappings
- Prometheus metrics updating at port 8004
- No errors in logs

---

### Phase 4: Query API Extensions (Days 8-9)

**Tasks:**
- [ ] Add `opensearch-py` to Query API requirements
- [ ] Update Query API Dockerfile
- [ ] Add OpenSearch client initialization to `startup_event`
- [ ] Implement `/search/fulltext` endpoint
- [ ] Implement `/search/facets` endpoint
- [ ] Implement `/search/analytics` endpoint
- [ ] Implement `/search/query` endpoint
- [ ] Test all endpoints using FastAPI docs (http://localhost:8000/docs)
- [ ] Rebuild and restart Query API container

**Critical Files:**
- `core-services/api/query_api.py`
- `core-services/api/requirements.txt`
- `core-services/api/Dockerfile`

**Example Test:**
```bash
# Full-text search
curl "http://localhost:8000/search/fulltext?q=ABC123"

# Faceted search
curl "http://localhost:8000/search/facets?camera_id=cam1"

# Analytics
curl "http://localhost:8000/search/analytics?metric=plates_per_hour&interval=1h"
```

---

### Phase 5: Monitoring & Documentation (Day 10)

**Tasks:**
- [ ] Add Prometheus scrape job for elasticsearch-consumer
- [ ] Restart Prometheus
- [ ] Create Grafana dashboard: `elasticsearch-search.json`
- [ ] Import dashboard to Grafana
- [ ] Verify Loki log collection for new service
- [ ] Run performance benchmarks
- [ ] Update documentation in `docs/ALPR_Pipeline/`
- [ ] Update `CLAUDE.md` with new ports and services

**Critical Files:**
- `core-services/monitoring/prometheus/prometheus.yml`
- `core-services/monitoring/grafana/dashboards/elasticsearch-search.json`
- `docs/ALPR_Pipeline/Elasticsearch_Integration.md` (new)
- `CLAUDE.md`

**Performance Targets:**
- Indexing throughput: > 100 events/sec
- Search latency (p95): < 100ms
- Bulk duration (p95): < 500ms
- Memory usage: < 1.5GB (OpenSearch)

---

## 8. Key Decisions & Trade-offs

### Decision 1: OpenSearch vs Elasticsearch

**Choice:** OpenSearch

**Rationale:**
- Apache 2.0 license (no restrictions)
- Elasticsearch-compatible API
- Better AWS integration for future cloud deployment
- No licensing costs

---

### Decision 2: Real-time vs Batch Indexing

**Choice:** Near-real-time (5-second batches)

**Rationale:**
- Bulk indexing is 10-100x more efficient
- 5-second delay acceptable for search use case
- Balances throughput with freshness

---

### Decision 3: Single vs Time-based Indices

**Choice:** Monthly time-based indices

**Rationale:**
- Easy retention (delete whole index)
- Better query performance (smaller indices)
- Aligns with 90-day retention (3 indices max)

---

### Decision 4: Resource Allocation for Jetson

**Choice:** 1GB JVM heap max

**Rationale:**
- Jetson Orin NX has limited RAM
- Single-node cluster (no replication overhead)
- Disable security/ML plugins to reduce footprint

---

## 9. Testing Strategy

### Unit Tests

**File:** `tests/test_elasticsearch_consumer.py`

```python
def test_bulk_batching():
    """Test bulk indexer batches documents correctly"""
    indexer = BulkIndexer(batch_size=50, flush_interval=5)

    # Add 49 documents (should not flush)
    for i in range(49):
        indexer.add(create_test_event(f"PLATE{i}"))
    assert indexer.pending_count() == 49

    # Add 1 more (should flush at 50)
    indexer.add(create_test_event("PLATE50"))
    assert indexer.pending_count() == 0

def test_avro_deserialization():
    """Test PlateEvent Avro deserialization"""
    consumer = ElasticsearchConsumer(...)
    mock_msg = create_mock_avro_message()
    event = consumer._deserialize(mock_msg)

    assert event["event_id"] is not None
    assert event["plate"]["normalized_text"] == "ABC123"
```

### Integration Tests

```python
@pytest.mark.integration
def test_end_to_end_indexing():
    """Test: Kafka → Consumer → OpenSearch → Query API"""

    # 1. Publish test event to Kafka
    producer = create_avro_producer()
    test_event = create_test_plate_event(plate_text="TEST123")
    producer.produce(topic="alpr.plates.detected", value=test_event)
    producer.flush()

    # 2. Wait for indexing
    wait_for_document(event_id=test_event["event_id"], timeout=30)

    # 3. Verify in OpenSearch
    client = OpenSearch(["http://localhost:9200"])
    result = client.get(index="alpr-events-*", id=test_event["event_id"])
    assert result["_source"]["plate"]["normalized_text"] == "TEST123"

    # 4. Verify via Query API
    response = requests.get("http://localhost:8000/search/fulltext?q=TEST123")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
```

---

## 10. Rollback Plan

### Disable Search Only (Partial)

```bash
# Stop search services
docker compose stop elasticsearch-consumer opensearch opensearch-dashboards

# Remove containers
docker compose rm -f elasticsearch-consumer opensearch opensearch-dashboards

# System continues with TimescaleDB queries
```

### Full Rollback

```bash
# Stop all services
docker compose down

# Revert changes
git checkout HEAD -- docker-compose.yml
git checkout HEAD -- core-services/api/query_api.py
git checkout HEAD -- core-services/monitoring/prometheus/prometheus.yml

# Remove new files
rm -rf core-services/search
rm -rf config/elasticsearch.yaml

# Restart
docker compose up -d
```

---

## Critical Files Reference

| File | Purpose | Pattern |
|------|---------|---------|
| `docker-compose.yml` | Add OpenSearch services | Follow kafka-consumer pattern |
| `core-services/search/elasticsearch_consumer.py` | Main consumer | Follow `avro_kafka_consumer.py` |
| `core-services/search/Dockerfile` | Container image | Follow `alerting/Dockerfile` |
| `core-services/api/query_api.py` | Add search endpoints | Extend existing FastAPI |
| `core-services/monitoring/prometheus/prometheus.yml` | Add scrape job | Follow existing jobs |
| `config/elasticsearch.yaml` | Configuration | Follow `kafka.yaml` pattern |

---

## Success Criteria

- [ ] OpenSearch cluster running and healthy
- [ ] Events indexed in real-time (< 10 second latency)
- [ ] Full-text search working with fuzzy matching
- [ ] Faceted search returns aggregations
- [ ] Analytics endpoints return time-series data
- [ ] Prometheus metrics exposed and scraped
- [ ] Grafana dashboard shows indexing/search metrics
- [ ] Performance targets met (100 events/sec, < 100ms search)
- [ ] Documentation complete
- [ ] Integration tests passing

---

## Next Steps After Implementation

**Phase 4 Priority 6:** Multi-Topic Kafka
- Separate topics for events, metrics, alerts, DLQ
- Better organization and consumer isolation

**Phase 4 Priority 7:** Advanced BI
- Apache Superset or Metabase
- Pre-built dashboards and reports
- Executive-level analytics
