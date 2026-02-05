# Model Training Guide

Complete guide for training ALPR models (YOLOv11 detection + PaddleOCR) with and without MLflow tracking.

**Related:** [MLflow Model Registry](./mlflow-model-registry.md)

---

## Overview

| Model | Framework | Purpose | Current File |
|-------|-----------|---------|--------------|
| Vehicle Detector | YOLOv11 (Ultralytics) | Detect cars, trucks, buses | `models/yolo11n.pt` |
| Plate Detector | YOLOv11 (Ultralytics) | Detect license plates | `models/yolo11n-plate.pt` |
| Plate OCR | PaddleOCR | Read plate text | PaddleOCR pretrained |

---

## 1. Dataset Preparation

### YOLO Dataset Structure

```
datasets/plates/
├── images/
│   ├── train/
│   │   ├── img_001.jpg
│   │   ├── img_002.jpg
│   │   └── ...
│   └── val/
│       ├── img_100.jpg
│       └── ...
├── labels/
│   ├── train/
│   │   ├── img_001.txt
│   │   ├── img_002.txt
│   │   └── ...
│   └── val/
│       ├── img_100.txt
│       └── ...
└── plates.yaml
```

### Label Format (YOLO)

Each `.txt` file contains one line per object:
```
class_id x_center y_center width height
```

All values are **normalized (0-1)** relative to image dimensions.

**Example:** `img_001.txt`
```
0 0.4531 0.6250 0.1200 0.0800
0 0.7812 0.5400 0.0950 0.0650
```

**Calculation:**
```
x_center = (bbox_x + bbox_width/2) / image_width
y_center = (bbox_y + bbox_height/2) / image_height
width = bbox_width / image_width
height = bbox_height / image_height
```

### Dataset Config File

Create `datasets/plates/plates.yaml`:
```yaml
# Dataset paths (relative to this file or absolute)
path: /home/jetson/OVR-ALPR/datasets/plates
train: images/train
val: images/val

# Classes
nc: 1  # number of classes
names: ['license_plate']

# Optional: test set
# test: images/test
```

### Vehicle Detection Dataset

For vehicle detection, use COCO format or custom:
```yaml
# datasets/vehicles/vehicles.yaml
path: /home/jetson/OVR-ALPR/datasets/vehicles
train: images/train
val: images/val

nc: 4
names: ['car', 'truck', 'bus', 'motorcycle']
```

---

## 2. Labeling Tools

### LabelImg (Recommended for Quick Start)

```bash
# Install
pip install labelImg

# Launch
labelImg datasets/plates/images/train datasets/plates/classes.txt

# In GUI:
# 1. Change save format to YOLO (View → Change Save Format)
# 2. Open Dir → select images folder
# 3. Change Save Dir → select labels folder
# 4. Draw bounding boxes, press 'w' for new box
# 5. Save with Ctrl+S
```

Create `classes.txt`:
```
license_plate
```

### CVAT (Web-Based, Team Collaboration)

```bash
# Run CVAT with Docker
git clone https://github.com/opencv/cvat
cd cvat
docker compose up -d

# Access at http://localhost:8080
# Export annotations in YOLO format
```

### Roboflow (Cloud + Auto-Labeling)

1. Upload images to https://roboflow.com
2. Use auto-labeling or manual annotation
3. Apply augmentations
4. Export in YOLOv8 format (compatible with YOLOv11)

### Label Studio (Multi-Format)

```bash
pip install label-studio
label-studio start

# Access at http://localhost:8080
# Create project with Object Detection template
# Export as YOLO format
```

---

## 3. Training YOLOv11

### Basic Training (Without MLflow)

```bash
# Train plate detector
yolo detect train \
    data=datasets/plates/plates.yaml \
    model=yolo11n.pt \
    epochs=100 \
    imgsz=640 \
    batch=16 \
    device=0 \
    project=runs/train \
    name=plate_detector

# Results saved to runs/train/plate_detector/
```

### Training with MLflow Tracking

```bash
# Train with experiment tracking (recommended)
python scripts/training/train_with_mlflow.py \
    --data datasets/plates/plates.yaml \
    --model yolo11n.pt \
    --epochs 100 \
    --batch 16 \
    --imgsz 640 \
    --name plate-detector-v2

# View results at http://localhost:5000
```

