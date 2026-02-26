# OCR Service

**Module:** `edge_services/ocr/`
**Config:** `config/ocr.yaml`
**Engine:** PaddleOCR (PP-OCRv4) + optional EasyOCR ensemble

The OCR service converts license plate image crops into text strings. It runs on the Jetson Orin NX after the plate detector identifies plate bounding boxes, and outputs normalized plate text with a confidence score to the event processor.

---

## Overview

Three classes are available, each trading latency for accuracy:

| Class | File | Engine(s) | Strategies | Best for |
|---|---|---|---|---|
| `PaddleOCRService` | `ocr_service.py` | PaddleOCR | 3 | Production (primary) |
| `EnhancedOCRService` | `enhanced_ocr.py` | PaddleOCR | 5 | Difficult conditions |
| `PlateOCR` | `plate_ocr.py` | PaddleOCR + EasyOCR | 3 × 2 engines | Highest accuracy |

`PaddleOCRService` is the default used by `pilot.py`. `EnhancedOCRService` and `PlateOCR` are drop-in replacements for situations requiring higher accuracy at the cost of extra latency.

---

## Quick Start

```python
from edge_services.ocr import PaddleOCRService
from shared.schemas.event import BoundingBox

ocr = PaddleOCRService(config_path="config/ocr.yaml", use_gpu=True)
ocr.warmup()

# Single plate
bbox = BoundingBox(x1=100, y1=200, x2=300, y2=260)
result = ocr.recognize_plate(frame, bbox)
if result:
    print(f"{result.text}  conf={result.confidence:.2f}")

# Batch (more efficient for multiple plates per frame)
results = ocr.recognize_plates_batch(frame, [bbox1, bbox2, bbox3])
```

---

## Processing Pipeline

```
frame + bounding box(es)
         │
         ▼
  ┌─────────────────────────────────────────┐
  │            Plate Crop Extraction        │
  │  Clamp coords to frame bounds           │
  │  Reject invalid / empty crops           │
  └─────────────┬───────────────────────────┘
                │
         ┌──────┴───────┐
         │              │
         ▼              ▼
  Strategy 1      Strategy 2         Strategy 3
  Raw image       Preprocessed       2× Upscaled
  (no changes)    (CLAHE + denoise   (for plates
                  + optional         < 80px tall)
                  sharpening)
         │              │                  │
         └──────┬────────┘──────────────────┘
                │
                ▼
        Select highest confidence result
                │
                ▼
        Post-processing
        - Uppercase, strip non-alphanumeric
        - Apply character whitelist
        - Filter by confidence / length
                │
                ▼
        PlateDetection(text, confidence, bbox, raw_text)
```

---

## Classes

### `PaddleOCRService` (primary)

**File:** `edge_services/ocr/ocr_service.py`

```python
PaddleOCRService(
    config_path="config/ocr.yaml",
    use_gpu=True,
    enable_tensorrt=False,   # TensorRT optimization (requires model conversion)
)
```

**Methods:**

| Method | Description |
|---|---|
| `recognize_plate(frame, bbox, preprocess=True)` | Single plate — tries all 3 strategies, returns best |
| `recognize_plates_batch(frame, bboxes, preprocess=True)` | Multiple plates per frame — more efficient than looping |
| `preprocess_plate_crop(plate_crop)` | Standalone preprocessing (CLAHE, denoise, optional Florida orange logo removal) |
| `normalize_plate_text(text)` | Uppercase + strip + whitelist |
| `warmup(iterations=5)` | Run dummy inference to avoid cold-start latency on first real frame |

**Multi-strategy logic:**

1. **Raw** — Pass the crop directly; best for high-quality, well-lit plates
2. **Preprocessed** — Apply `preprocess_plate_crop()` (CLAHE contrast enhancement, optional denoising, optional sharpening); best for noisy or poorly lit plates
3. **2× Upscaled** — Only applied when plate height < 80 px; helps for distant plates

The strategy with the highest PaddleOCR confidence score wins.

**Florida orange logo removal:**

Enabled via `preprocessing.remove_color: true` in `config/ocr.yaml`. Converts the crop to HSV, masks the orange Sunshine State logo (hue 5–25°), and inpaints the masked region before running OCR. Disabled by default because PaddleOCR generally handles color input well.

---

### `EnhancedOCRService`

**File:** `edge_services/ocr/enhanced_ocr.py`

Drop-in replacement with 5 preprocessing strategies and majority voting. Adds ~2–3× latency but improves accuracy in difficult conditions.

```python
EnhancedOCRService(
    config_path="config/ocr.yaml",
    use_gpu=True,
    enable_multi_pass=True,   # set False to use only Strategy 1 (same as PaddleOCRService)
)
```

**5 preprocessing strategies:**

| # | Technique | Best for |
|---|---|---|
| 1 | CLAHE + fast NL-means denoise | Standard conditions |
| 2 | Global histogram equalization + bilateral filter | Faded or low-contrast plates |
| 3 | Adaptive Gaussian threshold (auto-inverted) | Uneven lighting, shadows |
| 4 | CLAHE + morphological closing | Broken or incomplete characters |
| 5 | CLAHE + unsharp masking (3×3 Laplacian) | Motion blur |

