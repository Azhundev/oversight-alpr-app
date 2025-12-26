# OVR-ALPR Project Status

**Last Updated:** 2025-12-25

This document provides a snapshot of the current implementation status, showing what's working, what's in progress, and what's planned next.

---

## 🎯 Current Status: **Production-Ready (Phase 2+ with Object Storage)**

The system is currently in **Phase 2+** with a complete distributed architecture suitable for production deployments with 1-10 cameras. Core ALPR functionality is fully operational with enterprise-grade backend services and object storage.

**Overall Completion:** 45% of original vision (95% of core features)

---

## ✅ Fully Implemented (Production-Ready)

### Edge Processing Services

#### 1. Camera Ingestion ✅
- **File:** `services/camera/camera_ingestion.py`
- **Status:** Production-ready with GPU hardware decode
- **Features:**
  - Multi-threaded frame capture (one thread per camera)
  - **GPU hardware-accelerated decoding (NVDEC) for RTSP streams** ✅
  - Software decoding for video files (CPU, seeking/looping compatible)
  - Frame buffering with queue management
  - RTSP streams and video file support
  - Automatic video looping for test files
  - FPS control and statistics
  - Codec auto-detection (H.264/H.265)
- **Performance:**
  - **RTSP streams:** 80-90% CPU reduction with GPU decode
  - **RTSP capacity:** 4-6 streams per Jetson Orin NX (3x increase)
  - **Video files:** CPU decode for compatibility
- **Implementation:** OpenCV 4.6.0 rebuilt with GStreamer 1.20.3 support
- **See:** `docs/Optimizations/gpu-decode-implementation-complete.md` for full details

#### 2. Vehicle & Plate Detection ✅
- **File:** `services/detector/detector_service.py`
- **Status:** Production-ready with TensorRT optimization
- **Features:**
  - YOLOv11 custom models
  - TensorRT FP16 optimization (2-3x speedup)
  - Vehicle detection (car, truck, bus, motorcycle)
  - Plate detection within vehicle bounding boxes
  - Model warmup for consistent inference times
  - Confidence thresholding and NMS

#### 3. Multi-Object Tracking ✅
- **File:** `services/tracker/bytetrack_service.py`
- **Status:** Production-ready
- **Features:**
  - ByteTrack algorithm implementation
  - Kalman filter for motion prediction
  - High/low confidence association
  - Track buffering for occlusions
  - Unique track ID assignment
  - Track state management (NEW, TRACKED, LOST, REMOVED)

#### 4. OCR Service ✅
- **File:** `services/ocr/ocr_service.py`
- **Status:** Production-ready with optimizations
- **Features:**
  - PaddleOCR GPU acceleration
  - Per-track throttling (run ONCE per track)
  - Multi-strategy preprocessing
  - Florida orange logo removal
  - Adaptive image enhancement (CLAHE, denoise, sharpen)
  - Best-shot selection based on quality
  - Batch processing support

#### 5. Event Processing & Validation ✅
- **File:** `services/event_processor/event_processor_service.py`
- **Status:** Production-ready
- **Features:**
  - Plate text normalization (uppercase, alphanumeric)
  - Format validation (US state patterns)
  - Fuzzy deduplication (Levenshtein similarity)
  - 5-minute time window deduplication
  - Metadata enrichment (site, host, timestamps)
  - Confidence filtering

#### 6. Kafka Event Publishing ✅
- **File:** `services/event_processor/avro_kafka_publisher.py`
- **Status:** Production-ready with Avro serialization
- **Features:**
  - Avro binary serialization (62% size reduction vs JSON)
  - Schema Registry integration (localhost:8081)
  - Async publishing with acknowledgments
  - GZIP compression
  - Idempotent producer (exactly-once semantics)
  - Partition key for ordering (camera_id)
  - Automatic schema validation
  - Error handling and retries

### Backend Services (Docker)

#### 7. Apache Kafka Broker ✅
- **Container:** `alpr-kafka`
- **Status:** Production-ready
- **Features:**
  - Topic: `alpr.plates.detected`
  - 10,000+ msg/s capacity
  - 7-day message retention
  - GZIP compression
  - Consumer group coordination
  - Health checks

