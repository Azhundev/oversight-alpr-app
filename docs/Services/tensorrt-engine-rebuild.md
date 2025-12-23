# TensorRT Engine Rebuild Guide

## Overview

The OVR-ALPR system uses TensorRT engines for optimized YOLO model inference. This guide explains how the TensorRT engine caching system works and how to rebuild engines when needed.

## How TensorRT Engine Caching Works

### Automatic Engine Building

The system automatically builds TensorRT engines on **first run**:

1. **Initial Load**: When a `.pt` model is loaded, the detector checks for a corresponding `.engine` file
2. **Auto-Export**: If no engine exists, it automatically exports the PyTorch model to TensorRT format
3. **Caching**: The engine is saved to disk and reused on all subsequent runs
4. **Fast Loading**: Pre-built engines load in ~1 second vs ~7 minutes for rebuilding

### Current Engine Status

Both YOLO models now have pre-built TensorRT engines:

```bash
models/
├── yolo11n.pt              # Vehicle detection PyTorch model (5.4 MB)
├── yolo11n.engine          # Vehicle detection TensorRT engine (8.1 MB, 640x640) ✓
├── yolo11n-plate.pt        # Plate detection PyTorch model (5.2 MB)
└── yolo11n-plate.engine    # Plate detection TensorRT engine (7.3 MB, 416x416) ✓
```

**Precision**: FP16 (half precision)
**Input Sizes**:
- Vehicle model: 640x640 (standard YOLO11n)
- Plate model: 416x416 (matches training resolution)
**Performance**: 2-3x faster than PyTorch FP32
**Accuracy**: Minimal loss (<1%) compared to FP32

## When to Rebuild TensorRT Engines

Rebuild engines when:

1. **Model Updated**: After retraining the YOLO models
2. **Precision Change**: Switching between FP16 and INT8 modes
3. **TensorRT Version Update**: After upgrading TensorRT or CUDA
4. **Corruption**: If engine files become corrupted or produce errors
5. **Hardware Change**: After moving models to different Jetson device

## Rebuilding Engines

### Option 1: Automatic Rebuild (Recommended)

Simply delete the engine files and let the system rebuild them on next run:

```bash
# Delete existing engines
rm models/*.engine

# Run ALPR - engines will be rebuilt automatically
python3 pilot.py
```

The first run will take ~7 minutes to build both engines, then future runs will be fast.

### Option 2: Manual Batch Rebuild (Faster)

Use the rebuild script to build all engines in one go:

```bash
# Rebuild all engines with FP16 precision (recommended)
python3 scripts/rebuild_tensorrt_engines.py

# Rebuild only vehicle detection engine
python3 scripts/rebuild_tensorrt_engines.py --models vehicle

# Rebuild only plate detection engine
python3 scripts/rebuild_tensorrt_engines.py --models plate

# Rebuild with custom workspace size (if you have more GPU memory)
python3 scripts/rebuild_tensorrt_engines.py --workspace 4
```

### Option 3: INT8 Quantization (Experimental)

For maximum performance with INT8 quantization:

```bash
# Rebuild with INT8 (requires calibration data)
python3 scripts/rebuild_tensorrt_engines.py --precision int8 --calibration calibration.yaml
```

⚠️ **Warning**: INT8 mode is currently unstable on Jetson and may cause crashes. Stick with FP16 for production use.

## Rebuild Script Options

### Full Command Reference

```bash
python3 scripts/rebuild_tensorrt_engines.py [OPTIONS]

Options:
  --precision {fp16,int8}   TensorRT precision mode (default: fp16)
  --workspace WORKSPACE     Workspace size in GB (default: 2)
  --batch-size BATCH_SIZE   Batch size for inference (default: 1)
  --calibration CALIBRATION Path to calibration YAML for INT8 mode
  --models {all,vehicle,plate}  Which models to rebuild (default: all)
```

### Examples

#### Rebuild All Models (Default)

```bash
python3 scripts/rebuild_tensorrt_engines.py
```

Output:
```
======================================================================
🚀 TensorRT Engine Batch Rebuild
======================================================================
Precision:   FP16
Workspace:   2 GB
Batch Size:  1

======================================================================
🔨 Building TensorRT Engine: Vehicle Detection Model (YOLO11n)
======================================================================
  Source:      models/yolo11n.pt (5.4 MB)
  Target:      models/yolo11n.engine
  Precision:   FP16
  Workspace:   2 GB
  Batch Size:  1

📥 Loading PyTorch model...
⚙️  Exporting to TensorRT FP16...
...
✅ Export successful!
   Engine:   models/yolo11n.engine
   Size:     8.1 MB
   Time:     215.3s

======================================================================
📊 Build Summary
======================================================================
  vehicle      ✅ SUCCESS
  plate        ✅ SUCCESS

  Total: 2/2 successful
  Time:  431.4s
```

#### Rebuild Only Vehicle Model

```bash
python3 scripts/rebuild_tensorrt_engines.py --models vehicle
```

#### Rebuild with Larger Workspace

```bash
python3 scripts/rebuild_tensorrt_engines.py --workspace 4
```

Use larger workspace (4+ GB) if you have more GPU memory available. This can improve build quality and performance.

## Verification

### Check Engine Files Exist

