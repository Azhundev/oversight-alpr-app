# Plate Logging Use Case

**Created:** 2026-02-15
**Updated:** 2026-02-17
**Use Case:** Logging vehicle entries and exits with timestamps and metadata
**Related:** [Deployment Analysis](deployment-analysis.md) | [Gate Control](use-case-gate-control.md) | [Feature Tiers](feature-tiers.md)

---

> **Note:** Plate Logging includes ALL features from [Gate Control](use-case-gate-control.md) plus additional logging, duration tracking, and vehicle attribute features. It's not a separate product - it's an extended feature set enabled by license tier.

---

## Table of Contents

1. [Overview](#overview)
2. [Data Captured](#data-captured)
3. [Camera Configuration](#camera-configuration)
4. [Entry/Exit Workflow](#entryexit-workflow)
5. [Duration Tracking](#duration-tracking)
6. [Database Schema](#database-schema)
7. [API Endpoints](#api-endpoints)
8. [Reporting & Analytics](#reporting--analytics)
9. [Data Retention](#data-retention)
10. [Export Options](#export-options)
11. [Use Case Examples](#use-case-examples)

---

## Overview

Plate logging **extends Gate Control** with comprehensive tracking capabilities. Every Plate Logging deployment includes full gate control functionality.

### Feature Inheritance

```
┌─────────────────────────────────────────────────────────────────┐
│  PLATE LOGGING = Gate Control + Logging Extensions              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  FROM GATE CONTROL (included):                                  │
│  ✓ Plate detection + OCR                                        │
│  ✓ Whitelist/blacklist management                               │
│  ✓ Gate control (GPIO/HTTP)                                     │
│  ✓ Auto-enrollment mode                                         │
│  ✓ Basic event logging                                          │
│  ✓ Dashboard                                                    │
│                                                                  │
│  PLATE LOGGING ADDITIONS:                                       │
│  + Duration tracking (entry → exit time)                        │
│  + Tailgate detection (multi-camera)                            │
│  + Vehicle color detection                                      │
│  + Vehicle make/model (Professional+)                           │
│  + Advanced analytics & reports                                 │
│  + Email/SMS notifications                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Plate logging captures every vehicle entry and exit with detailed metadata for:
- **Audit trails** - Complete record of all vehicle movements
- **Duration tracking** - Time spent in parking/facility
- **Analytics** - Traffic patterns, peak hours, frequent visitors
- **Security** - Historical evidence if needed
- **Billing** - Time-based parking fees (optional)

### Key Capabilities

| Capability | From | Description |
|------------|------|-------------|
| **Plate detection** | Gate Control | YOLOv11 + PaddleOCR |
| **Whitelist/blacklist** | Gate Control | Access control lists |
| **Gate trigger** | Gate Control | GPIO/HTTP relay control |
| **Entry logging** | Plate Logging | Record plate, timestamp, camera |
| **Exit logging** | Plate Logging | Record departure with correlation |
| **Duration calculation** | Plate Logging | Automatic time tracking |
| **Tailgate detection** | Plate Logging | Multi-camera correlation |
| **Vehicle attributes** | Plate Logging | Color, make, model |
| **Reports** | Plate Logging | Daily, weekly, monthly summaries |

---

## Data Captured

### Per Event

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `plate_text` | string | Detected plate characters | "ABC123" |
| `plate_normalized` | string | Cleaned plate for matching | "ABC123" |
| `confidence` | float | OCR confidence (0.0-1.0) | 0.95 |
| `camera_id` | string | Source camera identifier | "entry_before_1" |
| `camera_position` | enum | before_gate, after_gate, exit_gate | "before_gate" |
| `camera_location` | string | Human-readable location | "Main Entrance" |
| `event_type` | enum | entry_request, entry_confirmed, exit | "entry_request" |
| `captured_at` | timestamp | When plate was detected | "2026-02-15T08:30:45Z" |
| `image_path` | string | Path to plate crop image | "/evidence/2026/02/15/abc123_083045.jpg" |

### Vehicle Attributes (Optional/Scalable)

| Field | Type | Tier | Example |
|-------|------|------|---------|
| `vehicle_type` | string | Basic | "car", "truck", "motorcycle" |
| `vehicle_color` | string | Basic | "white", "black", "silver" |
| `vehicle_make` | string | Premium | "Toyota", "Honda", "Ford" |
| `vehicle_model` | string | Premium | "Camry", "Civic", "F-150" |
| `vehicle_year_range` | string | Premium | "2020-2024" |
| `vehicle_image_path` | string | Premium | "/evidence/vehicles/..." |

### Computed Fields

| Field | Description | Calculation |
|-------|-------------|-------------|
| `entry_confirmed` | Vehicle actually entered | after_gate camera detected same plate |
| `duration_minutes` | Time between entry and exit | `exit_time - entry_confirmed_time` |
| `entry_event_id` | Link to corresponding entry | Matched by plate + time window |
| `is_overnight` | Stayed past midnight | `exit_date > entry_date` |
| `is_overstay` | Exceeded max duration | `duration > max_allowed` |
| `tailgate_detected` | Multiple vehicles on one open | Count plates in gate-open window |

---

## Camera Configuration

### Standard Setup (3 Cameras per Lane)

Each lane has cameras at three positions for complete tracking:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ENTRANCE LANE                                                   │
│  ═══════════════════════════════════════════════════════════    │
│                                                                  │
│  ┌─────────┐         ┌─────────┐         ┌─────────┐            │
│  │ Cam 1   │  ════>  │  GATE   │  ════>  │ Cam 2   │            │
│  │ BEFORE  │         │         │         │ AFTER   │            │
│  │ gate    │         │ ▼ ▼ ▼ ▼ │         │ gate    │            │
│  └────┬────┘         └─────────┘         └────┬────┘            │
│       │                                       │                  │
│       ▼                                       ▼                  │
│  ┌──────────────┐                    ┌──────────────┐           │
│  │ Log APPROACH │                    │ Log ENTERED  │           │
│  │ • Plate      │                    │ • Plate      │           │
│  │ • Timestamp  │                    │ • Confirmed  │           │
│  │ • Request    │                    │ • Inside     │           │
│  └──────────────┘                    └──────────────┘           │
│                                                                  │
│               ════════════════════════════                      │
│                   PARKING FACILITY                               │
│               ════════════════════════════                      │
│                                                                  │
│  EXIT LANE                                                       │
│  ═══════════════════════════════════════════════════════════    │
│                                                                  │
│                          ┌─────────┐         ┌─────────┐        │
│               ════════>  │  GATE   │  ════>  │ Cam 3   │        │
│                          │         │         │ EXIT    │        │
│                          │ ▼ ▼ ▼ ▼ │         │         │        │
│                          └─────────┘         └────┬────┘        │
│                                                   │              │
│                                                   ▼              │
│                                          ┌──────────────┐       │
│                                          │ Log EXIT     │       │
│                                          │ • Plate      │       │
│                                          │ • Duration   │       │
│                                          │ • Departed   │       │
│                                          └──────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Camera Positions Explained

| Position | Camera | Purpose | Data Captured |
|----------|--------|---------|---------------|
| **Before Gate** | Entry Cam 1 | Capture approaching vehicle | Plate, timestamp, gate request |
| **After Gate** | Entry Cam 2 | Confirm vehicle entered | Plate, entry confirmed, inside count |
| **Exit Gate** | Exit Cam | Capture departing vehicle | Plate, exit time, duration |

### Why Multiple Entry Cameras?

| Benefit | Description |
|---------|-------------|
| **Confirmation** | Verify vehicle actually entered (didn't turn around) |
| **Accuracy** | Two reads improve OCR confidence |
| **Tailgating detection** | Detect if multiple cars entered on one gate open |
| **Billing accuracy** | Only charge for confirmed entries |

### Camera Configuration File

```yaml
# config/cameras.yaml
cameras:
  # Entrance lane - before gate
  - id: entry_before_1
    name: "Main Entrance - Approach"
    rtsp_url: "rtsp://192.168.1.10:554/stream1"
    event_type: entry_request
    position: before_gate
    location: "Front Gate"
    gate_id: gate_1

  # Entrance lane - after gate
  - id: entry_after_1
    name: "Main Entrance - Inside"
    rtsp_url: "rtsp://192.168.1.11:554/stream1"
    event_type: entry_confirmed
    position: after_gate
    location: "Front Gate"
    gate_id: gate_1

  # Exit lane
  - id: exit_cam_1
    name: "Main Exit"
    rtsp_url: "rtsp://192.168.1.12:554/stream1"
    event_type: exit
    position: exit_gate
    location: "Front Gate"

# For facilities with multiple lanes
  - id: entry_before_2
    name: "Side Entrance - Approach"
    rtsp_url: "rtsp://192.168.1.20:554/stream1"
    event_type: entry_request
    position: before_gate
    location: "Side Gate"
    gate_id: gate_2
```

### Scaling: Vehicle Attribute Detection

With additional cameras or enhanced models, capture more vehicle details:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ENHANCED VEHICLE DETECTION                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STANDARD CAMERAS (Plate-focused)                               │
│  ┌──────────────┐                                               │
│  │ • License    │  → ABC123                                     │
│  │   Plate      │  → Confidence: 0.95                           │
│  └──────────────┘                                               │
│                                                                  │
│  ENHANCED CAMERAS (Wide-angle + Plate)                          │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ Wide-angle   │  │ Plate        │                             │
│  │ • Vehicle    │  │ • License    │                             │
│  │ • Color      │  │   Plate      │                             │
│  │ • Brand/Make │  │              │                             │
│  │ • Model      │  │              │                             │
│  └──────────────┘  └──────────────┘                             │
│        │                  │                                      │
│        ▼                  ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Combined Record:                                         │    │
│  │ • Plate: ABC123                                         │    │
│  │ • Brand: Toyota                                         │    │
│  │ • Model: Camry                                          │    │
│  │ • Color: White                                          │    │
│  │ • Year: 2020-2024 (estimated)                           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Vehicle Attribute Models

| Attribute | Model | Accuracy | Use Case |
|-----------|-------|----------|----------|
| **Color** | YOLOv11 + classifier | ~90% | Search, identification |
| **Brand/Make** | Vehicle make model | ~85% | Premium logging |
| **Model** | Vehicle make model | ~75% | Fleet tracking |
| **Vehicle Type** | YOLOv11 classes | ~95% | Truck/car/motorcycle |

### Enhanced Configuration

```yaml
# config/cameras.yaml (enhanced)
cameras:
  - id: entry_before_1
    name: "Main Entrance - Approach"
    rtsp_url: "rtsp://192.168.1.10:554/stream1"
    event_type: entry_request
    position: before_gate
    detection:
      plate: true
      vehicle_color: true
      vehicle_make: false  # Requires additional model
      vehicle_model: false

  - id: entry_wide_1
    name: "Main Entrance - Wide Angle"
    rtsp_url: "rtsp://192.168.1.13:554/stream1"
    event_type: vehicle_attributes
    position: before_gate
    detection:
      plate: false  # Other camera handles plate
      vehicle_color: true
      vehicle_make: true
      vehicle_model: true

# Feature flags for detection
detection_features:
  plate_ocr: true
  vehicle_color: true      # Basic tier
  vehicle_make_model: false # Premium tier
  vehicle_tracking: true
```

### Hardware Scaling for Attributes

| Setup | Cameras | Detects | Hardware |
|-------|---------|---------|----------|
| **Basic** | 3 (before/after/exit) | Plate only | Orin Nano 8GB |
| **Standard** | 3 | Plate + Color | Orin Nano 8GB |
| **Enhanced** | 4-5 | Plate + Color + Type | Orin NX 8GB |
| **Premium** | 5-6 | All attributes | Orin NX 16GB |

---

## Entry/Exit Workflow

### Complete Entry Flow (Before + After Gate)

```
┌─────────────────────────────────────────────────────────────────┐
│                     ENTRY WORKFLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STEP 1: BEFORE GATE (Approach)                                 │
│  ════════════════════════════════                               │
│                                                                  │
│  1. Camera BEFORE gate captures approaching vehicle             │
│     │                                                            │
│     ▼                                                            │
│  2. YOLO detects plate → OCR extracts "ABC123"                  │
│     │                                                            │
│     ▼                                                            │
│  3. Create ENTRY_REQUEST record:                                │
│     ┌─────────────────────────────────────────────┐             │
│     │ {                                           │             │
│     │   "plate_text": "ABC123",                  │             │
│     │   "event_type": "entry_request",           │             │
│     │   "camera_position": "before_gate",        │             │
│     │   "captured_at": "2026-02-15T08:30:45Z",   │             │
│     │   "vehicle_color": "white",                │             │
│     │   "confidence": 0.95                       │             │
│     │ }                                           │             │
│     └─────────────────────────────────────────────┘             │
│     │                                                            │
│     ▼                                                            │
│  4. Gate opens (if authorized) or logs denial                   │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  STEP 2: AFTER GATE (Confirmation)                              │
│  ═════════════════════════════════                              │
│                                                                  │
│  5. Camera AFTER gate captures vehicle inside                   │
│     │                                                            │
│     ▼                                                            │
│  6. Detect plate → Match to recent entry_request                │
│     ┌─────────────────────────────────────────────┐             │
│     │ SELECT * FROM plate_reads                   │             │
│     │ WHERE plate_normalized = 'ABC123'           │             │
│     │   AND event_type = 'entry_request'          │             │
│     │   AND captured_at > NOW() - INTERVAL '5min' │             │
│     │   AND NOT confirmed;                        │             │
│     └─────────────────────────────────────────────┘             │
│     │                                                            │
│     ▼                                                            │
│  7. Create ENTRY_CONFIRMED record + update request:             │
│     ┌─────────────────────────────────────────────┐             │
│     │ {                                           │             │
│     │   "plate_text": "ABC123",                  │             │
│     │   "event_type": "entry_confirmed",         │             │
│     │   "camera_position": "after_gate",         │             │
│     │   "entry_request_id": 12345,               │             │
│     │   "captured_at": "2026-02-15T08:30:52Z"    │             │
│     │ }                                           │             │
│     └─────────────────────────────────────────────┘             │
│     │                                                            │
│     ▼                                                            │
│  8. Vehicle now counted as INSIDE facility                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Tailgate Detection

```
┌─────────────────────────────────────────────────────────────────┐
│                     TAILGATE DETECTION                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Gate opens for ABC123 at 08:30:45                              │
│                                                                  │
│  Camera AFTER gate detects:                                     │
│    08:30:52 → ABC123 (expected) ✓                               │
│    08:30:55 → XYZ789 (unexpected!) ⚠️                           │
│                                                                  │
│  Result:                                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ ALERT: Tailgate detected!                               │    │
│  │ • Authorized: ABC123                                    │    │
│  │ • Unauthorized: XYZ789                                  │    │
│  │ • Gate open window: 08:30:45 - 08:30:58                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Exit Event (with Duration Calculation)

```
┌─────────────────────────────────────────────────────────────────┐
│                     EXIT WORKFLOW                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Exit camera captures departing vehicle                      │
│     │                                                            │
│     ▼                                                            │
│  2. Detect plate → "ABC123"                                     │
│     │                                                            │
│     ▼                                                            │
│  3. Find matching CONFIRMED ENTRY:                              │
│     ┌─────────────────────────────────────────────┐             │
│     │ SELECT * FROM plate_reads                   │             │
│     │ WHERE plate_normalized = 'ABC123'           │             │
│     │   AND event_type = 'entry_confirmed'        │             │
│     │   AND captured_at > NOW() - INTERVAL '7d'   │             │
│     │   AND exit_event_id IS NULL                 │             │
│     │ ORDER BY captured_at DESC                   │             │
│     │ LIMIT 1;                                    │             │
│     └─────────────────────────────────────────────┘             │
│     │                                                            │
│     ▼                                                            │
│  4. Calculate duration from CONFIRMED entry:                    │
│     entry_confirmed = 2026-02-15T08:30:52Z                      │
│     exit_time       = 2026-02-15T12:45:30Z                      │
│     duration        = 4 hours 14 minutes 38 seconds             │
│     │                                                            │
│     ▼                                                            │
│  5. Create EXIT record + link to entry:                         │
│     ┌─────────────────────────────────────────────┐             │
│     │ {                                           │             │
│     │   "plate_text": "ABC123",                  │             │
│     │   "event_type": "exit",                    │             │
│     │   "camera_position": "exit_gate",          │             │
│     │   "entry_confirmed_id": 12346,             │             │
│     │   "duration_minutes": 255,                 │             │
│     │   "captured_at": "2026-02-15T12:45:30Z"    │             │
│     │ }                                           │             │
│     └─────────────────────────────────────────────┘             │
│     │                                                            │
│     ▼                                                            │
│  6. Vehicle now counted as OUTSIDE (departed)                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Duration Tracking

### Matching Logic

```python
def find_entry_for_exit(plate: str, exit_time: datetime) -> Optional[PlateRead]:
    """
    Find the most recent unmatched entry for this plate.
    """
    # Look back window (default 24 hours)
    lookback = timedelta(hours=24)

    entry = db.query(PlateRead).filter(
        PlateRead.plate_normalized == normalize(plate),
        PlateRead.event_type == 'entry',
        PlateRead.captured_at > exit_time - lookback,
        PlateRead.exit_event_id.is_(None)  # Not yet matched
    ).order_by(
        PlateRead.captured_at.desc()
    ).first()

    return entry
```

### Handling Edge Cases

| Scenario | Detection | Handling |
|----------|-----------|----------|
| **No after-gate confirmation** | Entry request but no confirmation within 5min | Mark as "turned away" or gate malfunction |
| **After-gate without request** | Confirmation without prior request | Log as "manual entry" (walked in?) |
| **No matching entry for exit** | Exit without entry | Log as "orphan exit", create synthetic entry |
| **Multiple entries** | Same plate, no exits | Match to most recent confirmed entry |
| **Overnight stay** | Exit date > entry date | Calculate correctly, flag as overnight |
| **Very long stay** | Duration > 24h | Alert for potential issue, check camera |
| **Duplicate reads** | Same plate within 30s | Deduplicate using ByteTrack |
| **Tailgate detected** | Multiple plates after single gate open | Alert, log all plates |

### Duration Categories

```yaml
# config/duration_rules.yaml
duration_categories:
  short:
    max_minutes: 30
    label: "Quick visit"
  standard:
    max_minutes: 480  # 8 hours
    label: "Normal visit"
  extended:
    max_minutes: 1440  # 24 hours
    label: "Extended stay"
  overnight:
    label: "Overnight"
  overstay:
    threshold_hours: 72
    alert: true
    label: "Potential abandoned vehicle"
```

---

## Database Schema

### Main Tables

```sql
-- All plate reads (entries and exits)
CREATE TABLE plate_reads (
    id SERIAL PRIMARY KEY,

    -- Plate information
    plate_text VARCHAR(15) NOT NULL,
    plate_normalized VARCHAR(15) NOT NULL,
    confidence FLOAT NOT NULL,

    -- Event type and timing
    event_type VARCHAR(20) NOT NULL CHECK (event_type IN (
        'entry_request',    -- Before gate camera
        'entry_confirmed',  -- After gate camera
        'exit'              -- Exit gate camera
    )),
    captured_at TIMESTAMP DEFAULT NOW(),

    -- Camera information
    camera_id VARCHAR(50) NOT NULL,
    camera_position VARCHAR(20) CHECK (camera_position IN (
        'before_gate', 'after_gate', 'exit_gate'
    )),
    camera_location VARCHAR(100),
    gate_id VARCHAR(20),

    -- Linking events
    entry_request_id INTEGER REFERENCES plate_reads(id),   -- For entry_confirmed
    entry_confirmed_id INTEGER REFERENCES plate_reads(id), -- For exit
    duration_minutes INTEGER,  -- Calculated on exit

    -- Evidence
    image_path TEXT,
    vehicle_image_path TEXT,  -- Full vehicle image (optional)

    -- Vehicle attributes (Basic tier)
    vehicle_type VARCHAR(20),   -- car, truck, motorcycle, van
    vehicle_color VARCHAR(30),  -- white, black, silver, red, etc.

    -- Vehicle attributes (Premium tier)
    vehicle_make VARCHAR(30),   -- Toyota, Honda, Ford, etc.
    vehicle_model VARCHAR(50),  -- Camry, Civic, F-150, etc.
    vehicle_year_range VARCHAR(20), -- 2020-2024

    -- Processing metadata
    confirmed BOOLEAN DEFAULT FALSE,  -- Entry confirmed by after_gate camera
    track_id INTEGER,  -- ByteTrack ID for deduplication
    tailgate_detected BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX idx_plate_reads_normalized ON plate_reads(plate_normalized);
CREATE INDEX idx_plate_reads_time ON plate_reads(captured_at DESC);
CREATE INDEX idx_plate_reads_camera ON plate_reads(camera_id, captured_at DESC);
CREATE INDEX idx_plate_reads_event ON plate_reads(event_type, captured_at DESC);
CREATE INDEX idx_plate_reads_gate ON plate_reads(gate_id, captured_at DESC);

-- Unconfirmed entries (waiting for after_gate camera)
CREATE INDEX idx_plate_reads_pending ON plate_reads(plate_normalized)
    WHERE event_type = 'entry_request' AND NOT confirmed;

-- Confirmed entries without exit (vehicles inside)
CREATE INDEX idx_plate_reads_inside ON plate_reads(plate_normalized)
    WHERE event_type = 'entry_confirmed' AND entry_confirmed_id IS NULL;

-- Vehicle attribute search
CREATE INDEX idx_plate_reads_vehicle ON plate_reads(vehicle_make, vehicle_color)
    WHERE vehicle_make IS NOT NULL;
```

### Aggregation Views

```sql
-- Daily summary
CREATE VIEW daily_summary AS
SELECT
    DATE(captured_at) as date,
    COUNT(*) FILTER (WHERE event_type = 'entry_confirmed') as total_entries,
    COUNT(*) FILTER (WHERE event_type = 'exit') as total_exits,
    COUNT(*) FILTER (WHERE tailgate_detected) as tailgate_incidents,
    COUNT(DISTINCT plate_normalized) as unique_vehicles,
    AVG(duration_minutes) FILTER (WHERE duration_minutes IS NOT NULL) as avg_duration_min,
    MAX(duration_minutes) FILTER (WHERE duration_minutes IS NOT NULL) as max_duration_min
FROM plate_reads
GROUP BY DATE(captured_at)
ORDER BY date DESC;

-- Hourly traffic
CREATE VIEW hourly_traffic AS
SELECT
    DATE(captured_at) as date,
    EXTRACT(HOUR FROM captured_at) as hour,
    COUNT(*) FILTER (WHERE event_type = 'entry_confirmed') as entries,
    COUNT(*) FILTER (WHERE event_type = 'exit') as exits
FROM plate_reads
GROUP BY DATE(captured_at), EXTRACT(HOUR FROM captured_at)
ORDER BY date DESC, hour;

-- Currently parked vehicles (confirmed entries without exit)
CREATE VIEW vehicles_inside AS
SELECT
    pr.plate_normalized as plate,
    pr.captured_at as entry_time,
    NOW() - pr.captured_at as time_inside,
    pr.camera_location as entry_point,
    pr.vehicle_color,
    pr.vehicle_make,
    pr.vehicle_model
FROM plate_reads pr
WHERE pr.event_type = 'entry_confirmed'
  AND NOT EXISTS (
    SELECT 1 FROM plate_reads exit_pr
    WHERE exit_pr.entry_confirmed_id = pr.id
  )
  AND pr.captured_at > NOW() - INTERVAL '7 days'
ORDER BY pr.captured_at;

-- Pending entries (approach detected, not yet confirmed inside)
CREATE VIEW pending_entries AS
SELECT
    pr.plate_normalized as plate,
    pr.captured_at as approach_time,
    NOW() - pr.captured_at as waiting_time,
    pr.gate_id
FROM plate_reads pr
WHERE pr.event_type = 'entry_request'
  AND NOT pr.confirmed
  AND pr.captured_at > NOW() - INTERVAL '10 minutes'
ORDER BY pr.captured_at;

-- Frequent visitors with vehicle info
CREATE VIEW frequent_visitors AS
SELECT
    plate_normalized as plate,
    COUNT(*) as visit_count,
    MIN(captured_at) as first_visit,
    MAX(captured_at) as last_visit,
    AVG(duration_minutes) as avg_duration_min,
    MODE() WITHIN GROUP (ORDER BY vehicle_color) as usual_color,
    MODE() WITHIN GROUP (ORDER BY vehicle_make) as usual_make
FROM plate_reads
WHERE event_type = 'entry_confirmed'
  AND captured_at > NOW() - INTERVAL '30 days'
GROUP BY plate_normalized
HAVING COUNT(*) >= 3
ORDER BY visit_count DESC;

-- Vehicle color distribution
CREATE VIEW vehicle_colors AS
SELECT
    vehicle_color,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM plate_reads
WHERE vehicle_color IS NOT NULL
  AND captured_at > NOW() - INTERVAL '30 days'
GROUP BY vehicle_color
ORDER BY count DESC;

-- Vehicle make distribution (Premium tier)
CREATE VIEW vehicle_makes AS
SELECT
    vehicle_make,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM plate_reads
WHERE vehicle_make IS NOT NULL
  AND captured_at > NOW() - INTERVAL '30 days'
GROUP BY vehicle_make
ORDER BY count DESC;
```

---

## API Endpoints

### Event Retrieval

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/events` | List all events (paginated) |
| `GET` | `/api/events/{id}` | Get specific event by ID |
| `GET` | `/api/events/plate/{plate}` | Get all events for a plate |
| `GET` | `/api/events/today` | Get today's events |

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | datetime | Filter events after this time |
| `end_date` | datetime | Filter events before this time |
| `event_type` | string | Filter by "entry_request", "entry_confirmed", "exit" |
| `camera_id` | string | Filter by camera |
| `camera_position` | string | Filter by "before_gate", "after_gate", "exit_gate" |
| `gate_id` | string | Filter by gate |
| `limit` | int | Max results (default 100) |
| `offset` | int | Pagination offset |

**Example Request:**
```bash
curl "http://localhost:8000/api/events?start_date=2026-02-15&event_type=entry_confirmed&limit=50"
```

**Example Response:**
```json
{
  "events": [
    {
      "id": 12346,
      "plate_text": "ABC123",
      "event_type": "entry_confirmed",
      "camera_position": "after_gate",
      "captured_at": "2026-02-15T08:30:52Z",
      "camera_id": "entry_after_1",
      "camera_location": "Main Entrance",
      "confidence": 0.95,
      "image_url": "/api/images/12346.jpg",
      "entry_request_id": 12345,
      "vehicle_color": "white",
      "vehicle_make": "Toyota",
      "vehicle_model": "Camry"
    }
  ],
  "total": 127,
  "limit": 50,
  "offset": 0
}
```

### Duration Queries

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/duration/plate/{plate}` | Get visit duration history |
| `GET` | `/api/duration/average` | Average duration by time period |
| `GET` | `/api/vehicles/inside` | Currently parked vehicles |
| `GET` | `/api/vehicles/pending` | Vehicles at gate (not yet confirmed inside) |

**Example - Currently Inside:**
```bash
curl "http://localhost:8000/api/vehicles/inside"
```

**Response:**
```json
{
  "count": 45,
  "vehicles": [
    {
      "plate": "ABC123",
      "entry_time": "2026-02-15T08:30:52Z",
      "time_inside_minutes": 255,
      "entry_camera": "Main Entrance",
      "vehicle_color": "white",
      "vehicle_make": "Toyota",
      "vehicle_model": "Camry"
    },
    {
      "plate": "XYZ789",
      "entry_time": "2026-02-15T09:15:00Z",
      "time_inside_minutes": 210,
      "entry_camera": "Side Gate",
      "vehicle_color": "black",
      "vehicle_make": null,
      "vehicle_model": null
    }
  ]
}
```

### Vehicle Attribute Search (Premium)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/vehicles/search` | Search by vehicle attributes |
| `GET` | `/api/vehicles/colors` | Color distribution stats |
| `GET` | `/api/vehicles/makes` | Make distribution stats |

**Search by Attributes:**
```bash
curl "http://localhost:8000/api/vehicles/search?color=white&make=Toyota"
```

**Response:**
```json
{
  "count": 12,
  "vehicles": [
    {
      "plate": "ABC123",
      "vehicle_color": "white",
      "vehicle_make": "Toyota",
      "vehicle_model": "Camry",
      "last_seen": "2026-02-15T08:30:52Z",
      "visit_count": 47
    }
  ]
}
```

### Plate Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/search?q={query}` | Search plates (partial match) |

**Example:**
```bash
curl "http://localhost:8000/api/search?q=ABC"
```

### Tailgate Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/alerts/tailgate` | Recent tailgate incidents |
| `GET` | `/api/alerts/tailgate/today` | Today's tailgate incidents |

**Response:**
```json
{
  "incidents": [
    {
      "id": 456,
      "gate_id": "gate_1",
      "authorized_plate": "ABC123",
      "unauthorized_plate": "XYZ789",
      "gate_opened_at": "2026-02-15T08:30:45Z",
      "tailgate_detected_at": "2026-02-15T08:30:55Z"
    }
  ]
}
```

---

## Reporting & Analytics

### Pre-built Reports

| Report | Description | Endpoint | Tier |
|--------|-------------|----------|------|
| **Daily Summary** | Entries, exits, unique vehicles | `/api/reports/daily` | Basic |
| **Hourly Traffic** | Traffic by hour of day | `/api/reports/hourly` | Basic |
| **Peak Hours** | Busiest entry/exit times | `/api/reports/peak-hours` | Basic |
| **Duration Distribution** | How long vehicles stay | `/api/reports/duration` | Basic |
| **Frequent Visitors** | Vehicles with 3+ visits | `/api/reports/frequent` | Basic |
| **Overstays** | Vehicles exceeding max duration | `/api/reports/overstays` | Basic |
| **Tailgate Incidents** | Unauthorized entries | `/api/reports/tailgate` | Standard |
| **Vehicle Colors** | Color distribution | `/api/reports/colors` | Standard |
| **Vehicle Makes** | Make/brand distribution | `/api/reports/makes` | Premium |
| **Fleet Analysis** | Most common vehicle types | `/api/reports/fleet` | Premium |

### Dashboard Visualizations

```
┌─────────────────────────────────────────────────────────────────┐
│  PLATE LOGGING DASHBOARD                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  TODAY'S OVERVIEW                                           ││
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐││
│  │  │   127   │ │   89    │ │   45    │ │  2h15m  │ │    2    │││
│  │  │ Entries │ │ Exits   │ │ Inside  │ │ AvgStay │ │Tailgate │││
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  HOURLY TRAFFIC (Today)                                     ││
│  │                                                              ││
│  │  Entries █████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░           ││
│  │  Exits   ░░░░░░░░░████████████░░░░░░░░░░░░░░░░░░░           ││
│  │          6am      12pm      6pm      12am                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌────────────────────────────┐  ┌─────────────────────────────┐│
│  │  RECENT EVENTS             │  │  VEHICLES INSIDE (45)       ││
│  │                            │  │                             ││
│  │  12:45 ABC123 ← EXIT 4h14m │  │  ABC123 White Toyota  3h15m ││
│  │  12:30 XYZ789 → IN ✓       │  │  XYZ789 Black Honda   2h45m ││
│  │  12:28 DEF456 ← EXIT 2h02m │  │  DEF456 Silver Ford   1h30m ││
│  │  12:15 GHI321 → IN ✓       │  │  GHI321 Red  Unknown  0h45m ││
│  │  12:10 JKL987 ⚠ TAILGATE   │  │                             ││
│  └────────────────────────────┘  └─────────────────────────────┘│
│                                                                  │
│  ┌────────────────────────────┐  ┌─────────────────────────────┐│
│  │  VEHICLE COLORS            │  │  VEHICLE MAKES (Premium)    ││
│  │                            │  │                             ││
│  │  White  ██████████░ 35%    │  │  Toyota ████████░░ 28%      ││
│  │  Black  ████████░░░ 25%    │  │  Honda  ██████░░░░ 22%      ││
│  │  Silver ██████░░░░░ 18%    │  │  Ford   █████░░░░░ 18%      ││
│  │  Red    ███░░░░░░░░ 10%    │  │  Other  ██████░░░░ 32%      ││
│  │  Other  ████░░░░░░░ 12%    │  │                             ││
│  └────────────────────────────┘  └─────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Metrics Tracked

| Metric | Description | Use | Tier |
|--------|-------------|-----|------|
| `entries_per_hour` | Vehicles entering by hour | Staffing decisions | Basic |
| `exits_per_hour` | Vehicles leaving by hour | Peak planning | Basic |
| `avg_duration` | Average time spent | Capacity planning | Basic |
| `occupancy` | Current vehicles inside | Real-time monitoring | Basic |
| `unique_daily` | Unique plates per day | Traffic trends | Basic |
| `tailgate_count` | Unauthorized entries | Security monitoring | Standard |
| `confirmation_rate` | % entries confirmed by after-gate cam | System health | Standard |
| `color_distribution` | Vehicle colors breakdown | Demographics | Standard |
| `make_distribution` | Vehicle makes breakdown | Demographics | Premium |
| `repeat_visitors` | % returning within 30 days | Customer loyalty | Premium |

---

## Data Retention

### Retention Policies

```yaml
# config/retention.yaml
retention:
  # Event records
  plate_reads:
    hot_storage: 90 days    # Fast access, full details
    warm_storage: 1 year    # Compressed, queryable
    archive: 7 years        # Cold storage, legal compliance

  # Plate crop images
  images:
    retain_days: 30         # Delete after 30 days
    keep_flagged: true      # Keep images for flagged events

  # Aggregated data
  summaries:
    daily: forever          # Keep daily summaries
    hourly: 1 year          # Keep hourly data for 1 year
```

### Automatic Cleanup

```sql
-- Scheduled job (run daily)
DELETE FROM plate_reads
WHERE captured_at < NOW() - INTERVAL '90 days'
  AND NOT flagged;

-- Archive to cold storage before delete
INSERT INTO plate_reads_archive
SELECT * FROM plate_reads
WHERE captured_at < NOW() - INTERVAL '90 days'
  AND captured_at > NOW() - INTERVAL '91 days';
```

---

## Export Options

### CSV Export

```bash
curl "http://localhost:8000/api/export/csv?start=2026-02-01&end=2026-02-15" \
  -o events_feb.csv
```

**Output format:**
```csv
id,plate_text,event_type,captured_at,camera_id,duration_minutes
12345,ABC123,entry,2026-02-15T08:30:45Z,entry_cam_1,
12346,ABC123,exit,2026-02-15T12:45:30Z,exit_cam_1,255
```

### JSON Export

```bash
curl "http://localhost:8000/api/export/json?start=2026-02-01&end=2026-02-15" \
  -o events_feb.json
```

### Scheduled Reports

```yaml
# config/scheduled_reports.yaml
reports:
  - name: "Daily Summary"
    schedule: "0 6 * * *"  # 6 AM daily
    type: daily_summary
    format: pdf
    recipients:
      - admin@property.com

  - name: "Weekly Traffic"
    schedule: "0 8 * * 1"  # Monday 8 AM
    type: weekly_traffic
    format: xlsx
    recipients:
      - management@property.com
```

---

## Use Case Examples

### Parking Lot Management

Track vehicles in a paid or private parking lot:
- Log all entries (confirmed by after-gate camera)
- Calculate parking duration for billing
- Detect tailgating (unauthorized entries)
- Alert on vehicles exceeding max stay
- Generate occupancy reports

### Employee Parking

Monitor employee parking area:
- Cross-reference with employee database
- Track attendance patterns (entry/exit times)
- Identify unauthorized vehicles
- Detect tailgating incidents
- Generate compliance reports

### Gated Community

Log resident and visitor traffic:
- Distinguish residents (whitelist) from visitors
- Track visitor frequency and duration
- Detect tailgating behind authorized residents
- Generate activity reports for HOA
- Evidence for disputes (with vehicle images)

### Commercial Property

Track tenant and customer traffic:
- Separate tenant vs visitor counts
- Peak hour analysis for security staffing
- Loading dock monitoring
- Monthly traffic reports per tenant
- Vehicle type analysis (trucks, deliveries)

### Fleet/Vehicle Analysis (Premium)

Enhanced tracking with vehicle attributes:
- Identify vehicles by make/model/color (even without plate)
- "Find the white Toyota" search capability
- Demographics analysis (what vehicles visit most)
- Lost plate correlation (match by vehicle attributes)
- Security investigations with visual evidence

### Security & Access Control

Combined with gate control:
- Entry requires plate AND matches expected vehicle
- "ABC123 should be a white Toyota" verification
- Alert if plate on blacklist vehicle changes color/make
- Cloned plate detection (same plate, different vehicle)

---

## Related Documentation

- [Gate Control Use Case](use-case-gate-control.md) - Base features (Plate Logging extends this)
- [Project Structure](project-structure.md) - Single repository architecture
- [Modular Deployment](modular-deployment.md) - License-based feature loading
- [Feature Tiers](feature-tiers.md) - Scaling options and tier comparison
- [Deployment Analysis](deployment-analysis.md) - Hardware, costs, architecture
- [Hardware Reliability](hardware-reliability.md) - 24/7 operation
- [SaaS Business Model](saas-business-model.md) - Multi-customer deployment

