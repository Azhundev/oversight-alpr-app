# OVR-ALPR Services Overview

Complete guide to all services in the ALPR pipeline.

---

## Architecture Overview

The OVR-ALPR system is built with a modular service architecture, where each service handles a specific part of the ALPR pipeline:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE ALPR PIPELINE                             │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  EDGE PROCESSING (pilot.py)                                               │
│  ┌──────────────────────────────────────────────────────────────┐         │
│  │ 1. Camera → 2. Detection → 3. Tracking → 4. OCR → 5. Event  │         │
│  │  Ingestion     (YOLO)      (ByteTrack)   (Paddle)  Processing│         │
│  └──────────────────────────────────────────────────────────────┘         │
│                                    ↓                                       │
│  MESSAGING LAYER                                                           │
│  ┌──────────────────────────────────────────────────────────────┐         │
│  │ 6. Kafka Publisher → Kafka Broker → 7. Kafka Consumer        │         │
│  └──────────────────────────────────────────────────────────────┘         │
│                                    ↓                                       │
│  STORAGE LAYER                                                             │
│  ┌──────────────────────────────────────────────────────────────┐         │
│  │ 8. Storage Service → TimescaleDB (PostgreSQL + Timeseries)   │         │
│  └──────────────────────────────────────────────────────────────┘         │
│                                    ↓                                       │
│  API LAYER                                                                 │
│  ┌──────────────────────────────────────────────────────────────┐         │
│  │ 9. Query API (FastAPI) → REST Endpoints → Client Apps        │         │
│  └──────────────────────────────────────────────────────────────┘         │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## System Summary

**Total Services**: 13 core services + 6 infrastructure services + 5 monitoring services

**Edge Processing** (pilot.py):
1. Camera Ingestion Service
2. GPU Camera Ingestion Service (alternative)
3. Detector Service (YOLOv11)
4. Tracker Service (ByteTrack)
5. OCR Service (PaddleOCR)
6. Event Processor Service
7. Avro Kafka Publisher Service (with Schema Registry)

**Backend Services** (Docker):
8. Storage Service (Database abstraction)
9. Avro Kafka Consumer Service (Event persistence)
10. Query API Service (REST API)
11. Image Storage Service (MinIO uploads)
12. Alert Engine Service (Real-time notifications)
13. Consumer Entrypoint Service (JSON/Avro router)

**Infrastructure** (Docker):
- Apache Kafka (message broker)
- Confluent Schema Registry (Avro schema management)
- ZooKeeper (Kafka coordination)
- Kafka UI (web monitoring)
- TimescaleDB (time-series database)
- MinIO (S3-compatible object storage)

**Monitoring Stack** (Docker):
- Prometheus (metrics collection and storage)
- Grafana (metrics visualization and dashboards)
- Loki (log aggregation)
- Promtail (log shipping)
- cAdvisor (container resource metrics)

**Key Features**:
- Real-time plate detection and recognition
- Multi-object tracking with ID persistence
- Event validation and deduplication
- Asynchronous event streaming via Kafka
- Time-series optimized storage
- RESTful query API with pagination
- Comprehensive monitoring and logging

**Technology Stack**:
- **Edge**: Python 3.8+, PyTorch, TensorRT, PaddleOCR, OpenCV
- **Messaging**: Apache Kafka 7.5.0, Confluent Schema Registry 7.5.0, Avro
- **Storage**: TimescaleDB (PostgreSQL 16 + TimescaleDB), MinIO (S3-compatible)
- **API**: FastAPI, Uvicorn, Pydantic
- **Deployment**: Docker Compose
- **Hardware**: NVIDIA Jetson (Orin NX/AGX) with CUDA support

---

## Service Catalog

### 1. Camera Ingestion Service

**Location**: `services/camera/camera_ingestion.py`

**Purpose**: Capture and buffer video frames from multiple sources (RTSP streams, video files, USB cameras)

**Key Features**:
- Multi-threaded frame capture (one thread per camera)
- **GPU hardware-accelerated decoding (NVDEC) for RTSP streams via GStreamer** ✅
- Software decoding for video files (CPU, for looping/seeking compatibility)
- Frame buffering with queue management
- Automatic video looping for test files
- Codec auto-detection (H.264/H.265)
- Frame drop detection and statistics

**Performance (GPU Hardware Decode)**:
- **RTSP streams:** 80-90% CPU reduction, 4-6 streams per Jetson Orin NX
- **Video files:** CPU decode for compatibility, 1-2 streams per Jetson Orin NX

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
- **GPU hardware decoding for RTSP reduces CPU usage by 80-90%**
- **RTSP capacity:** 4-6 concurrent streams per Jetson Orin NX (3x increase)
- **Implementation:** OpenCV 4.6.0 with GStreamer 1.20.3 support
- **See:** `docs/Optimizations/gpu-decode-implementation-complete.md`

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

