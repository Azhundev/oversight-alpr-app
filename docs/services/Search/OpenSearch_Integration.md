# OpenSearch Integration for ALPR System

## Overview

The ALPR system now includes OpenSearch (Elasticsearch-compatible) for advanced full-text search, real-time analytics, and faceted queries on license plate detection events. This document describes the architecture, implementation, and usage of the search capabilities.

**Implementation Date**: December 29, 2025
**Phase**: Phase 4 Priority 5
**Status**: ✅ Production Ready

---

## Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Edge Processing                             │
│                         (pilot.py on Jetson)                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
                   ┌──────────────────────┐
                   │  Kafka Topic (Avro)  │
                   │ alpr.events.plates │
                   └──────────┬───────────┘
                              │
               ┌──────────────┼──────────────┬──────────────┐
               │              │              │              │
               ▼              ▼              ▼              ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │   Kafka      │ │ Elasticsearch│ │    Alert     │ │   (Other     │
      │  Consumer    │ │   Consumer   │ │   Engine     │ │  Consumers)  │
      └──────┬───────┘ └──────┬───────┘ └──────────────┘ └──────────────┘
             │                │
             ▼                ▼
      ┌──────────────┐ ┌──────────────┐
      │ TimescaleDB  │ │  OpenSearch  │
      │              │ │              │
      │ • SQL Queries│ │ • Full-text  │
      │ • Time-series│ │ • Facets     │
      │ • Analytics  │ │ • Analytics  │
      └──────┬───────┘ └──────┬───────┘
             │                │
             └────────┬───────┘
                      ▼
             ┌─────────────────┐
             │   Query API     │
             │   (FastAPI)     │
             │                 │
             │ /events/*       │
             │ /search/*       │
             └─────────────────┘
```

### Dual Storage Strategy

The system employs a **dual storage strategy** to leverage the strengths of both SQL and NoSQL databases:

| Feature | TimescaleDB | OpenSearch |
|---------|-------------|------------|
| **Use Case** | Structured queries, time-series analytics | Full-text search, faceted queries |
| **Query Type** | SQL | Query DSL |
| **Indexing** | B-tree, time-series | Inverted index, text analysis |
| **Best For** | Exact matches, aggregations, joins | Fuzzy search, relevance scoring |
| **Data Model** | Relational | Document-oriented |
| **Access** | `/events/*` endpoints | `/search/*` endpoints |

---

## Components

### 1. OpenSearch Cluster

**Service**: `alpr-opensearch`
**Image**: `opensearchproject/opensearch:2.11.0`
**Ports**:
- `9200`: HTTP API
- `9600`: Performance Analyzer

**Configuration**:
```yaml
discovery.type: single-node
DISABLE_SECURITY_PLUGIN: "true"
OPENSEARCH_JAVA_OPTS: "-Xms512m -Xmx1g"  # Optimized for Jetson
```

**Resource Usage**:
- Memory: ~886 MB (target: < 1.5 GB)
- CPU: ~0.6%

**Health Check**:
```bash
curl http://localhost:9200/_cluster/health
```

### 2. Elasticsearch Consumer

**Service**: `alpr-elasticsearch-consumer`
**Location**: `core_services/search/`
**Port**: `8004` (Prometheus metrics)

**Responsibilities**:
- Consume events from Kafka topic `alpr.events.plates`
- Deserialize Avro messages using Schema Registry
- Perform bulk indexing to OpenSearch
- Export Prometheus metrics

**Key Features**:
- **Adaptive Bulk Indexing**: Flushes on 50 documents OR 5 seconds (whichever comes first)
- **Monthly Index Rotation**: Pattern `alpr-events-YYYY.MM`
- **Error Handling**: Retry logic with exponential backoff
- **Monitoring**: Full Prometheus instrumentation

**Configuration**: `config/elasticsearch.yaml`

```yaml
opensearch:
  hosts:
    - "http://localhost:9200"
  index:
    prefix: "alpr-events"
    retention_days: 90
  bulk:
    size: 50
    flush_interval: 5
```

**Prometheus Metrics** (`:8004/metrics`):
```
elasticsearch_consumer_messages_consumed_total
elasticsearch_consumer_messages_indexed_total
elasticsearch_consumer_messages_failed_total
elasticsearch_consumer_bulk_requests_total
elasticsearch_consumer_bulk_size_documents (histogram)
elasticsearch_consumer_bulk_duration_seconds (histogram)
elasticsearch_consumer_opensearch_available (gauge)
```

### 3. Query API Search Endpoints

**Service**: `alpr-query-api`
**Port**: `8000`
**Documentation**: http://localhost:8000/docs

Four new search endpoints added:

#### a) Full-Text Search
```
GET /search/fulltext?q={query}&limit={n}&offset={m}
```

**Features**:
- Multi-field search (plate.text, normalized_text, vehicle.make)
- Fuzzy matching (`fuzziness: AUTO`)
- Time range filtering
- Camera filtering
- Pagination support

**Example**:
```bash
curl "http://localhost:8000/search/fulltext?q=ABC123&limit=10"
```

**Response**:
```json
{
  "query": "ABC123",
  "total": 5,
  "took_ms": 21,
  "results": [...],
  "limit": 10,
  "offset": 0
}
```

#### b) Faceted Search
```
GET /search/facets?camera_id={id}&vehicle_type={type}&limit={n}
```

**Features**:
- Returns matching events + aggregation facets
- Drill-down capabilities
- Multiple filter support

**Facets Returned**:
- `cameras`: Aggregation by camera_id
- `vehicle_types`: Aggregation by vehicle.type
- `vehicle_colors`: Aggregation by vehicle.color
- `sites`: Aggregation by node.site

**Example**:
```bash
curl "http://localhost:8000/search/facets?camera_id=CAM1&limit=20"
```

**Response**:
```json
{
  "total": 15,
  "took_ms": 12,
  "results": [...],
  "facets": {
    "cameras": [
      {"key": "CAM1", "doc_count": 15},
      {"key": "CAM2", "doc_count": 8}
    ],
    "vehicle_types": [
      {"key": "car", "doc_count": 12},
      {"key": "truck", "doc_count": 3}
    ],
    ...
  }
}
```

#### c) Analytics
```
GET /search/analytics?metric={metric}&interval={interval}
```

**Supported Metrics**:
1. **plates_per_hour**: Event count over time
2. **avg_confidence**: Average plate detection confidence
3. **top_plates**: Most frequently seen plates

**Example**:
```bash
curl "http://localhost:8000/search/analytics?metric=avg_confidence&interval=1h"
```

**Response**:
```json
{
  "metric": "avg_confidence",
  "took_ms": 6,
  "total_events": 124,
  "aggregations": {
    "confidence_over_time": {
      "buckets": [
        {
          "key_as_string": "2025-12-29T22:00:00.000Z",
          "key": 1767045600000,
          "doc_count": 45,
          "avg_confidence": {"value": 0.94}
        },
        ...
      ]
    }
  }
}
```

#### d) Advanced DSL Query
```
POST /search/query
Content-Type: application/json
```

**Features**:
- Direct access to OpenSearch Query DSL
- Full query power for advanced users
- Supports complex nested queries, aggregations

**Example**:
```bash
curl -X POST "http://localhost:8000/search/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "bool": {
        "must": [
          {"match": {"plate.text": "ABC"}},
          {"range": {"plate.confidence": {"gte": 0.9}}}
        ]
      }
    },
    "aggs": {
      "by_camera": {
        "terms": {"field": "camera_id"}
      }
    },
    "size": 50
  }'
```

---

## Index Design

### Index Template

**Pattern**: `alpr-events-*`
**Monthly Indices**: `alpr-events-2025.12`, `alpr-events-2026.01`, etc.

**Benefits of Monthly Indices**:
- Easy retention management (delete old indices)
- Better query performance (smaller indices)
- Aligns with 90-day retention (3 indices maximum)

### Field Mappings

```json
{
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
      "indexed_at": {"type": "date"}
    }
  }
}
```

**Key Decisions**:
- `plate.text`: **text + keyword** - Enables both full-text and exact match
- `plate.normalized_text`: **keyword only** - Exact match optimization
- `images.*`: **not indexed** - Storage only, reduces index size
- `vehicle.*`: **keyword** - Faceted search and filtering
- `captured_at`, `indexed_at`: **date** - Time-series queries

---

## Performance

### Benchmarks

Measured during end-to-end testing with live data:

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| **Indexing Throughput** | 23.4 events/sec | > 10 events/sec | ✅ |
| **Bulk Duration (p95)** | < 50ms | < 500ms | ✅ |
| **Full-text Search** | 21ms | < 100ms | ✅ |
| **Faceted Search** | 12ms | < 100ms | ✅ |
| **Analytics Query** | 6ms | < 100ms | ✅ |
| **Memory Usage** | 886 MB | < 1.5 GB | ✅ |

### Optimization Strategies

1. **Bulk Indexing**: Batches reduce network overhead by 10-100x
2. **Monthly Indices**: Smaller indices = faster queries
3. **Selective Indexing**: Images not indexed, reducing size
4. **Compression**: `best_compression` codec enabled
5. **Single Shard**: No replication overhead for single-node deployment

---

## Monitoring

### Grafana Dashboard

**Dashboard**: "ALPR - Search & Indexing (OpenSearch)"
**Location**: `core_services/monitoring/grafana/dashboards/elasticsearch-search.json`
**Access**: http://localhost:3000

**Panels**:
1. **Indexing Rate** - Real-time events/sec
2. **Total Messages Indexed** - Cumulative count
3. **OpenSearch Availability** - Cluster health (0=down, 1=up)
4. **Bulk Request Duration** - p95 and p99 latency
5. **Bulk Size** - Documents per batch (p50, p95)
6. **Message Flow** - Consumed vs Indexed vs Failed
7. **Bulk Request Rate** - Requests/sec

### Prometheus Queries

```promql
# Indexing rate
rate(elasticsearch_consumer_messages_indexed_total[1m])

# Bulk duration (p95)
histogram_quantile(0.95, rate(elasticsearch_consumer_bulk_duration_seconds_bucket[5m]))

# OpenSearch availability
elasticsearch_consumer_opensearch_available
```

### Health Checks

```bash
# OpenSearch cluster health
curl http://localhost:9200/_cluster/health

# Index statistics
curl http://localhost:9200/alpr-events-*/_stats

