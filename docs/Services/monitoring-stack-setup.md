# ALPR Monitoring Stack Setup

Complete monitoring infrastructure for the ALPR system using Prometheus, Grafana, Loki, and cAdvisor.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      ALPR Monitoring Stack                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │   pilot.py   │   │kafka-consumer│   │  query-api   │        │
│  │  (port 8001) │   │  (port 8002) │   │  (port 8000) │        │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘        │
│         │                  │                   │                 │
│         └──────────────────┴───────────────────┘                 │
│                            │                                     │
│                            ▼                                     │
│                    ┌───────────────┐                            │
│                    │  Prometheus   │◄─────┐                     │
│                    │  (port 9090)  │      │                     │
│                    └───────┬───────┘      │                     │
│                            │              │                     │
│                            │        ┌─────┴─────┐               │
│                            │        │  cAdvisor │               │
│                            │        │(port 8082)│               │
│                            │        └───────────┘               │
│                            │                                     │
│                            ▼                                     │
│                    ┌───────────────┐                            │
│                    │    Grafana    │                            │
│                    │  (port 3000)  │                            │
│                    └───────┬───────┘                            │
│                            │                                     │
│                            │                                     │
│                            ▼                                     │
│                    ┌───────────────┐                            │
│                    │     Loki      │◄────┐                      │
│                    │  (port 3100)  │     │                      │
│                    └───────────────┘     │                      │
│                                          │                      │
│                                    ┌─────┴──────┐               │
│                                    │  Promtail  │               │
│                                    │ (log ship) │               │
│                                    └────────────┘               │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Services Included

### 1. Prometheus (port 9090)
- **Purpose**: Metrics collection and storage
- **Scrapes metrics from**:
  - `pilot.py` - Edge processing metrics (FPS, latency, detection counts)
  - `kafka-consumer` - Message consumption metrics
  - `query-api` - HTTP request metrics
  - `cadvisor` - Container resource metrics
- **Retention**: 30 days
- **Access**: http://localhost:9090

### 2. Grafana (port 3000)
- **Purpose**: Metrics visualization and dashboards
- **Features**:
  - Pre-configured Prometheus and Loki datasources
  - Auto-provisioned dashboards
  - Real-time metrics visualization
- **Access**: http://localhost:3000
- **Credentials**:
  - Username: `admin`
  - Password: `alpr_admin_2024`

### 3. Loki (port 3100)
- **Purpose**: Log aggregation and storage
- **Features**:
  - Centralized log storage
  - Fast log queries
  - Integration with Grafana
- **Retention**: 7 days
- **Access**: http://localhost:3100

### 4. Promtail
- **Purpose**: Log shipping to Loki
- **Collects logs from**:
  - Docker containers
  - `pilot.py` log files
  - `kafka-consumer` log files
- **No exposed ports** (internal service)

### 5. cAdvisor (port 8082)
- **Purpose**: Container resource metrics
- **Metrics provided**:
  - CPU usage per container
  - Memory usage per container
  - Network I/O
  - Container lifecycle events
- **Access**: http://localhost:8082
- **Note**: Port 8082 is used to avoid conflict with Kafka UI (port 8080)

## Quick Start

### 1. Start the monitoring stack
```bash
cd /home/jetson/OVR-ALPR
docker compose up -d prometheus grafana loki promtail cadvisor
```

### 2. Verify all services are running
```bash
docker compose ps
```

Expected output should show all monitoring services as "Up":
- alpr-prometheus
- alpr-grafana
- alpr-loki
- alpr-promtail
- alpr-cadvisor

### 3. Access Grafana
1. Open browser to http://localhost:3000
2. Login with `admin` / `alpr_admin_2024`
3. Navigate to Dashboards → ALPR folder
4. View pre-built dashboards (will be created in step 2)

### 4. Access Prometheus
- Open browser to http://localhost:9090
- Run queries like: `alpr_plates_detected_total`

### 5. Access cAdvisor
- Open browser to http://localhost:8082
- View real-time container metrics

## Configuration Files

```
monitoring/
├── prometheus/
│   └── prometheus.yml              # Prometheus scrape configuration
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── datasources.yaml   # Auto-provision Prometheus + Loki
│   │   └── dashboards/
│   │       └── dashboards.yaml    # Dashboard loading configuration
│   └── dashboards/                # Dashboard JSON files (step 2)
├── loki/
│   └── loki-config.yaml           # Loki configuration
└── promtail/
    └── promtail-config.yaml       # Log shipping configuration
```

