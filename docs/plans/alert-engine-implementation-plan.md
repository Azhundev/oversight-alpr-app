# Alert Engine Implementation Plan (Phase 3 Priority 4)

## Overview
Implement a production-ready Alert Engine that consumes plate detection events from Kafka and sends notifications via Email, Slack, Webhooks, and SMS based on configurable rules.

## Architecture Decision
- **Location**: `/home/jetson/OVR-ALPR/core_services/alerting/` (Docker service, follows kafka-consumer pattern)
- **Pattern**: Based on `avro_kafka_consumer.py` - same Kafka consumer structure
- **Port**: 8003 for Prometheus metrics (8001=pilot, 8002=kafka-consumer)
- **Configuration**: `/home/jetson/OVR-ALPR/config/alert_rules.yaml`

## Core Components

### 1. Alert Engine (Main Kafka Consumer)
**File**: `core_services/alerting/alert_engine.py`

**Responsibilities**:
- Subscribe to `alpr.plates.detected` topic with Avro deserialization
- Consume PlateEvent messages and pass to RuleEngine
- Send alerts via notification channels
- Track Prometheus metrics
- Handle graceful shutdown (SIGINT/SIGTERM)

**Pattern to Follow**: Copy structure from `avro_kafka_consumer.py` (lines 1-100)
- Same DeserializingConsumer setup with Schema Registry
- Same signal handlers and graceful shutdown
- Same metrics pattern (class-level Counter/Histogram/Gauge)
- Same statistics tracking dict

### 2. Rule Engine (Rule Matching Logic)
**File**: `core_services/alerting/rule_engine.py`

**Responsibilities**:
- Load rules from `config/alert_rules.yaml`
- Evaluate PlateEvent against all enabled rules
- Support operators: `equals`, `contains`, `regex`, `in_list`, `greater_than`, `less_than`
- Access nested fields with dot notation (e.g., `plate.normalized_text`, `vehicle.color`)

**Key Classes**:
```python
class RuleEngine:
    def __init__(self, rules_config_path)
    def evaluate(self, event: Dict) -> List[MatchedRule]
    def _check_condition(self, condition: Dict, event: Dict) -> bool
    def _get_nested_value(self, event: Dict, field_path: str) -> Any

class MatchedRule:
    rule_id: str
    priority: str  # high, medium, low
    notify_channels: List[str]  # email, slack, webhook, sms
    message_template: str
    rate_limit_config: Dict
```

### 3. Notification System
**Files**: `core_services/alerting/notifiers/`

**Base Class**: `notifiers/base.py`
```python
class BaseNotifier(ABC):
    @abstractmethod
    def send(self, alert_data: Dict) -> bool
    def format_message(self, template: str, event: Dict) -> str
```

**Implementations**:
- `email_notifier.py` - Use `smtplib` for SMTP (Gmail, Office365, etc.)
- `slack_notifier.py` - Use `requests` to POST to Slack webhooks
- `webhook_notifier.py` - Generic HTTP POST with configurable headers/auth
- `sms_notifier.py` - Use Twilio API for SMS

### 4. Rate Limiting
**File**: `core_services/alerting/utils/rate_limiter.py`

**Responsibilities**:
- Prevent alert spam with configurable cooldown periods
- Track alerts by `(rule_id, dedup_key)` combination
- Dedup keys: `plate.normalized_text` (default), `camera_id`, `track_id`
- Auto-cleanup old cache entries to prevent memory leaks

```python
class RateLimiter:
    def should_alert(self, rule_id: str, event: Dict, cooldown_seconds: int, dedup_key: str) -> bool
```

### 5. Retry Handler
**File**: `core_services/alerting/utils/retry_handler.py`

**Responsibilities**:
- Retry failed notifications with exponential backoff
- Max 3 attempts by default (configurable)
- Delays: 5s, 10s, 20s

```python
class RetryHandler:
    def execute_with_retry(self, func: callable, *args, **kwargs) -> Tuple[bool, Exception]
```

## Configuration Schema

**File**: `config/alert_rules.yaml`