### Training Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `data` | (required) | Path to dataset YAML |
| `model` | yolo11n.pt | Base model (n/s/m/l/x) |
| `epochs` | 100 | Training epochs |
| `imgsz` | 640 | Input image size |
| `batch` | 16 | Batch size (-1 for auto) |
| `device` | 0 | CUDA device (0, 1, or cpu) |
| `workers` | 8 | Dataloader workers |
| `patience` | 50 | Early stopping patience |
| `lr0` | 0.01 | Initial learning rate |
| `lrf` | 0.01 | Final learning rate factor |
| `optimizer` | AdamW | Optimizer (SGD, Adam, AdamW) |
| `augment` | True | Enable augmentation |
| `cache` | False | Cache images (ram/disk) |
| `resume` | False | Resume from checkpoint |

### Model Variants

| Model | Size | mAP | Speed (Jetson) | Use Case |
|-------|------|-----|----------------|----------|
| `yolo11n.pt` | 6 MB | 39.5 | 15-20 FPS | **Recommended** for Jetson |
| `yolo11s.pt` | 22 MB | 47.0 | 10-15 FPS | Better accuracy |
| `yolo11m.pt` | 68 MB | 51.5 | 5-8 FPS | High accuracy |
| `yolo11l.pt` | 87 MB | 53.4 | 3-5 FPS | Maximum accuracy |

---

## 4. Export to TensorRT

### Export Best Model

```bash
# Export to TensorRT FP16 (recommended for Jetson)
yolo export \
    model=runs/train/plate_detector/weights/best.pt \
    format=engine \
    device=0 \
    half=True \
    imgsz=640

# Output: runs/train/plate_detector/weights/best.engine
```

### Export Options

| Option | Value | Description |
|--------|-------|-------------|
| `format` | engine | TensorRT engine |
| `half` | True | FP16 precision (2x faster) |
| `int8` | False | INT8 precision (unstable on Jetson) |
| `dynamic` | False | Dynamic input shapes |
| `simplify` | True | ONNX simplification |
| `workspace` | 4 | GPU workspace (GB) |
| `batch` | 1 | Batch size |

### Deploy to Models Folder

```bash
# Copy to models folder
cp runs/train/plate_detector/weights/best.engine models/yolo11n-plate.engine
cp runs/train/plate_detector/weights/best.pt models/yolo11n-plate.pt

# Test with pilot
python pilot.py
```

---

## 5. Data Augmentation

### Built-in YOLO Augmentations

YOLO applies these automatically during training:
- Mosaic (4-image combination)
- MixUp (image blending)
- HSV color jitter
- Random flip, scale, translate

### Custom Augmentation with Albumentations

```python
import albumentations as A
import cv2

# Define augmentation pipeline
transform = A.Compose([
    # Lighting variations
    A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.5),
    A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=30, val_shift_limit=30, p=0.3),

    # Noise and blur (simulate camera quality)
    A.GaussNoise(var_limit=(10, 50), p=0.3),
    A.MotionBlur(blur_limit=5, p=0.2),
    A.GaussianBlur(blur_limit=3, p=0.1),

    # Weather conditions
    A.RandomRain(slant_lower=-10, slant_upper=10, drop_length=20, p=0.1),
    A.RandomFog(fog_coef_lower=0.1, fog_coef_upper=0.3, p=0.1),
    A.RandomSunFlare(src_radius=100, p=0.1),

    # Geometric (small rotations only for plates)
    A.Rotate(limit=5, p=0.3),
    A.Perspective(scale=(0.02, 0.05), p=0.2),

], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))

# Apply augmentation
def augment_image(image_path, label_path, output_dir, num_augmented=5):
    image = cv2.imread(image_path)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Read YOLO labels
    with open(label_path, 'r') as f:
        labels = [line.strip().split() for line in f.readlines()]

    bboxes = [[float(x) for x in label[1:]] for label in labels]
    class_labels = [int(label[0]) for label in labels]

    for i in range(num_augmented):
        transformed = transform(image=image, bboxes=bboxes, class_labels=class_labels)
        # Save augmented image and labels...
```

### Augmentation Script

