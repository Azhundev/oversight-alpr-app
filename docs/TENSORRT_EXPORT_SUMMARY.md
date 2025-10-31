# TensorRT Export Summary

## Custom Plate Detector Model

### Export Details
- **Source Model**: `models/yolo11n-plate-custom.pt` (5.2 MB)
- **Export Format**: TensorRT Engine (.engine)
- **Precision**: FP16 (Half precision)
- **Input Size**: 640x640
- **Platform**: NVIDIA Jetson Orin NX
- **TensorRT Version**: 10.7.0

### Exported Files
1. **ONNX Intermediate**: `models/yolo11n-plate-custom.onnx` (11 MB)
2. **TensorRT Engine**: `models/yolo11n-plate-custom.engine` (8.4 MB)

### Performance Benchmarks

#### Inference Speed Comparison
| Model Type | Avg Inference Time | Format |
|------------|-------------------|---------|
| PyTorch | 26.8 ms | .pt |
| TensorRT | 24.0 ms | .engine |

**Speedup**: 1.12x faster with TensorRT FP16

### Performance Notes
- TensorRT engine is optimized specifically for Jetson Orin NX hardware
- FP16 precision maintains accuracy while improving speed
- Engine includes fused operations and optimized kernels
- Memory footprint: ~9 MB GPU memory during inference

### Usage

#### With Python/Ultralytics
```python
from ultralytics import YOLO

# Load TensorRT engine
model = YOLO("models/yolo11n-plate-custom.engine")

# Run inference
results = model(image)
```

#### With Pilot Script
```bash
# Using TensorRT engine (automatically detected)
python3 pilot.py --plate-model models/yolo11n-plate-custom.engine

# System will automatically use TensorRT for faster inference
```

### Deployment Recommendations
1. ✅ **Use TensorRT engine** for production deployment
2. ✅ Keep PyTorch model (.pt) for retraining or fine-tuning
3. ✅ Engine is platform-specific (Jetson Orin NX)
4. 🔲 For different hardware, re-export the .pt model

### Model Files Summary
```
models/
├── yolo11n-plate-custom.pt       # Original trained model (5.2 MB)
├── yolo11n-plate-custom.onnx     # ONNX intermediate (11 MB)
└── yolo11n-plate-custom.engine   # TensorRT engine (8.4 MB) ← USE THIS
```

## Next Steps
- ✅ TensorRT engine created and benchmarked
- ✅ Performance validated (1.12x speedup)
- 🔲 Optional: Create INT8 quantized engine for even faster inference
- 🔲 Optional: Benchmark on real video streams
