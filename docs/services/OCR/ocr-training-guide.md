# OCR Training Guide

How to retrain the CRNN OCR model once you have enough labeled plate crops.

---

## Current state

The system currently uses `PlateOCR` (PaddleOCR + EasyOCR ensemble) running async in a background thread. It works but accuracy is limited — PaddleOCR was not trained on Florida plates.

The CRNN training pipeline is fully built and ready. Once you have **500+ labeled real plate crops**, you can train a faster, more accurate, fully thread-safe CRNN model and replace PlateOCR.

---

## Where crops come from

Every plate detected by YOLO is saved automatically to:

```
output/crops/YYYY-MM-DD/
    CAM1_trackN.jpg    ← one file per tracked vehicle, overwritten if a better frame comes in
```

The filename is stable per track — if the detector sees the same car for 10 frames, only the best-quality crop is kept. Let the system run for a few days/weeks to accumulate crops naturally.

```bash
# Count crops collected so far
find output/crops -name "*.jpg" | wc -l
```

---

## Step 1 — Label the crops

### Run the labeling tool

```bash
python3 scripts/ocr/label_crops.py \
    --crops-dir output/crops \
    --output data/ocr_training/labels.txt
```

The script skips crops already in `labels.txt`, so you can run it repeatedly as new crops accumulate and it will only show new ones.

### Hotkeys

| Key | Action |
|---|---|
| Type characters | Build the plate text |
| `Enter` | Save label and move to next |
| `Escape` | Skip (mark as `__SKIP__`) |
| `Ctrl+Q` | Save and quit |
| `[` | Go back one image |

> **Note:** `Q` and `S` are valid plate characters — they are NOT hotkeys.

### Labeling rules

- Type only what's on the plate: letters `A–Z` and digits `0–9`, no spaces or dashes
- Skip blurry, angled, or unreadable crops with `Escape` — bad labels hurt more than no labels
- If PaddleOCR pre-labeled it incorrectly, just retype the correct text
- The orange Florida logo/graphic between letters and numbers is not a character — ignore it

### How many labels to collect

| Labels | Expected outcome |
|---|---|
| < 100 | CRNN will not converge — stick with PlateOCR |
| 200–300 | CRNN may converge; limited character coverage |
| 500+ | Reliable convergence, good accuracy |
| 1000+ | Production-quality results |

This is higher than typical OCR guides suggest because CRNN uses CTC loss and must learn character features **from scratch** (no pre-trained backbone). With fewer than ~500 samples, the model collapses to predicting blanks for every input — a known CTC failure mode.

---

## Step 2 — Review and filter labels

Before training, check for contamination. The main risk is the YOLO plate detector occasionally labels non-plate objects (signs, logos) as plates.

```bash
# Check what's in labels.txt
python3 -c "
lines = open('data/ocr_training/labels.txt').readlines()
real = [l.split('\t') for l in lines if '\t' in l and '__SKIP__' not in l]
print(f'Labeled: {len(real)}, Skipped: {lines.count(chr(9).join([l.split(chr(9))[0], \"__SKIP__\"]))}')
for p, t in real[:20]:
    print(f'  {t.strip():12s}  {p.split(\"/\")[-1].strip()}')
"
```

Signs to watch for in the label list:
- Words like `RESERVED`, `SUITE`, `EXIT`, `PARKING` — from parking garage footage
- Labels with no digits (real plates always have digits)
- Labels longer than 8 characters

If you find sign contamination, open the labeling tool in review mode to correct them:

```bash
python3 scripts/ocr/label_crops.py \
    --crops-dir output/crops \
    --output data/ocr_training/labels.txt \
    --review
```

---

## Step 3 — Pre-label new crops with PaddleOCR (optional speedup)

If you have hundreds of new unlabeled crops, run PaddleOCR over them first so you only need to correct errors rather than type everything from scratch:

```bash
python3 scripts/ocr/prelabel_with_paddleocr.py \
    --crops-dir output/crops \
    --output data/ocr_training/labels.txt
```

Then run `label_crops.py --review` to verify and fix incorrect pre-labels.

---

## Step 4 — Train

```bash
python3 scripts/ocr/train_crnn.py \
    --labels data/ocr_training/labels.txt \
    --output-dir models/crnn_florida \
    --epochs 300 \
    --batch-size 16 \
    --val-split 0.15 \
    --patience 100
```

