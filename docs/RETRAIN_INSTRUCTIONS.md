# How to Retrain for 720p.mp4 Video

## Problem
The model was trained on IMG_6930/IMG_6941 video frames, but you're testing on 720p.mp4.
The plate characteristics are different (size, angle, distance, etc.)

## Solution: Retrain on 720p.mp4

### Step 1: Extract frames from 720p.mp4
```bash
python3 scripts/extract_frames_from_video.py \
  --video videos/720p.mp4 \
  --output datasets/720p_plates/ \
  --interval 15
```

### Step 2: Label the images
- Use Roboflow, LabelImg, or CVAT to draw boxes around license plates
- Export in YOLO format
- Place labels in datasets/720p_plates/labels/

### Step 3: Create dataset
```bash
# Create dataset structure
mkdir -p datasets/720p_plates/{train,val}/{images,labels}

# Split and move files (80/20 split)
python3 << 'SPLIT'
import shutil
from pathlib import Path
import random

dataset_dir = Path("datasets/720p_plates")
images_dir = dataset_dir / "images"
labels_dir = dataset_dir / "labels"

images = sorted(list(images_dir.glob("*.jpg")))
random.seed(42)
random.shuffle(images)

split_idx = int(len(images) * 0.8)
train_images = images[:split_idx]
val_images = images[split_idx:]

for img in train_images:
    label = labels_dir / f"{img.stem}.txt"
    shutil.copy(img, dataset_dir / "train" / "images" / img.name)
    if label.exists():
        shutil.copy(label, dataset_dir / "train" / "labels" / label.name)

for img in val_images:
    label = labels_dir / f"{img.stem}.txt"
    shutil.copy(img, dataset_dir / "val" / "images" / img.name)
    if label.exists():
        shutil.copy(label, dataset_dir / "val" / "labels" / label.name)
SPLIT
```

### Step 4: Create data.yaml
```bash
cat > datasets/720p_plates/data.yaml << 'YAML'
path: /home/jetson/OVR-ALPR/datasets/720p_plates
train: train/images
val: val/images
nc: 1
names: ['license_plate']
YAML
```

### Step 5: Train
```bash
yolo detect train \
  data=datasets/720p_plates/data.yaml \
  model=yolo11n.pt \
  epochs=100 \
  imgsz=640 \
  batch=4 \
  workers=2
```

### Step 6: Deploy
```bash
# Copy trained model
cp runs/detect/train3/weights/best.pt models/yolo11n-plate-720p.pt

# Export to TensorRT
python3 -c "from ultralytics import YOLO; YOLO('models/yolo11n-plate-720p.pt').export(format='engine', half=True, device='cuda:0', imgsz=640)"

# Test
python3 pilot.py --plate-model models/yolo11n-plate-720p.engine
```

## Alternatively: Combine Datasets

Combine the existing dataset with new 720p frames:

```bash
# Copy old dataset
cp -r datasets/plate_training_round2 datasets/combined_plates

# Add new 720p frames and labels
cp datasets/720p_frames/*.jpg datasets/combined_plates/images/
cp datasets/720p_frames/*.txt datasets/combined_plates/labels/

# Re-split and retrain
# (follow steps 3-6 above)
```