### 8. Storage Service

**Location**: `services/storage/storage_service.py`

**Purpose**: Database abstraction layer for persisting plate events to TimescaleDB (PostgreSQL with time-series extensions)

**Key Features**:
- Connection pooling for thread-safe concurrent access
- Prepared SQL statements with parameter binding
- Automatic retry logic and error handling
- Duplicate event prevention (ON CONFLICT handling)
- Batch insert support
- Query methods for retrieval (by ID, plate, camera, time range)
- Statistics aggregation

**Main Class**: `StorageService`

**Methods**:
- `insert_event(event_dict)` → Insert single plate event
  - Returns: `True` if successful, `False` otherwise
  - Uses `ON CONFLICT (event_id, captured_at) DO NOTHING` for idempotency

- `insert_batch(events)` → Insert multiple events
  - Returns: Number of successfully inserted events

- `get_event_by_id(event_id)` → Retrieve single event
  - Returns: Event dictionary or `None`

- `get_events_by_plate(plate_text, limit, offset)` → Query by plate
  - Returns: List of events for given plate text (normalized)
  - Ordered by `captured_at DESC`

- `get_events_by_camera(camera_id, start_time, end_time, limit, offset)` → Query by camera
  - Returns: List of events from specific camera
  - Optional time range filtering

- `get_recent_events(limit)` → Get most recent events
  - Returns: List of recent events ordered by insertion time (`created_at DESC`)
  - **Fixed**: Now orders by `created_at` instead of `captured_at` for accurate recency

- `get_stats()` → Database statistics
  - Returns: Total events, unique plates, cameras, confidence averages, etc.

**Database Schema** (TimescaleDB):
```sql
CREATE TABLE plate_events (
    -- Primary identifiers
    event_id UUID NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,

    -- Source info
    camera_id VARCHAR(50),
    track_id VARCHAR(50),

    -- Plate data
    plate_text VARCHAR(20),
    plate_normalized_text VARCHAR(20),
    plate_confidence FLOAT,
    plate_region VARCHAR(10),

    -- Vehicle data
    vehicle_type VARCHAR(20),
    vehicle_make VARCHAR(50),
    vehicle_model VARCHAR(50),
    vehicle_color VARCHAR(30),

    -- Image URLs
    plate_image_url TEXT,
    vehicle_image_url TEXT,
    frame_image_url TEXT,

    -- Metadata
    latency_ms INTEGER,
    quality_score FLOAT,
    frame_number INTEGER,
    site_id VARCHAR(50),
    host_id VARCHAR(100),
    roi VARCHAR(50),
    direction VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (event_id, captured_at)
);

-- Hypertable for time-series optimization
SELECT create_hypertable('plate_events', 'captured_at');

-- Performance indexes
CREATE INDEX idx_plate_normalized ON plate_events (plate_normalized_text, captured_at DESC);
CREATE INDEX idx_camera_time ON plate_events (camera_id, captured_at DESC);
CREATE INDEX idx_created_at ON plate_events (created_at DESC);
```

**Usage Example**:
```python
from services.storage.storage_service import StorageService

storage = StorageService(
    host="localhost",
    port=5432,
    database="alpr_db",
    user="alpr",
    password="alpr_secure_pass"
)

# Insert event
success = storage.insert_event(event.to_dict())

# Query recent events
recent = storage.get_recent_events(limit=10)

# Query by plate
events = storage.get_events_by_plate("ABC1234", limit=100)

# Get stats
stats = storage.get_stats()
print(f"Total events: {stats['total_events']}")

# Cleanup
storage.close()
```

**Performance Notes**:
- Connection pooling: 1-10 concurrent connections
- TimescaleDB hypertable: Optimized for time-series queries
- Automatic data retention policies (optional)
- Insert latency: 1-5ms per event
- Query latency: 5-50ms depending on filters

---

### 9. Kafka Consumer Service

**Location**: `services/storage/kafka_consumer.py`

**Purpose**: Background service that consumes plate detection events from Kafka and persists them to TimescaleDB

**Key Features**:
- Continuous message consumption from Kafka topic
- Automatic offset management and commit
- JSON deserialization of event payloads
- Graceful shutdown handling (SIGINT/SIGTERM)
- Error handling with retry logic
- Consumer statistics and monitoring
- Configurable batch processing

**Main Class**: `KafkaStorageConsumer`

**Configuration**:
- Kafka Topic: `alpr.plates.detected`
- Consumer Group: `alpr-storage-consumer`
- Auto Offset Reset: `latest` (only new messages)
- Max Poll Records: 100 (batch size)
- Auto Commit: Enabled

**Methods**:
- `start()` → Begin consuming messages (blocking loop)
  - Runs indefinitely until stopped
  - Processes messages one-by-one
  - Logs stats every 100 messages

- `stop()` → Graceful shutdown
  - Closes Kafka consumer
  - Closes database connections
  - Logs final statistics

