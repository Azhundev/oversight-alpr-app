# YOLOv11 Training Guide for Florida License Plates

Complete guide to fine-tuning YOLOv11 for Florida license plate detection.

## Overview

This guide shows you how to:
1. Collect training data from your videos
2. Prepare the dataset
3. Train a custom YOLOv11 model
4. Export to TensorRT for Jetson
5. Integrate into your ALPR system

## Why Fine-tune?

Your current system uses:
- **Generic YOLOv11** trained on COCO dataset (no plates)
- **Contour-based plate detection** (unreliable)
- Result: ~1% plate detection rate

After fine-tuning:
- **Custom YOLOv11** trained specifically on Florida plates
- **ML-based plate detection** (much better)
- Expected: **70-90% plate detection rate**

## Prerequisites

```bash
# Install Ultralytics (YOLOv11)
pip3 install ultralytics

# Verify installation
python3 -c "from ultralytics import YOLO; print('YOLOv11 ready!')"
```

## Step 1: Collect Training Data

Use your existing videos to collect plate samples:

```bash
# Collect from your test video (with preview)
python3 tools/collect_plate_samples.py a.mp4 \
    --output training_data/raw_plates \
    --max-samples 500 \
    --skip-frames 5

# The script will:
# - Detect plates in video
# - Show preview window
# - Press 's' to save current detections
# - Press 'q' to quit
# - Auto-saves high-quality detections
```

**What you get:**
```
training_data/raw_plates/
├── images/          # Full frames with plates
├── labels/          # YOLO format annotations (class x y w h)
├── crops/           # Cropped plate images
└── metadata.json    # Collection details
```

### Multiple Videos

Collect from multiple videos for diversity:

```bash
# Collect from different times of day, weather, angles
python3 tools/collect_plate_samples.py video1.mp4 --output training_data/raw_plates
python3 tools/collect_plate_samples.py video2.mp4 --output training_data/raw_plates
python3 tools/collect_plate_samples.py video3.mp4 --output training_data/raw_plates
```

### How Much Data?

| Samples | Expected Performance |
|---------|---------------------|
| 100-200 | Basic (~50-60% detection) |
| 500-1000 | Good (~70-80% detection) |
| 1000-2000 | Excellent (~85-90% detection) |
| 2000+ | Professional (~90-95% detection) |

**Recommendation:** Start with 500 samples, test, then collect more if needed.

## Step 2: Manual Annotation (Optional)

The auto-collected data might have errors. You can:

### Option A: Use Auto-annotations (Faster)
Skip this step - use what the collector found.

### Option B: Manual Review (Better Quality)

Use **LabelImg** to review/correct annotations:

```bash
# Install LabelImg
pip3 install labelImg

# Open annotation tool
labelImg training_data/raw_plates/images training_data/raw_plates/labels
```

**In LabelImg:**
- Press 'w' to draw box
- Label as "license_plate"
- Press 'd' for next image
- Fix any wrong/missing boxes

### Option C: Combine Auto + Public Datasets

Download public plate datasets:
- **OpenALPR Dataset** - https://github.com/openalpr/benchmarks
- **UFPR-ALPR Dataset** - Brazilian plates (similar format)
- **RodoSol-ALPR** - Highway plates

## Step 3: Prepare Dataset

Split into train/val sets:

```bash
python3 tools/prepare_dataset.py \
    training_data/raw_plates \
    --output datasets/florida_plates \
    --train-split 0.8 \
    --val-split 0.2
```

**Output:**
```
datasets/florida_plates/
├── train/
│   ├── images/    # 80% of data
│   └── labels/
├── val/
│   ├── images/    # 20% of data
│   └── labels/
└── florida_plates.yaml  # Config file
```

## Step 4: Train the Model

### On Your Jetson (Slower but Convenient)

```bash
python3 tools/train_plate_detector.py \
    --data datasets/florida_plates/florida_plates.yaml \
    --model yolo11n.pt \
    --epochs 100 \
    --batch 8 \
    --imgsz 640 \
    --device 0
```

**Expected time:** 2-6 hours (depending on dataset size)

### On Cloud GPU (Faster - Recommended)

Train on Google Colab/AWS/etc, then transfer model:

```python
# In Colab notebook
from ultralytics import YOLO

# Upload your dataset first
model = YOLO('yolo11n.pt')

results = model.train(
    data='florida_plates.yaml',
    epochs=100,
    imgsz=640,
    batch=32,  # Larger batch on GPU
    device=0
)

# Download: runs/detect/florida_plates/weights/best.pt
```

Then copy `best.pt` to Jetson.

## Step 5: Export to TensorRT

If training on Jetson, this happens automatically.

If you trained elsewhere:

```bash
# On Jetson, export the trained model
python3 -c "
from ultralytics import YOLO
model = YOLO('best.pt')
model.export(format='engine', half=True, device=0)
"
```

**Output:** `best.engine` (TensorRT optimized for Jetson)

## Step 6: Integrate into ALPR System

### Update Detector Service

