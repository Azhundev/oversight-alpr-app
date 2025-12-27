# Edge Services

Services that run **on the edge device** (Jetson Orin NX) for real-time ALPR processing.

## Architecture

Edge services handle:
- Camera video ingestion
- Real-time license plate detection
- OCR processing
- Object tracking
- Event publishing to Kafka

```
┌─────────────────────────────────────────────────────────┐
│                    JETSON ORIN NX                        │
│                   (Edge Device)                          │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  📹 Camera Streams                                       │
│      ↓                                                    │
│  🎥 camera/          - Video ingestion & preprocessing   │
│      ↓                                                    │
│  🔍 detector/        - YOLOv11 plate detection          │
│      ↓                                                    │
│  📝 ocr/             - PaddleOCR text recognition        │
│      ↓                                                    │
│  🎯 tracker/         - Multi-object tracking             │
│      ↓                                                    │
│  ⚙️  event_processor/ - Event formatting & enrichment    │
│      ↓                                                    │
│  📤 Kafka Publisher  - Send events to backend           │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Services

### 📹 camera/
**Camera Ingestion Service**

Handles video stream acquisition and frame preprocessing.

- **Inputs**: RTSP/USB camera streams
- **Outputs**: Preprocessed video frames
- **Tech**: OpenCV, GStreamer
- **Config**: `config/cameras.yaml`

**Key Files**:
- `camera_ingestion.py` - Main ingestion logic
- `Dockerfile` - Containerization (optional)

---

### 🔍 detector/
**Plate Detection Module**

YOLOv11-based license plate detection.

- **Model**: `models/yolov11n-plate.pt`
- **Input**: Video frames
- **Output**: Bounding boxes of detected plates
- **Inference**: GPU-accelerated (TensorRT on Jetson)

---

### 📝 ocr/
**Optical Character Recognition**

PaddleOCR for reading license plate text.

- **Input**: Cropped plate images
- **Output**: Recognized text with confidence scores
- **Optimizations**: INT8 quantization for Jetson

---

### 🎯 tracker/
**Multi-Object Tracking**

Tracks vehicles/plates across frames.

- **Algorithm**: ByteTrack/BoT-SORT
- **Purpose**: Associate detections, reduce duplicates
- **Output**: Unique track IDs per vehicle

---

### ⚙️ event_processor/
**Event Processing & Publishing**

Formats detection events and publishes to Kafka.

- **Input**: Detections + OCR results + tracks
- **Output**: Avro-formatted Kafka messages
- **Schema**: `schemas/plate_detection_event.avsc`

---

## Running Edge Services

### Local Development

```bash
# Run main ALPR pipeline
python3 pilot.py

# With specific camera config
python3 pilot.py --config config/cameras.yaml

# Enable debug mode
python3 pilot.py --debug
```

### Production Deployment

```bash
# As systemd service
sudo systemctl start alpr-pilot
sudo systemctl status alpr-pilot

# View logs
journalctl -u alpr-pilot -f
```

## Configuration

### Camera Configuration
Edit `config/cameras.yaml`:

```yaml
cameras:
  - id: "camera_01"
    name: "Main Entrance"
    source: "rtsp://192.168.1.100:554/stream1"
    enabled: true
```

### Performance Tuning
Edit `pilot.py` or environment variables:

```bash
# GPU device
export CUDA_VISIBLE_DEVICES=0

# Batch size for detection
export YOLO_BATCH_SIZE=4

# Max FPS (limit processing)
export MAX_FPS=30
```

## Metrics

Edge services expose Prometheus metrics on port **8001**:

```bash
curl http://localhost:8001/metrics
```

**Key Metrics**:
- `alpr_fps_current` - Current processing FPS
- `alpr_plates_detected_total` - Total plates detected
- `alpr_processing_latency_seconds` - Frame processing time
- `alpr_kafka_publish_latency_seconds` - Event publish time

View in Grafana: **ALPR Overview Dashboard**

## Data Flow

```
Camera → camera/ → detector/ → ocr/ → tracker/ → event_processor/ → Kafka
   ↓         ↓          ↓        ↓        ↓            ↓
 RTSP     Frames    Boxes    Text   Track IDs      Events
```

## Dependencies

### System Requirements
- **GPU**: NVIDIA Jetson Orin NX (or compatible)
- **CUDA**: 11.4+
- **cuDNN**: 8.6+
- **TensorRT**: 8.5+

### Python Dependencies
See `requirements.txt`:
- `ultralytics` - YOLOv11
- `opencv-python` - Video processing
- `paddleocr` - Text recognition
- `kafka-python` - Event publishing
- `prometheus-client` - Metrics

## Troubleshooting

### Low FPS
1. Check GPU utilization: `tegrastats`
2. Reduce input resolution in camera config
3. Lower YOLOv11 model size (n → s → m)
4. Enable TensorRT optimization

### Detection Issues
1. Verify camera stream: `ffplay <rtsp_url>`
2. Check detection confidence threshold
3. Review plate crop images in logs
4. Validate YOLO model: `yolo detect predict`

### Kafka Connection Failures
1. Check Kafka is accessible: `nc -zv localhost 9092`
2. Verify schema registry: `curl http://localhost:8081/subjects`
3. Review Kafka consumer logs

## Related Documentation

- [ALPR Pipeline Overview](../docs/ALPR_Pipeline/)
- [Camera Configuration Guide](../docs/Services/camera-configuration.md)
- [Port Reference](../docs/alpr_pipeline/port-reference.md)
- [Core Services](../core-services/README.md)

---

**Note**: Edge services are designed to run **directly on the Jetson device**, not in Docker. They require direct GPU access for optimal performance.