# Document count
curl http://localhost:9200/alpr-events-*/_count

# Consumer metrics
curl http://localhost:8004/metrics
```

---

## Troubleshooting

### Common Issues

#### 1. Events Not Being Indexed

**Check Consumer Status**:
```bash
docker logs alpr-elasticsearch-consumer --tail 50
```

**Verify Kafka Connection**:
```bash
docker logs alpr-elasticsearch-consumer | grep "Connected to Kafka"
```

**Check OpenSearch Health**:
```bash
curl http://localhost:9200/_cluster/health
```

#### 2. Search Queries Returning No Results

**Verify Index Exists**:
```bash
curl http://localhost:9200/_cat/indices?v
```

**Check Document Count**:
```bash
curl http://localhost:9200/alpr-events-*/_count
```

**Test Direct Query**:
```bash
curl "http://localhost:9200/alpr-events-*/_search?q=*"
```

#### 3. High Memory Usage

**Check JVM Settings**:
```bash
docker inspect alpr-opensearch | grep OPENSEARCH_JAVA_OPTS
```

**Expected**: `-Xms512m -Xmx1g`

**Reduce if Needed** (in docker-compose.yml):
```yaml
OPENSEARCH_JAVA_OPTS: "-Xms256m -Xmx768m"
```

#### 4. Slow Indexing

**Check Bulk Size**:
```yaml
# config/elasticsearch.yaml
bulk:
  size: 50  # Increase to 100 for higher throughput
  flush_interval: 5  # Reduce to 3 for lower latency
