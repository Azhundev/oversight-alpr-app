# OCR Service

**Module:** `edge_services/ocr/`
**Active class:** `PlateOCR` (`plate_ocr.py`) — PaddleOCR, async via `ThreadPoolExecutor`

The OCR service converts license plate crop images into text strings. It runs on the Jetson Orin NX after the YOLO plate detector identifies bounding boxes, and outputs normalized plate text with a confidence score to the event processor.

---

## Current setup (pilot.py)

```python
from ocr.plate_ocr import PlateOCR

ocr = PlateOCR(use_gpu=True, use_easyocr=False)
ocr.warmup(iterations=1)

# Runs async — main thread never blocks on OCR
ocr_executor = ThreadPoolExecutor(max_workers=1)
fut = ocr_executor.submit(ocr.recognize_plate_crop, crop)
# ... collect fut.result() at top of next frame
```

OCR is submitted to a single background thread so YOLO detection never waits for it. Results arrive 1–2 frames later and are cached per track.

---

## Files

| File | Status | Purpose |
|---|---|---|
| `plate_ocr.py` | **Active** | `PlateOCR` — PaddleOCR with preprocessing, currently used by pilot.py |
| `crnn_ocr_service.py` | Ready, not deployed | Thread-safe ONNX CRNN — deploy once 500+ labeled samples are available |
| `ocr_service.py` | Superseded | `PaddleOCRService` — synchronous, kept for reference |
| `enhanced_ocr.py` | Superseded | `EnhancedOCRService` — 5-strategy multi-pass, kept for reference |

---

## PlateOCR (active)

**File:** `edge_services/ocr/plate_ocr.py`

```python
PlateOCR(
    use_gpu=True,
    use_easyocr=False,   # EasyOCR disabled — poor accuracy on plate crops, adds latency
    use_paddleocr=True,
    enable_ensemble=True,
)
```

### Methods

| Method | Description |
|---|---|
| `recognize_plate_crop(crop)` | Takes BGR numpy array, returns `(text, conf)` or `None`. Used by the async executor. |
| `read(crop)` | Same input, returns `OCRResult` with `.text`, `.confidence`, `.source`. |
| `warmup(iterations=1)` | Pre-warms PaddleOCR to avoid cold-start on first real frame. |

### Processing pipeline

```
plate crop (BGR)
    │
    ▼
Upscale if height < 50px (INTER_CUBIC)
    │
    ▼
Add 10px white border
    │
    ▼
Strategy 1: CLAHE + NL-means denoise
Strategy 2: Adaptive threshold (auto-invert if dark)
Strategy 3: CLAHE + sharpen (Laplacian)
    │
    ▼ (each strategy → PaddleOCR)
    │
    ▼
Select best result by confidence
    │
    ▼
Normalize: uppercase, strip non-alphanumeric
    │
    ▼
Florida pattern check → +0.10 confidence boost if valid
    │
    ▼
(text, confidence)
```

### Florida pattern validation

```
ABC1234   ← 3 letters + 4 digits (standard)
ABCD12    ← 3 letters + letter + 2 digits (specialty)
123ABC    ← 3 digits + 3 letters (older format)
AB12CD    ← 2+2+2
```

Any result matching a pattern gets a +0.10 confidence boost on top of PaddleOCR's raw score.

### Character correction

Position-aware substitutions for the standard `ABC1234` format:

| Position | Expected | Common misread | Correction |
|---|---|---|---|
| 1–3 (letter region) | Letter | `0→O`, `1→I`, `8→B` | digit → letter |
| 4–7 (digit region) | Digit | `O→0`, `I→1`, `B→8`, `G→6`, `S→5`, `Z→2` | letter → digit |

---

## CRNNOCRService (ready, not deployed)

**File:** `edge_services/ocr/crnn_ocr_service.py`

A lightweight CRNN model exported to ONNX. Fully thread-safe (`onnxruntime.InferenceSession`), faster than PaddleOCR (~5–20ms vs ~200ms), and works correctly with `ThreadPoolExecutor`.

**Not currently deployed** because the CRNN requires 500+ labeled real plate crops to converge and we have ~58 today. The training pipeline is fully built — see `docs/services/OCR/ocr-training-guide.md`.

