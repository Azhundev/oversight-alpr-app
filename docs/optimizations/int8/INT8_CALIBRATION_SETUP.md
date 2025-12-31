# INT8 Calibration Setup - Completed

This document summarizes the INT8 quantization setup for YOLOv11 using your custom training videos.

## What Was Done

### 1. Calibration Dataset Creation
- **Source**: 5 training videos from `videos/training/`
- **Total frames extracted**: 355 frames
- **Sampling rate**: 1 frame per second (every 30th frame at 30fps)
- **Output location**: `datasets/calibration/images/`

### Video Processing Details
| Video | Duration | Frames Extracted |
|-------|----------|------------------|
| IMG_6929.MOV | 57.4s | 58 frames |
| IMG_6930.MOV | 25.8s | 26 frames |
| IMG_6931.MOV | 80.0s | 81 frames |
| IMG_6941.MOV | 89.5s | 90 frames |
| IMG_6942.MOV | 109.5s | 100 frames |

### 2. Configuration Files
- **Calibration YAML**: `calibration.yaml` (created at project root)
- Points to `datasets/calibration/` for INT8 calibration data

### 3. Code Changes

#### detector_service.py (line 90)
```python
data='calibration.yaml',  # Calibration dataset from training videos
```

#### pilot.py (lines 79-80)
```python
fp16=False,  # Disable FP16 when using INT8
int8=True,   # Enable INT8 quantization for maximum performance
```

## How INT8 Calibration Works

When you run `pilot.py` for the first time with INT8 enabled:

1. **TensorRT will analyze** the 355 calibration frames from your videos
2. **Compute activation ranges** for each layer of the neural network
3. **Generate quantization scales** to convert FP32 → INT8
4. **Build optimized engine** with INT8 precision (~10-15 minutes)
5. **Cache the engine** as `.engine` file for future runs

Subsequent runs will use the cached INT8 engine and be much faster.

## Expected Performance Improvements

| Metric | FP16 (Before) | INT8 (After) | Improvement |
|--------|---------------|--------------|-------------|
| Inference time | ~25ms | ~12-15ms | **2x faster** |
| FPS | ~40 FPS | ~80+ FPS | **2x higher** |
| Memory usage | ~100MB | ~50MB | **50% less** |
| Model size | ~12MB | ~6MB | **50% smaller** |
| Accuracy | 100% | 98-99% | ~1-2% loss |

## Why Use Your Videos for Calibration?

Using your actual parking gate videos provides better calibration because:

1. **Domain-specific data**: Matches your actual deployment conditions
2. **Lighting conditions**: Captures your specific lighting (shadows, reflections, etc.)
3. **Camera angles**: Matches your camera mounting positions
4. **Vehicle types**: Represents the actual vehicles in your area
5. **Better accuracy**: More representative = better INT8 quantization

This is superior to using generic COCO dataset which may not reflect your parking gate scenario.

## Next Steps

### Test INT8 Engine Build
```bash
# First run will build INT8 engine (takes ~10-15 minutes)
python pilot.py

# Look for log messages:
# "Exporting model to TensorRT with INT8 precision..."
# "TensorRT engine created: yolo11n.engine"
```

### Monitor Performance
Watch for:
- **Inference time**: Should drop from ~25ms to ~12-15ms
- **FPS**: Should increase from ~40 to ~80+ FPS
- **Detection quality**: Should remain similar (verify visually)

### Troubleshooting

If calibration fails:
```bash
# Check calibration dataset exists
ls -l datasets/calibration/images/ | wc -l
# Should show 355

# Check YAML file
cat calibration.yaml
# Should point to datasets/calibration

# Check disk space (calibration needs ~500MB temporary space)
df -h
```

If accuracy drops significantly:
- Extract more frames: `--max-frames-per-video 200`
- Use smaller frame interval: `--frame-interval 15`
- Consider using FP16 instead if accuracy is critical

### Re-extract Calibration Frames (if needed)
```bash
# Extract more diverse samples
python scripts/prepare_calibration_dataset.py \
  --video-dir videos/training \
  --max-frames-per-video 200 \
  --frame-interval 15
```

## Files Created

```
OVR-ALPR/
├── calibration.yaml                        # Calibration config
├── datasets/
│   └── calibration/
│       └── images/                         # 355 calibration frames
│           ├── IMG_6929_frame_000000.jpg
│           ├── IMG_6929_frame_000030.jpg
│           └── ...
├── scripts/
│   └── prepare_calibration_dataset.py     # Frame extraction tool
└── docs/
    └── INT8_CALIBRATION_SETUP.md          # This file
```

## References

- [INT8_PRECISION_GUIDE.md](INT8_PRECISION_GUIDE.md) - General INT8 guide
- [TensorRT INT8 Calibration](https://docs.nvidia.com/deeplearning/tensorrt/developer-guide/index.html#working-with-int8)
- [Ultralytics TensorRT Export](https://docs.ultralytics.com/integrations/tensorrt/)

---

**Status**: INT8 quantization is now enabled and ready to use.
**Next**: Run `python pilot.py` to trigger INT8 calibration and engine build.