**Voting:**

Results from all strategies are grouped by normalized text. The text that appears most often across strategies wins. If multiple strategies agree, the confidence is boosted by `min(0.1 × (votes − 1), 0.15)` — capped at +15%.

---

### `PlateOCR`

**File:** `edge_services/ocr/plate_ocr.py`

Ensemble of PaddleOCR + EasyOCR with Florida plate pattern validation.

```python
from edge_services.ocr.plate_ocr import PlateOCR

ocr = PlateOCR(
    use_gpu=True,
    use_easyocr=True,
    use_paddleocr=True,
    enable_ensemble=True,
)

result = ocr.read(plate_crop)  # takes BGR numpy array directly
if result:
    print(result.text, result.confidence, result.source)
    # source: 'paddle', 'easyocr', or 'ensemble' (both agreed)
```

**`OCRResult` fields:**

| Field | Type | Description |
|---|---|---|
| `text` | str | Final normalized plate text |
| `confidence` | float | 0.0–1.0; boosted if engines agree or pattern validates |
| `raw_text` | str | Text before normalization |
| `source` | str | `'paddle'`, `'easyocr'`, or `'ensemble'` |

**Florida pattern validation:**

```
ABC1234   ← 3 letters + 4 digits (standard)
ABCD12    ← 3 letters + letter + 2 digits (specialty)
123ABC    ← 3 digits + 3 letters (older)
AB12CD    ← 2 letters + 2 digits + 2 letters
```

Any result matching a known pattern gets a +0.10 confidence boost. If two or more strategies agree on the same text, an additional +0.10 is added.

**Character correction table:**

Position-aware substitutions applied before pattern matching:

| Char | Corrected to | Applied in positions |
|---|---|---|
| `O` | `0` | Numeric region (chars 4+) |
| `I` | `1` | Numeric region |
| `L` | `1` | Numeric region |
| `S` | `5` | Numeric region |
| `Z` | `2` | Numeric region |
| `B` | `8` | Numeric region |
| `G` | `6` | Numeric region |

Reverse corrections (`0→O`, `1→I`, etc.) are applied in the letter region (first 3 chars).

---

## Configuration (`config/ocr.yaml`)

```yaml
ocr:
  paddle:
    use_gpu: true
    gpu_mem: 2000               # MB allocated on GPU
    det_db_thresh: 0.3          # text detection sensitivity (lower = more detections)
    det_db_box_thresh: 0.6      # box confidence threshold
    rec_batch_num: 6            # plates processed together per inference call

  preprocessing:
    min_plate_height: 48        # upscale plates shorter than this (pixels)
    target_height: 128          # upscale target height
    denoise: false              # NL-means denoising (disabled: too aggressive)
    enhance_contrast: false     # CLAHE (disabled: PaddleOCR handles internally)
    sharpen: false              # unsharp mask (disabled: can cause artifacts)
    remove_color: false         # Florida orange logo inpainting

  postprocessing:
    use_whitelist: true
    whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    min_confidence: 0.40        # reject results below this
    min_text_length: 3          # reject very short reads
    max_text_length: 10         # reject very long reads (likely misdetections)

  performance:
    use_tensorrt: true
    precision: "FP16"
    batch_timeout_ms: 50        # wait up to 50ms to fill a batch
    max_batch_size: 8

  fallback:
    enabled: false
    provider: "tesseract"       # tesseract or easyocr
```

### Tuning tips

| Symptom | Adjustment |
|---|---|
| Too many false reads | Raise `min_confidence` (e.g. 0.55) |
| Missing low-quality plates | Lower `min_confidence` (e.g. 0.30) |
| Short fragments like "AB" passing | Raise `min_text_length` to 5–6 |
| Distant cameras miss plates | Lower `min_plate_height` to 32 |
| Florida logo misread as 'C'/'O' | Enable `remove_color: true` |
| Blurry video stream | Enable `sharpen: true`, or switch to `EnhancedOCRService` |

---

## Preprocessing Deep Dive

All preprocessing is applied to grayscale. Images are returned as 3-channel BGR because PaddleOCR expects BGR input.

```
plate crop (BGR)
    │
    ├── [optional] Florida orange mask + inpaint (HSV color segmentation)
    │
    ▼
grayscale conversion
    │
    ├── upscale if height < min_plate_height (INTER_CUBIC)
    │
    ├── add 10px white border (helps OCR at edges)
    │
    ├── CLAHE (clipLimit=2.0, tileGrid=8×8)
    │
    ├── fast NL-means denoising (h=10, templateWindow=7, searchWindow=21)
    │
    └── [optional] unsharp mask (Laplacian kernel, weight 1.5/-0.5)
    │
    ▼
BGR conversion → passed to PaddleOCR
```

---

## Output: `PlateDetection`

