# ALPR System - Current Status

**Last Updated:** 2025-10-17

## ✅ READY TO TEST!

Your ALPR system is now ready for video inference testing on Jetson Orin NX.

## What's Working

### 1. Camera Ingestion Service ✅
**File:** `services/camera/camera_ingestion.py`

Features:
- ✅ Video file playback (720p.mp4, a.mp4)
- ✅ RTSP stream support
- ✅ USB camera support
- ✅ Multi-threaded capture (low latency)
- ✅ Hardware decoding for Jetson (GStreamer)
- ✅ Auto-loop for video files
- ✅ FPS calculation and stats
- ✅ Queue-based buffering

**Test it:**
```bash
cd services/camera
python3 camera_ingestion.py
```

### 2. YOLOv11 Detector Service ✅
**File:** `services/detector/detector_service.py`

Features:
- ✅ YOLOv11 vehicle detection (4 classes: car, truck, bus, motorcycle)
- ✅ TensorRT export (automatic on first run)
- ✅ FP16 precision for Jetson
- ✅ License plate detection (contour-based fallback)
- ✅ Custom plate model support
- ✅ Warmup for consistent latency
- ✅ Batch processing support

**Models:**
- Vehicle: `yolo11n.pt` (fastest)
- Plate: Optional custom model or contour detection

### 3. Complete Pilot Script ✅
**File:** `pilot.py`

**Run it NOW:**
```bash
python3 pilot.py
```

Features:
- ✅ End-to-end pipeline (camera → detection → visualization)
- ✅ Real-time FPS display
- ✅ Vehicle bounding boxes (green)
- ✅ Plate bounding boxes (yellow)
- ✅ Processing time metrics
- ✅ Screenshot save (press 's')
- ✅ Headless mode support
- ✅ Output saving

**Command Line Options:**
```bash
python3 pilot.py --help
python3 pilot.py --config config/cameras.yaml
python3 pilot.py --model yolo11n.pt
python3 pilot.py --save-output
python3 pilot.py --no-display  # Headless
python3 pilot.py --no-tensorrt  # Skip TensorRT
```

### 4. Configuration System ✅
**Location:** `config/`

All YAML files complete:
- ✅ `cameras.yaml` - Video sources configured (a.mp4 enabled)
- ✅ `detection.yaml` - YOLOv11 + TensorRT settings
- ✅ `ocr.yaml` - PaddleOCR ready (pending implementation)
- ✅ `tracking.yaml` - ByteTrack config
- ✅ `deduplication.yaml` - Event dedup rules
- ✅ `validation.yaml` - USA/Mexico/Canada plates

### 5. Event Schemas ✅
**File:** `shared/schemas/event.py`

Pydantic models ready:
- ✅ `DetectionEvent` - Main event structure
- ✅ `PlateDetection` - Plate with validation
- ✅ `VehicleDetection` - Vehicle data
- ✅ `BoundingBox` - Type-safe coordinates
- ✅ `KafkaEvent` / `DatabaseEvent` - Transport formats

### 6. Plate Validator ✅
**File:** `shared/utils/plate_validator.py`

- ✅ All 50 US states + DC
- ✅ Mexican states
- ✅ Canadian provinces
- ✅ Normalization (uppercase, remove spaces)
- ✅ OCR error correction (O→0, I→1, l→1, etc.)
- ✅ Regex validation per region

## Quick Test

### Minimal Test (5 minutes)

```bash
# 1. Install dependencies
pip3 install torch torchvision ultralytics opencv-python loguru pyyaml pydantic

# 2. Run pilot
python3 pilot.py

# 3. Watch detections!
# Press 'q' to quit
```

### Full Test (15 minutes)

```bash
# 1. Check CUDA
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# 2. Run pilot with all features
python3 pilot.py --save-output

# 3. Check output
ls output/
```

## Expected Output

### Console:
```
INFO     | Starting ALPR pilot...
INFO     | Initializing camera manager...
INFO     | Loaded video source: TEST-002 - Test Video Short
SUCCESS  | Loaded 1 camera sources
INFO     | Initializing YOLOv11 detector...
INFO     | Loading vehicle detection model: yolo11n.pt
INFO     | Exporting model to TensorRT...
SUCCESS  | TensorRT engine created: yolo11n.engine
INFO     | Warming up detector (10 iterations)...
SUCCESS  | Detector warmup complete
SUCCESS  | ALPR Pilot initialized successfully
INFO     | Starting ALPR pilot...
INFO     | Camera TEST-002 capture thread started
INFO     | Processed 100 frames | 23 vehicles detected | Avg FPS: 28.7
```