To deploy when ready:

```python
# In pilot.py — swap PlateOCR for CRNNOCRService
from ocr.crnn_ocr_service import CRNNOCRService

self.ocr = CRNNOCRService(
    model_path="models/crnn_florida/florida_plate_ocr.onnx",
    use_gpu=True,
)
self.ocr_min_confidence = 0.50
self.ocr_max_confidence_target = 0.80
```

---

## Performance on Jetson Orin NX

| Engine | Latency | Mode | Notes |
|---|---|---|---|
| `PlateOCR` (PaddleOCR, 3 strategies) | ~600–900ms | Async | Doesn't block YOLO; result arrives next frame |
| `CRNNOCRService` (ONNX, CPU) | ~30ms | Async | CUDA EP unavailable in this Jetson ONNX build |
| `CRNNOCRService` (ONNX, GPU) | ~5–10ms | Async | Once CUDA EP available or TensorRT export |

PaddleOCR runs at ~200ms per strategy × 3 strategies ≈ 600ms total. At 15 FPS (67ms/frame) this means OCR results lag the current frame by ~9 frames — acceptable for gate/parking use cases.

---

## Confidence scores

PaddleOCR's confidence is not well-calibrated for plate crops — it often returns 0.90–1.00 even for incorrect reads. The effective threshold in pilot.py is:

```python
self.ocr_min_confidence = 0.40   # accept almost all reads
self.ocr_max_confidence_target = 0.75  # stop re-running OCR once this is hit
```

The Florida pattern boost (+0.10) helps the useful reads rise slightly above noise, but confidence alone is not a reliable quality signal with PaddleOCR. Per-track accumulation (re-running OCR on the same plate across multiple frames) is the real quality mechanism.

---

## Async pattern in pilot.py

```python
# Top of process_frame — collect previous results
for track_id, fut in list(self.track_ocr_futures.items()):
    if not fut.done():
        continue
    del self.track_ocr_futures[track_id]
    result = fut.result()
    if result:
        text, conf = result
        # ... update cache, publish event

# Later — submit new jobs
crop = frame[y1:y2, x1:x2].copy()   # copy before submit
self._ocr_future_bboxes[track_id] = plate_bbox
fut = self.ocr_executor.submit(self.ocr.recognize_plate_crop, crop)
self.track_ocr_futures[track_id] = fut
```

Key points:
- `crop.copy()` is required — the frame buffer advances while OCR runs in the background
- `max_workers=1` — only one PaddleOCR call at a time (not concurrency-safe with multiple workers)
- Futures are collected at the **top** of the next frame, not inside the submission loop

---

## Known issues

### PaddleOCR confidence inflation

PaddleOCR reports 0.90–1.00 confidence on many incorrect reads. Do not rely on confidence alone to gate plate events. Use the `ocr_max_attempts` limit and per-track caching instead.

### Florida orange logo

The Sunshine State citrus graphic between letter and number groups can be detected as a character (often read as `C`, `O`, or garbage). To remove it:

```yaml
# config/ocr.yaml
preprocessing:
  remove_color: true   # masks HSV orange (hue 5–25°) and inpaints before OCR
```

Disabled by default — adds ~20ms per crop and is not always necessary.

### EasyOCR not suitable for real-time plate crops

EasyOCR was tested as a second vote (`use_easyocr=True`). Results on plate crops were poor — its CRAFT text detector splits plate numbers into fragments or misses regions entirely. EasyOCR is disabled (`use_easyocr=False`). Do not re-enable without re-testing on representative crops.

### ONNX CUDA EP not available

This Jetson's `onnxruntime` package was built without the CUDA Execution Provider. `CRNNOCRService` falls back to CPU (~30ms). Still fast enough for async use but not as fast as a GPU-enabled build.

---

## Related

- `docs/services/OCR/ocr-training-guide.md` — How to train the CRNN model once crops are collected
- `edge_services/ocr/crnn_ocr_service.py` — Thread-safe CRNN service (deploy when trained)
- `data/ocr_training/labels.txt` — 58 labeled crops; target 500+ for CRNN training
- `output/crops/` — Live plate crops saved by pilot.py (accumulate over time)
- `scripts/ocr/` — Label, train, and evaluate scripts