Both `PaddleOCRService` and `EnhancedOCRService` return a `PlateDetection` from `shared/schemas/event.py`:

```python
@dataclass
class PlateDetection:
    text: str           # "ABC1234"
    confidence: float   # 0.87
    bbox: BoundingBox   # original crop coordinates in the full frame
    raw_text: str       # "ABC1234[preprocessed]" — strategy name appended for debug
```

`PlateOCR.read()` returns an `OCRResult` (defined in `plate_ocr.py`) instead, since it is used standalone without a full-frame bbox.

---

## Performance on Jetson Orin NX

Approximate latencies (single plate crop, GPU, FP16):

| Class | Typical latency |
|---|---|
| `PaddleOCRService` (strategy 1 only) | ~15–25 ms |
| `PaddleOCRService` (all 3 strategies) | ~40–60 ms |
| `EnhancedOCRService` (5 strategies) | ~80–120 ms |
| `PlateOCR` (PaddleOCR + EasyOCR) | ~100–150 ms |

Batch processing with `recognize_plates_batch()` amortizes overhead — processing 4 plates together is faster than 4 sequential `recognize_plate()` calls.

**Warmup:** Always call `.warmup()` before the first real inference. PaddleOCR JIT-compiles on first run; warmup prevents a 2–5 second stall on the first frame.

---

## Troubleshooting

**OCR returns nothing on valid plates**

- Check `min_confidence` — may be too high for the camera quality; try 0.30
- Check plate height: crops < 48 px are hard for any OCR engine; adjust camera angle or zoom

**Plates read incorrectly (O/0, I/1 confusion)**

- Use `PlateOCR` with Florida pattern validation — the character correction tables handle the most common substitution errors
- Or enable `EnhancedOCRService` with majority voting

**High CPU/GPU load**

- Ensure `use_gpu: true` in config; PaddleOCR silently falls back to CPU if GPU is unavailable
- Reduce `rec_batch_num` if GPU memory is tight
- Use `PaddleOCRService` with `enable_tensorrt=True` after exporting the PaddleOCR model to TensorRT

**EasyOCR import error**

- `PlateOCR` gracefully degrades to PaddleOCR-only if EasyOCR is not installed
- Install: `pip install easyocr`

---

## Known Issues & Pitfalls

### PaddleOCR is not thread-safe (DO NOT run async)

**Symptom:** Moving OCR to a `ThreadPoolExecutor` background thread causes all OCR futures to silently return `None`. The `track_ocr_cache` stays empty, no plate text appears in the display, but plate bounding boxes are still drawn (YOLO detection unaffected).

**Root cause:** PaddleOCR's Paddle inference C++ backend is not safe to call from a non-main thread. The call raises an internal exception that is swallowed by `fut.result()` inside the `except Exception` handler, making it appear like OCR ran but found nothing.

**What was tried:**
```python
# DOES NOT WORK — Paddle inference fails silently in worker thread
self.ocr_executor = ThreadPoolExecutor(max_workers=1)
self.ocr_executor.submit(lambda: self.ocr.recognize_plate(...))
```

**Fix:** Keep OCR synchronous. The existing `should_run_ocr()` throttling in `pilot.py` already limits OCR to at most `ocr_max_attempts` calls per track and skips tracks that don't yet have 2+ stable frames — so synchronous OCR at ~200ms does not block the pipeline at a meaningful rate.

**If async is ever needed:** use `multiprocessing` (separate process with its own Paddle runtime) rather than `threading`.

---

### EasyOCR (PlateOCR) is too slow for real-time use on Jetson

**Symptom:** Switching `pilot.py` to `PlateOCR` (EasyOCR + PaddleOCR ensemble) causes plate crop count to drop dramatically. Even with GPU, EasyOCR takes ~700ms per inference call on the Orin NX.

**Root cause:** EasyOCR is accurate but not optimized for Jetson. At 700ms per call, it blocks the frame loop, starving YOLO of frames.

**Fix:** Use `PaddleOCRService` (synchronous, ~200ms, 3 strategies) as the primary OCR engine. EasyOCR can be used offline for post-processing or validation but not in the real-time loop.

---

### Florida orange logo breaks character segmentation

**Symptom:** OCR reads garbage in the middle section of the plate (e.g. `OCP🍊4B0` → `OCPEHED`). The orange Sunshine State graphic between the letter and number groups is detected as characters.

**Fix:** Enable `remove_color: true` in `config/ocr.yaml`. This masks the orange HSV region (hue 5–25°) and inpaints it with surrounding pixels before OCR runs, eliminating the false character detections.

```yaml
preprocessing:
  remove_color: true   # Required for Florida plates
```

---

## Related

- `edge_services/detector/` — YOLO plate detector that produces bounding boxes fed into OCR
- `edge_services/event_processor/` — Consumes `PlateDetection` results and publishes Kafka events
- `shared/schemas/event.py` — `BoundingBox` and `PlateDetection` dataclasses
- `config/ocr.yaml` — Full configuration reference
- `docs/alpr/project-architecture-charts.md` — System-level pipeline diagram
