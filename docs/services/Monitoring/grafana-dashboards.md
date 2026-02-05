# Grafana Dashboards Guide

This guide provides detailed information about the pre-built Grafana dashboards for the ALPR monitoring system.

## Dashboard Overview

| Dashboard | UID | Purpose | Refresh Rate |
|-----------|-----|---------|--------------|
| ALPR Overview | `alpr-overview` | Main dashboard for ALPR metrics (FPS, detections, latency) | 5s |
| System Performance | `system-performance` | Container resource usage (CPU, RAM, network) | 5s |
| Kafka & Database | `kafka-database` | Kafka consumer and database metrics | 5s |
| Search & Indexing | `search-indexing` | OpenSearch metrics, indexing rate, search latency | 5s |
| Model Registry | `alpr-model-registry` | MLflow model metrics, experiment tracking | 10s |
| Service Status | `service-status` | Container health, service up/down status | 5s |
| Logs Explorer | `logs-explorer` | Log aggregation and search | 10s |

## Dashboard Details

### 1. ALPR Overview

**Purpose**: Monitor real-time ALPR processing performance and detection metrics.

**Key Panels**:
- **Current FPS** (Gauge) - Live FPS with color-coded thresholds
  - Green: ≥ 25 FPS
  - Yellow: 20-25 FPS
  - Red: < 10 FPS

- **FPS Over Time** (Time Series) - Historical FPS trend
  - Shows mean, max, and current values

- **Plates Detected** (Stats)
  - Last Minute: Recent detection activity
  - Total: Cumulative detections since start

- **Frames Processed** (Stats)
  - Last Minute: Recent processing activity
  - Total: Cumulative frames processed

- **Processing Latency** (Time Series) - Frame processing time percentiles
  - p50 (median), p95, p99
  - Measured in seconds

- **Kafka Publish Latency** (Time Series) - Message publish time percentiles
  - p50 (median), p95, p99
  - Measured in seconds

- **Detection Rate** (Time Series) - Plates detected per minute

- **Plates by Camera** (Time Series) - Per-camera detection breakdown
  - Stacked bars showing 5-minute intervals

**Use Cases**:
- Monitor real-time processing performance
- Identify performance degradation
- Compare detection rates across cameras
- Troubleshoot latency issues

---

### 2. System Performance

**Purpose**: Monitor container resource utilization and system health.

**Key Panels**:
- **CPU Usage by Container** (Time Series) - Per-container CPU usage %
  - Shows mean, max, current values
  - Yellow threshold: 70%
  - Red threshold: 90%

- **Memory Usage by Container** (Time Series) - Per-container RAM usage
  - Shows mean, max, current values in bytes
  - Yellow threshold: 6 GB
  - Red threshold: 7 GB

- **CPU Usage (5m avg)** (Bar Gauge) - Current CPU usage ranking
  - Horizontal bars for easy comparison

- **Memory Usage (Current)** (Bar Gauge) - Current memory ranking
  - Shows which containers are using most RAM

- **Network Traffic RX/TX** (Time Series) - Network I/O per container
  - TX shown as negative (below axis) for easy visualization
  - Measured in bytes/second

- **Disk Usage** (Time Series) - Filesystem usage per container

- **Summary Stats**:
  - Running Containers: Total count
  - Total Memory Usage: Sum across all containers
  - Total Network RX: Aggregate receive rate
  - Total Network TX: Aggregate transmit rate

**Use Cases**:
- Identify resource-hungry containers
- Monitor for memory leaks
- Track network bandwidth usage
- Capacity planning

---

### 3. Kafka & Database

**Purpose**: Monitor message consumption, database operations, and API performance.

**Sections**:

#### Kafka Consumer Metrics
- **Messages Consumed** - Last minute and total counts
- **Processing Errors** - Error tracking (5m window)
  - Yellow: 1+ errors
  - Red: 10+ errors
- **Database Writes** - Total write operations
- **Message Consumption Rate** - Messages per minute
- **Error Rate** - Errors per minute

#### Database Metrics
- **Database Write Rate** - Writes per minute
- **Database Write Latency** - Write operation timing
  - p50, p95, p99 percentiles

#### API Metrics
- **API Request Rate** - Requests per second
- **Active Requests** - In-flight request count
- **API Latency p95** - 95th percentile response time
- **Request Rate by Endpoint** - Per-endpoint breakdown
- **Response Status Codes** - HTTP status distribution
  - Green: 2xx (success)
  - Yellow: 4xx (client errors)
  - Red: 5xx (server errors)

**Use Cases**:
- Monitor Kafka consumer lag
- Track database performance
- Identify API bottlenecks
- Detect error spikes
- Monitor endpoint performance

---

