# MLflow Model Registry

**Service:** `alpr-mlflow`
**Port:** 5000
**UI:** http://localhost:5000

MLflow Model Registry provides model versioning, experiment tracking, and deployment automation for the ALPR system.

---

## Quick Start

### 1. Start MLflow Service

```bash
# Start MLflow with dependencies
docker compose up -d mlflow

# Verify service is healthy
curl http://localhost:5000/health

# Check logs
docker logs -f alpr-mlflow
```

### 2. Register Existing Models

```bash
# Register current YOLO models to MLflow
python scripts/register_existing_models.py
```

### 3. Access MLflow UI

Open http://localhost:5000 in your browser to:
- View registered models
- Browse experiments
- Track model versions
- Promote models between stages

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MLflow Server                          │
│                    (localhost:5000)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐        ┌─────────────────────────┐    │
│  │  Backend Store  │        │    Artifact Store       │    │
│  │  (TimescaleDB)  │        │    (MinIO S3)          │    │
│  │                 │        │                         │    │
│  │  - Experiments  │        │  - Model Files (.pt)   │    │
│  │  - Runs         │        │  - TensorRT (.engine)  │    │
│  │  - Metrics      │        │  - Training Artifacts  │    │
│  │  - Parameters   │        │  - Plots & Configs     │    │
│  └────────┬────────┘        └───────────┬─────────────┘    │
│           │                             │                   │
│           └──────────────┬──────────────┘                   │
│                          │                                  │
└──────────────────────────┼──────────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            │                             │
    ┌───────▼───────┐            ┌────────▼────────┐
    │  Edge Pilot   │            │  Training Jobs  │
    │  (detector)   │            │  (train script) │
    │               │            │                 │
    │ Load models   │            │ Log experiments │
    │ from registry │            │ Register models │
    └───────────────┘            └─────────────────┘
```

---

## Model Stages

MLflow uses stages to manage model lifecycle:

| Stage | Description | Use Case |
|-------|-------------|----------|
| **None** | Just registered, not deployed | Initial upload, testing |
| **Staging** | Under validation/testing | Pre-production testing |
| **Production** | Active in deployment | Live inference |
| **Archived** | Previous versions, kept for history | Rollback capability |

### Stage Transitions

```
None → Staging → Production → Archived
         ↑           │
         └───────────┘ (rollback)
```

---

## Registered Models

### alpr-vehicle-detector

- **Description:** YOLOv11 vehicle detector trained on COCO dataset
- **Classes:** car, truck, bus, motorcycle
- **Files:** `.pt` (PyTorch), `.engine` (TensorRT), `.onnx` (ONNX)
- **Usage:** Detects vehicles in video frames

### alpr-plate-detector

- **Description:** Custom YOLOv11 license plate detector
- **Classes:** license_plate
- **Files:** `.pt` (PyTorch), `.engine` (TensorRT), `.onnx` (ONNX)
- **Usage:** Detects license plates within vehicle bounding boxes

---

## Training with MLflow

### Basic Training

```bash
# Train plate detector with MLflow tracking
python scripts/train_with_mlflow.py \
    --data plates.yaml \
    --model yolo11n.pt \
    --epochs 100 \
    --name plate-detector

# Train and register to model registry
python scripts/train_with_mlflow.py \
    --data plates.yaml \
    --epochs 100 \
    --name plate-detector \
    --register \
    --stage Staging
```

### Training Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--data` | (required) | Path to data YAML file |
| `--model` | yolo11n.pt | Base model for training |
| `--epochs` | 100 | Number of training epochs |
| `--imgsz` | 640 | Input image size |
| `--batch` | 16 | Batch size |
| `--device` | 0 | CUDA device |
| `--lr0` | 0.01 | Initial learning rate |
| `--optimizer` | AdamW | Optimizer (SGD, Adam, AdamW) |
| `--register` | false | Register model after training |
| `--stage` | Staging | Initial model stage |

### What Gets Logged

**Parameters:**
- epochs, batch_size, imgsz, learning_rate
- optimizer, augmentation settings
- data config path, base model

**Metrics:**
- mAP50, mAP50-95
- precision, recall
- box_loss, cls_loss, dfl_loss (per epoch)

**Artifacts:**
- `model/best.pt` - Best model weights
- `model/last.pt` - Final model weights
- `plots/` - Training curves, confusion matrix
- `config/args.yaml` - Training configuration

---

## Loading Models from MLflow

### In Detector Service

The detector automatically loads from MLflow when available:

```python
from edge_services.detector.detector_service import YOLOv11Detector

# With MLflow (default)
detector = YOLOv11Detector(
    vehicle_model_path="yolo11n.pt",
    plate_model_path="yolo11n-plate.pt",
    use_mlflow=True,
    mlflow_tracking_uri="http://localhost:5000"
)

# Without MLflow (local files only)
detector = YOLOv11Detector(
    vehicle_model_path="models/yolo11n.pt",
    plate_model_path="models/yolo11n-plate.pt",
    use_mlflow=False
)
```

### Direct Model Loading

