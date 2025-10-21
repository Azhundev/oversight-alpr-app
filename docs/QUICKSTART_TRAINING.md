# Quick Start: Train YOLOv11 for Florida Plates

## Your Situation

You have:
- ✅ `720p.mp4` with Florida license plates
- ✅ Working ALPR system (pilot.py)
- ✅ Training tools ready

Current problem:
- ❌ Only ~1% plate detection rate (7 plates from 654 vehicles)
- ❌ Using contour-based detection (unreliable)

Goal:
- ✅ Train custom YOLOv11 for **70-90% plate detection**

## 3-Step Process

### Step 1: Collect Training Data (RUNNING NOW!)

```bash
# Collecting Florida plates from your video
python3 tools/collect_plate_samples.py 720p.mp4 \
    --output training_data/florida_raw \
    --max-samples 200 \
    --skip-frames 10 \
    --no-preview
```

**What it does:**
- Processes every 10th frame (faster)
- Detects plates automatically
- Saves 200 samples (good for initial training)
- Creates YOLO format annotations

**Expected time:** 2-5 minutes

**Output:**
```
training_data/florida_raw/
├── images/       # Full frames
├── labels/       # YOLO annotations
├── crops/        # Cropped plates
└── metadata.json
```

### Step 2: Prepare Dataset

```bash
# Split into train/val (80/20)
python3 tools/prepare_dataset.py \
    training_data/florida_raw \
    --output datasets/florida_plates
```

**Creates:**
```
datasets/florida_plates/
├── train/
│   ├── images/  (160 samples)
│   └── labels/
├── val/
│   ├── images/  (40 samples)
│   └── labels/
└── florida_plates.yaml  ← Config for training
```

### Step 3: Train Model

**Option A: On Jetson (Slow but Easy)**
```bash
python3 tools/train_plate_detector.py \
    --data datasets/florida_plates/florida_plates.yaml \
    --epochs 100 \
    --batch 8 \
    --device 0
```

- Time: 2-4 hours
- Exports TensorRT automatically
- Best for: small datasets (<500 samples)

**Option B: Google Colab (Fast & Free!)**

1. Open Google Colab: https://colab.research.google.com
2. Create new notebook
3. Run:

```python
# Install YOLOv11
!pip install ultralytics

# Upload your dataset (zip it first)
from google.colab import files
uploaded = files.upload()  # Upload florida_plates.zip

# Unzip
!unzip florida_plates.zip

# Train
from ultralytics import YOLO
model = YOLO('yolo11n.pt')

results = model.train(
    data='florida_plates/florida_plates.yaml',
    epochs=100,
    imgsz=640,
    batch=32,  # Bigger batch on Colab GPU
    device=0
)

# Download best model
files.download('runs/detect/train/weights/best.pt')
```

4. Copy `best.pt` to Jetson
5. Export to TensorRT:

```bash
# On Jetson
python3 -c "
from ultralytics import YOLO
model = YOLO('best.pt')
model.export(format='engine', half=True, device=0, batch=1)
"
```

- Time: 30-60 minutes
- Much faster training
- Best for: medium-large datasets (500+ samples)

## Step 4: Test Your Model

```bash
# Test in pilot
python3 pilot.py --plate-model best.engine
```

Or edit `pilot.py` to use it permanently:

```python
self.detector = YOLOv11Detector(
    vehicle_model_path="yolo11n.pt",
    plate_model_path="best.engine",  # Your custom model!
    use_tensorrt=True
)
```

## Expected Results

| Before | After |
|--------|-------|
| 7 plates detected | 400-600 plates detected |
| 1% detection rate | 70-90% detection rate |
| Confidence: 0.3-0.5 | Confidence: 0.7-0.95 |
| Many missed plates | Most plates found |

## Troubleshooting

### "Not enough samples collected"

```bash
# Collect from more videos
python3 tools/collect_plate_samples.py video2.mp4 \
    --output training_data/florida_raw \
    --max-samples 300
```

### "Training out of memory"

```bash
# Reduce batch size
--batch 4

# Or use Colab instead
```

### "Low accuracy after training"

1. Collect more diverse data (500+ samples)
2. Review annotations for errors
3. Train longer (--epochs 200)
4. Try larger model (--model yolo11s.pt)

## Next Steps

After successful training:

1. **Collect more data** - Aim for 500-1000 samples over time
2. **Re-train periodically** - As you collect more varied data
3. **Train OCR model** - For better text recognition
4. **Deploy to production** - Use custom model in real system

## Summary Commands

```bash
# 1. Collect (DONE - running now!)
python3 tools/collect_plate_samples.py 720p.mp4 \
    --output training_data/florida_raw --max-samples 200

# 2. Prepare
python3 tools/prepare_dataset.py training_data/florida_raw

# 3. Train (choose one)
## On Jetson:
python3 tools/train_plate_detector.py \
    --data datasets/florida_plates/florida_plates.yaml --epochs 100

## OR on Colab (faster):
# See Option B above

# 4. Test
python3 pilot.py --plate-model best.engine
```

## Files Created

```
tools/
├── collect_plate_samples.py  ✅ Data collection
├── prepare_dataset.py         ✅ Dataset prep
└── train_plate_detector.py    ✅ Training script

docs/
└── TRAINING_GUIDE.md          ✅ Full documentation

training_data/
└── florida_raw/               🏃 Collecting now...

datasets/
└── florida_plates/            ⏳ Next step

models/
└── plate_detector/            ⏳ After training
```

**Check collection progress:**
```bash
# Count samples collected so far
ls training_data/florida_raw/images/ | wc -l
```

Good luck! 🚀
