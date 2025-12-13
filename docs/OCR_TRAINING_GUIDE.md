# OCR Model Training Guide

## Training PaddleOCR for Better License Plate Recognition

### Prerequisites
- Video footage of license plates (rear-view camera angle)
- Labeled training data (plate text)
- GPU for training (can train on desktop, deploy to Jetson)

---

## Method 1: Fine-tune PaddleOCR Recognition Model

### Step 1: Prepare Training Data

#### 1.1 Extract plate crops from your video
```bash
# Use the existing system to collect plate crops
python3 pilot.py --video your_video.mp4 --save-crops

# Crops will be saved to: output/crops/
```

#### 1.2 Annotate the crops
Create a label file `train_list.txt`:
```
output/crops/plate001.jpg    ABC123
output/crops/plate002.jpg    XYZ789
output/crops/plate003.jpg    4PLT567
...
```

Format: `image_path\tplate_text`

#### 1.3 Create dataset structure
```
dataset/
├── train_data/
│   ├── plate001.jpg
│   ├── plate002.jpg
│   └── ...
├── train_list.txt
└── val_list.txt
```

### Step 2: Configure PaddleOCR Training

#### 2.1 Install PaddleOCR (full version for training)
```bash
pip install paddlepaddle-gpu paddleocr
git clone https://github.com/PaddlePaddle/PaddleOCR.git
cd PaddleOCR
```

#### 2.2 Create training config
Create `configs/rec/PP-OCRv4/en_PP-OCRv4_rec_custom.yml`:

```yaml
Global:
  use_gpu: true
  epoch_num: 100
  log_smooth_window: 20
  print_batch_step: 10
  save_model_dir: ./output/custom_rec_model
  save_epoch_step: 10
  eval_batch_step: 500
  cal_metric_during_train: true
  pretrained_model: en_PP-OCRv4_rec_train/best_accuracy
  checkpoints:
  save_inference_dir:
  use_visualdl: false
  infer_img: doc/imgs_words/en/word_1.png
  character_dict_path: ppocr/utils/en_dict.txt
  max_text_length: 10
  infer_mode: false
  use_space_char: false
  distributed: true
  save_res_path: ./output/rec/predicts_custom.txt

Optimizer:
  name: Adam
  beta1: 0.9
  beta2: 0.999
  lr:
    name: Cosine
    learning_rate: 0.0001  # Lower LR for fine-tuning
    warmup_epoch: 5
  regularizer:
    name: L2
    factor: 1.0e-05

Architecture:
  model_type: rec
  algorithm: SVTR_LCNet
  Transform:
  Backbone:
    name: PPLCNetV3
    scale: 0.95
  Head:
    name: MultiHead
    head_list:
      - CTCHead:
          Neck:
            name: svtr
            dims: 120
            depth: 2
            hidden_dims: 120
            kernel_size: [1, 3]
            use_guide: True
          Head:
            fc_decay: 0.00001
      - NRTRHead:
          nrtr_dim: 384
          max_text_length: 10

Loss:
  name: MultiLoss
  loss_config_list:
    - CTCLoss:
    - NRTRLoss:

PostProcess:
  name: CTCLabelDecode

Metric:
  name: RecMetric
  main_indicator: acc

Train:
  dataset:
    name: SimpleDataSet
    data_dir: ./dataset/train_data/
    ext_op_transform_idx: 1
    label_file_list:
      - ./dataset/train_list.txt
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - RecAug:
      - CTCLabelEncode:
      - KeepKeys:
          keep_keys:
            - image
            - label
            - length
  loader:
    shuffle: true
    batch_size_per_card: 256
    drop_last: true
    num_workers: 8

Eval:
  dataset:
    name: SimpleDataSet
    data_dir: ./dataset/train_data/
    label_file_list:
      - ./dataset/val_list.txt
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - CTCLabelEncode:
      - KeepKeys:
          keep_keys:
            - image
            - label
            - length
  loader:
    shuffle: false
    drop_last: false
    batch_size_per_card: 256
    num_workers: 4
```

### Step 3: Train the Model

