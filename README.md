# Real-Time Vehicle & Plate Recognition System (ALPR)

Enterprise-grade, modular, GPU-accelerated ALPR pipeline for vehicle detection, license plate recognition, and analytics.

## Architecture

### Hybrid Edge-Core Architecture

**Edge Layer (GPU Nodes):**
- RTSP ingestion via ONVIF
- YOLOv11 vehicle + plate detection (DeepStream/TensorRT)
- PaddleOCR text extraction
- Object tracking (ByteTrack/NvDCF)
- Metadata enrichment
- Event deduplication
- S3/MinIO upload
- Kafka/MQTT publishing

**Core Layer (Cloud/Server):**
- Kafka event ingestion
- PostgreSQL/TimescaleDB storage
- OpenSearch for fuzzy search
- MinIO/S3 object storage
- Grafana/Kibana dashboards
- Alert service for hotlist matching

## Technology Stack

| Layer         | Technology                  |
|---------------|-----------------------------|
| Detection     | YOLOv11 (Ultralytics)       |
| Acceleration  | NVIDIA DeepStream/TensorRT  |
| OCR           | PaddleOCR (80+ languages)   |
| Tracking      | ByteTrack/NvDCF             |
| Database      | PostgreSQL + TimescaleDB    |
| Search        | OpenSearch                  |
| Storage       | MinIO / S3                  |
| Messaging     | Apache Kafka                |
| Cache         | Redis                       |
| Monitoring    | Prometheus + Grafana        |
| Tracing       | Jaeger                      |
| API           | FastAPI                     |
| Orchestration | Docker Compose + Kubernetes |

## Services

### 1. Detector Service
- **Role:** YOLOv11 inference via DeepStream/Triton
- **Scale:** GPU nodes (autoscale with K8s)
- **Tech:** Python/C++ (DeepStream SDK)

### 2. OCR Service
- **Role:** PaddleOCR with batch processing
- **Scale:** CPU/GPU nodes (autoscale)
- **Tech:** Python, PaddleOCR

### 3. Tracker Service
- **Role:** Multi-object tracking (ByteTrack/NvDCF)
- **Scale:** Stateful service
- **Tech:** Python/C++

### 4. Event Processor Service
- **Role:** Deduplication, enrichment, publishing
- **Scale:** Horizontal scaling
- **Tech:** Python, Kafka

### 5. Storage Service
- **Role:** Object storage for crops
- **Scale:** MinIO cluster
- **Pattern:** `s3://alpr/{site}/{camera}/{YYYY}/{MM}/{DD}/{HHmmss}_{event_id}.jpg`

### 6. API Service
- **Role:** REST API for queries and idempotent writes
- **Scale:** Horizontal scaling
- **Tech:** FastAPI, PostgreSQL

### 7. Database Service
- **Role:** Event metadata storage
- **Tech:** PostgreSQL/TimescaleDB

## Processing Pipeline

```
RTSP Stream
    ↓
[Decoder] → Resize frames (960×544)
    ↓
[YOLOv11 Detection] → Vehicles + Plates
    ↓
[Tracking] → Assign track_id (ByteTrack/NvDCF)
    ↓
[OCR] → PaddleOCR on plate ROI → Normalize text → Validate regex
    ↓
[Attribute Detection] → Color, make, model (once per track)
    ↓
[Event Assembly] → {timestamp, camera_id, track_id, plate, confidence, ...}
    ↓
[Deduplication] → Skip duplicates (same track_id/plate within X seconds)
    ↓
[Crop Storage] → Upload to S3/MinIO
    ↓
[Publish] → Kafka/MQTT event
    ↓
[Persist] → PostgreSQL + OpenSearch indexing
    ↓
[Visualize] → Grafana/Kibana dashboards
```

## Quick Start

### Prerequisites
- NVIDIA GPU with CUDA 11.8+
- Docker + Docker Compose
- Kubernetes (optional, for production)
- Python 3.10+

### Development Setup

```bash
# Clone repository
git clone <repo-url>
cd OVR-ALPR

# Build and start services
docker-compose up -d

# Check service health
docker-compose ps
```

### Production Deployment

```bash
# Deploy with Kubernetes + Helm
helm install alpr ./infrastructure/helm/alpr-chart

# Scale detector pods
kubectl scale deployment detector-service --replicas=3
```

## Configuration

All configuration is in `config/`:
- `cameras.yaml` - Camera definitions (RTSP URLs, locations)
- `detection.yaml` - YOLOv11 model config
- `ocr.yaml` - PaddleOCR settings
- `validation.yaml` - Plate regex patterns per country
- `deduplication.yaml` - Dedup rules and timeouts

## Event Schema

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-10-17T08:45:23.123Z",
  "camera_id": "CAM-001",
  "location": "Main Gate",
  "track_id": 42,
  "plate": {
    "text": "ABC1234",
    "confidence": 0.92,
    "bbox": [120, 340, 280, 380],
    "crop_url": "s3://alpr/site1/cam1/2025/10/17/084523_550e8400.jpg"
  },
  "vehicle": {
    "type": "car",
    "color": "blue",
    "make": "Toyota",
    "model": "Camry",
    "bbox": [100, 200, 500, 600],
    "crop_url": "s3://alpr/site1/cam1/2025/10/17/084523_550e8400_vehicle.jpg"
  }
}
```

## Quality & Optimization

- **Confidence Threshold:** 0.75 minimum for plate detection
- **Batch Inference:** OCR processes multiple plates in batches
- **Run Once Per Track:** Heavy models (make/model) run once per track_id
- **Deduplication:** Skip same plate within 10 seconds
- **GPU Precision:** FP16/INT8 for faster inference
- **Idempotent Writes:** Safe to replay events

## Monitoring

- **Metrics:** Prometheus scraping from all services
- **Dashboards:** Grafana (detection rate, latency, accuracy)
- **Tracing:** Jaeger for end-to-end request tracing
- **Logs:** Centralized logging with Loki/ELK

## Development

```bash
# Run tests
pytest tests/

# Lint code
black services/ shared/
flake8 services/ shared/

# Type checking
mypy services/ shared/
```

## License

Proprietary - Enterprise Use Only

## Authors

- Project Lead: Azhundev
- AI Assistant: Claude Code
