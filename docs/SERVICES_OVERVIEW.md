# OVR-ALPR Services Overview

Complete guide to all services in the ALPR pipeline.

---

## Architecture Overview

The OVR-ALPR system is built with a modular service architecture, where each service handles a specific part of the ALPR pipeline:

```
┌─────────────────────────────────────────────────────────────────────┐
│                           ALPR PIPELINE                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Camera Ingestion  →  2. Detection  →  3. Tracking              │
│          ↓                                      ↓                   │
│  4. OCR Processing   →  5. Event Processing  →  6. Publishing       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Service Catalog

### 1. Camera Ingestion Service

**Location**: `services/camera/camera_ingestion.py`

**Purpose**: Capture and buffer video frames from multiple sources (RTSP streams, video files, USB cameras)

**Key Features**:
- Multi-threaded frame capture (one thread per camera)
- Hardware-accelerated decoding for RTSP streams (GStreamer + nvv4l2decoder)
- Frame buffering with queue management
- Automatic video looping for test files
- Frame drop detection and statistics

**Configuration**: `config/cameras.yaml`

**Main Classes**:
- `CameraSource`: Single camera/video source handler
  - Manages VideoCapture instance
  - Background capture thread
  - Frame queue (non-blocking)
  - FPS calculation and stats

- `CameraManager`: Manages multiple camera sources
  - Loads camera config from YAML
  - Start/stop all cameras
  - Get frames from specific cameras

**Usage Example**:
```python
from services.camera.camera_ingestion import CameraManager

manager = CameraManager("config/cameras.yaml")
manager.start_all()

# Read frames
for camera_id, camera in manager.get_all_cameras().items():
    ret, frame = camera.read()
    if ret:
        # Process frame...
```

**Performance Notes**:
- Uses `buffer_size=2` (minimum) for smooth playback
- `get_latest=True` flushes old frames to prevent lag
- Target FPS control for video files (prevents buffering)
- Hardware decoding for RTSP reduces CPU usage by 60-80%

---

### 2. GPU Camera Ingestion Service (Alternative)

**Location**: `services/camera/gpu_camera_ingestion.py`

**Purpose**: GPU-accelerated video capture using CUDA/NVDEC

**Key Features**:
- NVDEC hardware video decoder (H.264/H.265)
- Direct GPU frame output (GpuMat)
- GPU-based resizing (cuda::resize)
- Multi-stream support with threading

**Main Classes**:
- `GPUVideoCapture`: Single-stream GPU capture
  - Uses cv2.cudacodec.createVideoReader
  - Fallback to CPU if GPU decode fails
  - Background capture thread with queue

- `MultiStreamCapture`: Multi-stream GPU capture
  - Manages multiple GPUVideoCapture instances
  - Batch frame reading

**Usage Example**:
```python
from services.camera.gpu_camera_ingestion import create_optimized_capture

cap = create_optimized_capture(
    source="rtsp://camera/stream",
    target_size=(960, 540),
    prefer_gpu=True
)

ret, frame = cap.read()  # Returns numpy array (CPU)
```

**Performance Notes**:
- 2-3x faster than CPU decode for RTSP
- Reduces CPU load significantly
- Best for multiple RTSP streams

---

### 3. Detector Service (YOLOv11)

**Location**: `services/detector/detector_service.py`

**Purpose**: Detect vehicles and license plates using YOLOv11

**Key Features**:
- TensorRT optimization for Jetson (2-4x speedup)
- FP16 precision support (stable, 2-3x faster)
- Separate models for vehicles and plates
- Fallback contour-based plate detection
- Model warmup for consistent inference times

**Configuration**:
- Vehicle model: `models/yolo11n.pt` (COCO pretrained)
- Plate model: `models/yolo11n-plate.pt` (custom trained)

**Main Class**: `YOLOv11Detector`

**Methods**:
- `detect_vehicles(frame, confidence_threshold=0.4, nms_threshold=0.5)`
  - Returns: `List[VehicleDetection]`
  - Detects: car, truck, bus, motorcycle

- `detect_plates(frame, vehicle_bboxes, confidence_threshold=0.6, nms_threshold=0.4)`
  - Returns: `Dict[vehicle_idx, List[BoundingBox]]`
  - Matches plates to vehicles by spatial overlap

- `warmup(iterations=10)`
  - Runs dummy inference to initialize TensorRT engine

**Usage Example**:
```python
from services.detector.detector_service import YOLOv11Detector

