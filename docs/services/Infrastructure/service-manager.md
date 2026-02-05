# ALPR Service Manager

**Enterprise-grade service orchestration with incremental startup support.**

## Overview

The Service Manager provides a REST API and web dashboard for controlling ALPR services. It enables:

- **Incremental startup** - Start services in groups to manage RAM usage
- **Visual dashboard** - Web UI with toggle controls
- **Dependency management** - Automatically checks service dependencies
- **Real-time monitoring** - Memory usage and health status
- **Audit logging** - Track all service actions

## Access

| Endpoint | Description |
|----------|-------------|
| http://localhost:8000/services/dashboard | Web dashboard with toggles |
| http://localhost:8000/services/status | System status JSON |
| http://localhost:8000/docs#/Service%20Manager | API documentation |

## Web Dashboard

Access the visual dashboard at: **http://localhost:8000/services/dashboard**

Features:
- Service groups with Start/Stop/Restart buttons
- Real-time memory usage display
- Health status indicators
- Auto-refresh every 10 seconds
- Pilot readiness indicator

## Service Groups

| Group | Services | Est. RAM | Dependencies |
|-------|----------|----------|--------------|
| **kafka** | zookeeper, kafka, schema-registry | ~700 MB | None |
| **storage** | timescaledb, minio, kafka-consumer, query-api | ~200 MB | kafka |
| **search** | opensearch, opensearch-dashboards, elasticsearch-consumer | ~1500 MB | kafka |
| **alerts** | alert-engine | ~50 MB | kafka |
| **monitoring** | prometheus, grafana, loki, promtail, cadvisor | ~600 MB | None |
| **analytics** | metabase | ~700 MB | storage |
| **optional** | kafka-ui | ~200 MB | kafka |

## API Endpoints

### Get System Status

```bash
curl http://localhost:8000/services/status
```

Response includes:
- Total/running service counts
- Memory usage per group
- Health status
- Pilot readiness

### Get Group Status

```bash
curl http://localhost:8000/services/status/kafka
```

### Start a Group

```bash
# Start with dependency check
curl -X POST http://localhost:8000/services/start/kafka

# Force start (skip dependency check)
curl -X POST "http://localhost:8000/services/start/storage?force=true"
```

### Stop a Group

```bash
curl -X POST http://localhost:8000/services/stop/monitoring
```

### Restart a Group

```bash
curl -X POST http://localhost:8000/services/restart/kafka
```

### List All Groups

```bash
curl http://localhost:8000/services/groups
```

### View Audit Log

```bash
curl http://localhost:8000/services/audit
```

## Incremental Startup Workflow

### Minimal Setup (for pilot.py testing)

```bash
# 1. Start just Kafka (~700 MB)
curl -X POST http://localhost:8000/services/start/kafka

# 2. Run pilot.py - it auto-connects
python3 pilot.py
```

### Add Persistence

```bash
# 3. Add storage services (~200 MB more)
curl -X POST http://localhost:8000/services/start/storage
```

### Add Search

```bash
# 4. Add search services (~1.5 GB more)
curl -X POST http://localhost:8000/services/start/search
```

### Full Stack

```bash
# 5. Add remaining services
curl -X POST http://localhost:8000/services/start/alerts
curl -X POST http://localhost:8000/services/start/monitoring
curl -X POST http://localhost:8000/services/start/analytics
```

## RAM Management

Use the dashboard to monitor memory and selectively enable features:

| Configuration | Services Running | Approx. RAM |
|--------------|------------------|-------------|
| Pilot only | 0 | ~500 MB |
| + Kafka | 3 | ~1.2 GB |
| + Storage | 7 | ~1.4 GB |
| + Search | 10 | ~2.9 GB |
| + Alerts | 11 | ~3.0 GB |
| + Monitoring | 16 | ~3.6 GB |
| + Analytics | 17 | ~4.3 GB |
| Full stack | 18 | ~4.5 GB |

## Security Considerations

The Service Manager has access to the Docker socket. For production:

1. **Network isolation** - Only expose on internal network
2. **Authentication** - Add auth middleware to `/services/*` endpoints
3. **Audit** - Monitor the audit log for unauthorized actions
4. **Read-only socket** - Docker socket is mounted read-only by default

### Adding Authentication (Example)

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("SERVICE_MANAGER_API_KEY", "your-secret-key")
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

# Add to router
@router.post("/start/{group}", dependencies=[Depends(verify_api_key)])
```

## Rebuilding Query API

After making changes, rebuild the Query API container:

```bash
docker compose build query-api
docker compose up -d query-api
```

## Troubleshooting

### Dashboard shows "unknown" status

Check if Docker socket is mounted:
```bash
docker exec alpr-query-api ls -la /var/run/docker.sock
```

### Cannot start services

Check if docker-compose.yml is mounted:
```bash
docker exec alpr-query-api cat /home/jetson/OVR-ALPR/docker-compose.yml | head
```

### Permission denied on Docker socket

Add query-api user to docker group or run container as root (not recommended for production).

## Integration with Grafana

The Service Manager status can be scraped by Prometheus:

```yaml
# In prometheus.yml
- job_name: 'service-manager'
  static_configs:
    - targets: ['query-api:8000']
  metrics_path: '/metrics'
```

Custom metrics are exposed via the standard FastAPI Prometheus instrumentator.
