# Scripts

Utility scripts for the ALPR system organized by category.

---

## Directory Structure

```
scripts/
├── database/      # Database initialization and migrations
├── kafka/         # Kafka setup and schema registry
├── mlflow/        # MLflow model registration
├── opencv/        # OpenCV build scripts for Jetson
├── tensorrt/      # TensorRT model export and optimization
├── testing/       # Benchmarks and validation scripts
├── training/      # Data collection and model training
└── utilities/     # System utilities and helpers
```

---

## Quick Reference

### database/ - Database Scripts

| Script | Description |
|--------|-------------|
| `init_db.sql` | Initialize TimescaleDB schema and hypertables |
| `init_mlflow_db.sql` | Create MLflow database and user |
| `add_created_at_index.sql` | Add index for timestamp queries |

```bash
# Run database initialization
docker exec -i alpr-timescaledb psql -U alpr -d alpr < scripts/database/init_db.sql
```

### kafka/ - Message Streaming

| Script | Description |
|--------|-------------|
| `setup_kafka.sh` | Initialize Kafka topics and configuration |
| `register_schemas.py` | Register Avro schemas with Schema Registry |
| `test_schema_registry.py` | Validate schema registration |

```bash
# Setup Kafka topics
./scripts/kafka/setup_kafka.sh

# Register schemas
python scripts/kafka/register_schemas.py
```

### mlflow/ - Model Registry

| Script | Description |
|--------|-------------|
| `register_existing_models.py` | Register current models to MLflow registry |

```bash
# Register models from models/ directory
python scripts/mlflow/register_existing_models.py
```

### opencv/ - OpenCV Build

| Script | Description |
|--------|-------------|
| `build_opencv_gstreamer.sh` | Build OpenCV with GStreamer support for Jetson |
| `check_opencv_build.sh` | Verify OpenCV installation |
| `monitor_opencv_build.sh` | Monitor build progress |

```bash
# Build OpenCV with GStreamer (takes ~2 hours on Jetson)
./scripts/opencv/build_opencv_gstreamer.sh
```

### tensorrt/ - Model Optimization

| Script | Description |
|--------|-------------|
| `rebuild_tensorrt_engines.py` | Rebuild TensorRT engines for current GPU |
| `rebuild_tensorrt_engines.sh` | Shell wrapper for engine rebuild |
| `export_int8_engine.py` | Export INT8 quantized engines |
| `patch_ultralytics.py` | Patch Ultralytics for TensorRT compatibility |
| `patch_ultralytics_tensorrt.sh` | Apply TensorRT patches |

```bash
# Rebuild TensorRT engines
python scripts/tensorrt/rebuild_tensorrt_engines.py

# Export INT8 engine with calibration
python scripts/tensorrt/export_int8_engine.py --model models/yolo11n-plate.pt --calibration-data data/calibration/
```

### testing/ - Benchmarks

| Script | Description |
|--------|-------------|
| `benchmark_plate_detection_sizes.py` | Benchmark different input sizes for plate detection |

```bash
# Run plate detection benchmark
python scripts/testing/benchmark_plate_detection_sizes.py
```

### training/ - Model Training

| Script | Description |
|--------|-------------|
| `collect_training_data.py` | Collect frames from video for training |
| `prepare_calibration_dataset.py` | Prepare dataset for INT8 calibration |
| `prepare_plate_training_data.py` | Format license plate annotations |
| `train_with_mlflow.py` | Train YOLOv11 with MLflow tracking |
| `review_annotations.py` | Review and fix annotations |
| `review_annotations_advanced.py` | Advanced annotation review tool |
| `setup_manual_labeling.sh` | Setup labeling environment |

```bash
# Collect training data from video
python scripts/training/collect_training_data.py --video input.mp4 --output data/frames/

# Train with MLflow tracking
python scripts/training/train_with_mlflow.py --data plates.yaml --epochs 100 --register

# Review annotations
python scripts/training/review_annotations.py --images data/images/ --labels data/labels/
```

### utilities/ - System Helpers

| Script | Description |
|--------|-------------|
| `optimize_memory.sh` | Optimize Jetson memory settings |
| `enable_blur_filtering.py` | Enable/configure blur detection |
| `start_storage_layer.sh` | Start storage services (TimescaleDB, MinIO) |

```bash
# Optimize Jetson memory
sudo ./scripts/utilities/optimize_memory.sh

# Start storage layer
./scripts/utilities/start_storage_layer.sh
```

---

## Related Documentation

- [Model Training Guide](../docs/services/MLFlow/model-training-guide.md)
- [TensorRT Export](../docs/services/TensorRT/TENSORRT_EXPORT.md)
- [Kafka Setup](../docs/services/Kafka/kafka-setup.md)
- [Storage Layer](../docs/services/Storage/storage-layer.md)