| Argument | Guidance |
|---|---|
| `--epochs` | 200–300 for 500 samples; more epochs don't hurt with early stopping |
| `--batch-size` | 16–32 depending on available GPU memory |
| `--val-split` | 0.15 (15% held out for validation); use 0.10 if you have fewer than 300 samples |
| `--patience` | Early stopping: stop if no improvement for N epochs. 50–100 is reasonable |
| `--lr` | Default 1e-3 works; try 3e-4 if training is unstable |

Training progress is logged to MLflow at `http://localhost:5000` (if Docker is running).

### What success looks like

```
Epoch  50/300  loss=0.82  val_loss=0.91  CER=0.12  exact=58%
Epoch 100/300  loss=0.41  val_loss=0.48  CER=0.06  exact=74%
Epoch 150/300  loss=0.21  val_loss=0.31  CER=0.03  exact=88%
```

CER (character error rate) below 10% and exact match above 70% is good enough to switch from PlateOCR.

### What failure looks like

```
Epoch   1/300  CER=1.000  pred=''  true='RJL469'
Epoch  50/300  CER=1.000  pred=''  true='RJL469'
```

Empty predictions throughout = CTC blank collapse. You need more training data. Do not increase epochs — it will not help.

---

## Step 5 — Switch pilot.py to the CRNN model

Once training succeeds, edit `pilot.py`:

```python
# Replace:
from ocr.plate_ocr import PlateOCR
# With:
from ocr.crnn_ocr_service import CRNNOCRService
```

And in `__init__`:

```python
# Replace:
self.ocr = PlateOCR(use_gpu=True)
self.ocr.warmup(iterations=1)
# With:
self.ocr = CRNNOCRService(
    model_path="models/crnn_florida/florida_plate_ocr.onnx",
    use_gpu=True,
)
self.ocr.warmup(iterations=3)
```

And adjust confidence thresholds:

```python
self.ocr_min_confidence = 0.50   # CRNN uses mean softmax confidence
self.ocr_max_confidence_target = 0.80
```

`CRNNOCRService` is thread-safe (onnxruntime backend) so the `ThreadPoolExecutor` async path works correctly with it — unlike PaddleOCR.

---

## Step 6 — Register in MLflow and distribute

```bash
# Train and register in one step
python3 scripts/ocr/train_crnn.py \
    --labels data/ocr_training/labels.txt \
    --output-dir models/crnn_florida \
    --register

# Promote to champion so the model sync agent distributes it
mlflow models set-model-alias \
    --model-name alpr-florida-ocr-crnn \
    --alias champion \
    --version 1
```

The model sync agent picks up the `champion` alias on its next poll and deploys the updated model to all edge devices.

---

## Data tips

### Crops accumulate automatically
pilot.py saves every plate detection to `output/crops/`. After a week of operation you may have hundreds of crops without any manual effort.

### Label in batches
Label 50–100 crops at a time. Run the labeling tool, quit, then retrain. Iterative improvement:

```
Collect 100 crops → label → train → measure accuracy
Collect 100 more  → label → retrain → measure again
```

### Existing labels are preserved
The current `data/ocr_training/labels.txt` already has 43 clean labeled plates. New labeling sessions append to this file — you don't lose previous work.

### Extracted YOLO dataset crops
369 crops were already extracted from `datasets/plate_training_round2` and `datasets/plate_training`. Most were parking signs and are marked `__SKIP__`. The 43 that survived filtering are real plates and are already in `labels.txt`.

---

## Files reference

| File | Purpose |
|---|---|
| `scripts/ocr/label_crops.py` | Interactive labeling tool |
| `scripts/ocr/prelabel_with_paddleocr.py` | Auto-label with PaddleOCR to speed up review |
| `scripts/ocr/train_crnn.py` | CRNN training + ONNX export |
| `scripts/ocr/extract_crops_from_yolo.py` | Extract crops from YOLO-annotated datasets |
| `data/ocr_training/labels.txt` | Labeled crops (tab-separated path + text) |
| `data/ocr_training/extracted_crops/` | Crops extracted from YOLO datasets |
| `models/crnn_florida/florida_plate_ocr.onnx` | Trained CRNN model (replace when retrained) |
| `edge_services/ocr/crnn_ocr_service.py` | Thread-safe ONNX OCR service for pilot.py |
| `edge_services/ocr/plate_ocr.py` | PaddleOCR + EasyOCR ensemble (current fallback) |
| `output/crops/` | Live plate crops collected by pilot.py |
