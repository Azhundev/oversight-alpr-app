# INT8 Calibration Troubleshooting Guide

## Issue Encountered

When trying to enable INT8 quantization, you may encounter this error during TensorRT export:

```
NvMapMemAllocInternalTagged: 1075072515 error 12
NvMapMemHandleAlloc: error 0
TensorRT export failed: NVML_SUCCESS == r INTERNAL ASSERT FAILED at
"/opt/pytorch/pytorch/c10/cuda/CUDACachingAllocator.cpp":838
```

## Root Cause

This is a **CUDA unified memory allocation error** specific to Jetson platforms. It occurs when:

1. **Insufficient GPU memory**: Other processes are using GPU memory
2. **Memory fragmentation**: System memory is fragmented
3. **Runtime export timing**: Exporting TensorRT engine while other models are loaded

The error code 12 means `ENOMEM` (Out of memory).

## Solution: Pre-Export INT8 Engine

Instead of exporting the INT8 engine at runtime (when pilot.py starts), we'll export it **beforehand** using a dedicated script. This ensures maximum available memory.

### Step 1: Free GPU Memory

```bash
# Reboot for cleanest state (recommended)
sudo reboot

# OR stop any GPU-using processes
sudo systemctl stop nvargus-daemon
pkill -f python
```

### Step 2: Run Standalone INT8 Export

```bash
# Export vehicle detection model to INT8 TensorRT engine
python3 scripts/export_int8_engine.py

# This will:
# - Load yolo11n.pt
# - Calibrate using your 355 training video frames
# - Generate yolo11n.engine (INT8 optimized)
# - Take ~10-15 minutes
```

**Expected output:**
```
============================================================
Starting INT8 TensorRT export
  Model: yolo11n.pt
  Calibration data: calibration.yaml
  Workspace: 2GB
  Batch size: 1
  Device: cuda:0
============================================================
This will take 10-15 minutes for INT8 calibration...

[TensorRT calibration progress...]

============================================================
INT8 engine exported successfully!
Engine path: yolo11n.engine
============================================================
```

### Step 3: Update pilot.py to Use Pre-Exported Engine

Once the `.engine` file exists, pilot.py will automatically use it instead of trying to export at runtime:

```python
# detector_service.py will check for .engine file first
# If yolo11n.engine exists, it loads it directly (fast)
# If not, it tries to export (what caused the error)
```

### Step 4: Run Pilot with Pre-Exported Engine

```bash
python3 pilot.py

# Should show:
# "Loading vehicle detection model: yolo11n.engine"
# (NOT "Exporting model to TensorRT...")
```

## Alternative Solutions

### Option 1: Reduce Workspace Size

If export still fails, try with less memory:

```bash
python3 scripts/export_int8_engine.py --workspace 1
```

### Option 2: Use FP16 Instead of INT8

If INT8 continues to fail, FP16 is still a great option (1.5-2x faster than FP32):

```python
# In pilot.py line 79-80:
fp16=True,   # Enable FP16
int8=False,  # Disable INT8
```

FP16 doesn't require calibration and exports much faster.

### Option 3: Use PyTorch Model (Current Fallback)

The system currently falls back to PyTorch mode when INT8 export fails. This works but is slower:

- **PyTorch**: ~40-50ms per frame
- **FP16 TensorRT**: ~25ms per frame
- **INT8 TensorRT**: ~12-15ms per frame

## Verification

After successful INT8 export, verify:

```bash
# Check engine file exists
ls -lh *.engine

# Expected:
# yolo11n.engine (~6MB)

# Run pilot and check inference time
python3 pilot.py

# Look for logs showing:
# "Vehicle detection: X vehicles in 12-15ms"  # INT8 speed
# vs "Vehicle detection: X vehicles in 40-50ms"  # PyTorch speed
```

## Memory Requirements Summary

| Operation | GPU Memory Needed | Notes |
|-----------|-------------------|-------|
| PyTorch inference | ~200MB | Default mode (current) |
| FP16 TensorRT | ~100MB | 2x faster, easy export |
| INT8 TensorRT export | ~500MB+ | One-time, 10-15 min |
| INT8 TensorRT inference | ~50MB | 4x faster after export |

## Understanding the Error

The `NvMapMemHandleAlloc: error 0` indicates Jetson's unified memory allocator (NvMap) couldn't allocate a large contiguous memory block needed for TensorRT calibration.

This doesn't mean your Jetson is broken - it's a common limitation when:
- Multiple models are loaded
- Other processes use GPU
- Memory is fragmented from previous operations

## Best Practice: Always Pre-Export

For production deployments, always export TensorRT engines offline:

```bash
# Development workflow:
1. Train/fine-tune model
2. Export to INT8/FP16 engine (scripts/export_int8_engine.py)
3. Deploy with pre-exported .engine file
4. Pilot.py just loads engine (fast startup)
```

This avoids runtime export delays and memory issues.

## Current Status

✅ Calibration dataset created (355 frames from your videos)
✅ pilot.py configured for INT8
⚠️ INT8 engine export failed due to memory
✅ System working in PyTorch fallback mode (~40ms/frame)

**Next action**: Run `python3 scripts/export_int8_engine.py` after reboot for clean INT8 export.

## Additional Help

If issues persist:

```bash
# Check CUDA/TensorRT installation
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
python3 -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='engine')"

# Check system memory
free -h
nvidia-smi

# Clear cache
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
```

---

**Summary**: The INT8 setup is complete, but runtime export failed due to memory constraints. Use the standalone export script after reboot for best results.
