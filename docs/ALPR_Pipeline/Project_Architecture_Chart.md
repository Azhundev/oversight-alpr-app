# OVR-ALPR System Architecture - Mermaid Chart

**Last Updated:** 2025-12-25

This document contains the Mermaid chart visualization of the complete OVR-ALPR system architecture based on the current implementation status.

---

## System Architecture Diagram

```mermaid
flowchart TB
    subgraph "Edge Processing Layer (Jetson Orin NX)"
        CAM["📹 Camera Ingestion<br/>✅ PRODUCTION<br/>GPU Hardware Decode (RTSP)<br/>CPU Decode (Video Files)<br/>4-6 RTSP streams"]
        DET["🎯 Vehicle & Plate Detection<br/>✅ PRODUCTION<br/>YOLOv11 + TensorRT FP16<br/>20ms latency"]
        TRK["🔍 Multi-Object Tracking<br/>✅ PRODUCTION<br/>ByteTrack + Kalman Filter<br/><1ms overhead"]
        OCR["📝 OCR Service<br/>✅ PRODUCTION<br/>PaddleOCR GPU<br/>10-30ms per plate"]
        EVT["⚡ Event Processing<br/>✅ PRODUCTION<br/>Validation + Dedup<br/>5-min time window"]
        PUB["📤 Kafka Publisher<br/>✅ PRODUCTION<br/>Avro Serialization<br/>62% size reduction"]
        IMG["🖼️ Image Storage Client<br/>✅ PRODUCTION<br/>Async uploads<br/>4 threads"]
    end

    subgraph "Configuration Files"
        CFG1["📄 cameras.yaml"]
        CFG2["📄 tracking.yaml"]
        CFG3["📄 ocr.yaml"]
    end

    subgraph "Infrastructure Layer (Docker)"
        subgraph "Message Streaming"
            ZK["🔧 ZooKeeper<br/>✅ PRODUCTION<br/>Kafka coordination"]
            KAFKA["📨 Kafka Broker<br/>✅ PRODUCTION<br/>10k+ msg/s<br/>7-day retention"]
            SR["📋 Schema Registry<br/>✅ PRODUCTION<br/>Confluent 7.5.0<br/>BACKWARD compat"]
            UI["🖥️ Kafka UI<br/>✅ PRODUCTION<br/>Web interface<br/>localhost:8080"]
        end

        subgraph "Storage Layer"
            CONS["📥 Kafka Consumer<br/>✅ PRODUCTION<br/>Avro deserialize<br/>100-500 events/s"]
            STORE["💾 Storage Service<br/>✅ PRODUCTION<br/>Connection pooling<br/>500-1k inserts/s"]
            TSDB["🗄️ TimescaleDB<br/>✅ PRODUCTION<br/>PostgreSQL 16<br/>Time-series optimized"]
            MINIO["📦 MinIO<br/>✅ PRODUCTION<br/>S3-compatible<br/>90-day retention"]
        end

        subgraph "API Layer"
            API["🌐 Query API<br/>✅ PRODUCTION<br/>FastAPI + OpenAPI<br/>50-100 req/s"]
        end

        subgraph "Monitoring Stack"
            PROM["📊 Prometheus<br/>✅ PRODUCTION<br/>Metrics collection<br/>30-day retention"]
            GRAF["📈 Grafana<br/>✅ PRODUCTION<br/>4 Dashboards<br/>localhost:3000"]
            LOKI["📝 Loki<br/>✅ PRODUCTION<br/>Log aggregation<br/>7-day retention"]
            PTAIL["🚚 Promtail<br/>✅ PRODUCTION<br/>Log shipping"]
            CADV["📦 cAdvisor<br/>✅ PRODUCTION<br/>Container metrics<br/>localhost:8082"]
        end
    end

    subgraph "Schema Definitions"
        SCHEMA["📐 plate_event.avsc<br/>PlateEvent Schema<br/>ID: 1, Version: 1"]
    end

    subgraph "External Clients"
        CLIENT["👤 API Clients<br/>HTTP/REST"]
        ADMIN["🔧 Admins<br/>Kafka UI / MinIO Console"]
    end

    %% Edge Processing Flow
    CAM -->|"Frames (30 FPS)"| DET
    DET -->|"Vehicle + Plate Boxes"| TRK
    TRK -->|"Tracked Objects"| OCR
    OCR -->|"Plate Text"| EVT
    EVT -->|"PlateEvent Dict"| PUB
    EVT -->|"Plate Crop"| IMG

    %% Configuration
    CFG1 -.->|"Configure"| CAM
    CFG2 -.->|"Configure"| TRK
    CFG3 -.->|"Configure"| OCR

    %% Schema Flow
    SCHEMA -.->|"Define structure"| PUB
    SCHEMA -.->|"Validate"| SR
    SR -.->|"Schema lookup"| CONS

    %% Kafka Flow
    PUB -->|"Avro binary<br/>GZIP compressed"| KAFKA
    ZK -.->|"Coordinate"| KAFKA
    SR -.->|"Validate"| KAFKA
    KAFKA -->|"Avro messages"| CONS

    %% Storage Flow
    CONS -->|"Event Dict"| STORE
    STORE -->|"SQL INSERT"| TSDB
    IMG -->|"S3 PUT<br/>async"| MINIO

    %% Query Flow
    API <-->|"SQL SELECT"| TSDB
    API <-->|"S3 GET"| MINIO
    CLIENT <-->|"HTTP/REST"| API

    %% Admin Flow
    ADMIN <-->|"Monitor"| UI
    ADMIN <-->|"Manage"| MINIO
    UI -.->|"Monitor"| KAFKA
    UI -.->|"View schemas"| SR

    %% Monitoring Flow
    PROM -.->|"Scrape"| PUB
    PROM -.->|"Scrape"| CONS
    PROM -.->|"Scrape"| API
    PROM -.->|"Scrape"| CADV
    GRAF -.->|"Query"| PROM
    GRAF -.->|"Query"| LOKI
    PTAIL -.->|"Ship logs"| LOKI
    CADV -.->|"Export metrics"| PROM
    ADMIN <-->|"View dashboards"| GRAF

    %% Styling
    classDef production fill:#90EE90,stroke:#228B22,stroke-width:2px,color:#000
    classDef config fill:#FFE4B5,stroke:#DAA520,stroke-width:2px,color:#000
    classDef schema fill:#E6E6FA,stroke:#9370DB,stroke-width:2px,color:#000
    classDef client fill:#87CEEB,stroke:#4682B4,stroke-width:2px,color:#000

    class CAM,DET,TRK,OCR,EVT,PUB,IMG,ZK,KAFKA,SR,UI,CONS,STORE,TSDB,MINIO,API,PROM,GRAF,LOKI,PTAIL,CADV production
    class CFG1,CFG2,CFG3 config
    class SCHEMA schema
    class CLIENT,ADMIN client
```