detector = YOLOv11Detector(
    vehicle_model_path="models/yolo11n.pt",
    plate_model_path="models/yolo11n-plate.pt",
    use_tensorrt=True,
    fp16=True
)

detector.warmup(iterations=10)

# Detect vehicles
vehicles = detector.detect_vehicles(frame, confidence_threshold=0.25)

# Detect plates within vehicles
vehicle_bboxes = [v.bbox for v in vehicles]
plates = detector.detect_plates(frame, vehicle_bboxes, confidence_threshold=0.20)
```

**Performance Notes**:
- FP16 TensorRT: 15-20ms per frame (vehicle + plate)
- PyTorch (.pt): 50-80ms per frame
- INT8 has stability issues on Jetson (use FP16)

---

### 4. Tracker Service (ByteTrack)

**Location**: `services/tracker/bytetrack_service.py`

**Purpose**: Multi-object tracking with identity persistence across frames

**Key Features**:
- Associates high and low confidence detections
- Kalman filter for motion prediction
- Track buffering for temporary occlusions
- Automatic track merging (prevents fragmentation)
- Configurable via YAML

**Configuration**: `config/tracking.yaml`

**Main Classes**:
- `Track`: Single object track
  - Kalman filter state estimation
  - Track ID, state (NEW, TRACKED, LOST, REMOVED)
  - Frame count, confidence

- `ByteTrackService`: Multi-object tracker
  - Three-stage association (high conf → low conf → lost tracks)
  - Linear assignment problem solver (LAP)
  - IoU-based matching

**Usage Example**:
```python
from services.tracker.bytetrack_service import ByteTrackService, Detection

tracker = ByteTrackService(config_path="config/tracking.yaml")

# Convert detections
detections = [
    Detection(bbox=bbox_to_numpy(v.bbox), confidence=v.confidence, class_id=0)
    for v in vehicles
]

# Update tracker
active_tracks = tracker.update(detections)

# Get track IDs
for track in active_tracks:
    print(f"Track {track.track_id}: bbox={track.tlbr}")
```

**Tracking Parameters**:
- `track_thresh`: 0.5 (high confidence threshold)
- `track_buffer`: 30 frames (keep lost tracks)
- `match_thresh`: 0.8 (IoU matching threshold)
- `min_box_area`: 100 px² (minimum bbox size)

**Performance Notes**:
- <1ms per frame overhead
- Handles 10+ simultaneous tracks
- Kalman prediction allows tracking through occlusions

---

### 5. OCR Service (PaddleOCR)

**Location**: `services/ocr/ocr_service.py`

**Purpose**: License plate text recognition from plate crops

**Key Features**:
- Multi-strategy OCR (raw, preprocessed, upscaled)
- Florida plate orange logo removal
- Adaptive preprocessing (denoise, CLAHE, sharpen)
- Confidence-based filtering
- Batch processing support

**Configuration**: `config/ocr.yaml`

**Main Class**: `PaddleOCRService`

**Methods**:
- `recognize_plate(frame, bbox, preprocess=True)`
  - Returns: `PlateDetection` (text, confidence, bbox)
  - Tries multiple preprocessing strategies, returns best

- `recognize_plates_batch(frame, bboxes, preprocess=True)`
  - Returns: `List[PlateDetection]`
  - Batch inference for multiple plates

- `normalize_plate_text(text)`
  - Returns: Uppercase, alphanumeric only
  - Removes spaces, dashes, special chars

**Preprocessing Pipeline**:
1. Orange logo removal (Florida plates)
2. Grayscale conversion
3. Resize (if too small)
4. Denoise (fastNlMeansDenoising)
5. Contrast enhancement (CLAHE)
6. Sharpening (optional, for motion blur)

**Usage Example**:
```python
from services.ocr.ocr_service import PaddleOCRService

