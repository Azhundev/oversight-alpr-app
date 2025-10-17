# ALPR System - Quick Start Guide

## Test the Pilot (Video Inference)

The pilot script is ready to test YOLOv11 detection on your video files!

### 1. Install Dependencies (Jetson-Specific!)

**⚠️ IMPORTANT: Jetson uses ARM64 architecture!**

Do NOT use standard pip PyTorch - use NVIDIA's Jetson wheels instead.

#### Quick Install (Automated):
```bash
# Run the installation script (recommended)
./install_jetson.sh
```

#### Manual Install:
```bash
# 1. Download NVIDIA PyTorch wheel for Jetson
# Check your JetPack version first
sudo apt-cache show nvidia-jetpack | grep Version

# For JetPack 5.1.x:
wget https://developer.download.nvidia.com/compute/redist/jp/v512/pytorch/torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl

# Install PyTorch
pip3 install torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl

# 2. Build TorchVision from source (required for ARM64)
git clone --branch v0.16.0 https://github.com/pytorch/vision torchvision
cd torchvision
export BUILD_VERSION=0.16.0
export TORCH_CUDA_ARCH_LIST="8.7"
python3 setup.py install --user
cd ..

# 3. Install Ultralytics WITHOUT dependencies (prevents x86_64 PyTorch install)
pip3 install numpy pillow pyyaml opencv-python loguru pydantic
pip3 install ultralytics --no-deps

# 4. Verify
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

**See `docs/JETSON_SETUP.md` for detailed instructions!**

### 2. Run the Pilot

The pilot script tests the complete pipeline: Camera Ingestion → YOLOv11 Detection → Visualization

```bash
# Basic usage (processes a.mp4 from config)
python3 pilot.py

# With all options
python3 pilot.py \
    --config config/cameras.yaml \
    --model yolo11n.pt \
    --save-output

# Headless mode (no display, for remote testing)
python3 pilot.py --no-display --save-output
```

### 3. What It Does

**Camera Ingestion:**
- ✅ Reads from video file (a.mp4)
- ✅ Multi-threaded capture (low latency)
- ✅ Supports RTSP streams
- ✅ Hardware decoding on Jetson (GStreamer)

**Detection:**
- ✅ YOLOv11 vehicle detection (car, truck, bus, motorcycle)
- ✅ License plate detection (contour-based fallback)
- ✅ TensorRT optimization (FP16)
- ✅ Real-time FPS display

**Visualization:**
- ✅ Green boxes = vehicles
- ✅ Yellow boxes = license plates
- ✅ FPS counter
- ✅ Processing time
- ✅ Frame counter

### 4. Keyboard Controls

While pilot is running:
- **`q`** - Quit
- **`s`** - Save screenshot to `output/`

### 5. Expected Performance (Jetson Orin NX)

| Model | Resolution | FPS | Latency |
|-------|-----------|-----|---------|
| YOLOv11n | 1920x1080 | 25-30 | ~35ms |
| YOLOv11n | 1280x720 | 35-45 | ~25ms |
| YOLOv11s | 1920x1080 | 18-22 | ~50ms |
| YOLOv11m | 1920x1080 | 12-15 | ~75ms |

*With TensorRT FP16 optimization*

### 6. Configuration

Edit `config/cameras.yaml` to change video source:

```yaml
video_sources:
  - id: TEST-001
    name: "Test Video 720p"
    file_path: "720p.mp4"  # Change to your video file
    loop: true
    enabled: false  # Set to true to use this

  - id: TEST-002
    name: "Test Video Short"
    file_path: "a.mp4"
    loop: true
    enabled: true  # Currently active
```

### 7. Test RTSP Stream

To test with real camera (RTSP):

```yaml
cameras:
  - id: CAM-001
    name: "Main Gate"
    location: "Main Entrance"
    rtsp_url: "rtsp://admin:password@192.168.1.100:554/stream"
    enabled: true  # Enable this
```

Then run:
```bash
python3 pilot.py
```

### 8. TensorRT Export (Faster Inference)

On first run, YOLOv11 will export to TensorRT engine:

```bash
# This happens automatically
Loading vehicle detection model: yolo11n.pt
Exporting model to TensorRT...
TensorRT engine created: yolo11n.engine
```

The `.engine` file is saved and reused on subsequent runs for faster startup.

### 9. Troubleshooting

**CUDA Not Available:**
```bash
# Check CUDA
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# If False, reinstall PyTorch with CUDA support
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

**Video File Not Found:**
```bash
# Use absolute path or check file exists
ls -la 720p.mp4 a.mp4
```

**Low FPS:**
- Use smaller model: `--model yolo11n.pt` (default)
- Reduce resolution in camera config
- Ensure TensorRT is enabled (check logs)

**Import Errors:**
```bash
# Add project root to PYTHONPATH
export PYTHONPATH=/home/jetson/OVR-ALPR:$PYTHONPATH
python3 pilot.py
```

### 10. Output

**Console:**
```
INFO  | Starting ALPR pilot...
INFO  | Press 'q' to quit, 's' to save screenshot
INFO  | Loading vehicle detection model: yolo11n.pt
INFO  | TensorRT engine created: yolo11n.engine
INFO  | Warming up detector (10 iterations)...
SUCCESS | ALPR Pilot initialized successfully
INFO  | Camera TEST-002 capture thread started
INFO  | Processed 100 frames | 47 vehicles detected | Avg FPS: 28.3
```

**Visualization Window:**
```
┌─────────────────────────────────────────┐
│ Camera: TEST-002                        │
│ FPS: 28.3 | Processing: 35.2ms          │
│ Detections: 2 vehicles | Frames: 156    │
│ Total Vehicles: 73 | Uptime: 5s         │
├─────────────────────────────────────────┤
│                                         │
│     [Green Box] car 0.92                │
│        [Yellow Box] PLATE               │
│                                         │
│     [Green Box] truck 0.87              │
│                                         │
└─────────────────────────────────────────┘
```

### 11. Next Steps

Once vehicle detection works:
1. ✅ Add PaddleOCR for plate text recognition
2. ✅ Add ByteTrack for vehicle tracking
3. ✅ Add deduplication logic
4. ✅ Add database persistence
5. ✅ Deploy to production

## Advanced Usage

### Custom Model

Train custom YOLOv11 plate detector:
```bash
# Train on your dataset
yolo detect train data=plates.yaml model=yolo11n.pt epochs=100

# Use in pilot
python3 pilot.py --model runs/detect/train/weights/best.pt
```

### Batch Processing

Process entire video folder:
```bash
for video in videos/*.mp4; do
    python3 pilot.py --no-display --save-output
done
```

### Performance Monitoring

```bash
# Watch GPU usage
sudo tegrastats

# Watch system resources
htop
```

## Support

For issues:
1. Check logs in console output
2. Verify CUDA availability
3. Check file paths
4. Review configuration YAML files

---

**Ready to test!** Run `python3 pilot.py` and watch vehicles get detected in real-time! 🚗
