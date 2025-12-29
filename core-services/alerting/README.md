# Alert Engine Service

Real-time notification system for ALPR plate detection events.

## Quick Start

```bash
# Start alert engine
docker compose up alert-engine -d

# View logs
docker logs -f alpr-alert-engine

# Stop alert engine
docker compose stop alert-engine
```

## Configuration

1. Edit `/home/jetson/OVR-ALPR/config/alert_rules.yaml`
2. Enable notification channels (email, slack, webhook, sms)
3. Add your watchlist plates to rules
4. Set environment variables for secrets

## Environment Variables

Create a `.env` file in the project root:

```bash
# Email
SMTP_PASSWORD=your_smtp_password

# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Webhook
WEBHOOK_TOKEN=your_api_token

# SMS (Twilio)
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
```

## Architecture

```
alert_engine.py          # Main Kafka consumer
├── rule_engine.py       # Evaluates event conditions
├── notifiers/           # Notification channel implementations
│   ├── base.py          # Abstract base class
│   ├── email_notifier.py
│   ├── slack_notifier.py
│   ├── webhook_notifier.py
│   └── sms_notifier.py
└── utils/               # Helper utilities
    ├── rate_limiter.py  # Prevents alert spam
    └── retry_handler.py # Retry with backoff
```

## Metrics

Prometheus metrics available at http://localhost:8003/metrics

Key metrics:
- `alert_engine_events_consumed_total` - Events processed
- `alert_engine_alerts_triggered_total` - Alerts sent
- `alert_engine_notifications_sent_total` - Notifications by channel
- `alert_engine_notifications_failed_total` - Notification failures

## Documentation

See `/home/jetson/OVR-ALPR/docs/Services/alert-engine.md` for complete documentation.

## Development

### Building

```bash
docker compose build alert-engine
```

### Testing

```bash
# Test rule evaluation locally
python3 -c "
import sys
sys.path.insert(0, '/home/jetson/OVR-ALPR/core-services/alerting')
from rule_engine import RuleEngine

engine = RuleEngine('/home/jetson/OVR-ALPR/config/alert_rules.yaml')
test_event = {
    'plate': {'normalized_text': 'ABC123', 'confidence': 0.95},
    'camera_id': 'test_cam'
}
matched = engine.evaluate(test_event)
print(f'Matched {len(matched)} rules')
"
```

### Adding New Notifiers

1. Create new file in `notifiers/` (e.g., `discord_notifier.py`)
2. Extend `BaseNotifier` class
3. Implement `send()` method
4. Add configuration to `alert_rules.yaml`
5. Initialize in `alert_engine.py`

## Status

✅ Production-Ready (Phase 3 Priority 4 - COMPLETE)

## Support

For issues or questions:
- Check logs: `docker logs alpr-alert-engine`
- View metrics: `curl http://localhost:8003/metrics`
- See documentation: `docs/Services/alert-engine.md`