---

## Implementation Status Overview

```mermaid
pie title "Implementation Status (By Component Count)"
    "Fully Implemented (Production)" : 20
    "Partially Implemented" : 2
    "Not Implemented" : 5
```

---

## Service Layer Breakdown

```mermaid
graph LR
    subgraph "Edge Services (6)"
        E1["Camera Ingestion ✅"]
        E2["Detection ✅"]
        E3["Tracking ✅"]
        E4["OCR ✅"]
        E5["Event Processing ✅"]
        E6["Kafka Publisher ✅"]
    end

    subgraph "Backend Services (7)"
        B1["Kafka Broker ✅"]
        B2["Schema Registry ✅"]
        B3["Kafka Consumer ✅"]
        B4["Storage Service ✅"]
        B5["TimescaleDB ✅"]
        B6["Query API ✅"]
        B7["MinIO ✅"]
    end

    subgraph "Monitoring Services (5)"
        M1["Prometheus ✅"]
        M2["Grafana ✅"]
        M3["Loki ✅"]
        M4["Promtail ✅"]
        M5["cAdvisor ✅"]
    end

    subgraph "Infrastructure (3)"
        I1["Docker Compose ✅"]
        I2["Main Pipeline ✅"]
        I3["YAML Configs ✅"]
    end

    E1 --> E2 --> E3 --> E4 --> E5 --> E6
    E6 --> B1 --> B3 --> B4 --> B5
    B3 -.-> B2
    B5 <--> B6
    B7 -.-> B6
    M1 -.-> E6
    M1 -.-> B3
    M1 -.-> B6
    M1 -.-> M5
    M2 -.-> M1
    M2 -.-> M3
    M4 -.-> M3
```

