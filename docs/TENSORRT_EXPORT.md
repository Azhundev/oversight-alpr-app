# TensorRT Export Guide for JetPack 6.1

## Overview

TensorRT provides 2-3x faster inference on NVIDIA Jetson compared to PyTorch. This guide covers exporting YOLOv11 models to TensorRT engine format.

## Prerequisites

Before exporting to TensorRT, ensure you have:

1. **PyTorch 2.5.0** (JetPack 6.1 specific)
2. **TorchVision 0.20.0**
3. **ONNX Runtime GPU 1.20.0** (ARM64 wheel)
4. **Numpy 1.23.5** (critical for compatibility)

### Quick Install

```bash
# Install ONNX Runtime GPU (required for TensorRT export)
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/onnxruntime_gpu-1.20.0-cp310-cp310-linux_aarch64.whl

# Fix numpy version (ONNX Runtime upgrades it, breaking compatibility)
pip3 install numpy==1.23.5

# Verify installation
python3 -c "import onnxruntime; print(f'ONNX Runtime: {onnxruntime.__version__}')"
python3 -c "import numpy; print(f'Numpy: {numpy.__version__}')"
```

## Export Methods

### Method 1: Using YOLO CLI (Recommended)

```bash
# Export YOLOv11n to TensorRT engine
yolo export model=yolo11n.pt format=engine

# This creates: yolo11n.engine (~15-30 seconds)

# Run inference with TensorRT engine
yolo predict model=yolo11n.engine source='a.mp4'
```

### Method 2: Using Python API

```python
from ultralytics import YOLO

# Load PyTorch model
model = YOLO('yolo11n.pt')

# Export to TensorRT engine
engine_path = model.export(
    format='engine',      # TensorRT format
    half=True,            # FP16 precision (faster on Jetson)
    device=0,             # GPU device
    workspace=2,          # Max workspace in GB
    batch=1               # Batch size
)

print(f"Engine exported to: {engine_path}")

# Load and use TensorRT engine
trt_model = YOLO(engine_path)
results = trt_model('a.mp4')
```

### Method 3: Automatic Export in Pilot

The pilot script automatically exports to TensorRT on first run if `use_tensorrt=True`:

```bash
python3 pilot.py  # Auto-exports yolo11n.pt → yolo11n.engine
```

## Export Options

### Precision Modes

**FP16 (Recommended for Jetson):**
```bash
yolo export model=yolo11n.pt format=engine half=True
```
- 2x faster inference
- 50% less memory
- Minimal accuracy loss (<1%)
- Best for Jetson Orin NX

**FP32 (Full Precision):**
```bash
yolo export model=yolo11n.pt format=engine half=False
```
- Slower but maintains full accuracy
- Use if FP16 causes issues

### Batch Size

**Single Frame (Default):**
```bash
yolo export model=yolo11n.pt format=engine batch=1
```
- Best for real-time video streams

**Batch Processing:**
```bash
yolo export model=yolo11n.pt format=engine batch=4
```
- Process multiple frames together
- Higher throughput, more latency

### Workspace Size

```bash
yolo export model=yolo11n.pt format=engine workspace=2
```
- Max GPU memory for optimization (in GB)
- Default: 4GB
- Reduce if CUDA OOM errors occur

## Model Comparison

| Model | PyTorch FPS | TensorRT FP16 FPS | Speedup | Engine Size |
|-------|-------------|-------------------|---------|-------------|
| YOLOv11n | 12-15 | 28-32 | 2.3x | ~10MB |
| YOLOv11s | 8-10 | 20-24 | 2.5x | ~25MB |
| YOLOv11m | 5-6 | 14-16 | 2.7x | ~55MB |
| YOLOv11l | 3-4 | 10-12 | 3.0x | ~100MB |

*Tested on Jetson Orin NX @ 1920x1080*

## Verification

### Check Engine Created

```bash
ls -lh *.engine
# Should show: yolo11n.engine (~10-15MB)
```

### Run Benchmark

```python
import time
import numpy as np
from ultralytics import YOLO

# Load TensorRT engine
model = YOLO('yolo11n.engine')

# Warmup (important for TensorRT)
dummy = np.zeros((640, 640, 3), dtype=np.uint8)
for _ in range(10):
    model(dummy, verbose=False)

# Benchmark
times = []
for _ in range(100):
    start = time.time()
    model(dummy, verbose=False)
    times.append(time.time() - start)

avg_time = np.mean(times) * 1000
fps = 1 / np.mean(times)

print(f"Average inference: {avg_time:.1f}ms")
print(f"FPS: {fps:.1f}")
```