### Window Display:
```
┌─────────────────────────────────────────┐
│ Camera: TEST-002                        │
│ FPS: 28.7 | Processing: 34.8ms          │
│ Detections: 1 vehicles | Total: 124     │
│ Total Vehicles: 23 | Uptime: 4s         │
├─────────────────────────────────────────┤
│                                         │
│  ╔═══════════════════════╗              │
│  ║ car 0.94              ║              │
│  ║   ┌─────────┐         ║              │
│  ║   │ PLATE   │         ║              │
│  ║   └─────────┘         ║              │
│  ╚═══════════════════════╝              │
│                                         │
└─────────────────────────────────────────┘
```

## Performance Targets (Jetson Orin NX)

| Configuration | FPS | Latency | Notes |
|---------------|-----|---------|-------|
| YOLOv11n @ 1080p | 25-30 | ~35ms | ✅ Recommended |
| YOLOv11n @ 720p | 35-45 | ~25ms | ✅ Best performance |
| YOLOv11s @ 1080p | 18-22 | ~50ms | Good accuracy |
| YOLOv11m @ 1080p | 12-15 | ~75ms | High accuracy |

*All with TensorRT FP16*

## What's Next (Not Needed for Testing)

### To Add Later:
- ⏳ PaddleOCR service (plate text recognition)
- ⏳ ByteTrack service (vehicle tracking + track_id)
- ⏳ Event processor (deduplication)
- ⏳ Database persistence
- ⏳ Kafka messaging
- ⏳ REST API
- ⏳ Dashboard

### Current Limitations:
- ❌ No OCR (plates detected but text not read)
- ❌ No tracking (no persistent track_id)
- ❌ No deduplication
- ❌ No database storage
- ❌ Single camera only (multi-cam needs threading)

### But You CAN:
- ✅ Detect vehicles in real-time
- ✅ Detect license plate regions
- ✅ Test on video files
- ✅ Test on RTSP streams
- ✅ Measure FPS and latency
- ✅ Save annotated frames
- ✅ Validate Jetson performance

## Files Created

```
OVR-ALPR/
├── pilot.py                          ✅ Main test script
├── QUICKSTART.md                     ✅ Usage guide
├── STATUS.md                         ✅ This file
├── README.md                         ✅ Project overview
│
├── config/                           ✅ All configs
│   ├── cameras.yaml
│   ├── detection.yaml
│   ├── ocr.yaml
│   ├── tracking.yaml
│   ├── deduplication.yaml
│   └── validation.yaml
│
├── shared/                           ✅ Shared code
│   ├── schemas/event.py
│   └── utils/plate_validator.py
│
├── services/                         ✅ Microservices
│   ├── camera/
│   │   └── camera_ingestion.py      ✅ READY
│   └── detector/
│       └── detector_service.py      ✅ READY
│
├── docs/
│   └── SETUP_PROGRESS.md             ✅ Progress tracker
│
└── requirements.txt                  ✅ Dependencies
```

## Troubleshooting

### CUDA Not Found
```bash
python3 -c "import torch; print(torch.cuda.is_available())"
# Should print: True

# If False:
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Module Not Found
```bash
# Add to PYTHONPATH
export PYTHONPATH=/home/jetson/OVR-ALPR:$PYTHONPATH

# Or run from project root
cd /home/jetson/OVR-ALPR
python3 pilot.py
```

### Video Not Found
```bash
# Check files exist
ls -la 720p.mp4 a.mp4

# Edit config to point to correct path
nano config/cameras.yaml
```

### Low FPS
1. Use YOLOv11n (fastest): `--model yolo11n.pt`
2. Check TensorRT is enabled (look for "TensorRT engine created" in logs)
3. Reduce resolution in config
4. Monitor GPU: `sudo tegrastats`

## Ready to Test! 🚀

**Run this now:**
```bash
python3 pilot.py
```

You should see:
1. YOLOv11 load and export to TensorRT (~30 seconds first time)
2. Video playback from a.mp4
3. Green boxes around detected vehicles
4. Yellow boxes around detected plates
5. Real-time FPS counter
6. Processing time stats

**Success criteria:**
- ✅ FPS > 20 on Jetson Orin NX
- ✅ Vehicles detected with green boxes
- ✅ Plates detected with yellow boxes
- ✅ No errors or crashes

---

**Questions or issues?** Check QUICKSTART.md for detailed instructions.