```yaml
notifications:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    use_tls: true
    username: "alpr-alerts@example.com"
    password: "${SMTP_PASSWORD}"  # From env var
    from_address: "ALPR Alerts <alpr-alerts@example.com>"
    recipients: ["security@example.com"]

  slack:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"
    channel: "#alpr-alerts"

  webhook:
    enabled: false
    url: "https://api.example.com/alpr/webhook"
    headers:
      Authorization: "Bearer ${WEBHOOK_TOKEN}"

  sms:
    enabled: false
    twilio_account_sid: "${TWILIO_ACCOUNT_SID}"
    twilio_auth_token: "${TWILIO_AUTH_TOKEN}"
    from_number: "+15551234567"
    to_numbers: ["+15559876543"]

rules:
  - id: "watchlist_plate"
    name: "Watchlist Plate Detected"
    enabled: true
    priority: "high"
    conditions:
      - field: "plate.normalized_text"
        operator: "in_list"
        value: ["ABC123", "XYZ789"]
    notify: [email, slack, sms]
    rate_limit:
      enabled: true
      cooldown_seconds: 300
      dedup_key: "plate.normalized_text"
    message_template: |
      🚨 WATCHLIST PLATE DETECTED
      Plate: {plate.normalized_text}
      Camera: {camera_id}
      Time: {captured_at}
```

## Docker Integration

### Dockerfile
**File**: `core_services/alerting/Dockerfile`

```dockerfile
FROM python:3.9-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libffi-dev libssl-dev && rm -rf /var/lib/apt/lists/*
COPY core_services/alerting/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core_services/alerting/ ./services/alerting/
COPY schemas/ ./schemas/
ENV PYTHONPATH=/app
EXPOSE 8003
CMD ["python", "-u", "services/alerting/alert_engine.py"]
```

### requirements.txt
**File**: `core_services/alerting/requirements.txt`

```
confluent-kafka[avro]>=2.12.0
prometheus-client>=0.19.0
loguru>=0.7.2
PyYAML>=6.0.1
requests>=2.31.0
twilio>=8.10.0
```

### docker-compose.yml Entry
**Add to**: `docker-compose.yml`

```yaml
  alert-engine:
    build:
      context: .
      dockerfile: core_services/alerting/Dockerfile
    container_name: alpr-alert-engine
    depends_on:
      kafka:
        condition: service_healthy
      schema-registry:
        condition: service_healthy
    ports:
      - "8003:8003"
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      KAFKA_TOPIC: alpr.plates.detected
      KAFKA_GROUP_ID: alpr-alert-engine
      SCHEMA_REGISTRY_URL: http://schema-registry:8081
      RULES_CONFIG_PATH: /app/config/alert_rules.yaml
      SMTP_PASSWORD: "${SMTP_PASSWORD:-}"
      SLACK_WEBHOOK_URL: "${SLACK_WEBHOOK_URL:-}"
      WEBHOOK_TOKEN: "${WEBHOOK_TOKEN:-}"
      TWILIO_ACCOUNT_SID: "${TWILIO_ACCOUNT_SID:-}"
      TWILIO_AUTH_TOKEN: "${TWILIO_AUTH_TOKEN:-}"
    volumes:
      - ./config/alert_rules.yaml:/app/config/alert_rules.yaml:ro
      - ./logs:/app/logs
    networks:
      - alpr-network
    restart: unless-stopped
```

## Prometheus Metrics

**Expose on port 8003**:

```python
# Rule evaluation
metrics_events_consumed = Counter('alert_engine_events_consumed_total', 'Total events consumed')
metrics_rules_matched = Counter('alert_engine_rules_matched_total', 'Rules matched', ['rule_id', 'priority'])
metrics_rule_evaluation_time = Histogram('alert_engine_rule_evaluation_time_seconds', 'Rule evaluation time')

# Alerting
metrics_alerts_triggered = Counter('alert_engine_alerts_triggered_total', 'Alerts triggered', ['rule_id'])
metrics_alerts_rate_limited = Counter('alert_engine_alerts_rate_limited_total', 'Alerts rate-limited', ['rule_id'])

# Notifications
metrics_notifications_sent = Counter('alert_engine_notifications_sent_total', 'Notifications sent', ['channel', 'rule_id'])
metrics_notifications_failed = Counter('alert_engine_notifications_failed_total', 'Notification failures', ['channel', 'error_type'])
metrics_notification_send_time = Histogram('alert_engine_notification_send_time_seconds', 'Notification send time', ['channel'])
```

