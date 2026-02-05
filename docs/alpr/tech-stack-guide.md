# OVR-ALPR Technology Stack Guide

**Last Updated:** 2026-02-03

This document provides detailed explanations of each technology used in the OVR-ALPR system, including their purpose, key features, and how they integrate with the overall architecture.

---

## Table of Contents

1. [Edge Processing Technologies](#edge-processing-technologies)
2. [Message Streaming Technologies](#message-streaming-technologies)
3. [Storage Technologies](#storage-technologies)
4. [API Technologies](#api-technologies)
5. [Alerting Technologies](#alerting-technologies)
6. [Monitoring & Analytics Technologies](#monitoring--analytics-technologies)
7. [MLOps Technologies](#mlops-technologies)
8. [Infrastructure Technologies](#infrastructure-technologies)

---

## Edge Processing Technologies

### Python 3.10

**Purpose:** Primary programming language for the edge processing pipeline.

**Why Python:**
- Extensive ML/AI library ecosystem (NumPy, OpenCV, TensorRT bindings)
- Rapid prototyping and iteration capability
- Strong community support for computer vision applications
- Native support for async operations (asyncio)

**Usage in OVR-ALPR:** Runs the main `pilot.py` pipeline that orchestrates camera ingestion, detection, tracking, OCR, and event publishing.

---

### YOLOv11 (You Only Look Once)

**Purpose:** Real-time object detection for vehicles and license plates.

**Key Features:**
- Single-pass neural network architecture for fast inference
- Detects multiple object classes simultaneously
- Optimized for edge deployment with various model sizes (n, s, m, l, x)
- Native support for TensorRT export

**Usage in OVR-ALPR:** Detects vehicles and license plates in video frames with ~20ms latency using the `yolo11n-plate.pt` model optimized for plate detection.

**Configuration:** Models stored in `models/` directory, trained on custom plate datasets.

---

### TensorRT (FP16)

**Purpose:** NVIDIA's deep learning inference optimizer and runtime.

**Key Features:**
- Hardware-optimized inference kernels for NVIDIA GPUs
- FP16 (half-precision) reduces memory usage by 50% with minimal accuracy loss
- Layer fusion and kernel auto-tuning for maximum throughput
- INT8 quantization support for further optimization

**Usage in OVR-ALPR:** Accelerates YOLOv11 inference on the Jetson Orin NX, achieving 20ms detection latency through optimized `.engine` files.

**Export Command:**
```bash
yolo export model=best.pt format=engine device=0 half=True
```

---

### PaddleOCR

**Purpose:** Optical Character Recognition for reading license plate text.

**Key Features:**
- Lightweight models optimized for edge devices
- Multi-language support (tuned for license plate formats)
- GPU-accelerated inference via PaddlePaddle
- High accuracy on distorted/angled text

**Usage in OVR-ALPR:** Extracts alphanumeric text from cropped license plate images with 10-30ms processing time per plate.

**Configuration:** Settings in `config/ocr.yaml` for confidence thresholds and preprocessing options.

---

### ByteTrack

**Purpose:** Multi-object tracking algorithm for maintaining vehicle identity across frames.

**Key Features:**
- Associates detections using both high and low confidence scores
- Kalman filter for motion prediction
- Handles occlusions and re-identification gracefully
- Minimal computational overhead (<1ms per frame)

**Usage in OVR-ALPR:** Assigns persistent track IDs to vehicles, enabling deduplication and temporal event correlation.

**Configuration:** Settings in `config/tracking.yaml` for track age, IoU thresholds, and confidence bounds.

---

### OpenCV 4.6.0

**Purpose:** Computer vision library for image processing and video I/O.

**Key Features:**
- Comprehensive image manipulation functions
- Video capture and encoding support
- GPU-accelerated operations (CUDA modules)
- Drawing and annotation utilities

**Usage in OVR-ALPR:** Handles frame preprocessing, image cropping for plate regions, annotation overlays, and video file I/O.

---

### GStreamer 1.20.3

**Purpose:** Multimedia framework for video pipeline construction.

**Key Features:**
- Hardware-accelerated video decoding (NVDEC on Jetson)
- RTSP stream handling with automatic reconnection
- Efficient memory management with zero-copy pipelines
- Flexible plugin architecture

**Usage in OVR-ALPR:** Powers camera ingestion with GPU-accelerated RTSP decoding, enabling 4-6 simultaneous camera streams on the Jetson Orin NX.

---

### CUDA 11.4

**Purpose:** NVIDIA's parallel computing platform for GPU acceleration.

**Key Features:**
- Direct GPU memory management
- Parallel kernel execution
- cuDNN integration for neural networks
- Unified memory for simplified programming

**Usage in OVR-ALPR:** Underlies all GPU-accelerated operations including TensorRT inference, PaddleOCR, and GStreamer video decoding.

---

## Message Streaming Technologies

### Apache Kafka 3.5

**Purpose:** Distributed event streaming platform for real-time data pipelines.

**Key Features:**
- High throughput (10k+ messages/second)
- Durable message storage with configurable retention (7 days)
- Consumer groups for parallel processing
- Exactly-once semantics support
- Partition-based scalability

**Usage in OVR-ALPR:** Central message bus connecting edge processing to backend services. Carries plate events, alerts, and system metrics across topics:
- `plate-events` - Primary detection events
- `alerts` - Triggered alert notifications
- `plate-events-dlq` - Dead letter queue for failed messages

**Port:** 9092 (internal), 29092 (external)

---

### Confluent Schema Registry 7.5

**Purpose:** Centralized schema management for Kafka messages.

**Key Features:**
- Schema versioning and evolution
- Compatibility checking (BACKWARD, FORWARD, FULL)
- Schema ID embedding in messages
- REST API for schema operations

**Usage in OVR-ALPR:** Stores and validates Avro schemas for plate events, ensuring producer-consumer compatibility and enabling schema evolution without breaking changes.

**Port:** 8081

---

### Apache Avro

**Purpose:** Compact binary serialization format with schema support.

**Key Features:**
- Schema evolution with backward/forward compatibility
- Compact binary encoding (62% smaller than JSON)
- Self-describing with schema embedding
- Strong typing with rich data types

**Usage in OVR-ALPR:** Serializes plate events for Kafka transport, reducing network bandwidth and storage requirements while maintaining type safety.

**Schema Location:** `schemas/plate_event.avsc`

---

### ZooKeeper 3.8

**Purpose:** Distributed coordination service for Kafka cluster management.

**Key Features:**
- Leader election for Kafka brokers
- Configuration management
- Distributed synchronization
- Health monitoring

**Usage in OVR-ALPR:** Coordinates the Kafka broker, managing topic metadata and partition assignments.

**Port:** 2181

---

### Kafka UI

**Purpose:** Web-based interface for Kafka cluster monitoring and management.

**Key Features:**
- Topic browsing and message inspection
- Consumer group monitoring
- Schema Registry integration
- Real-time metrics visualization

**Usage in OVR-ALPR:** Provides administrators with a visual interface for debugging message flow, inspecting events, and monitoring consumer lag.

**Port:** 8080

---

## Storage Technologies

### TimescaleDB 2.13

**Purpose:** Time-series database built on PostgreSQL for event storage.

**Key Features:**
- Automatic time-based partitioning (hypertables)
- Continuous aggregates for fast analytics
- Native PostgreSQL compatibility (SQL, extensions)
- Compression for historical data (90%+ reduction)
- Data retention policies

**Usage in OVR-ALPR:** Primary storage for plate events with hypertables partitioned by timestamp. Enables efficient time-range queries and aggregations for analytics dashboards.

**Port:** 5432

**Key Tables:**
- `plate_events` - Hypertable for detection events
- `mlflow` schema - MLflow experiment tracking

---

### PostgreSQL 16

**Purpose:** Relational database engine underlying TimescaleDB.

**Key Features:**
- ACID compliance and data integrity
- Advanced indexing (B-tree, GiST, GIN)
- JSON/JSONB support for flexible schemas
- Connection pooling and high concurrency

**Usage in OVR-ALPR:** Provides the foundation for TimescaleDB and MLflow backend storage, handling complex queries and relational data.

---

### MinIO

**Purpose:** S3-compatible object storage for images and artifacts.

**Key Features:**
- AWS S3 API compatibility
- High-performance object storage
- Bucket lifecycle policies (90-day retention)
- Web console for management
- Versioning and encryption support

**Usage in OVR-ALPR:** Stores license plate crop images uploaded asynchronously from the edge pipeline. Also serves as artifact storage for MLflow model files.

**Ports:** 9000 (API), 9001 (Console)

**Buckets:**
- `plate-images` - Cropped plate images
- `mlflow-artifacts` - Model files and training outputs

---

### OpenSearch 2.11.0

**Purpose:** Full-text search and analytics engine (Elasticsearch fork).

**Key Features:**
- Inverted index for fast text search
- Fuzzy matching and partial plate queries
- Aggregations for analytics
- RESTful API
- Sub-100ms search latency

**Usage in OVR-ALPR:** Enables full-text search across plate events, supporting wildcard queries, fuzzy matching, and time-range filtering. Powers the search API endpoints.

**Port:** 9200

**Index:** `plate-events` with optimized mappings for plate text search.

---

## API Technologies

### FastAPI

**Purpose:** Modern Python web framework for building REST APIs.

**Key Features:**
- Automatic OpenAPI/Swagger documentation
- Async request handling (asyncio)
- Pydantic data validation
- Dependency injection
- High performance (Starlette-based)

**Usage in OVR-ALPR:** Powers the Query API service with endpoints for:
- Event retrieval by ID, time range, plate text
- Full-text search via OpenSearch
- Service health and management
- Image URL generation

**Port:** 8000

**Documentation:** http://localhost:8000/docs

---

### Uvicorn

**Purpose:** ASGI server for running FastAPI applications.

**Key Features:**
- HTTP/1.1 and HTTP/2 support
- WebSocket support
- Multiple worker processes
- Graceful shutdown handling

**Usage in OVR-ALPR:** Serves the FastAPI application with production-ready performance and reliability.

---

### Pydantic

**Purpose:** Data validation and settings management using Python type hints.

**Key Features:**
- Automatic request/response validation
- JSON Schema generation
- Settings management from environment variables
- Custom validators

**Usage in OVR-ALPR:** Validates API request parameters and response models, ensuring data integrity and generating accurate API documentation.

---

## Alerting Technologies

### Custom Alert Engine

**Purpose:** Rule-based alerting system for license plate matches.

**Key Features:**
- YAML-configured alert rules
- Multiple notification channels
- Cooldown periods to prevent alert fatigue
- Pattern matching (exact, prefix, regex)

**Usage in OVR-ALPR:** Monitors Kafka plate events and triggers notifications when plates match configured watchlists or patterns.

**Configuration:** `config/alert_rules.yaml`

**Port:** 8003 (metrics)

---

### SMTP (Email)

**Purpose:** Email notification delivery for alerts.

**Usage in OVR-ALPR:** Sends email notifications to configured recipients when alert rules trigger. Supports TLS and authentication.

---

### Slack API

**Purpose:** Slack workspace integration for alert notifications.

**Usage in OVR-ALPR:** Posts alert messages to configured Slack channels using incoming webhooks, enabling team-wide visibility of important events.

---

### Twilio

**Purpose:** SMS notification delivery for critical alerts.

**Usage in OVR-ALPR:** Sends SMS messages for high-priority alerts requiring immediate attention, such as stolen vehicle detections.

---

## Monitoring & Analytics Technologies

### Prometheus 2.x

**Purpose:** Time-series metrics collection and alerting.

**Key Features:**
- Pull-based metrics scraping
- PromQL query language
- Built-in alerting rules
- Multi-dimensional data model (labels)
- 30-day retention

**Usage in OVR-ALPR:** Collects metrics from all services including:
- Edge pipeline (FPS, detection counts, latency)
- Kafka consumers (message rates, lag)
- Container resources (CPU, memory)
- Database performance

**Port:** 9090

---

### Grafana 10.x

**Purpose:** Visualization platform for metrics, logs, and traces.

**Key Features:**
- Multiple data source support (Prometheus, Loki, Tempo)
- Customizable dashboards
- Alerting integration
- User authentication and teams
- Dashboard provisioning

**Usage in OVR-ALPR:** Provides 5 pre-configured dashboards:
- System Overview
- Edge Pipeline Performance
- Kafka Metrics
- Service Health
- Container Resources

**Port:** 3000

---

### Metabase

**Purpose:** Business intelligence and analytics platform.

**Key Features:**
- SQL-based querying with visual builder
- Automated insights and x-rays
- Scheduled reports and dashboards
- Embedded analytics capability

**Usage in OVR-ALPR:** Enables non-technical users to explore plate event data, create ad-hoc queries, and build custom reports without writing SQL.

**Port:** 3001

---

### Loki 2.x

**Purpose:** Log aggregation system designed for Grafana.

**Key Features:**
- Label-based log indexing (like Prometheus)
- LogQL query language
- Multi-tenant support
- Cost-effective storage (indexes metadata, not content)
- 7-day retention

**Usage in OVR-ALPR:** Aggregates logs from all Docker containers, enabling centralized log search and correlation with metrics in Grafana.

**Port:** 3100

---

### Tempo

**Purpose:** Distributed tracing backend for request flow visualization.

**Key Features:**
- OpenTelemetry native support
- Trace-to-logs correlation
- Cost-effective object storage
- Grafana integration

**Usage in OVR-ALPR:** Traces API requests across services, helping identify latency bottlenecks and debug distributed system issues.

**Port:** 3200 (API), 4317 (OTLP gRPC), 4318 (OTLP HTTP)

---

### Promtail 2.x

**Purpose:** Log shipping agent for Loki.

**Key Features:**
- Docker log discovery
- Label extraction from log content
- Pipeline processing
- Multi-target support

**Usage in OVR-ALPR:** Collects logs from Docker containers and ships them to Loki with appropriate labels for filtering.

---

### cAdvisor

**Purpose:** Container resource monitoring.

**Key Features:**
- Real-time resource usage metrics
- Container isolation monitoring
- Historical resource data
- Prometheus metrics export

**Usage in OVR-ALPR:** Exposes container-level CPU, memory, network, and filesystem metrics for Prometheus scraping.

**Port:** 8082

---

### Node Exporter

**Purpose:** Host-level system metrics collection.

**Key Features:**
- CPU, memory, disk, network metrics
- Filesystem statistics
- System load monitoring
- Hardware temperature (where supported)

**Usage in OVR-ALPR:** Provides visibility into the underlying host system performance beyond container metrics.

**Port:** 9100

---

### Postgres Exporter

**Purpose:** PostgreSQL/TimescaleDB metrics collection.

**Key Features:**
- Connection pool statistics
- Query performance metrics
- Replication lag monitoring
- Table and index statistics

**Usage in OVR-ALPR:** Exposes TimescaleDB performance metrics including query times, connection counts, and hypertable statistics.

**Port:** 9187

---

### Kafka Exporter

**Purpose:** Kafka broker and consumer metrics collection.

**Key Features:**
- Consumer group lag monitoring
- Topic throughput metrics
- Broker health statistics
- Partition distribution

**Usage in OVR-ALPR:** Enables monitoring of Kafka message flow, consumer lag, and broker health through Prometheus.

**Port:** 9308

---

## MLOps Technologies

### MLflow 2.9.2

**Purpose:** Machine learning lifecycle management platform.

**Key Features:**
- Experiment tracking (parameters, metrics, artifacts)
- Model registry with versioning
- Model staging (None → Staging → Production)
- REST API for model serving
- UI for experiment comparison

**Usage in OVR-ALPR:** Manages YOLO model versions, tracks training experiments, and provides a registry for promoting models through development stages.

**Port:** 5000

**Components:**
- Backend Store: TimescaleDB (`mlflow` schema)
- Artifact Store: MinIO (`mlflow-artifacts` bucket)

**Key Scripts:**
- `scripts/mlflow/register_existing_models.py` - Register current models
- `scripts/training/train_with_mlflow.py` - Train with experiment tracking

---

## Infrastructure Technologies

### Docker 24.x

**Purpose:** Container runtime for application isolation and deployment.

**Key Features:**
- Process and filesystem isolation
- Reproducible environments
- Resource limiting (CPU, memory)
- Networking and volume management
- NVIDIA GPU support (nvidia-docker)

**Usage in OVR-ALPR:** Containerizes all backend services for consistent deployment and resource management.

---

### Docker Compose

**Purpose:** Multi-container application orchestration.

**Key Features:**
- Declarative service definitions
- Dependency management
- Network isolation
- Volume management
- Environment configuration

**Usage in OVR-ALPR:** Orchestrates 31 services defined in `docker-compose.yml`, managing startup order, networking, and resource allocation.

**Command:**
```bash
docker compose up -d
```

---

### NVIDIA Jetson Orin NX

**Purpose:** Edge AI computing platform for real-time inference.

**Key Features:**
- 100 TOPS AI performance
- 8GB/16GB unified memory
- CUDA cores for parallel processing
- Hardware video encode/decode (NVENC/NVDEC)
- Low power consumption (10-25W)

**Usage in OVR-ALPR:** Runs the edge processing pipeline (`pilot.py`) with GPU-accelerated detection, tracking, and OCR. Handles 4-6 RTSP streams at 15-25 FPS.

---

### Ubuntu 20.04

**Purpose:** Linux operating system for the Jetson platform.

**Key Features:**
- Long-term support (LTS)
- NVIDIA JetPack SDK compatibility
- Docker and container support
- Extensive package ecosystem

**Usage in OVR-ALPR:** Host operating system providing the runtime environment for both edge and backend services.

---

## Technology Integration Summary

| Layer | Technologies | Purpose |
|-------|--------------|---------|
| **Edge** | Python, YOLOv11, TensorRT, PaddleOCR, ByteTrack, OpenCV, GStreamer, CUDA | Real-time video processing and plate detection |
| **Streaming** | Kafka, Schema Registry, Avro, ZooKeeper | Event transport and schema management |
| **Storage** | TimescaleDB, PostgreSQL, MinIO, OpenSearch | Structured data, objects, and search |
| **API** | FastAPI, Uvicorn, Pydantic | REST interface for data access |
| **Alerting** | Custom Engine, SMTP, Slack, Twilio | Real-time notifications |
| **Monitoring** | Prometheus, Grafana, Loki, Tempo, Metabase | Observability and analytics |
| **MLOps** | MLflow | Model versioning and experiment tracking |
| **Infrastructure** | Docker, Docker Compose, Jetson Orin NX, Ubuntu | Runtime and orchestration |

---

## Related Documentation

- [Project Architecture Charts](project-architecture-charts.md) - Visual system diagrams
- [Services Overview](services-overview.md) - Detailed service reference
- [Port Reference](port-reference.md) - Complete port allocation
- [Project Status](project-status.md) - Implementation status
