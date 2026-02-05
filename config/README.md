# Configuration Files

YAML configuration files for the ALPR system. Edit these files to customize system behavior.

---

## Quick Reference

| File | Purpose | Key Settings |
|------|---------|--------------|
| `cameras.yaml` | Camera sources | RTSP URLs, video files, resolution |
| `detection.yaml` | Object detection | Model paths, confidence thresholds |
| `ocr.yaml` | License plate OCR | PaddleOCR settings, preprocessing |
| `tracking.yaml` | Vehicle tracking | ByteTrack parameters, zones |
| `validation.yaml` | Plate validation | Format rules, OCR corrections |
| `deduplication.yaml` | Event deduplication | Time windows, strategies |
| `kafka.yaml` | Message streaming | Broker settings, topics |
| `elasticsearch.yaml` | Search indexing | OpenSearch connection, indices |
| `alert_rules.yaml` | Notifications | Email, Slack, SMS, webhooks |
| `inference_optimization.yaml` | Performance | Batch settings, caching |

---

## Configuration Details

### cameras.yaml

Camera and video source configuration.

```yaml
cameras:
  - id: CAM-001
    name: "Main Gate"
    rtsp_url: "rtsp://user:pass@192.168.1.100:554/stream"
    enabled: true

video_sources:  # For testing
  - id: CAM1
    file_path: "videos/test.avi"
    loop: true
```

**Key settings:**
- `rtsp_url`: RTSP stream URL with credentials
- `enabled`: Enable/disable individual cameras
- `video_sources`: Test with local video files

---

### detection.yaml

YOLOv11 vehicle and plate detection settings.

```yaml
detection:
  vehicle:
    confidence_threshold: 0.6
    classes: [2, 3, 5, 7]  # car, motorcycle, bus, truck
  plate:
    confidence_threshold: 0.7
    custom_model: "models/plate_detector_yolo11n.pt"
```

**Key settings:**
- `confidence_threshold`: Minimum detection confidence (0.0-1.0)
- `classes`: COCO class IDs for vehicles
- `use_tensorrt`: Enable TensorRT acceleration

---

### ocr.yaml

PaddleOCR configuration for license plate reading.

```yaml
ocr:
  paddle:
    use_gpu: true
    rec_model: "en_PP-OCRv4_rec"
  postprocessing:
    min_confidence: 0.40
    whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
```

**Key settings:**
- `min_confidence`: Minimum OCR confidence to accept
- `whitelist`: Valid plate characters
- `use_tensorrt`: Enable TensorRT for OCR

---

### tracking.yaml

Multi-object tracking configuration.

```yaml
tracking:
  tracker: "bytetrack"
  bytetrack:
    track_thresh: 0.20
    track_buffer: 90
    match_thresh: 0.25
```

**Key settings:**
- `tracker`: Algorithm (bytetrack, nvdcf, deepsort)
- `track_buffer`: Frames to keep lost tracks
- `zones`: Define entry/exit lines for counting

---

### validation.yaml

License plate format validation and normalization.

```yaml
validation:
  normalization:
    uppercase: true
    ocr_corrections:
      rules:
        - from: "O"
          to: "0"
          context: "numeric"
  enabled_countries: [US, MX, CA]
```

**Key settings:**
- `ocr_corrections`: Fix common OCR errors (O→0, I→1)
- `enabled_countries`: Supported plate formats
- `min_length`/`max_length`: Valid plate length range

---

### deduplication.yaml

Event deduplication to prevent duplicate alerts.

```yaml
deduplication:
  strategies:
    by_track_id:
      enabled: true
    by_plate:
      window_seconds: 10
      camera_specific: true
```

**Key settings:**
- `window_seconds`: Time window for deduplication
- `camera_specific`: Deduplicate per camera vs globally
- `cache.backend`: redis or memory

---

### kafka.yaml

Kafka message streaming configuration.

```yaml
kafka:
  bootstrap_servers: "localhost:9092"
  topics:
    plate_events: "alpr.plates.detected"
  producer:
    compression_type: "gzip"
    acks: "all"
```

**Key settings:**
- `bootstrap_servers`: Kafka broker addresses
- `topics`: Topic names for different event types
- `acks`: Durability level (all, 1, 0)

---

### elasticsearch.yaml

OpenSearch configuration for full-text search.

> **Note:** Named `elasticsearch.yaml` for backwards compatibility but configures OpenSearch.

```yaml
opensearch:
  hosts:
    - "http://localhost:9200"
  index:
    prefix: "alpr-events"
    retention_days: 90
```

**Key settings:**
- `hosts`: OpenSearch server URLs
- `retention_days`: How long to keep indexed data
- `bulk.size`: Batch size for indexing

---

### alert_rules.yaml

Alert rules and notification channel configuration.

```yaml
notifications:
  email:
    enabled: false
    smtp_host: "smtp.gmail.com"
  slack:
    enabled: false
    webhook_url: "${SLACK_WEBHOOK_URL}"

rules:
  - id: "watchlist_plate"
    conditions:
      - field: "plate.normalized_text"
        operator: "in_list"
        value: ["ABC123", "XYZ789"]
    notify: ["email", "slack"]
```

**Key settings:**
- `notifications`: Configure email, Slack, SMS, webhooks
- `rules`: Define alert conditions and triggers
- `rate_limit`: Prevent alert spam

**Available operators:** `equals`, `contains`, `regex`, `in_list`, `greater_than`, `less_than`

---

### inference_optimization.yaml

Performance optimization settings.

```yaml
optimization:
  ocr:
    run_once_per_track: true
    min_stable_frames: 3
    cache_results: true
  resolution:
    inference_short_side: 960
```

**Key settings:**
- `run_once_per_track`: Run heavy models once per vehicle (10-30x savings)
- `inference_short_side`: Resize for faster inference
- `batch_ocr`: Batch multiple plates together

---

## Environment Variables

Some configs support environment variable substitution:

```yaml
password: "${SMTP_PASSWORD}"
webhook_url: "${SLACK_WEBHOOK_URL}"
```

Set these in your environment or `.env` file before starting services.

---

## Validation

Validate YAML syntax before applying changes:

```bash
# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('config/cameras.yaml'))"

# Validate all configs
for f in config/*.yaml; do python -c "import yaml; yaml.safe_load(open('$f'))"; done
```

---

## Related Documentation

- [Alert Engine](../docs/services/Alerts/alert-engine.md)
- [Kafka Setup](../docs/services/Kafka/kafka-setup.md)
- [OpenSearch Integration](../docs/services/Search/OpenSearch_Integration.md)
- [Model Training Guide](../docs/services/MLFlow/model-training-guide.md)