### 4. Logs Explorer

**Purpose**: Centralized log viewing and analysis with filtering capabilities.

**Key Features**:
- **Template Variables** (top of dashboard):
  - Service: Filter by service (pilot, kafka-consumer, etc.)
  - Container: Filter by container name
  - Search: Free-text search across logs

**Key Panels**:
- **Logs Stream** - Live log tail with filtering
  - Supports regex search
  - Time-ordered display
  - Log details expansion

- **Log Volume by Service** - Message count per service
  - Stacked bars showing 1-minute intervals

- **Log Volume by Level** - Breakdown by log level
  - Color-coded: ERROR (red), WARNING (yellow), INFO (green)

- **Error Logs** - Filtered view of errors and exceptions
  - Searches for: ERROR, Exception, Traceback

- **Warning Logs** - Filtered view of warnings
  - Searches for: WARNING, WARN

- **ALPR Pilot Logs** - Pilot-specific logs
  - Filtered for: plate, detection, FPS

**Use Cases**:
- Troubleshoot errors in real-time
- Search logs across all services
- Analyze error patterns
- Monitor detection events
- Debug performance issues

---

### 5. Search & Indexing

**Purpose**: Monitor OpenSearch indexing and search performance.

**Key Panels**:
- **Indexing Rate** - Real-time events/sec being indexed
- **Total Messages Indexed** - Cumulative count
- **OpenSearch Availability** - Cluster health (0=down, 1=up)
- **Bulk Request Duration** - p95 and p99 latency
- **Bulk Size** - Documents per batch (p50, p95)
- **Message Flow** - Consumed vs Indexed vs Failed
- **Search Latency** - Query response times

**Use Cases**:
- Monitor indexing throughput
- Identify indexing bottlenecks
- Track search performance
- Debug OpenSearch connectivity issues

---

### 6. Model Registry

**Purpose**: Monitor MLflow model registry and detector performance.

**Key Panels**:
- **MLflow Server Status** - Health indicator
- **Model Inference FPS** - Detection throughput
- **Inference Latency** - Processing time per frame
- **Detection Confidence** - Average confidence scores
- **Resource Usage** - CPU/memory for detector service

**Use Cases**:
- Track model performance after deployments
- Compare model versions
- Monitor inference efficiency
- Plan model optimization

---

### 7. Service Status

**Purpose**: Overview of all service health and availability.

**Key Panels**:
- **Service Health Grid** - Up/down status for all services
- **Container Status** - Running, stopped, restarting counts
- **Uptime** - Service availability percentage
- **Recent Restarts** - Container restart events
- **Resource Alerts** - Services exceeding thresholds

**Use Cases**:
- Quick health overview
- Identify failing services
- Monitor service stability
- Track system availability

---

## Accessing Dashboards

### Via Grafana UI
1. Open Grafana: http://localhost:3000
2. Login: `admin` / `alpr_admin_2024`
3. Navigate to **Dashboards** → **ALPR** folder
4. Select desired dashboard

### Direct Links (after Grafana is running)
- ALPR Overview: http://localhost:3000/d/alpr-overview
- System Performance: http://localhost:3000/d/system-performance
- Kafka & Database: http://localhost:3000/d/kafka-database
- Search & Indexing: http://localhost:3000/d/search-indexing
- Model Registry: http://localhost:3000/d/alpr-model-registry
- Service Status: http://localhost:3000/d/service-status
- Logs Explorer: http://localhost:3000/d/logs-explorer

---

## Dashboard Features

### Auto-Refresh
All dashboards auto-refresh:
- Metrics dashboards: Every 5 seconds
- Logs dashboard: Every 10 seconds

You can change the refresh rate in the top-right corner of each dashboard.

### Time Range Selection
Default time ranges:
- Metrics dashboards: Last 15 minutes
- Logs dashboard: Last 1 hour

Adjust using the time picker in the top-right corner.

### Legend Calculations
Most time series panels show:
- **Mean**: Average value over time range
- **Last**: Most recent value
- **Max**: Peak value

Click legend items to hide/show specific series.

### Filtering (Logs Explorer)
Use template variables at the top:
1. **Service** - Select one or more services
2. **Container** - Select specific containers
3. **Search** - Enter search terms (supports regex)

Example searches:
- `ERROR` - Show only errors
- `plate_number` - Show detection events
- `FPS.*([0-9]+)` - Regex for FPS values

---

## Customizing Dashboards

### Editing Panels
1. Click panel title → **Edit**
2. Modify query, visualization, or settings
3. Click **Apply** to save changes

### Adding New Panels
1. Click **Add panel** (top-right)
2. Select visualization type
3. Configure data source and query
4. Click **Apply**