#### 8. Confluent Schema Registry ✅
- **Container:** `alpr-schema-registry`
- **Status:** Production-ready
- **Features:**
  - Confluent Schema Registry 7.5.0
  - PlateEvent Avro schema (ID: 1, Version: 1)
  - BACKWARD compatibility mode
  - Schema validation and evolution
  - REST API at localhost:8081
  - Integrated with Kafka UI
  - Health checks

#### 9. Kafka Consumer Service ✅
- **File:** `services/storage/avro_kafka_consumer.py`
- **Container:** `alpr-kafka-consumer`
- **Status:** Production-ready with Avro support
- **Features:**
  - Continuous message consumption
  - Avro deserialization with Schema Registry
  - Automatic schema lookup by ID
  - Switchable JSON/Avro mode (USE_AVRO env var)
  - Graceful shutdown (SIGINT/SIGTERM)
  - Automatic offset management
  - Error handling with retry logic
  - Consumer statistics

#### 10. Storage Service ✅
- **File:** `services/storage/storage_service.py`
- **Status:** Production-ready
- **Features:**
  - Connection pooling (thread-safe)
  - Prepared SQL statements
  - Duplicate prevention (ON CONFLICT)
  - Batch insert support
  - Multiple query methods
  - Statistics aggregation

#### 11. TimescaleDB ✅
- **Container:** `alpr-timescaledb`
- **Status:** Production-ready
- **Features:**
  - PostgreSQL 16 + TimescaleDB extension
  - Hypertable time-series partitioning
  - Automatic data compression
  - Retention policies (configurable)
  - Continuous aggregates support
  - Optimized indexes

#### 12. Query API Service ✅
- **File:** `services/api/query_api.py`
- **Container:** `alpr-query-api`
- **Status:** Production-ready
- **Features:**
  - FastAPI with OpenAPI docs
  - Multiple query endpoints (ID, plate, camera, time range)
  - Pagination support (limit/offset)
  - CORS enabled
  - Health checks
  - Real-time statistics
  - Connection pooling

#### 13. MinIO Object Storage ✅
- **File:** `services/storage/image_storage_service.py`
- **Container:** `alpr-minio`
- **Status:** Production-ready
- **Features:**
  - S3-compatible object storage
  - Async image uploads (ThreadPoolExecutor with 4 threads)
  - Local cache with automatic cleanup
  - Upload retry logic with exponential backoff
  - Metadata tagging (camera_id, track_id, plate_text)
  - Health monitoring and statistics
  - MinIO console at localhost:9001
  - Bucket: `alpr-plate-images`

### Infrastructure

#### 14. Docker Compose Stack ✅
- **File:** `docker-compose.yml`
- **Status:** Production-ready
- **Services:**
  - ZooKeeper (Kafka coordination)
  - Kafka Broker
  - Schema Registry (Avro schemas)
  - Kafka UI (web interface)
  - TimescaleDB
  - Kafka Consumer
  - Query API
  - MinIO (object storage)
- **Features:**
  - Health checks for all services
  - Persistent volumes
  - Network isolation
  - Dependency management
  - Restart policies

#### 15. Main ALPR Pipeline ✅
- **File:** `pilot.py`
- **Status:** Production-ready with Avro
- **Features:**
  - Complete integration of all services
  - Avro event publishing with Schema Registry
  - Per-track OCR throttling
  - Spatial deduplication
  - Frame quality filtering
  - Best-shot plate crop saving
  - CSV logging + Kafka publishing
  - Headless mode support
  - Command-line configuration

### Configuration

#### 15. YAML Configuration Files ✅
- ✅ `config/cameras.yaml` - Camera definitions
- ✅ `config/tracking.yaml` - ByteTrack parameters
- ✅ `config/ocr.yaml` - PaddleOCR settings

---

## 🔄 Partially Implemented

### 1. Monitoring 🟡
- **Current:** Docker logs + Loguru file logging
- **Missing:** Prometheus, Grafana, metrics endpoints
- **Impact:** Difficult to troubleshoot production issues
- **Next:** Deploy monitoring stack (Priority 1)