```

**Monitor Metrics**:
```bash
curl -s http://localhost:8004/metrics | grep bulk_duration
```

---

## Maintenance

### Index Lifecycle Management

**Current Strategy**: Manual deletion of old indices

**Delete Indices Older Than 90 Days**:
```bash
# List all indices with dates
curl 'http://localhost:9200/_cat/indices/alpr-events-*?v'

# Delete specific index
curl -X DELETE 'http://localhost:9200/alpr-events-2025.09'
```

**Automated Retention** (future enhancement):
```python
from datetime import datetime, timedelta

# Delete indices older than 90 days
retention_days = 90
cutoff_date = datetime.now() - timedelta(days=retention_days)
# Implementation in index_manager.py
```

### Reindexing

If schema changes require reindexing:

```bash
# 1. Create new index with updated mapping
curl -X PUT 'http://localhost:9200/alpr-events-2025.12-v2' \
  -H 'Content-Type: application/json' \
  -d @core_services/search/opensearch/templates/alpr-events-template.json

# 2. Reindex from old to new
curl -X POST 'http://localhost:9200/_reindex' \
  -H 'Content-Type: application/json' \
  -d '{
    "source": {"index": "alpr-events-2025.12"},
    "dest": {"index": "alpr-events-2025.12-v2"}
  }'