ocr = PaddleOCRService(
    config_path="config/ocr.yaml",
    use_gpu=True
)

ocr.warmup(iterations=5)

# Single plate
plate_detection = ocr.recognize_plate(frame, plate_bbox)
if plate_detection:
    print(f"Plate: {plate_detection.text} (conf: {plate_detection.confidence:.2f})")

# Batch
plate_detections = ocr.recognize_plates_batch(frame, plate_bboxes)
```

**Performance Notes**:
- 50-150ms per plate (single)
- Multi-strategy adds latency but improves accuracy
- GPU acceleration provides 2-3x speedup

---

### 6. Event Processor Service

**Location**: `services/event_processor/event_processor_service.py`

**Purpose**: Normalize, validate, and deduplicate plate detections before publishing

**Key Features**:
- Plate text normalization (uppercase, remove special chars)
- Format validation (US state patterns)
- Fuzzy deduplication (Levenshtein similarity)
- Time-window deduplication (5 minutes)
- Metadata enrichment (site, host, timestamps)

**Main Class**: `EventProcessorService`

**Methods**:
- `process_detection(...)`
  - Returns: `PlateEvent` if valid, `None` if rejected
  - Pipeline: confidence check → normalize → validate → deduplicate → enrich

- `normalize_plate_text(raw_text)`
  - Returns: Cleaned plate text

- `validate_plate_format(normalized_text, region)`
  - Returns: (is_valid, error_message)

- `is_duplicate(normalized_text, track_id, timestamp)`
  - Returns: (is_duplicate, duplicate_event_id)

**Usage Example**:
```python
from services.event_processor.event_processor_service import EventProcessorService

processor = EventProcessorService(
    site_id="DC1",
    host_id="jetson-orin-nx",
    min_confidence=0.70,
    dedup_similarity_threshold=0.85,
    dedup_time_window_seconds=300
)

event = processor.process_detection(
    plate_text="ABC1234",
    plate_confidence=0.85,
    camera_id="CAM-001",
    track_id=42,
    vehicle_type="car",
    region="US-FL"
)

if event:
    print(f"Event ID: {event.event_id}")
    print(f"Plate: {event.plate['normalized_text']}")
```

**Validation Rules**:
- Min confidence: 0.70
- Min text length: 3 characters
- Max text length: 10 characters
- Must match regional format (alphanumeric, at least 1 letter + 1 number)

**Deduplication**:
- 85% similarity threshold (catches OCR errors like ABC123 vs ABC1Z3)
- 5-minute time window
- Automatic cache cleanup

---

### 7. Kafka Publisher Service

**Location**: `services/event_processor/kafka_publisher.py`

**Purpose**: Publish validated plate events to Kafka message queue

**Key Features**:
- Async publishing with acknowledgments
- GZIP compression
- Idempotent producer (exactly-once semantics)
- Partition key (camera_id) for ordering
- Mock publisher for testing

**Main Classes**:
- `KafkaPublisher`: Production Kafka publisher
  - Connects to Kafka broker
  - JSON serialization
  - Error handling and retries

- `MockKafkaPublisher`: Testing mock
  - Logs events to console
  - No Kafka dependency

**Configuration**:
- Bootstrap servers: `localhost:9092`
- Topic: `alpr.plates.detected`
- Compression: gzip
- Acks: all (strongest guarantee)

**Usage Example**:
```python
from services.event_processor.kafka_publisher import KafkaPublisher

publisher = KafkaPublisher(
    bootstrap_servers="localhost:9092",
    topic="alpr.plates.detected",
    compression_type="gzip",
    acks="all"
)

# Publish event
success = publisher.publish_event(event.to_dict())