```bash
ls -lh models/*.engine
```

Expected output:
```
-rw-rw-r-- 1 jetson jetson 8.1M Dec 19 21:18 models/yolo11n.engine
-rw-rw-r-- 1 jetson jetson 7.3M Dec 19 22:50 models/yolo11n-plate.engine
```

Note: The vehicle engine (8.1 MB) is larger than the plate engine (7.3 MB) because it uses a larger 640x640 input size vs 416x416.

### Verify Engines Load Correctly

```bash
python3 pilot.py 2>&1 | grep "Loading existing TensorRT"
```

Expected output:
```
Loading existing TensorRT engine: models/yolo11n.engine
Loading existing TensorRT engine: models/yolo11n-plate.engine
```

If you see "Exporting to TensorRT" instead, the engine is being rebuilt (this takes ~7 minutes).

### Check Engine Loading Time

Pre-built engines should load in **~1 second**:

```
[12/19/2025-22:40:20] [TRT] [I] Loaded engine size: 8 MiB
```

If loading takes >10 seconds, the engine might be rebuilding.

## Performance Comparison

### Build Time

| Model | PyTorch → TensorRT | Pre-built Engine Load |
|-------|-------------------|----------------------|
| Vehicle Detection | ~215 seconds | ~1 second |
| Plate Detection | ~215 seconds | ~1 second |
| **Total** | **~430 seconds** | **~2 seconds** |

### Inference Performance

| Model | FP32 (PyTorch) | FP16 (TensorRT) | Speedup |
|-------|----------------|-----------------|---------|
| Vehicle Detection | 40-60ms | 15-20ms | **2-3x** |
| Plate Detection | 15-25ms | 5-10ms | **2-3x** |

## Troubleshooting

### Engine Files Not Found

**Symptom**: "Exporting to TensorRT..." appears on every run

**Solution**: Check that `.engine` files exist in `models/` directory:
```bash
ls -lh models/*.engine
```

If missing, rebuild them:
```bash
python3 scripts/rebuild_tensorrt_engines.py
```

### Slow Loading

**Symptom**: TensorRT engine takes >10 seconds to load

**Cause**: Engine might be rebuilding or incompatible with current TensorRT version

**Solution**: Delete and rebuild engines:
```bash
rm models/*.engine
python3 scripts/rebuild_tensorrt_engines.py
```

### CUDA Out of Memory

**Symptom**: "CUDA out of memory" error during engine build

**Solution**: Reduce workspace size:
```bash
python3 scripts/rebuild_tensorrt_engines.py --workspace 1
```

Or close other GPU-intensive applications before rebuilding.

### Engine Build Fails

**Symptom**: "Export failed" or TensorRT errors

**Solution**:
1. Check CUDA and TensorRT versions are compatible:
   ```bash
   nvcc --version
   python3 -c "import tensorrt; print(tensorrt.__version__)"
   ```

2. Verify PyTorch model is valid:
   ```bash
   python3 -c "from ultralytics import YOLO; YOLO('models/yolo11n.pt')"
   ```

3. Try rebuilding with smaller workspace:
   ```bash
   python3 scripts/rebuild_tensorrt_engines.py --workspace 1
   ```

## Best Practices

### Production Deployment

1. **Pre-build Engines**: Always build engines before deploying to production
2. **Use FP16**: Stick with FP16 precision for stability (INT8 is experimental)
3. **Version Control**: Keep engine files in `.gitignore` (they're hardware-specific)
4. **Rebuild After Updates**: Rebuild engines after model retraining or system updates

### Development Workflow

1. **Train Model**: Train YOLO model with `yolo detect train`
2. **Copy Weights**: Copy best weights to `models/yolo11n-plate.pt`
3. **Rebuild Engines**: Run rebuild script to create new TensorRT engines
4. **Test**: Verify new engines work with `python3 pilot.py`

### After Retraining Custom Plate Model

```bash
# Copy trained model to models directory
cp runs/detect/train/weights/best.pt models/yolo11n-plate.pt

# Rebuild plate detection engine
python3 scripts/rebuild_tensorrt_engines.py --models plate

# Test with ALPR
python3 pilot.py
```

## Related Documentation

- **TensorRT Export**: `docs/TENSORRT_EXPORT.md` - Detailed export guide
- **Model Quantization**: `docs/MODEL_QUANTIZATION.md` - INT8 quantization guide
- **Performance Comparison**: `docs/PT_VS_ENGINE_COMPARISON.md` - PyTorch vs TensorRT benchmarks
- **INT8 Calibration**: `docs/INT8/INT8_CALIBRATION_SETUP.md` - INT8 calibration setup

## Summary

TensorRT engines are now **pre-built and cached** for instant loading on every run:

✅ **Vehicle model**: `yolo11n.engine` (8.1 MB, 640x640, FP16)
✅ **Plate model**: `yolo11n-plate.engine` (7.3 MB, 416x416, FP16)

The system automatically detects and loads these engines, providing **2-3x faster inference** with minimal accuracy loss.

**Important**: Each model uses its optimal input size:
- Vehicle detection uses 640x640 (standard YOLO11n size)
- Plate detection uses 416x416 (matches training resolution)

**Remember**: Rebuild engines after retraining models or updating TensorRT/CUDA versions.