```python
from edge_services.detector.mlflow_model_loader import MLflowModelLoader

loader = MLflowModelLoader(
    tracking_uri="http://localhost:5000",
    preferred_stage="Production"
)

# Load production model
path, metadata = loader.get_model_path(
    "alpr-plate-detector",
    fallback_filename="yolo11n-plate.pt"
)

print(f"Loaded from: {metadata['source']}")  # 'mlflow' or 'local'
print(f"Version: {metadata.get('version', 'N/A')}")
```

---

## Model Promotion Workflow

### 1. Register New Model Version

```bash
# After training completes
python scripts/train_with_mlflow.py \
    --data plates.yaml \
    --epochs 100 \
    --register \
    --stage None
```

### 2. Promote to Staging

```python
import mlflow
from mlflow.tracking import MlflowClient

client = MlflowClient("http://localhost:5000")

# Get latest version
versions = client.get_latest_versions("alpr-plate-detector")
latest = versions[0]

# Promote to Staging
client.transition_model_version_stage(
    name="alpr-plate-detector",
    version=latest.version,
    stage="Staging"
)
```

### 3. Test in Staging

```bash
# Run detector with staging model
export MLFLOW_MODEL_STAGE=Staging
python pilot.py --config config/cameras.yaml
```

### 4. Promote to Production

```python
# After validation
client.transition_model_version_stage(
    name="alpr-plate-detector",
    version=latest.version,
    stage="Production",
    archive_existing_versions=True  # Archive old production version
)
```

---

## API Reference

### List Registered Models

```bash
curl http://localhost:5000/api/2.0/mlflow/registered-models/list | jq
```

### Get Model Versions

```bash
curl "http://localhost:5000/api/2.0/mlflow/registered-models/get?name=alpr-plate-detector" | jq
```

### Get Latest Version by Stage

```bash
curl "http://localhost:5000/api/2.0/mlflow/registered-models/get-latest-versions?name=alpr-plate-detector&stages=Production" | jq
```

### Search Experiments

```bash
curl http://localhost:5000/api/2.0/mlflow/experiments/search | jq
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MLFLOW_TRACKING_URI` | http://localhost:5000 | MLflow server URL |
| `MLFLOW_S3_ENDPOINT_URL` | http://minio:9000 | MinIO endpoint for artifacts |
| `AWS_ACCESS_KEY_ID` | alpr_minio | MinIO access key |
| `AWS_SECRET_ACCESS_KEY` | alpr_minio_secure_pass_2024 | MinIO secret key |

---

## Monitoring

### Grafana Dashboard

Access the Model Registry dashboard at:
http://localhost:3000/d/alpr-model-registry

Panels include:
- MLflow server status
- Model inference FPS
- Inference latency
- Detection confidence metrics
- Resource usage

### Health Check

```bash
# MLflow health
curl http://localhost:5000/health

# Check MLflow container
docker ps | grep mlflow
docker logs alpr-mlflow --tail 50
```

---

## Troubleshooting

### MLflow Won't Start

```bash
# Check if dependencies are running
docker compose ps timescaledb minio

# Check MLflow logs
docker logs alpr-mlflow

# Verify database exists
docker exec alpr-timescaledb psql -U alpr -c "\l" | grep mlflow
```

### Can't Connect to MLflow

```bash
# Verify port is accessible
curl http://localhost:5000/health

# Check network
docker network inspect alpr-network | grep mlflow
```

### Models Not Loading from MLflow

```python
# Test loader directly
from edge_services.detector.mlflow_model_loader import MLflowModelLoader

loader = MLflowModelLoader()
print(f"Connected: {loader._mlflow_connected}")
print(f"Models: {loader.list_models()}")
```

### Artifacts Not Uploading to MinIO

```bash
# Check MinIO bucket exists
docker exec alpr-minio-init mc ls minio/alpr-mlflow-artifacts

# Verify MinIO credentials
docker exec alpr-mlflow env | grep AWS
```

---

## Storage

### Backend Store (TimescaleDB)

- **Database:** `mlflow_db`
- **User:** `mlflow`
- **Tables:** Experiments, runs, metrics, params, tags

### Artifact Store (MinIO)

- **Bucket:** `alpr-mlflow-artifacts`
- **Structure:**
  ```
  alpr-mlflow-artifacts/
  ├── {experiment_id}/
  │   └── {run_id}/
  │       └── artifacts/
  │           ├── model/
  │           │   ├── best.pt
  │           │   └── last.pt
  │           └── plots/
  │               └── *.png
  ```

---

## Resource Requirements

| Resource | Allocation |
|----------|------------|
| CPU | 0.6 cores |
| Memory | 600 MB |
| Storage | Shared with MinIO |

---

## Related Documentation

- **[Model Training Guide](./model-training-guide.md)** - Complete guide for training YOLO and PaddleOCR models
- [Detector Service](../ALPR_Pipeline/SERVICES_OVERVIEW.md#detector-service)
- [MinIO Object Storage](./minio-setup.md)
- [Grafana Dashboards](./grafana-dashboards.md)
- [Model Quantization](../../optimizations/MODEL_QUANTIZATION.md)
- [Project Status](../alpr/project-status.md)
