# Model Quantization Guide

Complete breakdown of quantization settings for all models in the OVR-ALPR pipeline.

---

## Overview

The OVR-ALPR system uses different quantization levels for different models to balance performance and accuracy on NVIDIA Jetson Orin NX.

**Current Configuration**:
- **YOLO Models**: FP16 (16-bit) via TensorRT
- **PaddleOCR Models**: FP32 (32-bit) on CPU

---

## Quantization by Model

### 1. YOLOv11 Vehicle Detection Model

**Source Model**: `models/yolo11n.pt` (PyTorch)
**TensorRT Engine**: `models/yolo11n.engine` (7.5 MB)
**Quantization**: **FP16 (Half Precision)**

**Configuration** (pilot.py:93):
```python
self.detector = YOLOv11Detector(
    vehicle_model_path="models/yolo11n.pt",
    use_tensorrt=True,
    fp16=True,   # ← FP16 quantization enabled
    int8=False,  # ← INT8 disabled (has bugs on Jetson)
    batch_size=1,
)
```

**Performance**:
- Inference time: 15-20ms per frame
- Speedup: 2-3x faster than FP32 PyTorch
- Accuracy: Minimal loss (<1%)

**Export Process** (detector_service.py:109-117):
```python
engine_path = model.export(
    format='engine',
    half=True,           # FP16 precision
    device='cuda:0',
    batch=1,
    workspace=2,         # 2GB workspace
)
```

---

### 2. YOLOv11 Plate Detection Model

**Source Model**: `models/yolo11n-plate.pt` (Custom trained)
**TensorRT Engine**: `models/yolo11n-plate.engine` (7.3 MB)
**Quantization**: **FP16 (Half Precision)**

**Configuration**: Same as vehicle model (inherited)

**Performance**:
- Inference time: 5-10ms per frame
- Input size: 416x416 (trained at this resolution)
- Speedup: 2-3x faster than FP32

**Notes**:
- Uses same FP16 TensorRT export as vehicle model
- Optimized for small object detection (license plates)
- FP16 maintains accuracy for plate detection

---

### 3. PaddleOCR Detection Model

**Model**: `en_PP-OCRv3_det_infer`
**Quantization**: **FP32 (Full Precision)**
**Backend**: CPU (PaddlePaddle Inference)

**Configuration** (pilot.py:108-109):
```python
self.ocr = PaddleOCRService(
    config_path="config/ocr.yaml",
    use_gpu=True,           # Limited GPU support
    enable_tensorrt=False,  # TensorRT disabled
)
```

**Performance**:
- Inference time: 30-50ms per plate
- Precision: 32-bit floating point
- No quantization applied

**Limitations**:
- PaddleOCR has limited GPU acceleration
- TensorRT conversion requires manual model conversion
- Runs primarily on CPU even with `use_gpu=True`

---

### 4. PaddleOCR Recognition Model

**Model**: `en_PP-OCRv4_rec_infer`
**Quantization**: **FP32 (Full Precision)**
**Backend**: CPU (PaddlePaddle Inference)

**Performance**:
- Inference time: 50-100ms per plate
- Precision: 32-bit floating point
- Most expensive operation in the pipeline

---

## Quantization Summary Table

| Model | Source | Engine | Quantization | Precision | Size | Inference Time | Speedup |
|-------|--------|--------|--------------|-----------|------|----------------|---------|
| **Vehicle YOLO** | `yolo11n.pt` | `yolo11n.engine` | **FP16** | 16-bit | 7.5 MB | 15-20ms | 2-3x |
| **Plate YOLO** | `yolo11n-plate.pt` | `yolo11n-plate.engine` | **FP16** | 16-bit | 7.3 MB | 5-10ms | 2-3x |
| **OCR Detection** | PaddleOCR v3 | N/A | **FP32** | 32-bit | N/A | 30-50ms | 1x |
| **OCR Recognition** | PaddleOCR v4 | N/A | **FP32** | 32-bit | N/A | 50-100ms | 1x |

**Total Pipeline Latency**: 100-180ms per frame (with OCR)

---

## Why FP16 Instead of INT8?

### INT8 Issues on Jetson

From pilot.py:94:
```python
int8=False,  # INT8 has TensorRT bugs with this model/Jetson combo
```

**Problems with INT8**:
1. **TensorRT Export Failures**: INT8 export crashes or produces corrupted engines
2. **Calibration Required**: Needs calibration dataset (`calibration.yaml`)
3. **Accuracy Degradation**: Significant accuracy loss for small objects (plates)
4. **Debugging Complexity**: Hard to diagnose when INT8 model fails

**Code Path for INT8** (detector_service.py:95-107):
```python
if self.int8:
    logger.info("Exporting model to TensorRT with INT8 precision...")
    engine_path = model.export(
        format='engine',
        int8=True,
        device=self.device,
        batch=self.batch_size,
        workspace=4,  # 4GB workspace for calibration
        data='calibration.yaml',  # Calibration dataset required
        dynamic=False,  # Disable dynamic shapes for INT8
        imgsz=640,
    )
```

### FP16 Advantages

✅ **Stable**: No export failures on Jetson
✅ **Fast**: 2-3x speedup over FP32 (close to INT8 performance)
✅ **Accurate**: <1% accuracy loss
✅ **Simple**: No calibration dataset required
✅ **Reliable**: Consistent inference times

---

## Precision Comparison

| Precision | Bits | Range | Accuracy | Speed | Jetson Support |
|-----------|------|-------|----------|-------|----------------|
| **FP32** | 32 | ±3.4×10³⁸ | 100% (baseline) | 1x | ✅ Full |
| **FP16** | 16 | ±6.5×10⁴ | 99% | 2-3x | ✅ **Recommended** |
| **INT8** | 8 | -128 to 127 | 95-98% | 3-4x | ⚠️ Unstable |