Update `core_services/monitoring/prometheus/prometheus.yml`:
```yaml
- job_name: 'alert-engine'
  static_configs:
    - targets: ['alert-engine:8003']
  scrape_interval: 10s
```

## Implementation Steps (7-Day Plan)

### Day 1-2: Foundation
1. Create directory structure: `core_services/alerting/`, `notifiers/`, `utils/`
2. Implement `rule_engine.py` with condition operators
3. Create `config/alert_rules.yaml` with 3 sample rules
4. Write unit tests for rule evaluation

### Day 3-4: Notifications
5. Implement `base.py` (BaseNotifier abstract class)
6. Implement `email_notifier.py` (SMTP with TLS)
7. Implement `slack_notifier.py` (webhook POST)
8. Implement `webhook_notifier.py` (generic HTTP)
9. Implement `sms_notifier.py` (Twilio API)
10. Unit tests for each notifier (use mocks)

### Day 5: Rate Limiting & Retry
11. Implement `rate_limiter.py` with cooldown logic
12. Implement `retry_handler.py` with exponential backoff
13. Unit tests for both

### Day 6: Main Engine
14. Implement `alert_engine.py` (copy pattern from `avro_kafka_consumer.py`)
15. Integrate RuleEngine, RateLimiter, Notifiers, RetryHandler
16. Add Prometheus metrics throughout
17. Signal handlers for graceful shutdown

### Day 7: Docker & Testing
18. Create `Dockerfile` and `requirements.txt`
19. Update `docker-compose.yml`
20. Create `.env` template for secrets
21. Integration test: Start stack, publish test events, verify alerts
22. Write documentation: `docs/Services/alert-engine.md`

## Key Design Decisions

1. **Sync Notification Sending**: Notifications sent synchronously within consumer loop (simpler, acceptable latency). Can migrate to async later if needed.

2. **In-Memory Rules**: Rules loaded from YAML on startup. Restart service to reload (or implement file watcher). No database needed.

3. **Simple Operators First**: Start with 6 operators (equals, contains, regex, in_list, greater_than, less_than). Add time-based conditions later.

4. **Fail-Open Philosophy**: If notification fails after retries, log failure but continue processing. Don't crash service.

5. **Rate Limiting Per-Rule**: Each rule has its own cooldown config. Global rate limit as fallback.

## Critical Files Reference

**Existing files to reference**:
- `/home/jetson/OVR-ALPR/core_services/storage/avro_kafka_consumer.py` - Main pattern
- `/home/jetson/OVR-ALPR/schemas/plate_event.avsc` - Event structure
- `/home/jetson/OVR-ALPR/config/cameras.yaml` - Config pattern
- `/home/jetson/OVR-ALPR/docker-compose.yml` - Service definition

**New files to create**:
- `/home/jetson/OVR-ALPR/core_services/alerting/alert_engine.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/rule_engine.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/notifiers/base.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/notifiers/email_notifier.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/notifiers/slack_notifier.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/notifiers/webhook_notifier.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/notifiers/sms_notifier.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/utils/rate_limiter.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/utils/retry_handler.py`
- `/home/jetson/OVR-ALPR/core_services/alerting/Dockerfile`
- `/home/jetson/OVR-ALPR/core_services/alerting/requirements.txt`
- `/home/jetson/OVR-ALPR/config/alert_rules.yaml`
- `/home/jetson/OVR-ALPR/docs/Services/alert-engine.md`

## Success Criteria

- [x] Alert engine consumes from Kafka with Avro deserialization
- [x] Rules evaluate correctly against PlateEvent fields
- [x] All 4 notification channels work (Email, Slack, Webhook, SMS)
- [x] Rate limiting prevents alert spam
- [x] Prometheus metrics exposed on port 8003
- [x] Docker Compose service starts with health checks
- [x] Graceful shutdown on SIGINT/SIGTERM
- [x] Integration test passes (watchlist plate triggers all channels)

## Estimated Effort
7 days (56 hours) for complete implementation, testing, and documentation.