---

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant Camera as 📹 Camera
    participant Detector as 🎯 Detector
    participant Tracker as 🔍 Tracker
    participant OCR as 📝 OCR
    participant EventProc as ⚡ Event Processor
    participant KafkaPub as 📤 Kafka Publisher
    participant SchemaReg as 📋 Schema Registry
    participant Kafka as 📨 Kafka
    participant Consumer as 📥 Consumer
    participant Storage as 💾 Storage
    participant DB as 🗄️ TimescaleDB
    participant MinIO as 📦 MinIO
    participant API as 🌐 API

    Camera->>Detector: Frame (1920x1080)
    Detector->>Tracker: Detections (vehicles, plates)
    Tracker->>OCR: Plate crops with track IDs
    OCR->>EventProc: Plate text + metadata
    EventProc->>KafkaPub: PlateEvent dict
    EventProc->>MinIO: Plate crop (async)

    KafkaPub->>SchemaReg: Get schema ID
    SchemaReg-->>KafkaPub: Schema (ID: 1)
    KafkaPub->>Kafka: Avro binary + schema ID

    Kafka->>Consumer: Avro message
    Consumer->>SchemaReg: Lookup schema by ID
    SchemaReg-->>Consumer: Schema definition
    Consumer->>Storage: Deserialized event dict
    Storage->>DB: SQL INSERT

    API->>DB: SQL SELECT
    DB-->>API: Event data
    API->>MinIO: S3 GET (image URL)
    MinIO-->>API: Plate image
    API-->>Camera: JSON response
```

---

## Performance Metrics Chart

```mermaid
graph TB
    subgraph "Edge Processing (Jetson Orin NX)"
        P1["Throughput: 15-25 FPS"]
        P2["RTSP Streams: 4-6"]
        P3["Video Streams: 1-2"]
        P4["Detection: 20ms"]
        P5["OCR: 10-30ms"]
        P6["Tracking: <1ms"]
        P7["End-to-end: 40-90ms"]
        P8["CPU: 40-60%"]
        P9["GPU: 30-50%"]
    end

    subgraph "Backend Services"
        B1["Kafka: 10k+ msg/s"]
        B2["Consumer: 100-500 evt/s"]
        B3["Storage: 500-1k ins/s"]
        B4["Query API: 50-100 req/s"]
        B5["TimescaleDB: 1k+ writes/s"]
        B6["Total RAM: 2-3GB"]
        B7["Total CPU: ~30%"]
    end

    style P1 fill:#90EE90
    style B1 fill:#87CEEB
```

---

## Phase Completion Status

```mermaid
gantt
    title ALPR Project Phases
    dateFormat YYYY-MM-DD

    section Phase 1: Core ALPR
    Camera Ingestion           :done, p1a, 2025-01-01, 7d
    Detection & Tracking       :done, p1b, 2025-01-08, 7d
    OCR Integration            :done, p1c, 2025-01-15, 7d
    Basic Pipeline             :done, p1d, 2025-01-22, 7d

    section Phase 2: Distributed Arch
    Kafka Setup                :done, p2a, 2025-02-01, 7d
    TimescaleDB                :done, p2b, 2025-02-08, 7d
    Storage Service            :done, p2c, 2025-02-15, 7d
    Query API                  :done, p2d, 2025-02-22, 7d

    section Phase 2+: Storage
    MinIO Integration          :done, p2e, 2025-12-20, 5d
    Schema Registry            :done, p2f, 2025-12-25, 1d

    section Phase 3: Production
    Monitoring Stack           :done, p3a, 2025-12-26, 1d
    Alert Engine               :active, p3b, 2025-12-27, 14d
    BI Dashboards              :p3c, 2026-01-10, 7d

    section Phase 4: Enterprise
    Elasticsearch              :p4a, 2026-01-23, 14d
    Advanced BI                :p4b, 2026-02-06, 14d

    section Phase 5: Scale
    DeepStream Migration       :p5a, 2026-02-20, 42d
    Triton Inference           :p5b, 2026-04-03, 21d
