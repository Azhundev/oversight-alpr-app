# OVR-ALPR System Architecture

This document provides a detailed overview of the OVR-ALPR system architecture, component interactions, and design decisions.

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Component Details](#component-details)
3. [Data Flow](#data-flow)
4. [Technology Stack](#technology-stack)
5. [Design Decisions](#design-decisions)
6. [Performance Considerations](#performance-considerations)

## High-Level Architecture

The system uses a **hybrid architecture** combining edge computing (Jetson) with containerized services (Docker).

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  JETSON DEVICE (Edge)                   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │           ALPR Pipeline (pilot.py)               │  │
│  │                                                  │  │
│  │  ┌────────────┐      ┌──────────────────┐       │  │
│  │  │  Camera    │      │    YOLOv11       │       │  │
│  │  │  Manager   │ ───→ │    Detector      │       │  │
│  │  │            │      │  - Vehicle Det   │       │  │
│  │  │ - USB Cam  │      │  - Plate Det     │       │  │
│  │  │ - IP Cam   │      │  (TensorRT/GPU)  │       │  │
│  │  └────────────┘      └─────────┬────────┘       │  │
│  │                                 │                │  │
│  │                                 ▼                │  │
│  │                      ┌──────────────────┐        │  │
│  │                      │   Paddle OCR     │        │  │
│  │                      │   Service        │        │  │
│  │                      │  (GPU Accel)     │        │  │
│  │                      └─────────┬────────┘        │  │
│  │                                │                 │  │
│  │                                ▼                 │  │
│  │                      ┌──────────────────┐        │  │
│  │                      │   ByteTrack      │        │  │
│  │                      │   Tracker        │        │  │
│  │                      │  (Multi-Object)  │        │  │
│  │                      └─────────┬────────┘        │  │
│  │                                │                 │  │
│  │                                ▼                 │  │
│  │                      ┌──────────────────┐        │  │
│  │                      │     Event        │        │  │
│  │                      │   Processor      │        │  │
│  │                      │  (Validation &   │        │  │
│  │                      │   Publishing)    │        │  │
│  │                      └─────────┬────────┘        │  │
│  └────────────────────────────────┼─────────────────┘  │
│                                   │                    │
│                                   │ Kafka Publisher    │
└───────────────────────────────────┼────────────────────┘
                                    │
                                    │ TCP/IP (Port 9092)
                                    ▼
┌─────────────────────────────────────────────────────────┐
│          DOCKER INFRASTRUCTURE (Same Device)            │
│                                                         │
│  ┌────────────────────────────────────────────────┐    │
│  │              Message Streaming Layer           │    │
│  │                                                │    │
│  │  ┌─────────────┐         ┌─────────────┐      │    │
│  │  │  ZooKeeper  │  ←────→ │   Kafka     │      │    │
│  │  │  (Coord)    │         │  (Broker)   │      │    │
│  │  └─────────────┘         └──────┬──────┘      │    │
│  │                                 │             │    │
│  │                          Topic:              │    │
│  │                     alpr.events.plates     │    │
│  └──────────────────────────────────┼───────────┘    │
│                                     │                │
│                    ┌────────────────┴─────────┐      │
│                    │                          │      │
│                    ▼                          ▼      │
│  ┌─────────────────────────────┐   ┌──────────────┐ │
│  │   Kafka Consumer Service    │   │  Kafka UI    │ │
│  │   (Python/Docker)            │   │ (Monitoring) │ │
│  │                              │   └──────────────┘ │
│  │  - Consumes plate events     │    Port: 8080     │
│  │  - Validates data            │                   │
│  │  - Batch inserts to DB       │                   │
│  │  - Error handling            │                   │
│  └──────────────┬───────────────┘                   │
│                 │                                    │
│                 │ SQL (PostgreSQL Wire Protocol)     │
│                 ▼                                    │
│  ┌──────────────────────────────────────────────┐   │
│  │          Storage Layer                       │   │
│  │                                              │   │
│  │  ┌──────────────────────────────────────┐   │   │
│  │  │        TimescaleDB                   │   │   │
│  │  │    (PostgreSQL + Time-Series)        │   │   │
│  │  │                                      │   │   │
│  │  │  Tables:                             │   │   │
│  │  │  - plate_events (hypertable)        │   │   │
│  │  │  - plate_reads                      │   │   │
│  │  │                                      │   │   │
│  │  │  Indexes:                            │   │   │
│  │  │  - detected_at (time-based)         │   │   │
│  │  │  - plate_normalized_text            │   │   │
│  │  │  - camera_id                        │   │   │
│  │  └──────────────┬───────────────────────┘   │   │
│  │                 │                            │   │
│  └─────────────────┼────────────────────────────┘   │
│                    │                                │
│                    │ SQL Queries                    │
│                    ▼                                │
│  ┌──────────────────────────────────────────────┐   │
│  │          Query API Layer                     │   │
│  │                                              │   │
│  │  ┌──────────────────────────────────────┐   │   │
│  │  │      FastAPI REST API                │   │   │
│  │  │                                      │   │   │
│  │  │  Endpoints:                          │   │   │
│  │  │  - GET /health                       │   │   │
│  │  │  - GET /stats                        │   │   │
│  │  │  - GET /events/recent                │   │   │
│  │  │  - GET /events/{id}                  │   │   │
│  │  │  - GET /events/plate/{text}          │   │   │
│  │  │  - GET /events/camera/{id}           │   │   │
│  │  │  - GET /events/search                │   │   │
│  │  │                                      │   │   │
│  │  │  Features:                           │   │   │
│  │  │  - Auto-generated OpenAPI docs       │   │   │
│  │  │  - CORS support                      │   │   │
│  │  │  - Health checks                     │   │   │
│  │  └──────────────────────────────────────┘   │   │
│  │                                              │   │
│  └──────────────────────────────────────────────┘   │
│                    Port: 8000                       │
│                                                     │
└─────────────────────────────────────────────────────┘
                         │
                         │ HTTP/REST
                         ▼
                ┌─────────────────┐
                │   Web Clients   │
                │   Dashboards    │
                │   Mobile Apps   │
                └─────────────────┘
```

## Component Details

### 1. Camera Manager

**Location**: `edge_services/camera/camera_ingestion.py`

**Responsibilities**:
- Multi-camera support (USB, IP/RTSP, video files)
- Frame buffering and synchronization
- FPS control and frame dropping
- Camera reconnection on failure

**Key Features**:
- Threaded frame capture for each camera
- Circular buffer to prevent memory leaks
- Automatic retry on connection loss
- Resolution and FPS configuration

**Output**: Raw video frames (BGR format)

### 2. YOLOv11 Detector

**Location**: `edge_services/detector/detector_service.py`

**Responsibilities**:
- Vehicle detection (cars, trucks, motorcycles)
- License plate detection
- GPU-accelerated inference (TensorRT)

**Models**:
- **Vehicle Model**: `yolo11n.pt` - Detects vehicles in frame
- **Plate Model**: `yolov11n-plate.pt` - Detects plates on vehicles

**Optimizations**:
- TensorRT engine conversion (FP16/INT8)
- Batch processing
- Non-maximum suppression (NMS)
- Confidence thresholding

**Output**: Bounding boxes with confidence scores

### 3. OCR Service

**Location**: `edge_services/ocr/ocr_service.py`

**Responsibilities**:
- License plate text recognition
- Text normalization
- Confidence scoring
- Regional validation

**Technology**: PaddleOCR
- GPU acceleration
- Multi-language support
- Pre-trained on license plate fonts

**Output**: Plate text, confidence, region

### 4. ByteTrack Tracker

**Location**: `edge_services/tracker/bytetrack_service.py`

**Responsibilities**:
- Multi-object tracking across frames
- Track ID assignment
- Track lifecycle management
- Occlusion handling

**Algorithm**: ByteTrack
- Kalman filtering for motion prediction
- Association using IoU matching
- Low-confidence detection recovery

**Output**: Track ID, trajectory, state

### 5. Event Processor

**Location**: `edge_services/event_processor/event_processor_service.py`

**Responsibilities**:
- Plate read validation (confidence, format)
- Duplicate detection per track
- Event enrichment (timestamps, metadata)
- Publishing to Kafka

**Validation Rules**:
- Minimum confidence threshold
- Plate format validation
- Regional pattern matching
- Quality score calculation

**Output**: Validated event JSON

### 6. Kafka Message Broker

**Container**: `alpr-kafka`
**Technology**: Apache Kafka (Confluent)

**Responsibilities**:
- Event streaming backbone
- Message persistence
- Pub/sub coordination
- Load distribution

**Topics**:
- `alpr.events.plates` - Main event stream

**Configuration**:
- 7-day message retention
- Gzip compression
- Single broker (can be scaled)

### 7. Kafka Consumer

**Container**: `alpr-kafka-consumer`
**Location**: `core_services/storage/kafka_consumer.py`

**Responsibilities**:
- Consume events from Kafka
- Batch insert to database
- Error handling and retry
- Offset management

**Features**:
- Automatic offset commits
- Graceful shutdown
- Stats tracking
- Reconnection on failure

### 8. TimescaleDB

**Container**: `alpr-timescaledb`
**Technology**: PostgreSQL + TimescaleDB extension

**Responsibilities**:
- Time-series data storage
- Fast time-based queries
- Data compression
- Retention policies

**Schema**:
```sql
CREATE TABLE plate_events (
    event_id UUID PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL,
    camera_id VARCHAR(100) NOT NULL,
    track_id VARCHAR(100),
    plate_text VARCHAR(20),
    plate_normalized_text VARCHAR(20),
    plate_confidence FLOAT,
    -- ... more fields
);

-- Hypertable for time-series optimization
SELECT create_hypertable('plate_events', 'detected_at');

-- Indexes
CREATE INDEX idx_detected_at ON plate_events (detected_at DESC);
CREATE INDEX idx_plate_normalized ON plate_events (plate_normalized_text);
CREATE INDEX idx_camera_id ON plate_events (camera_id);
```

### 9. Query API

**Container**: `alpr-query-api`
**Location**: `core_services/api/query_api.py`
**Technology**: FastAPI

**Responsibilities**:
- REST API for querying events
- OpenAPI documentation
- CORS support
- Health monitoring

**Endpoints**:
- `GET /` - API info
- `GET /health` - Health check
- `GET /stats` - Database statistics
- `GET /events/recent` - Recent events
- `GET /events/{id}` - Event by ID
- `GET /events/plate/{text}` - Events by plate
- `GET /events/camera/{id}` - Events by camera
- `GET /events/search` - Advanced search

## Data Flow

### Frame Processing Pipeline

```
Camera Frame (30 FPS)
    │
    ▼
Frame Skip Logic (Process every Nth frame)
    │
    ▼
Vehicle Detection (YOLOv11)
    │
    ├─► No vehicles? → Skip frame
    │
    └─► Vehicles found
         │
         ▼
     Plate Detection (YOLOv11)
         │
         ├─► No plates? → Continue tracking
         │
         └─► Plates found
              │
              ▼
          OCR Recognition (PaddleOCR)
              │
              ▼
          Track Assignment (ByteTrack)
              │
              ▼
          Event Validation
              │
              ├─► Low confidence? → Discard
              ├─► Duplicate? → Discard
              │
              └─► Valid & Unique
                   │
                   ▼
              Publish to Kafka
```

### Event Storage Pipeline

```
Kafka Topic (alpr.events.plates)
    │
    ▼
Kafka Consumer (Subscribed)
    │
    ▼
Deserialize JSON
    │
    ▼
Validate Event
    │
    ├─► Invalid? → Log error, skip
    │
    └─► Valid
         │
         ▼
     Insert to TimescaleDB
         │
         ├─► Success → Commit offset
         │
         └─► Failure → Retry, log
```

### Query Pipeline

```
HTTP Request (GET /events/recent)
    │
    ▼
FastAPI Endpoint
    │
    ▼
StorageService.get_recent_events()
    │
    ▼
SQL Query (SELECT ... ORDER BY detected_at DESC LIMIT N)
    │
    ▼
TimescaleDB (Optimized time-series query)
    │
    ▼
Result Set
    │
    ▼
JSON Serialization
    │
    ▼
HTTP Response
```

## Technology Stack

### Edge Computing (Jetson)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Deep Learning | YOLOv11 | Object detection |
| OCR | PaddleOCR | Text recognition |
| Tracking | ByteTrack | Multi-object tracking |
| Acceleration | TensorRT | GPU optimization |
| Language | Python 3.8+ | Application logic |
| Computer Vision | OpenCV | Image processing |

### Infrastructure (Docker)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Message Broker | Apache Kafka | Event streaming |
| Database | TimescaleDB | Time-series storage |
| Search Engine | OpenSearch | Full-text search & analytics |
| Object Storage | MinIO | Plate image storage |
| API Framework | FastAPI | REST API |
| Container | Docker | Service isolation |
| Orchestration | Docker Compose | Service management |
| Coordination | ZooKeeper | Kafka coordination |

### Monitoring & Observability (Docker)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Metrics | Prometheus | Metrics collection & alerting |
| Visualization | Grafana | Dashboards & visualization |
| Logging | Loki + Promtail | Log aggregation |
| Tracing | Tempo | Distributed tracing (OTLP) |
| BI Analytics | Metabase | Business intelligence |

### MLOps (Docker)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Model Registry | MLflow | Model versioning & tracking |

## Design Decisions

### Why Hybrid Architecture?

**Edge Processing** (Not Dockerized):
- ✅ Direct GPU access (CUDA, TensorRT)
- ✅ Low latency for real-time processing
- ✅ Hardware-optimized inference
- ✅ No container overhead

**Containerized Services**:
- ✅ Easy deployment and scaling
- ✅ Service isolation
- ✅ Version management
- ✅ Platform independence

### Why Kafka?

**Alternatives considered**: Direct DB writes, REST API, Message Queue (RabbitMQ)

**Kafka chosen for**:
- ✅ Decoupling producers from consumers
- ✅ Message persistence and replay
- ✅ Horizontal scalability
- ✅ Exactly-once delivery semantics
- ✅ Stream processing capabilities

### Why TimescaleDB?

**Alternatives considered**: PostgreSQL, InfluxDB, MongoDB

**TimescaleDB chosen for**:
- ✅ PostgreSQL compatibility (familiar SQL)
- ✅ Time-series optimization (fast queries)
- ✅ Automatic partitioning
- ✅ Compression
- ✅ Rich SQL features (JOINs, indexes)

### Why FastAPI?

**Alternatives considered**: Flask, Django REST, Express.js

**FastAPI chosen for**:
- ✅ Automatic OpenAPI documentation
- ✅ Type validation with Pydantic
- ✅ High performance (Starlette + Uvicorn)
- ✅ Modern async support
- ✅ Easy to learn and use

## Performance Considerations

### Throughput

**Single Jetson Orin NX 16GB**:
- **Cameras**: 2-4 simultaneous streams
- **Frame Rate**: 15-30 FPS per camera (with frame skip)
- **Detections**: 100-500 vehicles/hour
- **Plate Reads**: 50-200 plates/hour
- **Latency**: <100ms per frame (detection + OCR + tracking)

### Bottlenecks

1. **GPU Inference**: Most time spent in YOLOv11 detection
   - **Solution**: TensorRT optimization, frame skipping

2. **OCR Processing**: PaddleOCR on cropped plates
   - **Solution**: Batch processing, GPU acceleration

3. **Disk I/O**: Writing frames to disk
   - **Solution**: Disable in production, use NVMe

4. **Network**: Streaming from multiple IP cameras
   - **Solution**: Optimize RTSP settings, reduce resolution

### Optimization Strategies

**Inference Optimization**:
- TensorRT FP16 mode (2-3x speedup)
- Model quantization (INT8)
- Batch processing when possible

**Frame Processing**:
- Adaptive frame skip based on vehicle presence
- Skip frames when no vehicles detected
- Early exit if no plates found

**Database Optimization**:
- Batch inserts from Kafka consumer
- Proper indexes on query columns
- TimescaleDB compression policies
- Partitioning by time

**Network Optimization**:
- Kafka message compression (gzip)
- Efficient JSON serialization
- Connection pooling

## Scalability

### Vertical Scaling (Single Device)

- Upgrade to Jetson AGX Orin (more CUDA cores)
- Increase memory (32GB vs 16GB)
- Faster storage (NVMe SSD)

### Horizontal Scaling (Multiple Devices)

- Multiple Jetson devices per site
- Each device handles 2-4 cameras
- Central Kafka cluster
- Load-balanced Query API instances

See [README.md](README.md#scaling) for scaling guide.

## Security Architecture

### Network Security

- Docker internal network isolation
- Expose only necessary ports
- Firewall rules

### Data Security

- Database password protection
- API authentication (optional)
- HTTPS/TLS for API (production)
- Encrypted database connections

### Access Control

- User authentication for Query API
- Role-based access control
- API rate limiting

See [security.md](security.md) for detailed security guide.

## Observability Stack

The system includes comprehensive observability with the three pillars:

### Metrics (Prometheus + Grafana)
- System and container metrics via cAdvisor, Node Exporter
- Application metrics from all services
- Custom dashboards for ALPR operations
- Alerting rules for anomaly detection

### Logging (Loki + Promtail)
- Centralized log aggregation from all containers
- LogQL queries for log analysis
- Integration with Grafana for visualization
- 7-day retention policy

### Tracing (Tempo + OpenTelemetry)
- Distributed tracing across services
- OTLP protocol support (gRPC port 4317, HTTP port 4318)
- Query API instrumented with OpenTelemetry
- Trace-to-log correlation via trace_id
- Service dependency visualization

### Access URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards & Explore |
| Prometheus | http://localhost:9090 | Metrics queries |
| Tempo | http://localhost:3200 | Trace queries |
| Metabase | http://localhost:3001 | BI analytics |
| MLflow | http://localhost:5000 | Model registry |

## Future Enhancements

### Planned Features

1. **Kubernetes Support**: Deploy on K8s clusters
2. **Authentication**: JWT-based API auth
3. **Multi-Region Deployment**: Geo-distributed setup

### Completed Features
- ✅ Real-time Alerts (Alert Engine with multi-channel notifications)
- ✅ Analytics Dashboard (Grafana + Metabase)
- ✅ Distributed Tracing (Tempo + OpenTelemetry)
- ✅ Model Registry (MLflow)
- ✅ ML Model Updates (MLflow model versioning)

### Research Areas

- Federated learning for privacy-preserving model updates
- Edge AI optimization with NVIDIA Triton
- Advanced tracking with Re-ID models
- Context-aware plate validation