### 2. Kafka Topics 🟡
- **Current:** Single topic (`alpr.plates.detected`)
- **Missing:** Separate topics for metrics, DLQ, alerts
- **Impact:** Less organized event streams
- **Next:** Multi-topic architecture (Phase 4)

---

## ❌ Not Implemented (Planned)

### Critical Gaps (Phase 3 - Production Essentials)

1. **Monitoring Stack** ❌ - Priority 1
   - Prometheus (metrics)
   - Grafana (dashboards)
   - Loki (log aggregation)
   - **Effort:** 1 week

2. **Alert Engine** ❌ - Priority 2
   - Real-time notifications
   - Watchlist matching
   - Slack/Email/SMS/Webhooks
   - **Effort:** 2 weeks

3. **BI Dashboards** ❌ - Priority 3
   - Pre-built Grafana dashboards
   - Event visualization
   - Analytics
   - **Effort:** 1 week

### Important Gaps (Phase 4 - Enterprise Features)

4. **Elasticsearch/OpenSearch** ❌
   - Full-text search
   - Advanced analytics
   - **Effort:** 2 weeks

5. **Schema Registry** ❌
   - Event schema versioning
   - Schema validation
   - **Effort:** 1 week

6. **Advanced BI** ❌
   - Apache Superset or Metabase
   - Custom reports
   - **Effort:** 2 weeks

### Future Enhancements (Phase 5 - Scale)

7. **DeepStream Migration** ❌
   - GPU-optimized pipeline
   - 6-8x throughput increase
   - 8-12 streams per Jetson
   - **Effort:** 4-6 weeks

8. **Triton Inference Server** ❌
   - Centralized batch inference
   - **Effort:** 2-3 weeks

### MLOps (Phase 6)

9. **Model Registry (MLflow)** ❌
   - Version control
   - Experiment tracking
   - **Effort:** 2 weeks

10. **Training Pipeline (TAO Toolkit)** ❌
    - Automated retraining
    - **Effort:** 4-6 weeks

---

## 📊 Performance Metrics

### Edge Processing (Jetson Orin NX)

| Metric | Current Performance | Notes |
|--------|---------------------|-------|
| **Throughput** | 15-25 FPS | Full pipeline with OCR |
| **Streams per Device (RTSP)** | 4-6 | With GPU hardware decode + OCR |
| **Streams per Device (Video)** | 1-2 | With CPU decode + OCR |
| **Detection Latency** | 20ms | Vehicle + Plate (TensorRT) |
| **OCR Latency** | 10-30ms | Per plate (throttled) |
| **Tracking Overhead** | <1ms | ByteTrack is lightweight |
| **End-to-end Latency** | 40-90ms | Frame capture to Kafka |
| **CPU Usage** | 40-60% | With TensorRT optimization |
| **GPU Usage** | 30-50% | Shared with CUDA |
| **Events Published** | 1-10/min | Per camera |

### Backend Services (Docker)

| Service | Throughput | Latency | Resource Usage |
|---------|------------|---------|----------------|
| **Kafka Broker** | 10,000+ msg/s | 1-5ms | 512MB RAM, <10% CPU |
| **Kafka Consumer** | 100-500 events/s | <10ms | 256MB RAM, <5% CPU |
| **Storage Service** | 500-1000 inserts/s | 1-5ms | 512MB RAM |
| **Query API** | 50-100 req/s | 10-100ms | 256MB RAM |
| **TimescaleDB** | 1000+ writes/s | 5-50ms | 1-2GB RAM, 10-20% CPU |

**Total Backend:** ~2-3GB RAM, ~30% CPU

**System Capacity:** 100+ events/second sustained (thousands peak)

---

## 🗂️ File Structure (Current)

