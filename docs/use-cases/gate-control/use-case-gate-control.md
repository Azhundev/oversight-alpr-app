# Gate Control Use Case

**Created:** 2026-02-15
**Updated:** 2026-02-17
**Use Case:** Automated gate access control using license plate recognition
**Related:** [Deployment Analysis](deployment-analysis.md) | [Plate Logging](use-case-plate-logging.md) | [Feature Tiers](feature-tiers.md)

---

> **Architecture Note:** Gate Control is a module within the **alpr-edge** single repository. All use cases (gate control, parking logger, etc.) share the same codebase with features enabled by license configuration. See [Project Structure](project-structure.md) for details.

> **Relationship:** [Plate Logging](use-case-plate-logging.md) **extends** Gate Control with additional duration tracking, tailgate detection, and vehicle attribute features. All Plate Logging deployments include full Gate Control functionality.

---

## Table of Contents

1. [Overview](#overview)
2. [System Requirements](#system-requirements)
3. [Gate Control Workflow](#gate-control-workflow)
4. [Enrollment Mode](#enrollment-mode)
5. [Access Control Logic](#access-control-logic)
6. [Gate Controller Integration](#gate-controller-integration)
7. [Dashboard Features](#dashboard-features)
8. [Database Schema](#database-schema)
9. [API Endpoints](#api-endpoints)
10. [Performance Requirements](#performance-requirements)
11. [Failure Handling](#failure-handling)

---

## Overview

Automated gate control using ALPR (Automatic License Plate Recognition) to:
- **Open gates** automatically for authorized vehicles (whitelist)
- **Deny access** and alert for unauthorized vehicles (blacklist)
- **Log** all access attempts for audit purposes
- **Learn** authorized vehicles during an enrollment period

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Hands-free access** | No cards, remotes, or codes needed |
| **Automatic enrollment** | Learn residents/employees over time |
| **Security** | Alert on blacklisted or unknown vehicles |
| **Audit trail** | Complete log of all gate events |
| **24/7 operation** | Works day and night with IR cameras |

---

## System Requirements

### Hardware

| Component | Specification |
|-----------|---------------|
| **Camera** | 1080p IP camera with RTSP, IR night vision |
| **Compute** | Jetson Orin Nano 8GB or higher |
| **Gate Controller** | GPIO relay, network relay, or existing gate API |
| **Network** | Local network (internet optional) |

### Performance

| Metric | Requirement |
|--------|-------------|
| **Detection latency** | <100ms |
| **Gate trigger time** | <500ms from plate recognition |
| **Uptime** | 99.9% (works offline) |

---

## Gate Control Workflow

### Phase 1: Enrollment (First 2 Weeks)

```
┌────────────────────────────────────────────────────────────────┐
│                    ENROLLMENT MODE                              │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌───────────────┐    ┌─────────────────┐  │
│  │   Camera    │───>│ Detect Plate  │───>│ Track Candidate │  │
│  │   (Entry)   │    │ + OCR         │    │ (count visits)  │  │
│  └─────────────┘    └───────────────┘    └────────┬────────┘  │
│                                                    │           │
│                           ┌────────────────────────┘           │
│                           ▼                                    │
│            ┌──────────────────────────────┐                   │
│            │  Seen 3+ times in 14 days?   │                   │
│            └──────────────┬───────────────┘                   │
│                           │                                    │
│              ┌────────────┴────────────┐                      │
│              │                         │                      │
│              ▼                         ▼                      │
│     ┌──────────────┐          ┌──────────────┐               │
│     │ YES:         │          │ NO:          │               │
│     │ Auto-add to  │          │ Keep         │               │
│     │ Whitelist    │          │ Tracking     │               │
│     └──────────────┘          └──────────────┘               │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Enrollment Settings:**

| Setting | Default | Description |
|---------|---------|-------------|
| `enrollment_threshold` | 3 | Times plate must be seen to auto-whitelist |
| `enrollment_window_days` | 14 | Window for counting plate occurrences |
| `enrollment_mode` | true → false | Disable after initial period |

### Phase 2: Operational (After Enrollment)

```
┌────────────────────────────────────────────────────────────────┐
│                    OPERATIONAL MODE                             │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌───────────────┐                          │
│  │   Camera    │───>│ Detect Plate  │                          │
│  │   (Entry)   │    │ + OCR         │                          │
│  └─────────────┘    └───────┬───────┘                          │
│                             │                                   │
│                             ▼                                   │
│              ┌──────────────────────────┐                      │
│              │    CHECK ACCESS LISTS    │                      │
│              └──────────────┬───────────┘                      │
│                             │                                   │
│       ┌─────────────────────┼─────────────────────┐            │
│       │                     │                     │            │
│       ▼                     ▼                     ▼            │
│ ┌───────────┐        ┌───────────┐        ┌───────────┐       │
│ │ WHITELIST │        │ BLACKLIST │        │  UNKNOWN  │       │
│ └─────┬─────┘        └─────┬─────┘        └─────┬─────┘       │
│       │                    │                    │              │
│       ▼                    ▼                    ▼              │
│ ┌───────────┐        ┌───────────┐        ┌───────────┐       │
│ │ OPEN GATE │        │   DENY    │        │   DENY    │       │
│ │           │        │ + ALERT   │        │ + LOG     │       │
│ │ Log entry │        │ Log event │        │ Log event │       │
│ └───────────┘        └───────────┘        └───────────┘       │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## Access Control Logic

### Decision Flow

```python
def check_access(plate_text: str) -> AccessDecision:
    """
    Check plate against access lists and return decision.
    Priority: Blacklist > Whitelist > Unknown
    """
    # Normalize plate (remove spaces, uppercase)
    normalized = normalize_plate(plate_text)

    # Check blacklist first (highest priority)
    if is_blacklisted(normalized):
        return AccessDecision(
            allowed=False,
            reason="blacklist",
            action="deny_and_alert"
        )

    # Check whitelist
    if is_whitelisted(normalized):
        return AccessDecision(
            allowed=True,
            reason="whitelist",
            action="open_gate"
        )

    # Unknown plate
    return AccessDecision(
        allowed=False,
        reason="unknown",
        action="deny_and_log"
    )
```

### List Types

| List | Action | Use Case |
|------|--------|----------|
| **Whitelist** | Open gate immediately | Residents, employees, regular visitors |
| **Blacklist** | Deny + send alert | Banned vehicles, stolen vehicles |
| **Unknown** | Deny + log (configurable) | First-time visitors |

### Plate Normalization

Plates are normalized before comparison:

```
"ABC 123"  → "ABC123"
"abc-123"  → "ABC123"
" ABC123 " → "ABC123"
```

---

## Gate Controller Integration

### Option 1: GPIO Relay (Direct Connection)

```
┌──────────────────┐          ┌────────────────┐
│  Jetson GPIO     │──wire───>│  Relay Module  │
│  (Pin 18)        │          │  (5V/12V)      │
└──────────────────┘          └───────┬────────┘
                                      │
                                      ▼
                              ┌────────────────┐
                              │  Gate Motor    │
                              │  Dry Contact   │
                              └────────────────┘
```

**Implementation:**

```python
import RPi.GPIO as GPIO

GATE_PIN = 18
OPEN_DURATION = 5  # seconds

def open_gate():
    GPIO.output(GATE_PIN, GPIO.HIGH)
    time.sleep(OPEN_DURATION)
    GPIO.output(GATE_PIN, GPIO.LOW)
```

**Wiring:**
- Jetson GPIO pin → Relay IN
- Relay COM → Gate motor "open" contact
- Relay NO → Gate motor common

### Option 2: Network Relay (HTTP/MQTT)

```
┌──────────────────┐   HTTP/MQTT   ┌────────────────┐
│  Jetson          │──────────────>│  Network Relay │
│  (WiFi/Ethernet) │               │  (e.g., Shelly)│
└──────────────────┘               └───────┬────────┘
                                           │
                                           ▼
                                   ┌────────────────┐
                                   │  Gate Motor    │
                                   └────────────────┘
```

**Implementation:**

```python
import requests

RELAY_URL = "http://192.168.1.100/relay/0"

def open_gate():
    requests.get(f"{RELAY_URL}?turn=on&timer=5")
```

**Popular Network Relays:**
- Shelly 1 (~$15)
- Sonoff Basic (~$10)
- ESP8266 + Relay board (~$8)

### Option 3: Existing Gate System API

Many modern gate systems have APIs:

```python
def open_gate():
    requests.post(
        "https://gate-system.local/api/open",
        headers={"Authorization": "Bearer <token>"},
        json={"gate_id": "main_entrance", "duration": 5}
    )
```

### Gate Controller Configuration

```yaml
# config/gate.yaml
gate_controller:
  type: gpio  # gpio, http, mqtt, api

  # GPIO options
  gpio:
    pin: 18
    active_high: true
    open_duration_ms: 5000

  # HTTP options
  http:
    url: "http://192.168.1.100/relay/0"
    method: GET
    open_params:
      turn: "on"
      timer: 5

  # MQTT options
  mqtt:
    broker: "192.168.1.50"
    topic: "gate/control"
    open_payload: "OPEN"
    close_payload: "CLOSE"
```

---

## Dashboard Features

### Whitelist Management

| Feature | Description |
|---------|-------------|
| **Add plate** | Manually add plate with owner info |
| **Remove plate** | Deactivate plate from whitelist |
| **Temporary access** | Set expiration date for visitors |
| **Bulk import** | Upload CSV of plates |
| **Search** | Find plate by partial match |

### Blacklist Management

| Feature | Description |
|---------|-------------|
| **Add plate** | Add plate with reason/notes |
| **Alert config** | Set notification method (email/SMS) |
| **Review** | See all blacklist alerts |

### Gate Event Log

| Column | Description |
|--------|-------------|
| **Timestamp** | When event occurred |
| **Plate** | Detected plate text |
| **Action** | opened, denied, alert |
| **Source** | Camera that detected plate |
| **Response time** | ms to trigger gate |

### Dashboard Screenshot Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  GATE CONTROL DASHBOARD                        [Admin ▼] [⚙️]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  TODAY'S STATS                                              ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    ││
│  │  │   127    │  │    3     │  │    0     │  │   124    │    ││
│  │  │ Total    │  │ Denied   │  │ Alerts   │  │ Approved │    ││
│  │  │ Events   │  │          │  │          │  │          │    ││
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌──────────────────────────┐  ┌───────────────────────────────┐│
│  │  QUICK ACTIONS           │  │  RECENT ACTIVITY              ││
│  │                          │  │                               ││
│  │  [+ Add to Whitelist]    │  │  12:34 ABC123 ✓ Opened        ││
│  │  [+ Add to Blacklist]    │  │  12:32 XYZ789 ✓ Opened        ││
│  │  [🔍 Search Plate]       │  │  12:30 ???999 ✗ Denied        ││
│  │  [📊 View Reports]       │  │  12:28 DEF456 ✓ Opened        ││
│  │                          │  │  12:25 ABC123 ✓ Opened        ││
│  └──────────────────────────┘  └───────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  WHITELIST (245 plates)                    [+ Add] [Import] ││
│  │  ┌─────────────────────────────────────────────────────────┐││
│  │  │ Plate    │ Owner        │ Added      │ Expires │ Actions│││
│  │  ├─────────────────────────────────────────────────────────┤││
│  │  │ ABC123   │ John Smith   │ 2026-01-15 │ Never   │ [Edit] │││
│  │  │ DEF456   │ Jane Doe     │ 2026-01-20 │ Never   │ [Edit] │││
│  │  │ GHI789   │ Guest        │ 2026-02-10 │ 2026-03-10 │ [Ed]│││
│  │  └─────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Access List Table

```sql
CREATE TABLE access_list (
    id SERIAL PRIMARY KEY,
    plate_text VARCHAR(15) UNIQUE NOT NULL,
    list_type VARCHAR(10) NOT NULL CHECK (list_type IN ('whitelist', 'blacklist')),
    added_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,  -- NULL = permanent
    added_by VARCHAR(50),  -- 'auto_enrollment' or username
    vehicle_description TEXT,
    owner_name VARCHAR(100),
    notes TEXT,
    active BOOLEAN DEFAULT TRUE
);

-- Fast lookup indexes
CREATE INDEX idx_access_whitelist ON access_list(plate_text)
    WHERE list_type = 'whitelist' AND active = TRUE;
CREATE INDEX idx_access_blacklist ON access_list(plate_text)
    WHERE list_type = 'blacklist' AND active = TRUE;
```

### Gate Events Table

```sql
CREATE TABLE gate_events (
    id SERIAL PRIMARY KEY,
    plate_text VARCHAR(15),
    action VARCHAR(20) NOT NULL,  -- 'opened', 'denied', 'blacklist_alert'
    camera_id VARCHAR(20),
    event_at TIMESTAMP DEFAULT NOW(),
    gate_response_ms INTEGER,
    confidence FLOAT,
    image_path TEXT,
    notes TEXT
);

CREATE INDEX idx_gate_events_time ON gate_events(event_at DESC);
CREATE INDEX idx_gate_events_plate ON gate_events(plate_text);
```

### Enrollment Candidates Table

```sql
CREATE TABLE enrollment_candidates (
    id SERIAL PRIMARY KEY,
    plate_text VARCHAR(15) UNIQUE NOT NULL,
    first_seen TIMESTAMP DEFAULT NOW(),
    last_seen TIMESTAMP DEFAULT NOW(),
    times_seen INTEGER DEFAULT 1,
    promoted_to_whitelist BOOLEAN DEFAULT FALSE,
    promoted_at TIMESTAMP
);
```

### Access Check Function

```sql
CREATE OR REPLACE FUNCTION check_plate_access(p_plate TEXT)
RETURNS TABLE(allowed BOOLEAN, list_type TEXT, owner_name TEXT) AS $$
BEGIN
    -- Check blacklist first (priority)
    IF EXISTS (
        SELECT 1 FROM access_list
        WHERE plate_text = p_plate
          AND list_type = 'blacklist'
          AND active = TRUE
    ) THEN
        RETURN QUERY SELECT FALSE, 'blacklist'::TEXT, NULL::TEXT;
        RETURN;
    END IF;

    -- Check whitelist
    RETURN QUERY
    SELECT TRUE, 'whitelist'::TEXT, al.owner_name
    FROM access_list al
    WHERE al.plate_text = p_plate
      AND al.list_type = 'whitelist'
      AND al.active = TRUE
      AND (al.expires_at IS NULL OR al.expires_at > NOW());

    -- If no whitelist match, plate is unknown
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'unknown'::TEXT, NULL::TEXT;
    END IF;
END;
$$ LANGUAGE plpgsql;
```

---

## API Endpoints

### Whitelist Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/whitelist` | List all whitelisted plates |
| `POST` | `/api/whitelist` | Add plate to whitelist |
| `DELETE` | `/api/whitelist/{plate}` | Remove plate from whitelist |
| `PUT` | `/api/whitelist/{plate}` | Update plate details |

### Blacklist Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/blacklist` | List all blacklisted plates |
| `POST` | `/api/blacklist` | Add plate to blacklist |
| `DELETE` | `/api/blacklist/{plate}` | Remove plate from blacklist |

### Gate Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/gate/open` | Manually trigger gate open |
| `GET` | `/api/gate/status` | Get current gate status |
| `GET` | `/api/gate/events` | Get recent gate events |

### Access Check

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/access/check/{plate}` | Check if plate has access |

**Example Request:**
```bash
curl http://localhost:8000/api/access/check/ABC123
```

**Example Response:**
```json
{
  "plate": "ABC123",
  "allowed": true,
  "list_type": "whitelist",
  "owner_name": "John Smith",
  "checked_at": "2026-02-15T12:34:56Z"
}
```

---

## Performance Requirements

### Timing Budget

```
┌─────────────────────────────────────────────────────────────────┐
│  GATE RESPONSE TIME BUDGET (<500ms total)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Camera → Frame capture      ████░░░░░░░░░░░░░░░░  50ms         │
│  Frame → Plate detection     ██████░░░░░░░░░░░░░░  100ms        │
│  Detection → OCR             ██████░░░░░░░░░░░░░░  100ms        │
│  OCR → DB lookup             █░░░░░░░░░░░░░░░░░░░  20ms         │
│  Decision → Gate trigger     █░░░░░░░░░░░░░░░░░░░  30ms         │
│                              ─────────────────────              │
│  TOTAL                       ███████████░░░░░░░░░  ~300ms       │
│  BUFFER                      ░░░░░░░░░░██████████  200ms        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Optimization Strategies

| Strategy | Impact | Implementation |
|----------|--------|----------------|
| **TensorRT FP16** | 2-3x faster detection | Export model with `half=True` |
| **Pre-warmed model** | No cold start delay | Load model on service start |
| **In-memory list cache** | <1ms lookups | Cache whitelist/blacklist in RAM |
| **GPIO direct control** | Minimal latency | No network hop for relay |

---

## Failure Handling

### Scenarios and Actions

| Scenario | Detection | Action |
|----------|-----------|--------|
| **Camera offline** | No frames for 30s | Alert admin, log error |
| **OCR failure** | Low confidence (<0.6) | Deny access, save image for review |
| **Database down** | Connection error | Use in-memory cache, queue writes |
| **Gate controller fail** | No response | Alert admin, manual override required |
| **Power failure** | System restart | Auto-start services, resume operation |

### Failover Mode

```python
# Graceful degradation when database unavailable
class GateController:
    def __init__(self):
        self.cache = {}  # In-memory whitelist cache
        self.db_available = True

    def check_access(self, plate):
        if self.db_available:
            try:
                return self.db_check(plate)
            except DatabaseError:
                self.db_available = False
                self.start_reconnect_task()

        # Fallback to cache
        if plate in self.cache:
            return self.cache[plate]

        # Unknown plate during DB outage - configurable behavior
        return self.failover_policy  # 'deny' or 'allow'
```

### Health Monitoring

```yaml
# Health check endpoints
endpoints:
  - /health/camera     # Camera stream active
  - /health/database   # DB connection OK
  - /health/gate       # Gate controller responsive
  - /health/model      # ALPR model loaded
```

---

## Related Documentation

- [Deployment Analysis](deployment-analysis.md) - Hardware, costs, architecture comparison
- [Plate Logging Use Case](use-case-plate-logging.md) - Entry/exit logging with timestamps (extends Gate Control)
- [Project Structure](project-structure.md) - Single repository architecture for all use cases
- [Modular Deployment](modular-deployment.md) - License-based feature loading
- [Feature Tiers](feature-tiers.md) - Scaling features for different needs
- [Hardware Reliability](hardware-reliability.md) - 24/7 operation best practices
- [SaaS Business Model](saas-business-model.md) - Multi-customer deployment

