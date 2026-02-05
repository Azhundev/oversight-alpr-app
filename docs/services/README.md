# Services Documentation

Documentation for all ALPR backend services organized by category.

---

## Directory Structure

```
docs/services/
├── Alerts/           # Alert engine and notifications
├── Infrastructure/   # Service management and startup
├── Kafka/            # Message streaming and schema registry
├── MLFlow/           # Model registry and training
├── Monitoring/       # Grafana, Prometheus, Loki
├── Search/           # OpenSearch full-text search
├── Storage/          # TimescaleDB, MinIO, Metabase
├── TensorRT/         # Model optimization and export
└── Testing/          # Test results and validations
```

---

## Quick Links

### Kafka/ - Message Streaming
| Document | Description |
|----------|-------------|
| [kafka-setup.md](Kafka/kafka-setup.md) | Complete Kafka setup guide |
| [kafka-quickstart.md](Kafka/kafka-quickstart.md) | Quick start commands |
| [SCHEMA_REGISTRY_IMPLEMENTATION.md](Kafka/SCHEMA_REGISTRY_IMPLEMENTATION.md) | Avro schema registry |
| [INTEGRATION_COMPLETE...md](Kafka/INTEGRATION_COMPLETE%20Kafka%20+%20Event%20Processing.md) | Kafka integration summary |

### Monitoring/ - Observability Stack
| Document | Description |
|----------|-------------|
| [monitoring-stack-setup.md](Monitoring/monitoring-stack-setup.md) | Prometheus, Grafana, Loki setup |
| [grafana-dashboards.md](Monitoring/grafana-dashboards.md) | Dashboard configuration |
| [grafana-dashboard-fixes.md](Monitoring/grafana-dashboard-fixes.md) | Dashboard troubleshooting |
| [monitoring-stack-test-results.md](Monitoring/monitoring-stack-test-results.md) | Validation results |

### Storage/ - Data Persistence
| Document | Description |
|----------|-------------|
| [storage-layer.md](Storage/storage-layer.md) | TimescaleDB and storage architecture |
| [metabase-setup.md](Storage/metabase-setup.md) | Business intelligence setup |
| [minio.html](Storage/minio.html) | MinIO object storage |

### Search/ - Full-Text Search
| Document | Description |
|----------|-------------|
| [OpenSearch_Integration.md](Search/OpenSearch_Integration.md) | OpenSearch setup and API |
| [opensearch-dashboards-setup.md](Search/opensearch-dashboards-setup.md) | Dashboards configuration |

### Alerts/ - Notifications
| Document | Description |
|----------|-------------|
| [alert-engine.md](Alerts/alert-engine.md) | Alert rules and channels |

### MLFlow/ - Model Management
| Document | Description |
|----------|-------------|
| [mlflow-model-registry.md](MLFlow/mlflow-model-registry.md) | Model versioning and deployment |
| [model-training-guide.md](MLFlow/model-training-guide.md) | Training YOLO and PaddleOCR |

### TensorRT/ - Model Optimization
| Document | Description |
|----------|-------------|
| [TENSORRT_EXPORT.md](TensorRT/TENSORRT_EXPORT.md) | Export models to TensorRT |
| [tensorrt-engine-rebuild.md](TensorRT/tensorrt-engine-rebuild.md) | Rebuild engines for Jetson |
| [PT_VS_ENGINE_COMPARISON.md](TensorRT/PT_VS_ENGINE_COMPARISON.md) | PyTorch vs TensorRT comparison |
| [OCR_TRAINING_GUIDE.md](TensorRT/OCR_TRAINING_GUIDE.md) | OCR model training |
| [OCR_FP16_ATTEMPT.md](TensorRT/OCR_FP16_ATTEMPT.md) | OCR FP16 optimization |

### Infrastructure/ - Service Management
| Document | Description |
|----------|-------------|
| [incremental-startup.md](Infrastructure/incremental-startup.md) | RAM-aware service startup |
| [service-manager.md](Infrastructure/service-manager.md) | Service control API |
| [event-processor-service.md](Infrastructure/event-processor-service.md) | Event processing pipeline |
| [Traffic_Enforcement_Camera_Systems.md](Infrastructure/Traffic_Enforcement_Camera_Systems.md) | Reference architecture |

### Testing/ - Validation Results
| Document | Description |
|----------|-------------|
| [LIVE_PILOT_TEST_RESULTS.md](Testing/LIVE_PILOT_TEST_RESULTS.md) | Live inference test |
| [EDGE_CORE_MIGRATION_TEST_RESULTS.md](Testing/EDGE_CORE_MIGRATION_TEST_RESULTS.md) | Directory migration test |
| [blur-filtering-test-results.md](Testing/blur-filtering-test-results.md) | Blur detection validation |
| [auto-reconnection-test.md](Testing/auto-reconnection-test.md) | Camera reconnection test |
| [plate-detection-input-size-analysis.md](Testing/plate-detection-input-size-analysis.md) | Input size optimization |

---

## Service Ports Reference

| Service | Port | URL |
|---------|------|-----|
| Query API | 8000 | http://localhost:8000/docs |
| Grafana | 3000 | http://localhost:3000 |
| Prometheus | 9090 | http://localhost:9090 |
| Loki | 3100 | http://localhost:3100 |
| Tempo | 3200 | http://localhost:3200 |
| MLflow | 5000 | http://localhost:5000 |
| Kafka UI | 8080 | http://localhost:8080 |
| MinIO Console | 9001 | http://localhost:9001 |
| OpenSearch | 9200 | http://localhost:9200 |
| Metabase | 3001 | http://localhost:3001 |

---

## Related Documentation

- [Project Architecture](../alpr/project-architecture-chart.md)
- [Port Reference](../alpr/port-reference.md)
- [Quick Reference](../deployment/quick-reference.md)