- `get_stats()` → Consumer metrics
  - Returns: consumed, stored, failed counts

**Usage Example**:
```python
from services.storage.kafka_consumer import KafkaStorageConsumer

consumer = KafkaStorageConsumer(
    kafka_bootstrap_servers="localhost:9092",
    kafka_topic="alpr.plates.detected",
    kafka_group_id="alpr-storage-consumer",
    db_host="localhost",
    db_port=5432,
    db_name="alpr_db",
    db_user="alpr",
    db_password="alpr_secure_pass"
)

# Start consuming (blocking)
consumer.start()
```

**Deployment** (Docker):
```bash
# Run as Docker service (docker-compose.yml)
docker-compose up -d kafka-consumer

# Check logs
docker logs -f alpr-kafka-consumer

# Stop service
docker-compose stop kafka-consumer
```

**Message Flow**:
1. Kafka message received from topic
2. JSON deserialization
3. Extract event metadata (event_id, plate_text, camera_id)
4. Call `StorageService.insert_event()`
5. Log success/failure
6. Commit offset to Kafka

**Performance Notes**:
- Throughput: 100-500 events/second
- Latency: <10ms per message
- No message loss (offset commit after successful storage)
- Automatic reconnection on failure

**Environment Variables**:
```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=alpr.plates.detected
KAFKA_GROUP_ID=alpr-storage-consumer
DB_HOST=localhost
DB_PORT=5432
DB_NAME=alpr_db
DB_USER=alpr
DB_PASSWORD=alpr_secure_pass
AUTO_OFFSET_RESET=latest
```

---

### 10. Query API Service

**Location**: `services/api/query_api.py`

**Purpose**: REST API for querying historical plate detection events from TimescaleDB

**Key Features**:
- FastAPI framework with automatic OpenAPI documentation
- CORS support for web clients
- Multiple query endpoints (by ID, plate, camera, time range)
- Pagination support (limit/offset)
- Health checks and statistics
- Connection pooling via StorageService
- JSON response formatting

**Main Endpoints**:

**GET /** - API root and endpoint listing
```json
{
  "name": "ALPR Query API",
  "version": "1.0.0",
  "endpoints": { ... }
}
```

**GET /health** - Health check
```json
{
  "status": "healthy",
  "database_connected": true
}
```

**GET /stats** - Database statistics
```json
{
  "is_connected": true,
  "total_events": 12543,
  "unique_plates": 3421,
  "active_cameras": 4,
  "earliest_event": "2025-01-10T08:00:00Z",
  "latest_event": "2025-01-15T16:30:00Z",
  "avg_confidence": 0.876,
  "avg_latency_ms": 85.3
}
```

**GET /events/recent?limit=10** - Recent events (by insertion time)
```json
{
  "count": 10,
  "events": [ ... ]
}
```

**GET /events/{event_id}** - Single event by ID
```json
{
  "event_id": "uuid",
  "captured_at": "2025-01-15T12:34:56Z",
  "plate_text": "ABC1234",
  ...
}
```

**GET /events/plate/{plate_text}?limit=100&offset=0** - Events by plate
```json
{
  "plate": "ABC1234",
  "count": 5,
  "limit": 100,
  "offset": 0,
  "events": [ ... ]
}
```

**GET /events/camera/{camera_id}?start_time=...&end_time=...** - Events by camera
```json
{
  "camera_id": "CAM-001",
  "start_time": "2025-01-15T00:00:00Z",
  "end_time": "2025-01-15T23:59:59Z",
  "count": 42,
  "events": [ ... ]
}
```

**GET /events/search?plate=...&camera=...&site=...** - Advanced search
- Supports multiple filters
- Time range filtering
- Pagination

**Usage Examples**:

```bash
# Get API documentation (interactive)
http://localhost:8000/docs

# Get recent events
curl http://localhost:8000/events/recent?limit=10

# Search by plate
curl http://localhost:8000/events/plate/ABC1234

# Search by camera with time range
curl "http://localhost:8000/events/camera/CAM-001?start_time=2025-01-15T00:00:00Z&limit=50"

# Get statistics
curl http://localhost:8000/stats
```

**Deployment** (Docker):
```bash
# Run as Docker service
docker-compose up -d query-api

# Access API
http://localhost:8000

# Access interactive docs
http://localhost:8000/docs

# Health check
curl http://localhost:8000/health
```

**Response Models** (Pydantic):
- `EventResponse`: Complete plate event data
- `StatsResponse`: Database statistics
- Automatic JSON serialization
- Type validation and documentation

**Performance Notes**:
- Response time: 10-100ms depending on query complexity
- Concurrent requests: 10-50 simultaneous connections
- Database connection pooling for efficiency
- CORS enabled for browser access

**Recent Fixes**:
- `/events/recent` now orders by `created_at` (insertion time) instead of `captured_at` for accurate recency
- Added `idx_created_at` index for optimized recent events queries

---

### 11. Image Storage Service (MinIO)

**Location**: `services/storage/image_storage_service.py`

**Purpose**: Async upload of plate crop images to MinIO S3-compatible object storage

**Key Features**:
- S3-compatible object storage integration
- Async background uploads using ThreadPoolExecutor (4 threads)
- Local cache with automatic cleanup (configurable retention)
- Upload retry logic with exponential backoff
- Metadata tagging (camera_id, track_id, plate_text, quality_score)
- Health monitoring and upload statistics
- Graceful shutdown with pending upload completion

**Main Class**: `ImageStorageService`

**Configuration**:
- MinIO Endpoint: `localhost:9000`
- Access Key: `alpr_minio`
- Bucket Name: `alpr-plate-images`
- Upload Threads: 4
- Cache Cleanup: 30 days retention

**Methods**:
- `upload_image_async(local_file_path, metadata)` → Queue image upload
  - Returns: S3 URL (`s3://bucket/path/to/image.jpg`)
  - Uploads in background thread
  - Adds to upload queue
  - Returns immediately (non-blocking)

- `upload_image_sync(local_file_path, metadata)` → Upload and wait
  - Returns: S3 URL or None on failure
  - Blocking upload with retry logic
  - Exponential backoff on failures

- `get_stats()` → Upload statistics
  - Returns: Total uploads, failures, queue size
  - Thread pool status

- `shutdown(wait=True, timeout=30)` → Graceful shutdown
  - Waits for pending uploads to complete
  - Stops upload threads
  - Logs final statistics

**Usage Example**:
```python
from services.storage.image_storage_service import ImageStorageService

storage = ImageStorageService(
    endpoint='localhost:9000',
    access_key='alpr_minio',
    secret_key='alpr_minio_secure_pass_2024',
    bucket_name='alpr-plate-images',
    local_cache_dir='output/crops',
    max_workers=4
)

# Async upload (non-blocking)
s3_url = storage.upload_image_async(
    local_file_path='output/crops/2025-12-25/CAM1_track42_frame123_q0.85.jpg',
    metadata={
        'camera_id': 'CAM1',
        'track_id': '42',
        'plate_text': 'ABC1234',
        'quality_score': '0.85',
        'frame_number': '123'
    }
)

print(f'Upload queued: {s3_url}')

# Get statistics
stats = storage.get_stats()
print(f'Uploads: {stats["upload_count"]}, Failures: {stats["upload_failures"]}')

# Cleanup
storage.shutdown(wait=True, timeout=30)
```

**Integration with pilot.py**:
- Integrated in `_save_best_crop_to_disk()` method
- Uploads occur AFTER saving to local filesystem
- S3 URLs stored in database `plate_image_url` field
- Non-blocking background uploads prevent pipeline delays

**Performance Notes**:
- Upload latency: 100-500ms per image (depending on network)
- Throughput: 10-20 uploads/second with 4 threads
- Automatic retry on network failures
- Local cache ensures data persistence even if MinIO is down

**MinIO Configuration** (docker-compose.yml):
```yaml
minio:
  image: minio/minio:latest
  container_name: alpr-minio
  ports:
    - "9000:9000"  # API
    - "9001:9001"  # Console
  environment:
    MINIO_ROOT_USER: alpr_minio
    MINIO_ROOT_PASSWORD: alpr_minio_secure_pass_2024
  command: server /data --console-address ":9001"
  volumes:
    - minio-data:/data
```

**Access MinIO Console**: http://localhost:9001

---

### 12. Alert Engine Service

**Location**: `core-services/alerting/alert_engine.py`

**Purpose**: Real-time rule-based notification engine that consumes plate detection events and triggers alerts via multiple channels (Email, Slack, Webhook, SMS)

**Key Features**:
- Rule-based event filtering and matching
- Multi-channel notifications (Email, Slack, Webhook, SMS via Twilio)
- YAML-based configuration for alert rules
- Prometheus metrics for alert monitoring
- Rate limiting and deduplication
- Pattern matching (exact, prefix, suffix, contains, regex)
- Avro/JSON event deserialization
- Graceful shutdown handling

**Main Class**: `AlertEngine`

**Configuration**: `config/alert_rules.yaml`

**Alert Rule Structure**:
```yaml
rules:
  - name: "High Priority Vehicle"
    description: "Alert when specific plates are detected"
    enabled: true
    conditions:
      plate_patterns:
        - pattern: "ABC*"
          match_type: "prefix"
      camera_ids:
        - "CAM-001"
        - "CAM-002"
    actions:
      - type: "email"
        recipients:
          - "security@example.com"
        subject: "ALPR Alert: High Priority Vehicle Detected"
      - type: "slack"
        channel: "#security-alerts"
```

**Supported Notification Channels**:

1. **Email (SMTP)**:
   - Requires: SMTP server, username, password
   - Customizable subject and body templates
   - Attachment support for plate images

2. **Slack**:
   - Uses Incoming Webhook URLs
   - Rich message formatting
   - Supports channels and DMs

3. **Webhook**:
   - Generic HTTP POST to custom endpoints
   - JSON payload with full event data
   - Optional authentication headers

4. **SMS (Twilio)**:
   - Requires: Twilio Account SID and Auth Token
   - International SMS support
   - Character limit handling

**Methods**:
- `process_event(event)` → Evaluate event against all enabled rules
  - Returns: List of triggered alerts
  - Executes all matching rule actions

- `send_notification(action, event)` → Send notification via specified channel
  - Returns: Success/failure status
  - Handles rate limiting and retries

- `evaluate_rule(rule, event)` → Check if event matches rule conditions
  - Returns: Boolean match result
  - Supports complex condition combinations

- `get_metrics()` → Prometheus metrics
  - Returns: Total events processed, alerts triggered, notification failures

**Metrics Exposed** (Port 8003):
```
# Events processed
alpr_alert_events_processed_total

# Alerts triggered by rule
alpr_alert_triggered_total{rule="rule_name"}

# Notifications sent by channel
alpr_notifications_sent_total{channel="email|slack|webhook|sms"}

# Notification failures
alpr_notifications_failed_total{channel="email|slack|webhook|sms"}

# Rule evaluation time
alpr_rule_evaluation_duration_seconds
```

**Usage Example**:
```python
from core-services.alerting.alert_engine import AlertEngine

engine = AlertEngine(
    kafka_bootstrap_servers="localhost:9092",
    kafka_topic="alpr.plates.detected",
    kafka_group_id="alpr-alert-engine",
    schema_registry_url="http://localhost:8081",
    rules_config_path="config/alert_rules.yaml"
)

# Start consuming and processing events
engine.start()
```

**Deployment** (Docker):
```bash
# Run as Docker service
docker compose up -d alert-engine

# Check logs
docker logs -f alpr-alert-engine

# View metrics
curl http://localhost:8003/metrics

# Stop service
docker compose stop alert-engine
```

**Environment Variables**:
```bash
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_TOPIC=alpr.plates.detected
KAFKA_GROUP_ID=alpr-alert-engine
SCHEMA_REGISTRY_URL=http://schema-registry:8081
RULES_CONFIG_PATH=/app/config/alert_rules.yaml

# Notification credentials (optional, based on channels used)
SMTP_PASSWORD=your_smtp_password
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
WEBHOOK_TOKEN=your_webhook_auth_token
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
```

**Pattern Matching Types**:
- `exact`: Exact plate text match (case-insensitive)
- `prefix`: Plate starts with pattern (e.g., "ABC*" matches "ABC123")
- `suffix`: Plate ends with pattern (e.g., "*123" matches "ABC123")
- `contains`: Plate contains pattern (e.g., "*BC1*" matches "ABC123")
- `regex`: Full regex pattern matching (e.g., "^[A-Z]{3}\d{3}$")

**Performance Notes**:
- Throughput: 100-500 events/second
- Rule evaluation: <1ms per rule per event
- Notification latency: 100-2000ms depending on channel
- Automatic retry on notification failures
- Rate limiting prevents notification spam

**Recent Features**:
- ✅ Multi-channel notification support
- ✅ YAML-based rule configuration
- ✅ Prometheus metrics integration
- ✅ Avro deserialization support
- ✅ Pattern matching with regex
- ✅ Graceful shutdown handling

---

## Infrastructure Services

### Kafka Ecosystem

**Apache Kafka** (`confluentinc/cp-kafka:7.5.0`)
- Message broker for event streaming
- Topic: `alpr.plates.detected`
- Port: 9092 (external), 29092 (internal)
- GZIP compression
- 7-day retention
- Container: `alpr-kafka`

**ZooKeeper** (`confluentinc/cp-zookeeper:7.5.0`)
- Kafka coordination service
- Port: 2181
- Required for Kafka broker
- Container: `alpr-zookeeper`

**Kafka UI** (`provectuslabs/kafka-ui:latest`)
- Web interface for Kafka management
- Port: 8080
- View topics, messages, consumer groups
- Real-time monitoring
- Container: `alpr-kafka-ui`
- Access: http://localhost:8080

**Confluent Schema Registry** (`confluentinc/cp-schema-registry:7.5.0`)
- Centralized schema management for Kafka
- Port: 8081
- Avro schema storage and validation
- BACKWARD compatibility mode
- Container: `alpr-schema-registry`
- REST API: http://localhost:8081

**Key Features**:
- PlateEvent Avro schema (ID: 1, Version: 1)
- Automatic schema validation on produce/consume
- Schema evolution with compatibility checking
- 62% message size reduction vs JSON
- Integrated with Kafka producers/consumers
- REST API for schema management
- Health checks and monitoring

### Database

**TimescaleDB** (`timescale/timescaledb:latest-pg16`)
- PostgreSQL 16 + TimescaleDB extension
- Time-series optimized storage
- Port: 5432
- Hypertable partitioning by time
- Automatic data retention (optional)
- Container: `alpr-timescaledb`
- Database: `alpr_db`
- User: `alpr`

**Key Features**:
- Hypertable: Automatic partitioning by `captured_at` timestamp
- Continuous aggregates: Pre-computed analytics (optional)
- Data retention policies: Auto-cleanup old data (optional)
- Compression: Automatic compression of old chunks
- Indexing: B-tree indexes for fast queries

### Object Storage

**MinIO** (`minio/minio:latest`)
- S3-compatible object storage for plate crop images
- Port: 9000 (API), 9001 (Console)
- Bucket: `alpr-plate-images`
- Automatic bucket initialization
- Container: `alpr-minio`
- Access Key: `alpr_minio`
- Console: http://localhost:9001

**Key Features**:
- S3 API compatibility (works with boto3, minio-py, AWS SDK)
- Web console for bucket management and browsing
- Async image uploads from pilot.py
- Metadata tagging support
- Lifecycle policies for automatic cleanup (optional)
- High-performance local storage
- Docker volume persistence (`minio-data`)
- Health checks and monitoring

### Monitoring & Observability

**Prometheus** (`prom/prometheus:latest`)
- Metrics collection and time-series storage
- Port: 9090
- Scrape interval: 5-30s depending on target
- Container: `alpr-prometheus`
- Config: `core-services/monitoring/prometheus/prometheus.yml`

**Key Features**:
- Scrapes metrics from all ALPR services
- 30-day retention
- PromQL query language
- Alert rule evaluation
- Targets: pilot.py, kafka-consumer, query-api, cAdvisor

**Grafana** (`grafana/grafana:latest`)
- Metrics visualization and dashboards
- Port: 3000
- Login: `admin` / `alpr_admin_2024`
- Container: `alpr-grafana`

**Pre-configured Dashboards**:
- **ALPR Overview** - Real-time FPS, detections, processing latency
- **System Performance** - CPU, RAM, network usage per container
- **Kafka & Database** - Message consumption, DB operations
- **Logs Explorer** - Centralized log search

**Loki** (`grafana/loki:latest`)
- Log aggregation system
- Port: 3100
- Container: `alpr-loki`
- Config: `core-services/monitoring/loki/loki-config.yaml`

**Key Features**:
- Lightweight log aggregation
- LogQL query language
- 7-day retention
- Integration with Grafana
- Label-based indexing

**Promtail** (`grafana/promtail:latest`)
- Log shipping agent
- Port: 9080 (internal)
- Container: `alpr-promtail`
- Config: `core-services/monitoring/promtail/promtail-config.yaml`

**Key Features**:
- Ships logs from Docker containers to Loki
- Ships logs from application log files
- Label extraction
- Multi-line log support

**cAdvisor** (`gcr.io/cadvisor/cadvisor:latest`)
- Container resource metrics
- Port: 8082 (external, changed from 8080 to avoid Kafka UI conflict)
- Container: `alpr-cadvisor`

**Key Features**:
- CPU, memory, network, disk metrics per container
- Real-time monitoring
- Historical resource usage
- Prometheus metrics export

**Access URLs**:
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Loki: http://localhost:3100 (API only)
- cAdvisor: http://localhost:8082

### Docker Compose Stack

**Network**: `alpr-network` (bridge)

**Volumes**:
- `zookeeper-data`: ZooKeeper persistent data
- `zookeeper-logs`: ZooKeeper logs
- `kafka-data`: Kafka message logs
- `timescaledb-data`: PostgreSQL database files
- `minio-data`: MinIO object storage files

**Startup Order**:
1. ZooKeeper
2. Kafka (depends on ZooKeeper)
3. Schema Registry (depends on Kafka)
4. TimescaleDB
5. MinIO
6. MinIO Init (depends on MinIO, creates buckets)
7. Kafka Consumer (depends on Kafka + Schema Registry + TimescaleDB)
8. Alert Engine (depends on Kafka + Schema Registry)
9. Query API (depends on TimescaleDB)
10. Kafka UI (depends on Kafka + Schema Registry)

**Management Commands**:
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f [service-name]

# Stop all services
docker-compose stop

# Restart specific service
docker-compose restart kafka-consumer

# View service status
docker-compose ps

# Remove all containers (keeps volumes)
docker-compose down

# Remove all containers and volumes (DELETES DATA!)
docker-compose down -v
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

### Edge Services (Python)

**Camera Ingestion**
- OpenCV (cv2)
- NumPy
- PyYAML

**Detector**
- Ultralytics YOLO
- PyTorch
- TensorRT (optional, recommended)

**Tracker**
- FilterPy (Kalman filter)
- LAP (linear assignment)
- Cython-bbox (fast IoU)

**OCR**
- PaddleOCR
- PaddlePaddle
- OpenCV

**Event Processor**
- Python stdlib (re, uuid, datetime)
- Levenshtein (fuzzy matching)

**Kafka Publisher**
- kafka-python 2.0+

### Backend Services (Python)

**Storage Service**
- psycopg2 (PostgreSQL driver)
- psycopg2.pool (connection pooling)
- loguru (logging)

**Kafka Consumer**
- kafka-python 2.0+
- services.storage.storage_service
- loguru (logging)

**Query API**
- FastAPI 0.100+
- Uvicorn (ASGI server)
- Pydantic (data validation)
- services.storage.storage_service
- loguru (logging)

### Infrastructure Services (Docker)

**Kafka Broker**
- confluentinc/cp-kafka:7.5.0
- Java 11+
- ZooKeeper

**ZooKeeper**
- confluentinc/cp-zookeeper:7.5.0
- Java 11+

**Kafka UI**
- provectuslabs/kafka-ui:latest
- Node.js runtime

**TimescaleDB**
- timescale/timescaledb:latest-pg16
- PostgreSQL 16
- TimescaleDB extension

---

## Performance Summary

### Edge Processing (pilot.py)

| Service | CPU Time | GPU Time | Bottleneck |
|---------|----------|----------|------------|
| Camera Ingestion (RTSP GPU) | <2ms | 3-5ms | I/O |
| Camera Ingestion (Video CPU) | 10-15ms | - | I/O |
| Vehicle Detection | 5-10ms | 10-15ms | GPU inference |
| Plate Detection | 5-8ms | 5-10ms | GPU inference |
| Tracking | <1ms | - | LAP solver |
| OCR | 20-50ms | 50-150ms | PaddleOCR |
| Event Processing | <1ms | - | Levenshtein |
| Kafka Publishing | 5-10ms | - | Network |

**Total Edge Pipeline**: 40-90ms per frame (with OCR), 20-40ms (detection only)

**Throughput**: 15-25 FPS (full pipeline), 25-50 FPS (detection only)

### Backend Services (Docker)

| Service | Throughput | Latency | Resource Usage |
|---------|------------|---------|----------------|
| Kafka Broker | 10,000+ msg/s | 1-5ms | Low CPU, 512MB RAM |
| Kafka Consumer | 100-500 events/s | <10ms | Low CPU, 256MB RAM |
| Storage Service | 500-1000 inserts/s | 1-5ms per insert | Low CPU, 512MB RAM |
| Query API | 50-100 req/s | 10-100ms | Low CPU, 256MB RAM |
| TimescaleDB | 1000+ writes/s | 5-50ms | Medium CPU, 1-2GB RAM |

**Total System Capacity**: 100+ events/second sustained (thousands peak)

---

## Configuration Files

- `config/cameras.yaml`: Camera sources and settings
- `config/tracking.yaml`: ByteTrack parameters
- `config/ocr.yaml`: PaddleOCR preprocessing settings
- `pilot.py`: Main application configuration

---

## Complete Data Flow

### End-to-End Event Lifecycle

1. **Capture** (Camera Ingestion)
   - Frame captured from RTSP stream or video file
   - Hardware-accelerated decoding
   - Frame buffering and queue management

2. **Detection** (YOLO Detector)
   - Vehicle detection (car, truck, bus, motorcycle)
   - Plate detection within vehicle bounding boxes
   - TensorRT FP16 optimization

3. **Tracking** (ByteTrack)
   - Assign unique track IDs to vehicles
   - Kalman filter motion prediction
   - Associate detections across frames

4. **OCR** (PaddleOCR)
   - Per-track throttling (avoid redundant OCR)
   - Multi-strategy preprocessing
   - Confidence-based filtering

5. **Validation** (Event Processor)
   - Plate text normalization
   - Format validation (US state patterns)
   - Fuzzy deduplication (5-minute window)
   - Metadata enrichment

6. **Publishing** (Kafka Publisher)
   - JSON serialization
   - Publish to `alpr.plates.detected` topic
   - GZIP compression
   - Async with acknowledgments

7. **Messaging** (Kafka Broker)
   - Message buffering and ordering
   - Topic partitioning by camera_id
   - 7-day retention
   - Consumer group coordination

8. **Consumption** (Kafka Consumer)
   - Subscribe to topic
   - JSON deserialization
   - Offset management

9. **Storage** (Storage Service)
   - Insert into TimescaleDB
   - Duplicate prevention
   - Hypertable partitioning
   - Automatic indexing

10. **Persistence** (TimescaleDB)
    - Time-series optimized storage
    - Automatic partitioning by time
    - Continuous aggregates
    - Data retention policies

11. **Query** (Query API)
    - REST endpoints for retrieval
    - Multiple query patterns
    - Pagination support
    - Real-time statistics

12. **Consumption** (Client Applications)
    - Web dashboards
    - Mobile apps
    - Analytics tools
    - Alert systems

---

## Quick Start Guide

### 1. Start Infrastructure Services

```bash
# Start Kafka, TimescaleDB, and backend services
cd /home/jetson/OVR-ALPR
docker-compose up -d

# Verify services are running
docker-compose ps

# Check logs
docker-compose logs -f
```

### 2. Run Edge ALPR Pipeline

```bash
# Run full pipeline with display
python pilot.py

# Headless mode (no visualization)
python pilot.py --no-display

# Custom configuration
python pilot.py --model models/yolo11n.pt --plate-model models/yolo11n-plate.pt
```

### 3. Query Events via API

```bash
# Get recent events
curl http://localhost:8000/events/recent?limit=10

# Search by plate
curl http://localhost:8000/events/plate/ABC1234

# Get statistics
curl http://localhost:8000/stats

# Interactive API docs
http://localhost:8000/docs
```

### 4. Monitor Kafka

```bash
# Kafka UI web interface
http://localhost:8080

# View topic messages
# Navigate to Topics → alpr.plates.detected → Messages

# Check consumer lag
# Navigate to Consumers → alpr-storage-consumer
```

### 5. Query Database Directly

```bash
# Connect to TimescaleDB
docker exec -it alpr-timescaledb psql -U alpr -d alpr_db

# Query recent events
SELECT event_id, captured_at, plate_normalized_text, camera_id
FROM plate_events
ORDER BY created_at DESC
LIMIT 10;

# Get statistics
SELECT * FROM plate_events_stats;

# Exit
\q
```

---

## Troubleshooting

### Kafka Consumer Not Storing Events

**Symptom**: Events visible in Kafka but not in database

**Solutions**:
1. Check consumer logs: `docker logs -f alpr-kafka-consumer`
2. Verify database connection: `docker exec alpr-timescaledb pg_isready -U alpr`
3. Check consumer group lag in Kafka UI
4. Restart consumer: `docker-compose restart kafka-consumer`

### Query API Returning Empty Results

**Symptom**: `/events/recent` returns empty array

**Solutions**:
1. Verify database has events: `docker exec -it alpr-timescaledb psql -U alpr -d alpr_db -c "SELECT COUNT(*) FROM plate_events;"`
2. Check API logs: `docker logs -f alpr-query-api`
3. Verify database connection in API health check: `curl http://localhost:8000/health`
4. Check `created_at` index exists: Run `scripts/add_created_at_index.sql`

### Kafka Broker Not Starting

**Symptom**: `alpr-kafka` container exits immediately

**Solutions**:
1. Ensure ZooKeeper is running: `docker-compose ps zookeeper`
2. Check ZooKeeper logs: `docker logs alpr-zookeeper`
3. Clean up stale data: `docker-compose down -v && docker-compose up -d`
4. Verify port 9092 not in use: `lsof -i :9092`

### TimescaleDB Connection Refused

**Symptom**: Consumer/API cannot connect to database

**Solutions**:
1. Verify TimescaleDB is healthy: `docker-compose ps timescaledb`
2. Check database logs: `docker logs alpr-timescaledb`
3. Test connection: `docker exec alpr-timescaledb pg_isready -U alpr`
4. Ensure `init_db.sql` ran successfully: Check for tables in database

---

## Next Steps

### For Development

1. **Review service documentation** for implementation details
2. **Check configuration files** in `config/` directory
3. **Read performance guides** in `docs/` for optimization tips
4. **Explore examples** in `services/*/example_usage.py`

### For Deployment

1. **Configure environment variables** in `docker-compose.yml`
2. **Set up data retention policies** in TimescaleDB
3. **Enable SSL/TLS** for production Kafka
4. **Configure CORS** properly in Query API
5. **Set up monitoring** with Prometheus/Grafana
6. **Configure backup** for TimescaleDB volumes

### For Monitoring

1. **Set up Kafka UI** for topic monitoring (http://localhost:8080)
2. **Enable TimescaleDB monitoring** views
3. **Configure logging** aggregation (ELK/Loki)
4. **Set up alerting** for consumer lag and errors
5. **Monitor disk usage** for Kafka and TimescaleDB volumes

For more information, see:
- [Storage Layer Documentation](storage-layer.md)
- [Storage Quickstart Guide](storage-quickstart.md)
- [Kafka Integration Guide](INTEGRATION_COMPLETE%20Kafka%20+%20Event%20Processing.md)
- [Kafka Setup Guide](kafka-setup.md)
- [Event Processor Service Details](event-processor-service.md)
- [Performance Optimization Guide](PERFORMANCE_OPTIMIZATION_GUIDE.md)
- [Deployment Architecture](deployment/architecture.md)