Create `scripts/augment_dataset.py`:
```python
#!/usr/bin/env python3
"""Augment plate detection dataset"""
import os
import cv2
import albumentations as A
from pathlib import Path
from tqdm import tqdm

def main():
    input_dir = Path("datasets/plates/images/train")
    label_dir = Path("datasets/plates/labels/train")
    output_img_dir = Path("datasets/plates/images/train_aug")
    output_label_dir = Path("datasets/plates/labels/train_aug")

    output_img_dir.mkdir(parents=True, exist_ok=True)
    output_label_dir.mkdir(parents=True, exist_ok=True)

    transform = A.Compose([
        A.RandomBrightnessContrast(p=0.5),
        A.GaussNoise(p=0.3),
        A.MotionBlur(blur_limit=3, p=0.2),
        A.Rotate(limit=5, p=0.3),
    ], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))

    for img_path in tqdm(list(input_dir.glob("*.jpg"))):
        # Process and save augmented versions...
        pass

if __name__ == "__main__":
    main()
```

---

## 6. Training PaddleOCR

### Dataset Structure

```
datasets/ocr/
├── train/
│   ├── images/
│   │   ├── plate_001.jpg  # Cropped plate images
│   │   ├── plate_002.jpg
│   │   └── ...
│   └── labels.txt
└── val/
    ├── images/
    └── labels.txt
```

### Label Format

`labels.txt`:
```
images/plate_001.jpg	ABC1234
images/plate_002.jpg	XYZ5678
images/plate_003.jpg	FL 123ABC
```

Tab-separated: `image_path<TAB>text_label`

### Install PaddlePaddle

```bash
# For Jetson (ARM64)
pip install paddlepaddle-gpu==2.5.2 -f https://www.paddlepaddle.org.cn/whl/linux/mkl/avx/stable.html

# Or CPU version
pip install paddlepaddle

# Install PaddleOCR
pip install paddleocr
```

### Clone PaddleOCR Repository

```bash
cd /home/jetson
git clone https://github.com/PaddlePaddle/PaddleOCR.git
cd PaddleOCR
pip install -r requirements.txt
```

### Train Recognition Model

```bash
# Download pretrained model
wget https://paddleocr.bj.bcebos.com/PP-OCRv4/english/en_PP-OCRv4_rec_train.tar
tar -xf en_PP-OCRv4_rec_train.tar

# Train with custom data
python tools/train.py \
    -c configs/rec/PP-OCRv4/en_PP-OCRv4_rec.yml \
    -o Global.pretrained_model=./en_PP-OCRv4_rec_train/best_accuracy \
       Global.epoch_num=100 \
       Global.save_epoch_step=10 \
       Global.eval_batch_step=[0,500] \
       Train.dataset.data_dir=/home/jetson/OVR-ALPR/datasets/ocr/train \
       Train.dataset.label_file_list=["/home/jetson/OVR-ALPR/datasets/ocr/train/labels.txt"] \
       Eval.dataset.data_dir=/home/jetson/OVR-ALPR/datasets/ocr/val \
       Eval.dataset.label_file_list=["/home/jetson/OVR-ALPR/datasets/ocr/val/labels.txt"]
```

### Export for Inference

```bash
# Export to inference model
python tools/export_model.py \
    -c configs/rec/PP-OCRv4/en_PP-OCRv4_rec.yml \
    -o Global.pretrained_model=output/rec/best_accuracy \
       Global.save_inference_dir=./inference/plate_ocr
```

---

## 7. Training Scripts

### Complete Training Script

Create `scripts/train_plate_detector.sh`:
```bash
#!/bin/bash
# Train and export plate detector

set -e

# Configuration
DATASET="datasets/plates/plates.yaml"
BASE_MODEL="yolo11n.pt"
EPOCHS=100
BATCH=16
IMGSZ=640
NAME="plate_detector_$(date +%Y%m%d)"

echo "=== Training Plate Detector ==="
echo "Dataset: $DATASET"
echo "Base Model: $BASE_MODEL"
echo "Epochs: $EPOCHS"

# Train
yolo detect train \
    data=$DATASET \
    model=$BASE_MODEL \
    epochs=$EPOCHS \
    batch=$BATCH \
    imgsz=$IMGSZ \
    device=0 \
    project=runs/train \
    name=$NAME \
    exist_ok=True

# Export to TensorRT
echo "=== Exporting to TensorRT ==="
yolo export \
    model=runs/train/$NAME/weights/best.pt \
    format=engine \
    device=0 \
    half=True

# Copy to models folder
echo "=== Deploying Model ==="
cp runs/train/$NAME/weights/best.pt models/yolo11n-plate.pt
cp runs/train/$NAME/weights/best.engine models/yolo11n-plate.engine

echo "=== Training Complete ==="
echo "Model saved to models/yolo11n-plate.engine"
echo "Run 'python pilot.py' to test"
```