```

---

## Technology Stack

```mermaid
mindmap
  root((OVR-ALPR<br/>Tech Stack))
    Edge Processing
      Python 3.10
      YOLOv11
      TensorRT FP16
      PaddleOCR
      ByteTrack
      OpenCV 4.6.0
      GStreamer 1.20.3
      CUDA 11.4
    Message Streaming
      Apache Kafka 3.5
      Confluent Schema Registry 7.5
      Apache Avro
      ZooKeeper 3.8
      Kafka UI
    Storage
      TimescaleDB 2.13
      PostgreSQL 16
      MinIO (S3-compatible)
    API
      FastAPI
      Uvicorn
      Pydantic
    Infrastructure
      Docker 24.x
      Docker 24.x
      Docker Compose
      NVIDIA Jetson Orin NX
      Ubuntu 20.04
    Monitoring
      Prometheus 2.x
      Grafana 10.x
      Loki 2.x
      Promtail 2.x
      cAdvisor
```

---

## Current Limitations & Next Steps

```mermaid
graph LR
    subgraph "Current State ✅"
        C1["4-6 RTSP streams<br/>(GPU decode)"]
        C2["15-25 FPS throughput"]
        C3["Docker logs only"]
        C4["Manual API queries"]
        C5["Single Kafka topic"]
    end

    subgraph "Phase 3 Goals 🎯"
        G1["Prometheus metrics ✅"]
        G2["Grafana dashboards ✅"]
        G3["Real-time alerts 🔄"]
        G4["Watchlist matching"]
        G5["Multi-topic architecture"]
    end

    subgraph "Phase 5 Vision 🚀"
        V1["8-12 streams<br/>(DeepStream)"]
        V2["50+ FPS throughput"]
        V3["Triton Inference"]
        V4["Multi-site aggregation"]
    end

    C1 -.->|"Optimize"| G1
    C2 -.->|"Monitor"| G2
    C3 -.->|"Add"| G1
    C4 -.->|"Automate"| G3
    C5 -.->|"Expand"| G5

    G1 -.->|"Scale"| V1
    G2 -.->|"Enhance"| V2
    G3 -.->|"Upgrade"| V3
    G5 -.->|"Aggregate"| V4

    style C1 fill:#90EE90
    style G1 fill:#FFD700
    style V1 fill:#87CEEB
```

---

## System Capacity Overview

```mermaid
graph TB
    subgraph "Current Capacity (Phase 2+)"
        CAP1["Streams: 4-6 RTSP / 1-2 Video"]
        CAP2["Throughput: 15-25 FPS"]
        CAP3["Events: 100+ events/sec sustained"]
        CAP4["Backend: 10k+ msg/s Kafka"]
        CAP5["Storage: 1k+ writes/s DB"]
        CAP6["Cameras: 1-10 cameras total"]
    end

    subgraph "Resource Usage"
        RES1["Jetson: 40-60% CPU, 30-50% GPU"]
        RES2["Backend: 2-3GB RAM, ~30% CPU"]
        RES3["Total: 4-6GB RAM recommended"]
    end

    style CAP1 fill:#90EE90
    style CAP2 fill:#90EE90
    style CAP3 fill:#90EE90
    style RES1 fill:#FFE4B5
```

---

## Notes

- **Status Legend:**
  - ✅ = Fully Implemented (Production-Ready)
  - 🟡 = Partially Implemented
  - ❌ = Not Implemented (Planned)
  - 🔴 = Critical Gap
  - 🟢 = Working Well

- **Overall Completion:** 75% of original vision (100% of core features, 90% of Phase 3)
- **Current Phase:** Phase 3 (Production Essentials - Monitoring Stack Complete)
- **Next Phase:** Phase 3 Completion (Alert Engine & BI Integration)

---

## Related Documentation

- [Project_Status.md](Project_Status.md) - Detailed implementation status
- [SERVICES_OVERVIEW.md](SERVICES_OVERVIEW.md) - Complete service reference
- [ALPR_Next_Steps.md](ALPR_Next_Steps.md) - Detailed roadmap
- [PIPELINE_COMPARISON.md](PIPELINE_COMPARISON.md) - Architecture comparisons