## Exposed Metrics Endpoints

| Service | Port | Endpoint | Description |
|---------|------|----------|-------------|
| pilot.py | 8001 | `/metrics` | Edge processing metrics |
| kafka-consumer | 8002 | `/metrics` | Storage service metrics |
| query-api | 8000 | `/metrics` | API request metrics |
| cAdvisor | 8082 | `/metrics` | Container metrics |
| Prometheus | 9090 | `/metrics` | Prometheus self-metrics |

## Key Metrics Available

### pilot.py Metrics
- `alpr_frames_processed_total` - Total frames processed
- `alpr_plates_detected_total` - Total plates detected
- `alpr_processing_latency_seconds` - Processing time per frame
- `alpr_fps_current` - Current FPS
- `alpr_kafka_publish_latency_seconds` - Kafka publish latency

### kafka-consumer Metrics
- `alpr_messages_consumed_total` - Total Kafka messages consumed
- `alpr_database_writes_total` - Total database writes
- `alpr_processing_errors_total` - Total processing errors

### query-api Metrics
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency
- `http_requests_in_progress` - Active requests

### cAdvisor Metrics
- `container_cpu_usage_seconds_total` - CPU usage per container
- `container_memory_usage_bytes` - Memory usage per container
- `container_network_receive_bytes_total` - Network RX
- `container_network_transmit_bytes_total` - Network TX

## Troubleshooting

### Prometheus not scraping metrics
1. Check if target services are exposing metrics:
   ```bash
   curl http://localhost:8001/metrics  # pilot.py
   curl http://localhost:8002/metrics  # kafka-consumer
   curl http://localhost:8000/metrics  # query-api
   ```

2. Check Prometheus targets status:
   - Go to http://localhost:9090/targets
   - Verify all targets are "UP"

### Grafana not showing data
1. Verify datasources are configured:
   - Go to Configuration → Data Sources
   - Check Prometheus and Loki are listed

2. Check if Prometheus is receiving data:
   - Go to http://localhost:9090
   - Run query: `up`
   - Should show all services

### Loki not receiving logs
1. Check Promtail is running:
   ```bash
   docker compose logs promtail
   ```

2. Verify log files exist:
   ```bash
   ls -la /home/jetson/OVR-ALPR/logs/
   ```

### cAdvisor not showing container metrics
- cAdvisor requires privileged mode and access to /sys
- Verify the service has proper volume mounts in docker-compose.yml

## Performance Considerations

### Resource Usage
- **Prometheus**: ~200-500 MB RAM (depends on cardinality)
- **Grafana**: ~100-200 MB RAM
- **Loki**: ~100-300 MB RAM
- **Promtail**: ~50-100 MB RAM
- **cAdvisor**: ~100-200 MB RAM

**Total overhead**: ~550 MB - 1.3 GB RAM

### Storage Requirements
- **Prometheus**: ~1-2 GB/month (with 30-day retention)
- **Loki**: ~500 MB - 1 GB/month (with 7-day retention)
- **Grafana**: ~100 MB (dashboards + settings)

**Total storage**: ~2-4 GB

### Optimizing Performance
1. **Reduce scrape frequency** in `prometheus.yml` if needed
2. **Limit log retention** in `loki-config.yaml`
3. **Disable unused cAdvisor metrics** (already configured)

## Next Steps

1. **Create Grafana Dashboards** (Step 2)
   - ALPR Overview Dashboard
   - System Performance Dashboard
   - Kafka & Database Dashboard
   - Camera Ingestion Dashboard

2. **Test the Stack** (Step 3)
   - Verify metrics collection
   - Test dashboard functionality
   - Validate alerting (if configured)

3. **Optional Enhancements**
   - Add AlertManager for alerting
   - Add Kafka JMX exporter
   - Add PostgreSQL exporter for TimescaleDB
   - Set up remote storage for long-term retention

## Security Notes

**IMPORTANT**: Change default credentials in production!

```yaml
# In docker-compose.yml, update:
GF_SECURITY_ADMIN_PASSWORD: your_secure_password_here
```

Also consider:
- Enabling HTTPS for Grafana
- Restricting network access to monitoring services
- Using authentication for Prometheus endpoints
- Setting up user roles in Grafana
