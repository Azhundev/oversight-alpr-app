# OCR Training Guide

Training a custom OCR model on real Florida plate crops to improve accuracy and restore async threading.

---

## Why train a custom model?

PaddleOCR's `en_PP-OCRv4_rec` is a general-purpose recognizer. It was not trained on Florida plates and does not know:
- The Sunshine State orange citrus graphic sits between the letter and number groups
- The font and spacing specific to Florida DMV plates
- Common character confusion patterns on Florida plates (e.g. `D`/`0`, `Y`/`V`)

A model fine-tuned on real Florida plate crops fixes these issues at the source rather than patching them in post-processing.

### Bonus: solves the async threading problem

PaddleOCR is not thread-safe (see `ocr-service.md` → Known Issues). The recommended training target is a **CRNN exported to ONNX**, which runs via `onnxruntime.InferenceSession`. ONNX Runtime is explicitly thread-safe, so training a custom model also restores `ThreadPoolExecutor` async OCR and the FPS improvement that came with it.

---

## Three-step workflow

```
Plate crops (output/crops/)
         │
         ▼  Step 1
    Label crops
    (type the correct plate text for each image)
         │
         ▼  Step 2
    Train CRNN → export to ONNX
    (or fine-tune PaddleOCR rec model)
         │
         ▼  Step 3
    Register in MLflow → model sync agent distributes to all devices
```

---

## Step 1 — Label the crops

### What you need

- Plate crop images in `output/crops/`
- The correct plate text for each image

### Label format

A plain text file with one entry per line:

```
output/crops/2026-02-26/CAM1_track99.jpg	HYUL84
output/crops/2026-02-26/CAM1_track142.jpg	LLKD78
output/crops/2026-02-26/CAM1_track164.jpg	O6DAYV
```

Tab-separated: `image_path<TAB>plate_text`. This is compatible with both PaddleOCR's training format and the custom CRNN pipeline.

### Labeling script

```bash
python scripts/ocr_training/label_crops.py \
    --crops-dir output/crops \
    --output labels.txt
```

The script shows each crop in a window, you type the plate text, press Enter. Press `s` to skip an unreadable image. Resumes from where you left off if interrupted.

### How many labels?

| Count | Expected outcome |
|---|---|
| 50–100 | Visible improvement on the specific plates seen |
| 200–300 | Reliable improvement across Florida plate styles |
| 500+ | Production-quality results |

57 crops (current) is enough to start and measure improvement. Keep the system running to collect more.

### Tips for labeling

- Type only the characters visible on the plate (`A–Z`, `0–9`), no spaces or dashes
- If you can't read it confidently, press `s` to skip — bad labels hurt training
- The orange logo is not a character; ignore it
- If PaddleOCR got it almost right (e.g. `HYUEL84` for `HYUL84`), still label the correct text

---

## Step 2 — Train

Two options. **Option B (CRNN + ONNX) is recommended** because the result is thread-safe.

---

### Option A — Fine-tune PaddleOCR recognition model

Fine-tunes `en_PP-OCRv4_rec` on your labeled Florida plate crops. Uses the existing PaddleOCR inference path in `pilot.py` — no code changes needed after training.

**Limitations:**
- Requires PaddlePaddle training environment (separate from inference)
- Output model is not thread-safe (same limitation as today)
- More complex setup than Option B

**Setup:**

```bash
pip install paddlepaddle-gpu  # training-only dependency
git clone https://github.com/PaddlePaddle/PaddleOCR
cd PaddleOCR
```

**Data preparation:**

```bash
# Convert labels.txt to PaddleOCR format
python scripts/ocr_training/prepare_paddle_dataset.py \
    --labels labels.txt \
    --output-dir data/paddle_ocr/ \
    --val-split 0.15
```

PaddleOCR expects:
```
data/paddle_ocr/
  train/
    images/       ← symlinks or copies of crop images
    train_list.txt   ← "images/CAM1_track99.jpg	HYUL84"
  val/
    images/
    val_list.txt
```

**Training config (`configs/rec/PP-OCRv4/en_PP-OCRv4_rec_fine_tune.yml`):**

Key settings to modify:
```yaml
Global:
  pretrained_model: ./pretrain_models/en_PP-OCRv4_rec_train/best_accuracy
  character_dict_path: ppocr/utils/en_dict.txt
  max_text_length: 10

Train:
  dataset:
    data_dir: ./data/paddle_ocr/train/
    label_file_list: ["./data/paddle_ocr/train/train_list.txt"]
  loader:
    batch_size_per_card: 32
    num_workers: 4

Eval:
  dataset:
    data_dir: ./data/paddle_ocr/val/
    label_file_list: ["./data/paddle_ocr/val/val_list.txt"]
```

**Train:**

```bash
python tools/train.py -c configs/rec/PP-OCRv4/en_PP-OCRv4_rec_fine_tune.yml
```

**Export and copy:**

```bash
python tools/export_model.py \
    -c configs/rec/PP-OCRv4/en_PP-OCRv4_rec_fine_tune.yml \
    -o Global.pretrained_model=output/rec_ppocr_v4/best_accuracy \
       Global.save_inference_dir=inference/florida_rec

cp -r inference/florida_rec models/florida_rec/
```