### Saving Changes
After editing:
1. Click **Save dashboard** (top-right)
2. Add optional change description
3. Click **Save**

**Note**: Changes are saved to the Grafana database, not the JSON files.

---

## Common Queries

### Prometheus Queries

**Total plates detected**:
```promql
sum(alpr_plates_detected_total)
```

**Detection rate (per minute)**:
```promql
rate(alpr_plates_detected_total[1m]) * 60
```

**Processing latency p95**:
```promql
histogram_quantile(0.95, sum(rate(alpr_processing_latency_seconds_bucket[1m])) by (le))
```

**CPU usage by container**:
```promql
sum(rate(container_cpu_usage_seconds_total{name=~"alpr-.*"}[1m])) by (name) * 100
```

**Memory usage**:
```promql
container_memory_usage_bytes{name=~"alpr-.*"}
```

### Loki Queries (LogQL)

**All logs from pilot service**:
```logql
{service="pilot"}
```

**Error logs across all services**:
```logql
{service=~".+"} |~ "ERROR|Exception"
```

**Logs containing specific text**:
```logql
{service="pilot"} |~ "plate_number"
```

**Log count by level**:
```logql
sum by (level) (count_over_time({service=~".+"} | regexp "(?P<level>ERROR|WARNING|INFO)" [1m]))
```

---

## Troubleshooting

### Dashboard Not Showing Data

**Check datasources**:
1. Go to **Configuration** → **Data Sources**
2. Verify Prometheus and Loki are listed and reachable
3. Click **Test** on each datasource

**Check if services are running**:
```bash
docker compose ps prometheus grafana loki
```

**Check Prometheus targets**:
- Go to http://localhost:9090/targets
- Verify all targets show "UP" status

### Metrics Missing

**Verify metric endpoints**:
```bash
# Check pilot.py metrics
curl http://localhost:8001/metrics

# Check kafka-consumer metrics
curl http://localhost:8002/metrics

# Check query-api metrics
curl http://localhost:8000/metrics
```

**Check Prometheus is scraping**:
- Go to http://localhost:9090
- Run query: `up{job="alpr-pilot"}`
- Should return `1` if scraping successfully

### Logs Not Appearing

**Check Loki is running**:
```bash
docker compose logs loki
```

**Check Promtail is shipping logs**:
```bash
docker compose logs promtail
```

**Verify log files exist**:
```bash
ls -la /home/jetson/OVR-ALPR/logs/
```

### Dashboard JSON Updates Not Loading

Dashboards are auto-provisioned on first start. To reload:
1. Restart Grafana: `docker compose restart grafana`
2. Or delete the dashboard in Grafana UI and restart

---

## Port Reference

| Service | Internal Port | External Port | URL |
|---------|--------------|---------------|-----|
| Grafana | 3000 | 3000 | http://localhost:3000 |
| Prometheus | 9090 | 9090 | http://localhost:9090 |
| Loki | 3100 | 3100 | http://localhost:3100 |
| cAdvisor | 8080 | 8082 | http://localhost:8082 |
| Kafka UI | 8080 | 8080 | http://localhost:8080 |
| pilot.py metrics | - | 8001 | http://localhost:8001/metrics |
| kafka-consumer metrics | 8002 | - | - |
| query-api metrics | 8000 | - | - |

**Note**: cAdvisor is accessible on port **8082** externally (changed from 8080 to avoid conflict with Kafka UI).

---

## Best Practices

### Dashboard Organization
- Use **ALPR Overview** as your main monitoring dashboard
- Keep it open on a dedicated monitor for real-time monitoring
- Use **System Performance** to diagnose resource issues
- Use **Kafka & Database** for data pipeline monitoring
- Use **Search & Indexing** for OpenSearch monitoring
- Use **Model Registry** for MLflow and inference monitoring
- Use **Service Status** for quick health checks
- Use **Logs Explorer** for troubleshooting

### Alert Recommendations
Consider setting up alerts for:
- FPS drops below 20
- Processing latency p95 > 500ms
- CPU usage > 90%
- Memory usage > 7 GB
- Kafka consumer errors > 10 in 5 minutes
- Database write failures

### Performance Optimization
- Limit time ranges for heavy queries
- Use appropriate scrape intervals
- Disable unused panels if needed
- Export dashboards as JSON for version control

---

## Next Steps

1. **Explore the dashboards** - Familiarize yourself with each view
2. **Customize panels** - Adjust to your specific needs
3. **Set up alerting** - Configure Grafana alerts for critical metrics
4. **Create custom dashboards** - Build dashboards for specific use cases
5. **Monitor trends** - Use dashboards to identify performance patterns

For more information on Grafana features, visit: https://grafana.com/docs/