### Training with Validation

Create `scripts/train_and_validate.py`:
```python
#!/usr/bin/env python3
"""Train model and run validation"""
from ultralytics import YOLO
import mlflow
from pathlib import Path

def train_model(
    data_yaml: str,
    base_model: str = "yolo11n.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
):
    # Start MLflow run
    mlflow.set_tracking_uri("http://localhost:5000")
    mlflow.set_experiment("plate-detection")

    with mlflow.start_run():
        # Log parameters
        mlflow.log_params({
            "data": data_yaml,
            "base_model": base_model,
            "epochs": epochs,
            "imgsz": imgsz,
            "batch": batch,
        })

        # Train
        model = YOLO(base_model)
        results = model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=0,
        )

        # Log metrics
        mlflow.log_metrics({
            "mAP50": results.results_dict["metrics/mAP50(B)"],
            "mAP50-95": results.results_dict["metrics/mAP50-95(B)"],
            "precision": results.results_dict["metrics/precision(B)"],
            "recall": results.results_dict["metrics/recall(B)"],
        })

        # Log model artifact
        mlflow.log_artifact(results.save_dir / "weights" / "best.pt")

        # Validate
        val_results = model.val()
        print(f"Validation mAP50: {val_results.box.map50:.4f}")

        return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--epochs", type=int, default=100)
    args = parser.parse_args()

    train_model(args.data, epochs=args.epochs)
```

---

## 8. Best Practices

### Data Collection Tips

1. **Variety**: Collect images in different lighting, weather, angles
2. **Balance**: Equal samples of each plate type/region
3. **Quality**: Include some blurry/low-quality images for robustness
4. **Negatives**: Include images without plates (hard negatives)

### Training Tips

1. **Start small**: Train on 100 images first to verify pipeline
2. **Monitor loss**: Watch for overfitting (val loss increasing)
3. **Learning rate**: Use default, adjust only if training unstable
4. **Augmentation**: Enable for small datasets (<1000 images)
5. **Early stopping**: Use patience=50 to prevent overfitting

### Validation Checklist

- [ ] mAP50 > 0.8 for plate detection
- [ ] Precision > 0.85 (minimize false positives)
- [ ] Recall > 0.80 (catch most plates)
- [ ] Test on held-out images from different cameras
- [ ] Verify TensorRT export works
- [ ] Test inference speed on Jetson

---

## 9. Troubleshooting

### CUDA Out of Memory

```bash
# Reduce batch size
yolo detect train data=plates.yaml batch=8  # or batch=4

# Or use auto batch
yolo detect train data=plates.yaml batch=-1
```

### Training Not Converging

- Check label format (YOLO normalized coordinates)
- Verify images and labels match (same filenames)
- Reduce learning rate: `lr0=0.001`
- Increase epochs: `epochs=200`

### TensorRT Export Fails

```bash
# Clear cache and retry
rm -rf ~/.cache/torch/hub/ultralytics*
yolo export model=best.pt format=engine half=True workspace=2
```

### Low mAP After Training

- Add more training data
- Increase augmentation
- Try larger model (yolo11s instead of yolo11n)
- Check for label errors

---

## 10. Quick Reference

### Train Commands

```bash
# Basic training
yolo detect train data=plates.yaml model=yolo11n.pt epochs=100

# With MLflow
python scripts/training/train_with_mlflow.py --data plates.yaml --epochs 100

# Resume training
yolo detect train data=plates.yaml resume=True

# Export to TensorRT
yolo export model=best.pt format=engine half=True
```

### Useful Paths

| Item | Path |
|------|------|
| Models | `models/` |
| Datasets | `datasets/` |
| Training runs | `runs/train/` |
| Training scripts | `scripts/` |
| MLflow UI | http://localhost:5000 |

---

## Related Documentation

- [MLflow Model Registry](./mlflow-model-registry.md) - Model versioning and deployment
- [Model Quantization](../../optimizations/MODEL_QUANTIZATION.md) - FP16/INT8 optimization
- [Performance Guide](../../optimizations/PERFORMANCE_OPTIMIZATION_GUIDE.md) - Inference optimization
