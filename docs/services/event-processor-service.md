# Event Processor Service

## Overview

The `EventProcessorService` is a centralized service that handles **post-OCR processing** for ALPR plate detections. It consolidates normalization, validation, deduplication, and metadata enrichment into a single service before publishing events to Kafka/MQTT.

## Architecture Decision

**Single Service vs Multiple Services**: We chose a **single consolidated service** for the following reasons:

- **Cohesive data flow**: All operations work on the same `PlateEvent` object
- **Shared state**: Deduplication cache, validation rules, and normalization patterns are in one place
- **Atomic processing**: Events are either fully valid or rejected (no partial states)
- **Simpler integration**: One service call from `pilot.py`
- **Easier testing**: Single service to mock/test
- **Gate control scenario**: Sequential pipeline with no need for separate scaling

## Features

### 1. Plate Text Normalization
- Converts to uppercase
- Removes spaces, hyphens, dots
- Strips special characters
- Example: `"ABC 123"` → `"ABC123"`

### 2. Plate Format Validation
- Validates against region-specific patterns (US-FL, US-CA, US-TX, US-NY)
- Regex-based format matching
- Example: Florida plates must be `ABC123` or `123ABC` format

### 3. Fuzzy Deduplication
- Levenshtein distance algorithm for similarity matching
- Configurable similarity threshold (default: 85%)
- Time-window based deduplication (default: 5 minutes)
- Prevents duplicate events from track fragmentation or OCR errors

### 4. Metadata Enrichment
- Adds event ID (UUID)
- Timestamps (ISO 8601)
- Camera/track identifiers
- Vehicle attributes (type, make, model, color)
- Image paths (plate, vehicle, frame crops)
- Node information (site, host)
- Custom extras (ROI, direction, quality scores)

### 5. Event Payload Generation
- Structured JSON output for Kafka/MQTT
- Conforms to standardized event schema

## Event Payload Schema

```json
{
  "event_id": "uuid",
  "captured_at": "2025-12-04T20:15:12.431Z",
  "camera_id": "west_gate_cam_03",
  "track_id": "t-8f2c3",
  "plate": {
    "text": "ABC 123",
    "normalized_text": "ABC123",
    "confidence": 0.91,
    "region": "US-FL"
  },
  "vehicle": {
    "type": "car",
    "make": "Toyota",
    "model": "Camry",
    "color": "silver"
  },
  "images": {
    "plate_url": "s3://alpr/2025/12/04/west_gate/plate_...jpg",
    "vehicle_url": "s3://alpr/2025/12/04/west_gate/veh_...jpg",
    "frame_url": "s3://alpr/2025/12/04/west_gate/frame_...jpg"
  },
  "latency_ms": 42,
  "node": {
    "site": "DC1",
    "host": "jetson-orin-02"
  },
  "extras": {
    "roi": "lane-2",
    "direction": "inbound",
    "quality_score": 0.89,
    "frame_number": 1234
  }
}
```

## Usage

### Basic Usage

```python
from services.event_processor import EventProcessorService

# Initialize processor
processor = EventProcessorService(
    site_id="DC1",
    host_id="jetson-orin-02",
    min_confidence=0.70,
    dedup_similarity_threshold=0.85,
    dedup_time_window_seconds=300,
)

# Process a detection
event = processor.process_detection(
    plate_text="ABC 123",
    plate_confidence=0.91,
    camera_id="west_gate_cam_03",
    track_id=8243,
    vehicle_type="car",
    vehicle_color="silver",
    plate_image_path="output/crops/2025-12-04/plate.jpg",
    region="US-FL",
    roi="lane-2",
    direction="inbound",
    quality_score=0.89,
)

if event:
    # Convert to JSON for Kafka/MQTT
    json_payload = event.to_json()

    # Publish to Kafka
    # kafka_producer.send("alpr.events.plates", json_payload.encode())

    # Or publish to MQTT
    # mqtt_client.publish("alpr/plates/detected", json_payload)
```

### Integration with pilot.py

Replace the current `_save_plate_read()` logic in `pilot.py` (lines 271-284) with:

```python
# Initialize processor (in __init__)
self.event_processor = EventProcessorService(
    site_id="DC1",
    host_id="jetson-orin-nx",
)

# In process_frame() - replace _save_plate_read() calls
if plate_detection.confidence >= self.ocr_min_confidence:
    event = self.event_processor.process_detection(
        plate_text=plate_detection.text,
        plate_confidence=plate_detection.confidence,
        camera_id=camera_id,
        track_id=track_id,
        vehicle_type=vehicles[vehicle_idx].vehicle_type,
        vehicle_color=vehicles[vehicle_idx].color,
        plate_image_path=str(self.crops_dir / f"{camera_id}_track{track_id}.jpg"),
        quality_score=self.track_best_plate_quality.get(track_id, 0.0),
        frame_number=self.frame_count,
    )

    if event:
        # Publish to Kafka/MQTT
        self.kafka_producer.send("alpr.events.plates", event.to_json().encode())
```

## Configuration

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `site_id` | str | "DC1" | Site/datacenter identifier |
| `host_id` | str | "jetson-orin-nx" | Host machine identifier |
| `min_confidence` | float | 0.70 | Minimum OCR confidence (0.0-1.0) |
| `dedup_similarity_threshold` | float | 0.85 | Min similarity for duplicate (0.0-1.0) |
| `dedup_time_window_seconds` | int | 300 | Deduplication time window (seconds) |

### Supported Regions

| Region | Format | Example |
|--------|--------|---------|
| US-FL | `ABC123` or `123ABC` | Florida standard |
| US-CA | `1ABC234` | California standard |
| US-TX | `ABC1234` | Texas standard |
| US-NY | `ABC1234` | New York standard |

Add more regions by updating `PLATE_FORMATS` in `event_processor_service.py`.

## Testing

Run the example tests:

```bash
python3 services/event-processor/example_usage.py
```

Expected output:
- ✅ Basic usage test passes
- ✅ Deduplication test passes
- ✅ Validation test passes
- ✅ Integration example runs successfully

## Rejection Reasons

Events can be rejected for the following reasons:

1. **Low Confidence**: OCR confidence below `min_confidence` threshold
2. **Empty Text**: Normalized plate text is empty
3. **Invalid Format**: Plate doesn't match region format pattern
4. **Duplicate**: Plate is too similar to recent detection (fuzzy match)

All rejections are logged with detailed reasons.

## Performance Considerations

- **Deduplication Cache**: Automatically cleaned up based on time window
- **Regex Validation**: Fast pattern matching (< 1ms per plate)
- **Levenshtein Distance**: O(n*m) complexity, but plate texts are short (6-8 chars)
- **Memory Usage**: Minimal - cache stores only recent plates within time window

## Future Enhancements

1. **Country Format Support**: Add international plate formats
2. **OCR Corrections**: Context-aware character corrections (0↔O, 1↔I, etc.)
3. **Confidence Boosting**: Cross-reference with vehicle attributes
4. **Persistent Cache**: Redis-backed deduplication for multi-node deployments
5. **A/B Testing**: Support multiple validation strategies

## Related Documentation

- [Kafka Integration Guide](./kafka-integration.md) (to be created)
- [MQTT Integration Guide](./mqtt-integration.md) (to be created)
- [Training Workflow](./training-workflow.md)