Update `config/ocr.yaml`:
```yaml
ocr:
  paddle:
    rec_model_dir: "models/florida_rec"   # override default model
```

---

### Option B — CRNN + ONNX (recommended)

Trains a lightweight CRNN (Convolutional Recurrent Neural Network) on your labeled crops, exports to ONNX, and registers it in MLflow. The resulting model:

- Runs via `onnxruntime.InferenceSession` → **thread-safe**
- ~5–20ms inference → **faster than PaddleOCR**
- Deployable via the model sync agent to all edge devices
- Works with `ThreadPoolExecutor` async OCR (restores FPS)

**Architecture:**

```
plate crop (grayscale, resized to 32×128)
    │
    ▼
CNN feature extractor (MobileNetV2 backbone, 4 stages)
    │
    ▼
Sequence features (W/4 time steps, 256 channels)
    │
    ▼
BiLSTM (2 layers, 256 hidden units)
    │
    ▼
CTC decoder → plate text
```

**Training:**

```bash
python scripts/ocr_training/train_crnn.py \
    --labels labels.txt \
    --output-dir models/crnn_florida/ \
    --epochs 100 \
    --batch-size 32 \
    --val-split 0.15
```

The script:
1. Loads labeled crops
2. Augments data (small rotations, brightness/contrast jitter, slight blur)
3. Trains with CTC loss
4. Evaluates character accuracy and full-plate exact-match rate
5. Exports best checkpoint to `models/crnn_florida/florida_plate_ocr.onnx`
6. Logs metrics and registers model in MLflow

**Expected training time on Jetson Orin NX:** ~20–40 min for 200 labeled crops, 100 epochs.

**MLflow registration:**

```bash
python scripts/ocr_training/train_crnn.py --labels labels.txt --register-mlflow
```

The model is registered as `alpr-florida-ocr-crnn` in MLflow. Promote to `champion` to distribute via the model sync agent:

```bash
mlflow models set-model-alias \
    --model-name alpr-florida-ocr-crnn \
    --alias champion \
    --version 1
```

**Inference integration:**

```python
# In pilot.py — thread-safe, can use ThreadPoolExecutor
import onnxruntime as ort
import cv2, numpy as np

sess = ort.InferenceSession(
    "models/crnn_florida/florida_plate_ocr.onnx",
    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
)

def read_plate_onnx(crop_bgr: np.ndarray) -> str:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    img = cv2.resize(gray, (128, 32)).astype(np.float32) / 255.0
    img = img[np.newaxis, np.newaxis, ...]   # (1, 1, 32, 128)
    logits = sess.run(None, {"input": img})[0]
    return ctc_decode(logits)   # greedy CTC decode → plate text string
```

---

## Step 3 — Deploy

After training (either option):

1. Register the model in MLflow (done automatically by training scripts)
2. Set the `champion` alias
3. The model sync agent picks it up on next poll and distributes to all devices
4. `alpr-pilot` restarts automatically with the new model

See `docs/services/MLFlow/model-sync-agent.md` for the full deployment workflow.

---

## Data strategy

### Collecting more crops

The system now saves every plate YOLO detects to `output/crops/` (even without a successful OCR read). Let it run for a few days before the next training cycle.

```bash
# Count available crops
find output/crops -name "*.jpg" | wc -l

# Open labeling tool
python scripts/ocr_training/label_crops.py --crops-dir output/crops --output labels.txt
```

### Augmentation (handled by training script)

With few real images, augmentation multiplies effective dataset size:

| Augmentation | Purpose |
|---|---|
| ±5° rotation | Slightly tilted plates |
| ±20% brightness | Morning/evening lighting |
| ±15% contrast | Overcast vs direct sun |
| Gaussian blur (σ=0.5) | Slightly out-of-focus frames |
| Horizontal flip | Not applied — flips break plate text |

### Iterative improvement

Train → deploy → collect new crops → label new errors → retrain. Each cycle improves accuracy on the specific plates your cameras see.

```
Week 1: 57 crops → first model → measure CER (character error rate)
Week 2: 150 crops → retrain → compare CER
Week 4: 300 crops → production-quality model
```

---

## Measuring accuracy

```bash
# Run evaluation on a held-out set
python scripts/ocr_training/evaluate_ocr.py \
    --model models/crnn_florida/florida_plate_ocr.onnx \
    --labels labels_val.txt
```

Metrics reported:
- **CER** (character error rate) — fraction of characters wrong
- **Exact match rate** — fraction of plates read 100% correctly
- **Per-class confusion matrix** — which characters get confused most often

Target: CER < 5%, exact match > 85% on held-out Florida plates.

---

## Related

- `scripts/ocr_training/label_crops.py` — interactive labeling tool (to be created)
- `scripts/ocr_training/train_crnn.py` — CRNN training + ONNX export (to be created)
- `scripts/ocr_training/evaluate_ocr.py` — accuracy evaluation (to be created)
- `docs/services/OCR/ocr-service.md` — OCR service reference, known issues
- `docs/services/MLFlow/model-sync-agent.md` — model distribution to edge devices
- `output/crops/` — plate crop images collected by pilot.py
