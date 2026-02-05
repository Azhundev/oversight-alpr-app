## Project Instructions for Claude Code

### Documentation
- Always create new .md files inside the `docs/` folder (organized by topic)
- Keep documentation up to date when adding features
- Use existing documentation structure (see docs/ALPR_Pipeline/)

### Model Training
- **YOLOv11 Plate Model**: `models/yolo11n-plate.pt`
  - Training data: License plate images with annotations
  - Retrain using: `yolo detect train data=plates.yaml model=yolo11n.pt epochs=100 imgsz=640`
  - Export to TensorRT: `yolo export model=best.pt format=engine device=0 half=True`

### System Architecture
- **Edge Processing**: `pilot.py` runs on Jetson (detection, tracking, OCR)
- **Core Services**: Docker containers (Kafka, DB, API, Alerts, Monitoring)
- **Configuration**: All YAML files in `config/` directory
- **Service Folder Structure**:
  - `edge_services/`: Edge processing (camera, detector, tracker, ocr, events)
  - `core_services/`: Backend (storage, api, alerting, monitoring)

### Important Ports
- 8000: Query API
- 8001: Pilot metrics (edge)
- 8002: Kafka Consumer metrics
- 8003: Alert Engine metrics
- 8004: Elasticsearch Consumer metrics
- 8080: Kafka UI
- 8081: Schema Registry
- 3000: Grafana
- 3001: Metabase
- 3100: Loki (logs)
- 3200: Tempo (tracing API)
- 4317/4318: Tempo OTLP (gRPC/HTTP)
- 5000: MLflow Model Registry
- 9090: Prometheus
- 9000/9001: MinIO (API/Console)
- 9200/9600: OpenSearch
- 5432: TimescaleDB

### Key Commands
```bash
# Start backend services
docker compose up -d

# Run edge pipeline
python3 pilot.py

# View logs
docker logs -f alpr-kafka-consumer
docker logs -f alpr-alert-engine

# Access services
http://localhost:8000/docs     # API docs
http://localhost:3000           # Grafana dashboards
http://localhost:3200           # Tempo tracing API
http://localhost:5000           # MLflow Model Registry
http://localhost:8080           # Kafka UI
http://localhost:9001           # MinIO Console

# MLflow Model Registry
python scripts/register_existing_models.py  # Register current models
python scripts/train_with_mlflow.py --data plates.yaml --epochs 100  # Train with tracking
```

### Service Dependencies
- Kafka Consumer depends on: Kafka, Schema Registry, TimescaleDB
- Alert Engine depends on: Kafka, Schema Registry
- Elasticsearch Consumer depends on: Kafka, Schema Registry, OpenSearch
- Query API depends on: TimescaleDB, MinIO, OpenSearch, Tempo (optional tracing)
- MLflow depends on: TimescaleDB (backend), MinIO (artifacts)
- Tempo depends on: None (standalone)
- Grafana depends on: Prometheus, Loki, Tempo
- Pilot (edge) publishes to: Kafka (localhost:9092), loads models from MLflow

### Recent Major Changes
- ✅ Added Grafana Tempo for distributed tracing (2026-02-02)
- ✅ Added MLflow Model Registry for model versioning (2026-02-01)
- ✅ Integrated OpenSearch for full-text search and analytics (2025-12-29)
- ✅ Added Elasticsearch Consumer for real-time indexing (2025-12-29)
- ✅ Extended Query API with 4 new search endpoints (2025-12-29)
- ✅ Added Alert Engine with multi-channel notifications (2025-12-28)
- ✅ Completed monitoring stack (Prometheus, Grafana, Loki) (2025-12-28)
- ✅ Added MinIO object storage integration (2025-12-27)
- ✅ Migrated to Avro serialization with Schema Registry (2025-12-26)
- ✅ Implemented TimescaleDB hypertables (2025-12-25)

### Common Tasks
1. **Add new alert rule**: Edit `config/alert_rules.yaml`, restart alert-engine
2. **Add new camera**: Edit `config/cameras.yaml`, restart pilot.py
3. **View metrics**: Check Grafana dashboards at http://localhost:3000
4. **Query events**: Use REST API at http://localhost:8000/docs
5. **Search plates**: Use search endpoints at http://localhost:8000/docs#/default/search_fulltext_search_fulltext_get
6. **Debug Kafka**: Use Kafka UI at http://localhost:8080
7. **Check OpenSearch**: http://localhost:9200/_cluster/health
8. **Register models**: Run `python scripts/register_existing_models.py`
9. **Train with tracking**: Run `python scripts/train_with_mlflow.py --data plates.yaml`
10. **View traces**: Grafana → Explore → Select "Tempo" datasource

### Current System Status
- Phase 6 Priority 12 COMPLETE: Distributed Tracing (Tempo) operational
- Phase 6 Priority 10 COMPLETE: MLflow Model Registry operational
- Phase 4 COMPLETE: OpenSearch, Multi-topic Kafka, Metabase BI
- 16 core services + 7 infrastructure + 7 monitoring services + 1 MLOps
- Tempo at http://localhost:3200 for distributed tracing
- MLflow at http://localhost:5000 for model versioning and experiment tracking
- Next: Phase 5 Scale & Optimization (DeepStream, Triton - optional)