```bash
# Fine-tune from pretrained model
python3 tools/train.py -c configs/rec/PP-OCRv4/en_PP-OCRv4_rec_custom.yml

# Monitor training
tensorboard --logdir=./output/custom_rec_model/
```

### Step 4: Export and Deploy

```bash
# Export to inference model
python3 tools/export_model.py \
    -c configs/rec/PP-OCRv4/en_PP-OCRv4_rec_custom.yml \
    -o Global.pretrained_model=./output/custom_rec_model/best_accuracy \
    Global.save_inference_dir=./custom_plate_rec_model

# Copy to Jetson
scp -r custom_plate_rec_model/ jetson@jetson-orin:/home/jetson/OVR-ALPR/models/

# Update config to use custom model
# Edit config/ocr.yaml:
#   rec_model: "models/custom_plate_rec_model"
```

---

## Method 2: Automated Training Pipeline

### Use the built-in plate crop collector:

```bash
# 1. Run system on your video to collect crops
python3 pilot.py --video rear_view_footage.mp4 --save-all-crops

# 2. Manually label the saved crops
# Create: output/crops/labels.txt

# 3. Generate training data
python3 scripts/prepare_ocr_training.py \
    --crops-dir output/crops/ \
    --labels output/crops/labels.txt \
    --output dataset/

# 4. Train using PaddleOCR
cd PaddleOCR
python3 tools/train.py -c configs/rec/PP-OCRv4/en_PP-OCRv4_rec_custom.yml
```

---

## Method 3: Use EasyOCR (Alternative)

EasyOCR allows easier custom training:

```bash
pip install easyocr

# Train custom model
python3 scripts/train_easyocr.py \
    --train-data dataset/train_list.txt \
    --val-data dataset/val_list.txt \
    --output models/easyocr_custom

# Update config to use EasyOCR
# Edit config/ocr.yaml:
#   fallback:
#     enabled: true
#     provider: "easyocr"
```

---

## Tips for Better Training Data

### 1. **Diverse Samples**
- Different lighting conditions
- Various angles
- Multiple plate types
- Motion blur examples

### 2. **Quality Over Quantity**
- 500-1000 well-labeled samples > 10,000 poor labels
- Clear, readable plates
- Correct text labels

### 3. **Data Augmentation**
- Rotation (-5° to +5°)
- Brightness/contrast variation
- Slight blur (simulate motion)
- Noise addition

### 4. **Balanced Dataset**
- Equal representation of all characters (A-Z, 0-9)
- Different plate lengths
- Various backgrounds

---

## Quick Start: Create Training Script

Create `scripts/prepare_ocr_training.py`:
```python
#!/usr/bin/env python3
"""
Prepare OCR training data from video
"""
import cv2
import os
from pathlib import Path

def extract_plates_from_video(video_path, output_dir):
    """Extract plate crops from video using existing detector"""
    # Run pilot.py to extract crops
    os.system(f"python3 pilot.py --video {video_path} --save-crops")

    print(f"Crops saved to: {output_dir}")
    print("Next: Manually label crops in output/crops/labels.txt")
    print("Format: image_path<TAB>plate_text")

if __name__ == "__main__":
    extract_plates_from_video("your_video.mp4", "output/crops/")
```

---

## Expected Improvements

After training on ~500 labeled plates from your camera angle:
- **Accuracy**: +10-20% improvement
- **Confidence**: Higher confidence scores
- **Angle-specific**: Better at rear-view angles
- **Character confusion**: Fewer O/0, I/1, etc. errors

---

## Important Notes

1. **Training is compute-intensive**: Use a desktop GPU (RTX 3060+)
2. **Deployment**: Trained model can be deployed to Jetson
3. **Iteration**: Start with 100 samples, evaluate, add more
4. **Validation**: Always test on held-out validation set

---

## Alternative: Character-level Fine-tuning

If you notice specific character confusions (e.g., O vs 0):

```python
# Add character-specific augmentation
# Focus training on confused pairs
confused_pairs = [('O', '0'), ('I', '1'), ('S', '5'), ('Z', '2')]
```

This targeted approach can fix specific issues without full retraining.