# Cleanup
publisher.flush()
publisher.close()
```

**Event Schema** (PlateEvent):
```json
{
  "event_id": "uuid-v4",
  "captured_at": "2025-01-15T12:34:56.789Z",
  "camera_id": "CAM-001",
  "track_id": "t-42",
  "plate": {
    "text": "ABC1234",
    "normalized_text": "ABC1234",
    "confidence": 0.850,
    "region": "US-FL"
  },
  "vehicle": {
    "type": "car",
    "make": null,
    "model": null,
    "color": null
  },
  "images": {
    "plate_url": "output/crops/2025-01-15/CAM-001_track42_frame123_q0.85.jpg",
    "vehicle_url": "",
    "frame_url": ""
  },
  "latency_ms": 0,
  "node": {
    "site": "DC1",
    "host": "jetson-orin-nx"
  },
  "extras": {
    "roi": null,
    "direction": null,
    "quality_score": 0.850,
    "frame_number": 123
  }
}
```

---

## Service Integration (pilot.py)

**Location**: `pilot.py`

**Purpose**: Main application that integrates all services into a complete ALPR pipeline

**Pipeline Flow**:
```
1. CameraManager.read()        → Get frame from camera
2. YOLOv11.detect_vehicles()   → Detect vehicles
3. ByteTrack.update()          → Track vehicles
4. YOLOv11.detect_plates()     → Detect plates within vehicles
5. PaddleOCR.recognize_plate() → Read plate text (per-track throttling)
6. EventProcessor.process()    → Validate & deduplicate
7. KafkaPublisher.publish()    → Publish to Kafka
8. Visualization                → Display results
```

**Key Features**:
- Per-track OCR throttling (prevents redundant OCR)
- Best-shot selection (quality-based plate crop saving)
- Spatial deduplication (merges fragmented tracks)
- Adaptive frame sampling (skip frames when no vehicles)
- Frame quality filtering (skip blurry frames)
- CSV logging + Kafka publishing

**Usage**:
```bash
# Full pipeline with all features
python pilot.py

# Headless mode (no display)
python pilot.py --no-display

# Disable OCR (detection only)
python pilot.py --no-ocr

# Frame skipping (every 3rd frame)
python pilot.py --skip-frames 2

# Custom models
python pilot.py --model models/yolo11n.pt --plate-model models/yolo11n-plate.pt
```

---

## Service Dependencies

### Camera Ingestion
- OpenCV (cv2)
- NumPy
- PyYAML

### Detector
- Ultralytics YOLO
- PyTorch
- TensorRT (optional, recommended)

### Tracker
- FilterPy (Kalman filter)
- LAP (linear assignment)
- Cython-bbox (fast IoU)

### OCR
- PaddleOCR
- PaddlePaddle
- OpenCV

### Event Processor
- Python stdlib (re, uuid, datetime)

### Kafka Publisher
- kafka-python

---

## Performance Summary

| Service | CPU Time | GPU Time | Bottleneck |
|---------|----------|----------|------------|
| Camera Ingestion | <5ms | - | I/O |
| Vehicle Detection | 5-10ms | 10-15ms | GPU inference |
| Plate Detection | 5-8ms | 5-10ms | GPU inference |
| Tracking | <1ms | - | LAP solver |
| OCR | 20-50ms | 50-150ms | PaddleOCR |
| Event Processing | <1ms | - | Levenshtein |
| Kafka Publishing | 5-10ms | - | Network |

**Total Pipeline**: 40-90ms per frame (with OCR), 20-40ms (detection only)

**Throughput**: 15-25 FPS (full pipeline), 25-50 FPS (detection only)

---

## Configuration Files

- `config/cameras.yaml`: Camera sources and settings
- `config/tracking.yaml`: ByteTrack parameters
- `config/ocr.yaml`: PaddleOCR preprocessing settings
- `pilot.py`: Main application configuration

---

## Next Steps

1. **Review service documentation** for implementation details
2. **Check configuration files** in `config/` directory
3. **Read performance guides** in `docs/` for optimization tips
4. **Explore examples** in `services/*/example_usage.py`

For more information, see:
- [Event Processor Service Details](event-processor-service.md)
- [Kafka Setup Guide](kafka-setup.md)
- [Performance Optimization Guide](PERFORMANCE_OPTIMIZATION_GUIDE.md)