Edit `services/detector/detector_service.py`:

```python
def __init__(
    self,
    vehicle_model_path: str = "yolo11n.pt",
    plate_model_path: str = "best.engine",  # Your custom model!
    use_tensorrt: bool = True,
    ...
):
    # Load vehicle detector
    self.vehicle_model = YOLO(vehicle_model_path)

    # Load custom plate detector
    if plate_model_path:
        self.plate_model = YOLO(plate_model_path)
        logger.success(f"Loaded custom plate detector: {plate_model_path}")
    else:
        self.plate_model = None
```

### Use in Pilot

```bash
# Run with custom plate detector
python3 pilot.py --plate-model best.engine
```

Or hardcode in `pilot.py`:

```python
self.detector = YOLOv11Detector(
    vehicle_model_path="yolo11n.pt",
    plate_model_path="models/florida_plates.engine",  # Custom model
    use_tensorrt=True
)
```

## Training Tips

### 1. Data Quality > Quantity
- 500 high-quality samples > 2000 poor samples
- Ensure variety: day/night, angles, distances, weather

### 2. Monitor Training
Training creates plots in `runs/detect/florida_plates/`:
- `results.png` - Loss and metrics over epochs
- `confusion_matrix.png` - Detection accuracy
- `PR_curve.png` - Precision-Recall

**Good signs:**
- Loss decreases steadily
- mAP@0.5 > 0.8 (80%+)
- No overfitting (train/val similar)

**Bad signs:**
- Loss stops improving early
- Train accuracy >> Val accuracy (overfitting)
- mAP < 0.5 (need more/better data)

### 3. Hyperparameter Tuning

If results aren't good enough:

```bash
# Try larger model (slower but more accurate)
--model yolo11s.pt  # or yolo11m.pt

# More epochs
--epochs 200

# Different image size
--imgsz 1280  # Higher resolution (slower)

# Adjust learning rate
# Edit train_plate_detector.py:
lr0=0.001  # Initial learning rate
lrf=0.01   # Final learning rate
```

### 4. Data Augmentation

Already enabled in `train_plate_detector.py`:
- Random rotation (±10°)
- Brightness/contrast adjustments
- Horizontal flip
- Mosaic augmentation

## Evaluation

After training, test on new videos:

```bash
# Test detector
python3 -c "
from ultralytics import YOLO
model = YOLO('best.engine')

results = model('test_video.mp4', save=True, conf=0.5)
print(f'Detections: {len(results)}')
"
```

Check `runs/detect/predict/` for annotated video.

## Expected Improvements

| Metric | Before (Generic YOLO) | After (Fine-tuned) |
|--------|----------------------|-------------------|
| Plate Detection Rate | ~1% | 70-90% |
| False Positives | High | Low |
| OCR Opportunities | 7/654 vehicles | 400-600/654 vehicles |
| Confidence | 0.3-0.5 | 0.7-0.95 |

## Troubleshooting

### "Out of memory during training"
```bash
# Reduce batch size
--batch 4  # or even 2
```

### "Model not improving"
- Need more data (collect 500+ more samples)
- Check label quality (review annotations)
- Try different base model (yolo11s.pt)

### "Training too slow on Jetson"
- Use cloud GPU (Google Colab free tier works!)
- Reduce epochs to 50 for quick test
- Use smaller model (yolo11n.pt)

### "TensorRT export fails"
```bash
# Try without TensorRT first
model.export(format='onnx', half=True)

# Then convert ONNX to TensorRT manually
trtexec --onnx=best.onnx --saveEngine=best.engine --fp16
```

## Advanced: Multi-stage Training

For best results, train in stages:

### Stage 1: Plate Detection (This Guide)
→ Better plate bounding boxes

### Stage 2: Plate OCR (Future)
→ Better text recognition
→ Use cropped plates from Stage 1
→ Train with PaddleOCR or EasyOCR

### Stage 3: Vehicle Attributes (Future)
→ Color, make, model classification
→ Uses vehicle crops from detector

## Resources

- **YOLOv11 Docs:** https://docs.ultralytics.com/
- **Training Tutorial:** https://docs.ultralytics.com/modes/train/
- **Dataset Format:** https://docs.ultralytics.com/datasets/detect/
- **LabelImg Tool:** https://github.com/heartexlabs/labelImg

## Next Steps

After successful training:

1. **Integrate custom model** into pilot.py
2. **Test on real footage** from your cameras
3. **Collect more data** where model fails
4. **Re-train** with expanded dataset
5. **Consider OCR training** for better text recognition

## Summary Commands

```bash
# 1. Collect data
python3 tools/collect_plate_samples.py video.mp4 --max-samples 500

# 2. Prepare dataset
python3 tools/prepare_dataset.py training_data/raw_plates

# 3. Train
python3 tools/train_plate_detector.py \
    --data datasets/florida_plates/florida_plates.yaml \
    --epochs 100

# 4. Test
python3 pilot.py --plate-model models/plate_detector/florida_plates/weights/best.engine
```

**Good luck training!** 🚀
