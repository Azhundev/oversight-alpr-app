# Grafana Dashboard Fixes Summary

## Issue
Grafana dashboards were showing no data for:
- Current FPS (ALPR Overview)
- FPS Over Time (ALPR Overview)
- Processing Latency Percentiles (ALPR Overview)
- Kafka consumer metrics (Kafka & Database dashboard)
- Database metrics (Kafka & Database dashboard)

## Root Cause
The dashboard JSON files contained **incorrect metric names** that didn't match the actual metrics being exported by the services.

## Metrics Comparison

### ALPR Pilot Metrics (port 8001)
| Dashboard Query (WRONG) | Actual Metric (CORRECT) | Status |
|------------------------|------------------------|---------|
| `alpr_fps_current` | `alpr_fps` | ✅ FIXED |
| `alpr_processing_latency_seconds_bucket` | `alpr_processing_time_seconds_bucket` | ✅ FIXED |
| `alpr_kafka_publish_latency_seconds_bucket` | ❌ Does not exist | ✅ REMOVED |

### Kafka Consumer Metrics (port 8002)
| Dashboard Query (WRONG) | Actual Metric (CORRECT) | Status |
|------------------------|------------------------|---------|
| `alpr_messages_consumed_total` | `kafka_consumer_messages_consumed_total` | ✅ FIXED |
| `alpr_processing_errors_total` | `kafka_consumer_messages_failed_total` | ✅ FIXED |
| `alpr_database_writes_total` | `kafka_consumer_messages_stored_total` | ✅ FIXED |
| `alpr_database_write_latency_seconds_bucket` | `kafka_consumer_db_insert_time_seconds_bucket` | ✅ FIXED |

### Query API Metrics (port 8000)
| Dashboard Query (WRONG) | Actual Metric (CORRECT) | Status |
|------------------------|------------------------|---------|
| `http_requests_in_progress` | ❌ Does not exist | ✅ REPLACED with `vector(0)` |

## Changes Made

### 1. ALPR Overview Dashboard
**File**: `core-services/monitoring/grafana/dashboards/alpr-overview.json`

- ✅ Fixed FPS gauge panel: `alpr_fps_current` → `alpr_fps`
- ✅ Fixed FPS time series panel: `alpr_fps_current` → `alpr_fps`
- ✅ Fixed processing latency percentiles: `alpr_processing_latency_seconds_bucket` → `alpr_processing_time_seconds_bucket`
- ✅ Removed Kafka publish latency panel (metric doesn't exist)

### 2. Kafka & Database Dashboard
**File**: `core-services/monitoring/grafana/dashboards/kafka-database.json`

- ✅ Fixed messages consumed panels: `alpr_messages_consumed_total` → `kafka_consumer_messages_consumed_total`
- ✅ Fixed processing errors: `alpr_processing_errors_total` → `kafka_consumer_messages_failed_total`
- ✅ Fixed database writes: `alpr_database_writes_total` → `kafka_consumer_messages_stored_total`
- ✅ Fixed database write latency: `alpr_database_write_latency_seconds_bucket` → `kafka_consumer_db_insert_time_seconds_bucket`
- ✅ Replaced `http_requests_in_progress` with `vector(0)` (metric doesn't exist)

### 3. Grafana Service
- ✅ Restarted Grafana to reload updated dashboard configurations

## Verification

### To verify the fixes work:

1. **Start the pilot** (if not already running):
   ```bash
   python3 pilot.py --no-display
   ```

2. **Check metrics are being exposed**:
   ```bash
   # Check pilot metrics
   curl http://localhost:8001/metrics | grep alpr_fps

   # Check Prometheus is scraping
   curl 'http://localhost:9090/api/v1/query?query=alpr_fps'
   ```

3. **View dashboards**:
   - ALPR Overview: http://localhost:3000/d/alpr-overview
   - Kafka & Database: http://localhost:3000/d/kafka-database

   Login: `admin` / `alpr_admin_2024`

## Expected Results

After starting pilot.py, you should see:

### ALPR Overview Dashboard
- ✅ **Current FPS**: Live FPS gauge (updates every 5s)
- ✅ **FPS Over Time**: Line chart showing FPS trend
- ✅ **Processing Latency**: p50, p95, p99 percentiles
- ✅ **Plates Detected**: Counter metrics
- ✅ **Frames Processed**: Counter metrics

### Kafka & Database Dashboard
- ✅ **Messages Consumed**: Real-time count
- ✅ **Processing Errors**: Error tracking
- ✅ **Database Writes**: Write operations
- ✅ **Database Write Latency**: p50, p95, p99 percentiles
- ✅ **API Request Rate**: HTTP request metrics

## Technical Details

### Available Metrics (Verified)

**ALPR Pilot (localhost:8001/metrics):**
- `alpr_fps{camera_id="CAM1"}` - Current FPS
- `alpr_processing_time_seconds_bucket` - Processing time histogram
- `alpr_detection_time_seconds_bucket` - Detection time histogram
- `alpr_ocr_time_seconds_bucket` - OCR time histogram
- `alpr_frames_processed_total` - Total frames processed
- `alpr_plates_detected_total` - Total plates detected
- `alpr_vehicles_detected_total` - Total vehicles detected
- `alpr_events_published_total` - Total events published
- `alpr_active_tracks` - Currently tracked vehicles

**Kafka Consumer (kafka-consumer:8002/metrics):**
- `kafka_consumer_messages_consumed_total` - Messages consumed from Kafka
- `kafka_consumer_messages_stored_total` - Messages stored in database
- `kafka_consumer_messages_failed_total` - Failed messages
- `kafka_consumer_processing_time_seconds_bucket` - Processing time histogram
- `kafka_consumer_db_insert_time_seconds_bucket` - Database insert time histogram
- `kafka_consumer_lag` - Consumer lag

**Query API (query-api:8000/metrics):**
- `http_requests_total{method,handler,status}` - HTTP request counter
- `http_request_duration_seconds_bucket` - Request duration histogram

### Prometheus Scraping Status
All services are being scraped successfully by Prometheus:
- ✅ alpr-pilot: http://host.docker.internal:8001/metrics (5s interval)
- ✅ kafka-consumer: http://kafka-consumer:8002/metrics (10s interval)
- ✅ query-api: http://query-api:8000/metrics (10s interval)

## Files Modified

1. `core-services/monitoring/grafana/dashboards/alpr-overview.json`
2. `core-services/monitoring/grafana/dashboards/kafka-database.json`
3. `docs/Services/grafana-dashboard-fixes.md` (this file)

## Next Steps

When you restart pilot.py, the dashboards should immediately show live data. If you still see no data:

1. Verify pilot is running: `ps aux | grep pilot.py`
2. Check metrics endpoint: `curl http://localhost:8001/metrics | grep alpr_fps`
3. Check Prometheus is scraping: http://localhost:9090/targets (should show "UP")
4. Check Prometheus has data: http://localhost:9090/graph (query `alpr_fps`)
5. Check Grafana datasource: http://localhost:3000/datasources (test Prometheus connection)