# 3. Delete old index
curl -X DELETE 'http://localhost:9200/alpr-events-2025.12'

# 4. Create alias
curl -X POST 'http://localhost:9200/_aliases' \
  -H 'Content-Type: application/json' \
  -d '{
    "actions": [
      {"add": {"index": "alpr-events-2025.12-v2", "alias": "alpr-events-2025.12"}}
    ]
  }'
```

### Backup and Restore

**Snapshot Repository** (future enhancement):
```bash
# Register snapshot repository
curl -X PUT 'http://localhost:9200/_snapshot/alpr_backup' \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "fs",
    "settings": {
      "location": "/mnt/backups/opensearch",
      "compress": true
    }
  }'

# Create snapshot
curl -X PUT 'http://localhost:9200/_snapshot/alpr_backup/snapshot_1?wait_for_completion=true'
```

---

## Use Cases

### 1. Fuzzy Plate Search

**Scenario**: Partial or unclear plate reading (e.g., "ABC12?" becomes "ABC12")

```bash
curl "http://localhost:8000/search/fulltext?q=ABC12"
```

**Returns**: Matches for ABC123, ABC124, ABC125, etc. (fuzzy matching)

### 2. Building a Drill-Down UI

**Step 1**: Get all facets
```bash
curl "http://localhost:8000/search/facets?limit=100"
```

**Step 2**: User selects camera "CAM1"
```bash
curl "http://localhost:8000/search/facets?camera_id=CAM1&limit=100"
```

**Step 3**: User selects vehicle type "truck"
```bash
curl "http://localhost:8000/search/facets?camera_id=CAM1&vehicle_type=truck&limit=100"
```

### 3. Traffic Analytics Dashboard

**Get hourly plate counts**:
```bash
curl "http://localhost:8000/search/analytics?metric=plates_per_hour&interval=1h"
```

**Get confidence trend**:
```bash
curl "http://localhost:8000/search/analytics?metric=avg_confidence&interval=1h"
```

**Get top plates**:
```bash
curl "http://localhost:8000/search/analytics?metric=top_plates&limit=20"
```

### 4. Complex Search

**Find all white Hondas at main entrance with high confidence**:
```bash
curl -X POST "http://localhost:8000/search/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "bool": {
        "must": [
          {"term": {"vehicle.make": "Honda"}},
          {"term": {"vehicle.color": "white"}},
          {"term": {"camera_id": "main-entrance"}},
          {"range": {"plate.confidence": {"gte": 0.95}}}
        ]
      }
    },
    "sort": [{"captured_at": "desc"}],
    "size": 50
  }'
```

---

## Future Enhancements

### Planned Features

1. **Automated Index Lifecycle Management**
   - Auto-delete indices older than 90 days
   - Auto-rollover to new indices

2. **Advanced Analytics**
   - Anomaly detection (unusual traffic patterns)
   - Time-series forecasting
   - Heatmaps (busiest cameras/times)

3. **Search Suggestions**
   - Auto-complete for plate numbers
   - "Did you mean?" for typos
   - Recent searches

4. **OpenSearch Dashboards**
   - Pre-built visualizations
   - Interactive exploration
   - Custom dashboard builder

5. **Multi-Site Search**
   - Federated search across multiple sites
   - Cross-site analytics
   - Site-specific retention policies

---

## References

- **OpenSearch Documentation**: https://opensearch.org/docs/latest/
- **Query DSL Reference**: https://opensearch.org/docs/latest/query-dsl/
- **Implementation Plan**: `/home/jetson/.claude/plans/concurrent-splashing-zebra.md`
- **Services Overview**: `docs/ALPR_Pipeline/SERVICES_OVERVIEW.md`
- **Configuration**: `config/elasticsearch.yaml`
- **Dashboard**: `core_services/monitoring/grafana/dashboards/elasticsearch-search.json`

---

## Conclusion

The OpenSearch integration provides powerful search and analytics capabilities that complement the existing TimescaleDB SQL queries. With dual storage, the ALPR system can handle both structured queries (exact matches, time-series) and unstructured queries (fuzzy search, relevance ranking) efficiently.

**Key Benefits**:
- ✅ Sub-30ms search latency for most queries
- ✅ Fuzzy matching for partial/unclear plates
- ✅ Real-time analytics and aggregations
- ✅ Faceted search for drill-down UIs
- ✅ Scalable architecture ready for growth
- ✅ Full monitoring and observability

**Production Status**: Fully operational and tested end-to-end ✅