---

## Optimization Opportunities

### 1. Enable PaddleOCR TensorRT (Advanced)

**Potential Speedup**: 2-4x faster OCR

**Steps**:
1. Convert PaddleOCR models to ONNX
2. Convert ONNX to TensorRT engines
3. Update PaddleOCRService to use TensorRT backend

**Code Change** (pilot.py):
```python
self.ocr = PaddleOCRService(
    config_path="config/ocr.yaml",
    use_gpu=True,
    enable_tensorrt=True,  # Enable TensorRT for OCR
)
```

**Challenges**:
- Requires manual model conversion
- PaddleOCR TensorRT support is limited
- May break preprocessing pipeline

---

### 2. Try INT8 for YOLO (Experimental)

**Potential Speedup**: 3-4x faster detection

**Requirements**:
1. Create calibration dataset (`calibration.yaml`)
2. Collect 500-1000 representative images
3. Test accuracy thoroughly

**Code Change** (pilot.py):
```python
self.detector = YOLOv11Detector(
    vehicle_model_path="models/yolo11n.pt",
    use_tensorrt=True,
    fp16=False,
    int8=True,  # Enable INT8 quantization
    batch_size=1,
)
```

**Calibration Dataset Format** (`calibration.yaml`):
```yaml
path: ./calibration
train: images/train
val: images/val

nc: 80  # Number of classes (COCO)
names: ['person', 'bicycle', 'car', ...]
```

**Risk**: May reduce plate detection accuracy by 2-5%

---

### 3. Use Lighter OCR Models

**Alternative OCR Engines**:
- **EasyOCR**: Simpler, faster, less accurate
- **TrOCR**: Transformer-based, GPU-optimized
- **Custom CRNN**: Trained specifically for plates

**Trade-offs**:
- Faster inference (20-50ms)
- Lower accuracy (85-90% vs 95%+)
- Less preprocessing flexibility

---

## Current Performance Breakdown

### Per-Frame Latency (with all features)

```
Camera Ingestion:     5ms      (I/O bound)
Vehicle Detection:   15-20ms   (FP16 TensorRT)
Plate Detection:      5-10ms   (FP16 TensorRT)
Tracking:             <1ms     (CPU)
OCR Detection:       30-50ms   (FP32 CPU)
OCR Recognition:     50-100ms  (FP32 CPU)
Event Processing:     <1ms     (CPU)
Kafka Publishing:     5-10ms   (Network)
─────────────────────────────
Total:              110-196ms  (5-9 FPS)
```

### Bottleneck Analysis

**Primary Bottleneck**: **OCR (80-150ms, 70-85% of total time)**

**Optimization Priority**:
1. **Highest Impact**: Optimize OCR (FP32 → FP16/TensorRT)
2. **Medium Impact**: Per-track throttling (already implemented)
3. **Low Impact**: YOLO INT8 (already fast with FP16)

---

## Recommendations

### Current Setup (Optimal for Stability)

✅ **Keep FP16 for YOLO models**: Stable, fast, accurate
✅ **Keep FP32 for OCR**: Most compatible, reliable
✅ **Use per-track throttling**: Reduces OCR calls by 90%

### Advanced Optimization (For Experts)

⚠️ **Try OCR TensorRT**: If you need <100ms total latency
⚠️ **Try YOLO INT8**: If you have calibration data and can validate accuracy
⚠️ **Use lighter OCR**: If accuracy >85% is acceptable

---

## How to Check Your Current Quantization

### 1. Check TensorRT Engines
```bash
ls -lh models/*.engine
```

Expected output:
```
-rw-rw-r-- 1 jetson jetson 7.5M models/yolo11n.engine
-rw-rw-r-- 1 jetson jetson 7.3M models/yolo11n-plate.engine
```

### 2. Check Code Configuration
```bash
grep -n "fp16\|int8" pilot.py edge-services/detector/detector_service.py
```

### 3. Monitor Inference Times

Run pilot and check logs:
```bash
python pilot.py 2>&1 | grep "detection:"
```

Expected output:
```
Vehicle detection: 6 vehicles in 15.2ms  ← FP16 TensorRT
Plate detection: 2 plates in 8.1ms      ← FP16 TensorRT
```

---

## Changing Quantization Settings

### Switch YOLO to FP32 (Debugging)

**Edit**: `pilot.py:93`
```python
self.detector = YOLOv11Detector(
    use_tensorrt=False,  # Disable TensorRT, use PyTorch
    fp16=True,
    int8=False,
)
```

**Result**: 50-80ms inference (slower, but easier to debug)

### Try YOLO INT8 (Experimental)

**Edit**: `pilot.py:93-94`
```python
self.detector = YOLOv11Detector(
    use_tensorrt=True,
    fp16=False,
    int8=True,  # Enable INT8
)
```

**Create**: `calibration.yaml` (see above)

**Test thoroughly**: Validate plate detection accuracy doesn't drop >5%

---

## Related Documentation

- [Performance Optimization Guide](PERFORMANCE_OPTIMIZATION_GUIDE.md)
- [INT8 Precision Guide](INT8_PRECISION_GUIDE.md)
- [TensorRT Engine Comparison](PT_VS_ENGINE_COMPARISON.md)
- [Services Overview](SERVICES_OVERVIEW.md)

---

## Summary

**Current Configuration**:
- ✅ YOLO models use **FP16 TensorRT** (optimal for Jetson)
- ✅ OCR models use **FP32 CPU** (stable, compatible)
- ✅ Total pipeline: 110-196ms per frame

**Bottleneck**: OCR (70-85% of processing time)

**Recommendation**: Keep current quantization, focus on per-track throttling and frame sampling to improve throughput.
