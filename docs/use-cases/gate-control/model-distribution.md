# Model Distribution Guide

**Created:** 2026-02-17
**Purpose:** How to distribute ML models to the team and edge devices
**Related:** [Team Development Guide](team-development-guide.md) | [Project Structure](project-structure.md)

---

## Table of Contents

1. [Overview](#overview)
2. [MLflow Model Registry](#mlflow-model-registry)
3. [Downloading Models](#downloading-models)
4. [Loading Models in Code](#loading-models-in-code)
5. [Model Versioning](#model-versioning)
6. [Offline Deployment](#offline-deployment)

---

## Overview

ML models (YOLO, PaddleOCR) are too large for git. We use **MLflow Model Registry** for:

- Version control for models
- Team access to trained models
- Staging → Production promotion
- Artifact storage with metadata

```
MODEL DISTRIBUTION FLOW
══════════════════════════════════════════════════════════════════

┌─────────────────┐         ┌─────────────────┐
│  Training       │         │  MLflow         │
│  (Your Jetson)  │────────>│  Registry       │
│                 │ register│  :5000          │
└─────────────────┘         └────────┬────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
             ┌───────────┐    ┌───────────┐    ┌───────────┐
             │ Team Dev  │    │ CI/CD     │    │ Edge      │
             │ Laptop    │    │ Pipeline  │    │ Devices   │
             │           │    │           │    │           │
             │ download  │    │ download  │    │ download  │
             └───────────┘    └───────────┘    └───────────┘
```

---

## MLflow Model Registry

### Current Setup (OVR-ALPR)

MLflow is running on your Jetson as part of OVR-ALPR:

| Service | URL | Purpose |
|---------|-----|---------|
| MLflow UI | http://localhost:5000 | Model registry & experiments |
| Artifact Store | MinIO (localhost:9000) | Model file storage |
| Backend | TimescaleDB | Metadata storage |

### Registered Models

| Model | Description | Size |
|-------|-------------|------|
| `yolo11n-plate` | License plate detection | ~5.4 MB |
| `yolo11n-plate-engine` | TensorRT optimized | ~7.9 MB |

---

## Downloading Models

### Option 1: MLflow CLI

```bash
# Set MLflow tracking URI (your Jetson IP)
export MLFLOW_TRACKING_URI=http://192.168.1.100:5000

# Download latest Production model
mlflow artifacts download \
  --artifact-uri models:/yolo11n-plate/Production \
  --dst-path models/

# Download specific version
mlflow artifacts download \
  --artifact-uri models:/yolo11n-plate/1 \
  --dst-path models/
```

### Option 2: Python Script

```python
#!/usr/bin/env python3
"""Download models from MLflow registry."""

import os
import mlflow
from pathlib import Path

# Configure MLflow
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://192.168.1.100:5000")
mlflow.set_tracking_uri(MLFLOW_URI)

def download_model(
    model_name: str = "yolo11n-plate",
    stage: str = "Production",
    dest_dir: str = "models"
):
    """Download a model from MLflow registry."""
    dest_path = Path(dest_dir)
    dest_path.mkdir(exist_ok=True)

    model_uri = f"models:/{model_name}/{stage}"
    print(f"Downloading {model_uri}...")

    local_path = mlflow.artifacts.download_artifacts(
        artifact_uri=model_uri,
        dst_path=str(dest_path)
    )

    print(f"Model downloaded to: {local_path}")
    return local_path

if __name__ == "__main__":
    download_model("yolo11n-plate", "Production")
```

### Option 3: Direct HTTP Download

```bash
# Get model info via API
curl http://192.168.1.100:5000/api/2.0/mlflow/registered-models/get?name=yolo11n-plate

# Download artifact directly (get path from above)
curl -O http://192.168.1.100:5000/get-artifact?path=model/yolo11n-plate.pt
```

---

## Loading Models in Code

### Auto-download from MLflow

```python
# src/alpr_edge/core/detector.py

import os
from pathlib import Path
from typing import Optional

import mlflow

from alpr_edge.config import settings


class PlateDetector:
    """YOLOv11 plate detector with MLflow integration."""

    def __init__(
        self,
        model_path: Optional[Path] = None,
        model_name: str = "yolo11n-plate",
        model_stage: str = "Production",
        device: Optional[str] = None,
    ):
        self.model_name = model_name
        self.model_stage = model_stage
        self.device = device or settings.device
        self.model = None

        # Use local path if provided, otherwise download from MLflow
        if model_path and model_path.exists():
            self.model_path = model_path
        else:
            self.model_path = self._get_model_from_mlflow()

    def _get_model_from_mlflow(self) -> Path:
        """Download model from MLflow if not cached locally."""
        cache_dir = settings.models_dir / self.model_name
        model_file = cache_dir / "yolo11n-plate.pt"

        if model_file.exists():
            return model_file

        # Download from MLflow
        mlflow_uri = os.getenv("MLFLOW_TRACKING_URI")
        if not mlflow_uri:
            raise FileNotFoundError(
                f"Model not found locally and MLFLOW_TRACKING_URI not set"
            )

        mlflow.set_tracking_uri(mlflow_uri)
        model_uri = f"models:/{self.model_name}/{self.model_stage}"

        print(f"Downloading model from MLflow: {model_uri}")
        local_path = mlflow.artifacts.download_artifacts(
            artifact_uri=model_uri,
            dst_path=str(cache_dir)
        )

        return Path(local_path) / "yolo11n-plate.pt"

    def load(self) -> "PlateDetector":
        """Load the YOLO model."""
        from ultralytics import YOLO
        self.model = YOLO(str(self.model_path))
        return self
```

### Environment Configuration

```bash
# .env for development
MLFLOW_TRACKING_URI=http://192.168.1.100:5000
ALPR_MODELS_DIR=models

# .env for production (models pre-installed)
ALPR_MODELS_DIR=/opt/alpr-edge/models
```

---

## Model Versioning

### Stages

| Stage | Purpose | Who Uses |
|-------|---------|----------|
| **None** | Newly registered | Testing only |
| **Staging** | Ready for QA | CI/CD, test deployments |
| **Production** | Validated, stable | All edge devices |
| **Archived** | Deprecated | None |

### Promoting a Model

```python
from mlflow import MlflowClient

client = MlflowClient()

# Promote from Staging to Production
client.transition_model_version_stage(
    name="yolo11n-plate",
    version=2,
    stage="Production"
)
```

### Version History

```bash
# List all versions
mlflow models list --name yolo11n-plate

# Get version details
mlflow models get-version --name yolo11n-plate --version 2
```

---

## Offline Deployment

For edge devices without MLflow access:

### Pre-package Models

```bash
#!/bin/bash
# scripts/package_models.sh

MODEL_DIR="deployment_models"
mkdir -p $MODEL_DIR

# Download from MLflow
export MLFLOW_TRACKING_URI=http://localhost:5000
mlflow artifacts download \
  --artifact-uri models:/yolo11n-plate/Production \
  --dst-path $MODEL_DIR/

# Create archive
tar -czvf models-$(date +%Y%m%d).tar.gz $MODEL_DIR/

echo "Models packaged: models-$(date +%Y%m%d).tar.gz"
```

### Include in Docker Image

```dockerfile
# docker/Dockerfile
FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3

# Copy pre-downloaded models
COPY models/yolo11n-plate.pt /app/models/
COPY models/yolo11n-plate.engine /app/models/

# ... rest of Dockerfile
```

### Device Provisioning

```bash
#!/bin/bash
# scripts/provision.sh

# Download models during device setup
export MLFLOW_TRACKING_URI=$PORTAL_URL:5000

python3 << 'EOF'
import mlflow
mlflow.artifacts.download_artifacts(
    artifact_uri="models:/yolo11n-plate/Production",
    dst_path="/opt/alpr-edge/models"
)
EOF
```

---

## Team Workflow

### For Developers (No GPU)

```bash
# Don't need actual model for most development
# Use mock detector instead
export ALPR_MOCK_DETECTOR=true
python -m alpr_edge.main --demo
```

### For Integration Testing

```bash
# Download model once
export MLFLOW_TRACKING_URI=http://192.168.1.100:5000
python scripts/download_models.py

# Run with real model (CPU mode)
ALPR_DEVICE=cpu python -m alpr_edge.main
```

### For Edge Deployment

```bash
# Models downloaded during provisioning
# or baked into Docker image
docker compose up -d
```

---

## Quick Reference

```bash
# Set MLflow URI
export MLFLOW_TRACKING_URI=http://192.168.1.100:5000

# Download production model
mlflow artifacts download -u models:/yolo11n-plate/Production -d models/

# List registered models
mlflow models list

# Python download
python -c "
import mlflow
mlflow.set_tracking_uri('http://192.168.1.100:5000')
mlflow.artifacts.download_artifacts('models:/yolo11n-plate/Production', 'models/')
"
```

---

## Related Documentation

- [Team Development Guide](team-development-guide.md) - Testing without Jetson
- [Project Structure](project-structure.md) - Repository layout
- [GitHub Setup Guide](github-setup-guide.md) - Repository setup
- [MLflow Documentation](../../alpr/ALPR_Pipeline/mlflow-model-registry.md) - Full MLflow setup