```
OVR-ALPR/
├── pilot.py                          # ✅ Main ALPR pipeline
├── requirements.txt                  # ✅ Python dependencies
├── docker-compose.yml                # ✅ Infrastructure services
│
├── config/                           # ✅ YAML configurations
│   ├── cameras.yaml
│   ├── tracking.yaml
│   └── ocr.yaml
│
├── models/                           # ✅ YOLO models
│   ├── yolo11n.pt                    # Vehicle detection
│   └── yolo11n-plate.pt              # Plate detection
│
├── services/                         # ✅ All services implemented
│   ├── camera/
│   │   ├── camera_ingestion.py       # ✅ Multi-threaded capture
│   │   └── gpu_camera_ingestion.py   # ✅ GPU decode (alternative)
│   ├── detector/
│   │   └── detector_service.py       # ✅ YOLOv11 + TensorRT
│   ├── tracker/
│   │   └── bytetrack_service.py      # ✅ Multi-object tracking
│   ├── ocr/
│   │   └── ocr_service.py            # ✅ PaddleOCR
│   ├── event_processor/
│   │   ├── event_processor_service.py# ✅ Validation + dedup
│   │   ├── kafka_publisher.py        # ✅ Event publishing (JSON)
│   │   └── avro_kafka_publisher.py   # ✅ Avro publishing
│   ├── storage/
│   │   ├── storage_service.py        # ✅ Database abstraction
│   │   ├── kafka_consumer.py         # ✅ JSON consumer
│   │   ├── avro_kafka_consumer.py    # ✅ Avro consumer
│   │   ├── consumer_entrypoint.py    # ✅ JSON/Avro switch
│   │   └── image_storage_service.py  # ✅ MinIO integration
│   └── api/
│       └── query_api.py              # ✅ REST API (FastAPI)
│
├── schemas/                          # ✅ Avro schemas
│   └── plate_event.avsc              # PlateEvent schema definition
│
├── scripts/                          # ✅ Utility scripts
│   ├── init_db.sql                   # Database initialization
│   ├── add_created_at_index.sql      # Performance optimization
│   ├── register_schemas.py           # Schema Registry setup
│   └── test_schema_registry.py       # Integration tests
│
├── output/                           # Runtime output
│   └── crops/                        # Plate crops by date
│
└── docs/                             # ✅ Documentation
    ├── ALPR_Pipeline/
    │   ├── SERVICES_OVERVIEW.md      # Complete service reference
    │   ├── ALPR_Next_Steps.md        # Roadmap & next steps
    │   ├── PIPELINE_COMPARISON.md    # Architecture comparison
    │   └── Project_Status.md         # This file
    ├── storage-layer.md
    ├── kafka-setup.md
    └── [other technical docs...]
```

---

## 🎯 Known Issues & Limitations

### Current Limitations

1. **Stream Capacity per Jetson** 🟢 (Improved with GPU Decode)
   - **RTSP streams:** 4-6 streams per Jetson Orin NX (with GPU hardware decode enabled)
   - **Video files:** 1-2 streams (CPU decode for testing/looping compatibility)
   - GPU hardware decode provides 80-90% CPU reduction for RTSP streams
   - **Further scaling:** DeepStream migration for 8-12+ streams (Phase 5)

2. **No Real-time Alerting** 🔴
   - Manual API queries required
   - No automated notifications
   - **Fix:** Alert Engine (Priority 2)

3. **Limited Observability** 🔴
   - No centralized metrics
   - Docker logs only
   - Difficult to troubleshoot production issues
   - **Fix:** Prometheus + Grafana (Priority 1)

### Known Bugs

None currently - system is stable in production testing.

### Recent Enhancements

- ✅ **2025-12-25:** **Schema Registry with Avro Serialization** - Confluent Schema Registry fully operational
  - Confluent Schema Registry 7.5.0 deployed via Docker Compose (localhost:8081)
  - PlateEvent Avro schema registered (ID: 1, Version: 1)
  - AvroKafkaPublisher integrated into pilot.py
  - AvroKafkaConsumer with automatic schema deserialization
  - BACKWARD compatibility mode for schema evolution
  - 62% message size reduction compared to JSON
  - Automatic schema validation on produce/consume
  - Consumer supports switchable JSON/Avro mode via USE_AVRO env var
