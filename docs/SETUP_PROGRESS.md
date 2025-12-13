# ALPR System - Setup Progress

## ✅ Completed

### 1. Project Structure
- Created microservices directory layout
- Organized shared schemas and utilities
- Set up configuration directory
- Infrastructure templates ready

### 2. Configuration Files
All YAML configs created and optimized for Jetson Orin NX:

- ✅ `config/cameras.yaml` - Camera definitions (RTSP + video files)
- ✅ `config/detection.yaml` - YOLOv11 + TensorRT settings
- ✅ `config/ocr.yaml` - PaddleOCR configuration
- ✅ `config/tracking.yaml` - ByteTrack/NvDCF settings
- ✅ `config/deduplication.yaml` - Event dedup rules
- ✅ `config/validation.yaml` - USA/Mexico/Canada plate validation

### 3. Shared Components
- ✅ `shared/schemas/event.py` - Pydantic models for type-safe events
  - `DetectionEvent` - Main event structure
  - `PlateDetection` - Plate data with validation
  - `VehicleDetection` - Vehicle data
  - `KafkaEvent` / `DatabaseEvent` - Transport/storage formats

- ✅ `shared/utils/plate_validator.py` - North America plate validation
  - All 50 US states + DC
  - Mexican states (standard + regional)
  - Canadian provinces
  - Normalization (uppercase, remove spaces/dashes)
  - OCR error correction (O→0, I→1, etc.)

### 4. Services Implemented

#### Detector Service
- ✅ `services/detector/detector_service.py`
  - YOLOv11 integration
  - TensorRT optimization for Jetson
  - FP16 precision support
  - Vehicle detection (car, truck, bus, motorcycle)
  - Plate detection (custom model + contour fallback)
  - Warmup function for consistent latency
  - Test harness included

### 5. Documentation
- ✅ `README.md` - Complete system overview
- ✅ `requirements.txt` - All dependencies listed

## 🔄 In Progress

### Next Services to Build
1. **OCR Service** - PaddleOCR with batch processing
2. **Tracker Service** - ByteTrack implementation
3. **Event Processor** - Deduplication + enrichment
4. **Storage Service** - MinIO/S3 uploads
5. **API Service** - FastAPI REST endpoints
6. **Database** - PostgreSQL schema

## 📋 Next Steps

### Immediate (Pilot on Jetson Orin NX)
1. Create OCR service with PaddleOCR
2. Implement ByteTrack tracker
3. Build event processor with Redis dedup
4. Create simple pilot script (all-in-one)
5. Test on video files (720p.mp4, a.mp4)

### Phase 2 (Dockerization)
1. Create Dockerfiles for each service
2. Docker Compose for local testing
3. Setup Kafka + Redis + PostgreSQL containers

### Phase 3 (Production/Core)
1. Kubernetes manifests
2. Helm charts
3. Horizontal scaling configs
4. Monitoring (Prometheus/Grafana)
5. Distributed deployment

## Technology Stack

| Component | Technology | Status |
|-----------|-----------|---------|
| Detection | YOLOv11 + TensorRT | ✅ Implemented |
| OCR | PaddleOCR | 🔄 Next |
| Tracking | ByteTrack | 🔄 Next |
| Messaging | Kafka/MQTT | ⏳ Pending |
| Database | PostgreSQL | ⏳ Pending |
| Cache | Redis | ⏳ Pending |
| Storage | MinIO/S3 | ⏳ Pending |
| API | FastAPI | ⏳ Pending |

## File Structure

```
OVR-ALPR/
├── 720p.mp4                     # Test video
├── a.mp4                        # Test video
├── README.md                    # Main documentation
├── requirements.txt             # Python dependencies
│
├── config/                      # ✅ All configs complete
│   ├── cameras.yaml
│   ├── detection.yaml
│   ├── ocr.yaml
│   ├── tracking.yaml
│   ├── deduplication.yaml
│   └── validation.yaml
│
├── shared/                      # ✅ Shared code complete
│   ├── schemas/
│   │   └── event.py            # Pydantic models
│   └── utils/
│       └── plate_validator.py  # North America validation
│
├── services/                    # 🔄 Services in progress
│   ├── detector/
│   │   └── detector_service.py # ✅ YOLOv11 detector
│   ├── ocr/                    # ⏳ TODO
│   ├── tracker/                # ⏳ TODO
│   ├── event-processor/        # ⏳ TODO
│   ├── api/                    # ⏳ TODO
│   └── storage/                # ⏳ TODO
│
├── infrastructure/              # ⏳ TODO
│   ├── docker/
│   ├── kubernetes/
│   └── helm/
│
├── tests/                       # ⏳ TODO
└── docs/                        # 🔄 In progress
    └── SETUP_PROGRESS.md        # This file
```

## Performance Targets (Jetson Orin NX)

| Metric | Target | Notes |
|--------|--------|-------|
| Detection FPS | 20-30 | YOLOv11n + TensorRT FP16 |
| OCR Latency | <100ms | PaddleOCR batch processing |
| Tracking Overhead | <5ms | ByteTrack is lightweight |
| End-to-end Latency | <200ms | Frame → Event published |
| Concurrent Cameras | 2-4 | Depends on resolution |

## Testing Plan

### Unit Tests
- [ ] Plate validator (all US states, MX, CA)
- [ ] Event schema validation
- [ ] Detector service
- [ ] OCR service
- [ ] Tracker service

### Integration Tests
- [ ] Full pipeline (frame → event)
- [ ] Deduplication logic
- [ ] Database persistence
- [ ] Kafka publishing

### System Tests
- [ ] Multi-camera stress test
- [ ] Long-running stability (24h+)
- [ ] Memory leak detection
- [ ] GPU utilization monitoring

## Notes

- **Jetson Orin NX Optimizations:**
  - TensorRT FP16 for 2x inference speedup
  - Unified memory for zero-copy between CPU/GPU
  - NVDEC hardware decoder for RTSP streams
  - Batch processing where possible

- **North America Focus:**
  - Plate validation covers USA (50 states), Mexico, Canada
  - OCR optimized for Latin alphabet
  - All configs use imperial units (mph, feet, etc.)

- **Scalability:**
  - Pilot runs on single Jetson (edge)
  - Production scales horizontally (Kubernetes)
  - Stateless services for easy scaling