Expected results:
- YOLOv11n: ~32ms (31 FPS)
- YOLOv11s: ~48ms (21 FPS)
- YOLOv11m: ~68ms (15 FPS)

## Troubleshooting

### Issue: "onnxruntime not found"

**Solution:**
```bash
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/onnxruntime_gpu-1.20.0-cp310-cp310-linux_aarch64.whl
```

### Issue: Export crashes or hangs

**Causes:**
1. Wrong numpy version
2. Insufficient GPU memory
3. Corrupted model file

**Solutions:**
```bash
# Fix numpy version
pip3 install numpy==1.23.5

# Reduce workspace size
yolo export model=yolo11n.pt format=engine workspace=1

# Re-download model
rm yolo11n.pt
yolo export model=yolo11n.pt format=engine
```

### Issue: "ImportError" after ONNX Runtime install

**Cause:** ONNX Runtime upgrades numpy to latest, breaking TorchVision

**Solution:**
```bash
# Always reinstall numpy 1.23.5 after ONNX Runtime
pip3 install numpy==1.23.5

# Verify
python3 -c "import torch; import torchvision; print('OK')"
```

### Issue: Lower FPS than expected

**Checks:**
```bash
# 1. Verify power mode
sudo nvpmodel -q
# Should show: MAXN (mode 0)

# 2. Lock clocks
sudo jetson_clocks

# 3. Check GPU utilization
sudo tegrastats
# GR3D should be near 100%

# 4. Verify FP16 is enabled
ls -lh yolo11n.engine
# Should be ~10MB (FP32 would be ~20MB)
```

### Issue: Accuracy drop with FP16

**Expected:** <1% mAP loss with FP16

**If unacceptable:**
```bash
# Use FP32 (slower but full precision)
yolo export model=yolo11n.pt format=engine half=False
```

## Advanced Usage

### Custom Model Export

If you trained a custom YOLOv11 model:

```bash
# Export custom plate detector
yolo export model=runs/detect/train/weights/best.pt format=engine half=True

# Use in pilot
python3 pilot.py --model runs/detect/train/weights/best.engine
```

### Dynamic Batch Size (Not Recommended for Jetson)

```python
model.export(
    format='engine',
    dynamic=True,  # Allow variable input sizes
    half=True
)
```

**Note:** Dynamic shapes reduce optimization effectiveness. Use fixed batch size for best performance.

### Export Multiple Models

```bash
# Export all model sizes
for model in yolo11n.pt yolo11s.pt yolo11m.pt; do
    yolo export model=$model format=engine half=True
done
```

## Integration with Pilot

The pilot script uses TensorRT automatically:

```python
# In pilot.py
detector = YOLOv11Detector(
    vehicle_model_path='yolo11n.pt',
    use_tensorrt=True,  # Enable TensorRT
    fp16=True,          # Use FP16 precision
    device='cuda:0'
)

# On first run, automatically exports to yolo11n.engine
# Subsequent runs load the engine directly (faster startup)
```

## Performance Tips

1. **Always warmup** (5-10 iterations) before benchmarking
2. **Use FP16** for Jetson (2x faster, minimal accuracy loss)
3. **Fix batch size** during export (better optimization)
4. **Set max performance mode** (`sudo nvpmodel -m 0`)
5. **Lock GPU clocks** (`sudo jetson_clocks`)
6. **Monitor GPU usage** (`sudo tegrastats`) to ensure full utilization

## Export Formats Comparison

| Format | Speed | Compatibility | Use Case |
|--------|-------|---------------|----------|
| PyTorch (.pt) | Baseline | All platforms | Development |
| ONNX (.onnx) | 1.2-1.5x | CPU/GPU | Cross-platform |
| TensorRT (.engine) | 2-3x | NVIDIA GPUs | Production (Jetson) |
| OpenVINO | 1.5-2x | Intel CPUs | Edge deployment |

**For Jetson Orin NX: Always use TensorRT (.engine)**

## Resources

- **TensorRT Documentation:** https://docs.nvidia.com/deeplearning/tensorrt/
- **Ultralytics Export Guide:** https://docs.ultralytics.com/modes/export/
- **Jetson TensorRT:** https://developer.nvidia.com/tensorrt

## Summary

**Quick Export:**
```bash
yolo export model=yolo11n.pt format=engine
yolo predict model=yolo11n.engine source='a.mp4'
```

**Success Criteria:**
- ✅ Engine file created (~10-15MB)
- ✅ FPS 2-3x faster than PyTorch
- ✅ No accuracy loss (<1%)
- ✅ GPU utilization near 100%