- ✅ **2025-12-25:** **MinIO Object Storage Implemented** - S3-compatible image storage fully operational
  - MinIO server deployed via Docker Compose (localhost:9000)
  - Async image uploads with ThreadPoolExecutor (4 threads)
  - ImageStorageService class with retry logic and health monitoring
  - Integrated into pilot.py for automatic plate crop uploads
  - S3 URLs stored in database for external access
  - MinIO console available at localhost:9001
  - Bucket: `alpr-plate-images` with metadata tagging
- ✅ **2025-12-24:** **GPU Hardware Video Decode Complete** - NVDEC hardware decoder fully operational for RTSP streams
  - Hybrid architecture: RTSP uses GPU decode (80-90% CPU reduction), video files use CPU decode
  - Rebuilt OpenCV 4.6.0 with GStreamer 1.20.3 support (~2 hour build)
  - Codec auto-detection for H.264/H.265 streams
  - RTSP capacity increased from 1-2 to 4-6 streams per Jetson Orin NX (3x increase)
  - Test videos converted to H.264 8-bit format for compatibility
  - See `docs/Optimizations/gpu-decode-implementation-complete.md`
- ✅ **2025-12-23:** Fixed `/events/recent` ordering - now correctly orders by `created_at` instead of `captured_at`
- ✅ **2025-12-23:** Added database index on `created_at` column for optimized recent events queries

---

## 📅 Deployment Status

### Current Deployments

| Environment | Status | Components | Capacity |
|-------------|--------|------------|----------|
| **Development** | ✅ Active | All-in-one Jetson | 1-2 cameras |
| **Testing** | ✅ Active | Distributed (edge + server) | 2-4 cameras |
| **Production** | 🟡 Ready | Awaiting deployment | 1-10 cameras |

### Deployment Options

✅ **All-in-One** - Edge + backend on single Jetson
✅ **Distributed** - Edge on Jetson, backend on server
✅ **Multi-Edge** - Multiple Jetsons → shared backend
⏳ **Enterprise** - Multi-site with central aggregation (planned)

---

## 🚀 Next Priorities

See [ALPR_Next_Steps.md](ALPR_Next_Steps.md) for detailed roadmap.

### Phase 3: Production Essentials (3-4 Weeks Remaining)

**Completed:**
1. ✅ **MinIO Object Storage** - Complete

**Remaining:**
1. **Monitoring Stack** (1 week) - Priority 1
2. **Alert Engine** (2 weeks) - Priority 2
3. **Basic Dashboards** (1 week) - Priority 3

**Goal:** Transform from "working system" to "production system with full ops"

---

## 📈 Success Metrics

### Current Achievements ✅

- ✅ Complete edge-to-cloud pipeline functional
- ✅ Event persistence with time-series optimization
- ✅ REST API for event querying
- ✅ Docker-based deployment
- ✅ Per-track OCR optimization (10-30x performance gain)
- ✅ Sub-100ms edge processing latency
- ✅ Zero data loss (Kafka + TimescaleDB)

### Phase 3 Targets

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Image retention | 90 days (MinIO) | 90 days | ✅ Achieved |
| MTTR (Mean Time to Repair) | Unknown | <15 min | 🔴 Needs monitoring |
| Alert latency | N/A | <5 sec | 🔴 Needs alert engine |
| Dashboard users | 0 | 5+ | 🔴 Needs dashboards |
| Uptime | Unknown | 99.5% | 🔴 Needs monitoring |

---

## 🔗 Related Documentation

- [SERVICES_OVERVIEW.md](SERVICES_OVERVIEW.md) - Complete technical reference for all services
- [ALPR_Next_Steps.md](ALPR_Next_Steps.md) - Detailed roadmap and implementation plans
- [PIPELINE_COMPARISON.md](PIPELINE_COMPARISON.md) - Architecture comparisons
- [README.md](README.md) - Deployment guide

---

## 💡 Summary

**What's Working:** Complete ALPR pipeline from camera to database with event streaming and object storage

**What's Next:** Production monitoring, alerting, and dashboards (Phase 3 completion)

**Timeline:** 3-4 weeks to full production-grade system

**Status:** ✅ **Production-Ready for Small/Medium Deployments (1-10 cameras) with S3-compatible storage**
