#!/usr/bin/env python3
"""
Alert Engine for ALPR Events
Consumes PlateEvent messages from Kafka and sends notifications based on configured rules.
"""

import os
import signal
import sys
import time
import uuid
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger

# Kafka imports
try:
    from confluent_kafka import DeserializingConsumer, Producer
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
    from confluent_kafka.serialization import StringDeserializer, SerializationContext, MessageField
    CONFLUENT_KAFKA_AVAILABLE = True
except ImportError:
    CONFLUENT_KAFKA_AVAILABLE = False
    logger.warning("confluent-kafka not installed. Run: pip install confluent-kafka[avro]")

# Alert engine components
from rule_engine import RuleEngine, MatchedRule
from utils.rate_limiter import RateLimiter
from utils.retry_handler import RetryHandler
from notifiers.email_notifier import EmailNotifier
from notifiers.slack_notifier import SlackNotifier
from notifiers.webhook_notifier import WebhookNotifier
from notifiers.sms_notifier import SMSNotifier

# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, start_http_server


class AlertEngine:
    """
    Alert Engine for ALPR events with rule-based notifications.

    Consumes Avro-serialized plate detection events from Kafka and sends
    notifications via Email, Slack, Webhooks, and SMS based on configured rules.
    """

    # Prometheus metrics (class-level for global access)
    metrics_events_consumed = Counter('alert_engine_events_consumed_total', 'Total events consumed')
    metrics_rules_matched = Counter('alert_engine_rules_matched_total', 'Rules matched', ['rule_id', 'priority'])
    metrics_rule_evaluation_time = Histogram('alert_engine_rule_evaluation_time_seconds', 'Rule evaluation time')
    metrics_alerts_triggered = Counter('alert_engine_alerts_triggered_total', 'Alerts triggered', ['rule_id'])
    metrics_alerts_rate_limited = Counter('alert_engine_alerts_rate_limited_total', 'Alerts rate-limited', ['rule_id'])
    metrics_notifications_sent = Counter('alert_engine_notifications_sent_total', 'Notifications sent', ['channel', 'rule_id'])
    metrics_notifications_failed = Counter('alert_engine_notifications_failed_total', 'Notification failures', ['channel', 'error_type'])
    metrics_notification_send_time = Histogram('alert_engine_notification_send_time_seconds', 'Notification send time', ['channel'])
    metrics_retries = Counter('alert_engine_retry_attempts_total', 'Total retry attempts', ['attempt'])
    metrics_timeouts = Counter('alert_engine_processing_timeout_total', 'Total processing timeouts')
    metrics_dlq_sent = Counter('alert_engine_dlq_messages_sent_total', 'Total messages sent to DLQ', ['error_type'])

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        schema_registry_url: str = "http://localhost:8081",
        kafka_topic: str = "alpr.events.plates",
        kafka_group_id: str = "alpr-alert-engine",
        rules_config_path: str = "/app/config/alert_rules.yaml",
        auto_offset_reset: str = "latest",
        max_retries: int = 3,
        retry_delay_base: float = 2.0,
        processing_timeout: float = 30.0,
        enable_dlq: bool = True,
        dlq_topic: str = "alpr.dlq",
    ):
        """
        Initialize Alert Engine.

        Args:
            kafka_bootstrap_servers: Kafka broker addresses
            schema_registry_url: Schema Registry URL
            kafka_topic: Topic to consume from
            kafka_group_id: Consumer group ID
            rules_config_path: Path to alert_rules.yaml
            auto_offset_reset: Offset reset policy (latest, earliest)
            max_retries: Maximum retry attempts before sending to DLQ
            retry_delay_base: Base delay in seconds for exponential backoff
            processing_timeout: Maximum processing time in seconds per message
            enable_dlq: Enable Dead Letter Queue for failed messages
            dlq_topic: DLQ topic name
        """
        if not CONFLUENT_KAFKA_AVAILABLE:
            raise ImportError(
                "confluent-kafka not installed. "
                "Run: pip install confluent-kafka[avro]"
            )

        self.kafka_topic = kafka_topic
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.schema_registry_url = schema_registry_url
        self.kafka_group_id = kafka_group_id
        self.consumer = None
        self.running = False

        # Retry and DLQ configuration
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.processing_timeout = processing_timeout
        self.enable_dlq = enable_dlq
        self.dlq_topic = dlq_topic
        self.dlq_producer = None
        self.dlq_serializer = None

        # Statistics
        self.stats = {
            'consumed': 0,
            'rules_matched': 0,
            'alerts_sent': 0,
            'alerts_rate_limited': 0,
            'notifications_sent': 0,
            'notifications_failed': 0,
            'retried': 0,
            'timeout': 0,
            'dlq_sent': 0,
        }

        # Initialize components
        logger.info(f"Loading alert rules from: {rules_config_path}")
        self.rule_engine = RuleEngine(rules_config_path)
        self.rate_limiter = RateLimiter(cleanup_interval=3600)
        self.retry_handler = RetryHandler(max_attempts=3, initial_delay=5.0)

        # Initialize notifiers
        self.notifiers = self._initialize_notifiers()

        # Initialize Schema Registry client
        self.schema_registry_client = SchemaRegistryClient({
            'url': schema_registry_url
        })

        # Create Avro deserializer
        self.avro_deserializer = AvroDeserializer(
            self.schema_registry_client,
            from_dict=lambda obj, ctx: obj  # Events are already dicts
        )

        # String deserializer for keys
        self.string_deserializer = StringDeserializer('utf_8')

        # Consumer configuration
        self.config = {
            'bootstrap.servers': kafka_bootstrap_servers,
            'group.id': kafka_group_id,
            'auto.offset.reset': auto_offset_reset,
            'enable.auto.commit': True,
            'key.deserializer': self.string_deserializer,
            'value.deserializer': self.avro_deserializer,
        }

        # Initialize DLQ producer if enabled
        if self.enable_dlq:
            self._init_dlq_producer()

        # Initialize consumer
        self._connect()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start Prometheus metrics HTTP server on port 8003
        try:
            start_http_server(8003)
            logger.success("✅ Prometheus metrics endpoint started at http://localhost:8003/metrics")
        except Exception as e:
            logger.warning(f"⚠️  Failed to start Prometheus metrics server: {e}")

    def _initialize_notifiers(self) -> Dict[str, Any]:
        """Initialize all notification channels."""
        notifiers = {}

        # Email
        email_config = self.rule_engine.get_notification_config('email')
        if email_config:
            notifiers['email'] = EmailNotifier(email_config)
            logger.info("✅ Email notifier initialized")

        # Slack
        slack_config = self.rule_engine.get_notification_config('slack')
        if slack_config:
            notifiers['slack'] = SlackNotifier(slack_config)
            logger.info("✅ Slack notifier initialized")

        # Webhook
        webhook_config = self.rule_engine.get_notification_config('webhook')
        if webhook_config:
            notifiers['webhook'] = WebhookNotifier(webhook_config)
            logger.info("✅ Webhook notifier initialized")

        # SMS
        sms_config = self.rule_engine.get_notification_config('sms')
        if sms_config:
            notifiers['sms'] = SMSNotifier(sms_config)
            logger.info("✅ SMS notifier initialized")

        if not notifiers:
            logger.warning("⚠️  No notification channels enabled!")

        return notifiers

    def _connect(self):
        """Establish connection to Kafka broker."""
        try:
            self.consumer = DeserializingConsumer(self.config)
            logger.success(
                f"✅ Connected to Kafka (Avro): {self.kafka_bootstrap_servers}\n"
                f"   Schema Registry: {self.schema_registry_url}\n"
                f"   Group ID: {self.config['group.id']}"
            )
            self.consumer.subscribe([self.kafka_topic])
            logger.success(f"✅ Subscribed to topic: {self.kafka_topic}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Kafka: {e}")
            raise

    def _init_dlq_producer(self):
        """Initialize DLQ producer with Avro serialization"""
        try:
            # Try multiple schema paths (local dev and Docker container)
            schema_paths = [
                os.path.join(os.path.dirname(__file__), '../../schemas/dlq_message.avsc'),
                '/app/schemas/dlq_message.avsc',
                'schemas/dlq_message.avsc',
            ]

            schema_path = None
            for path in schema_paths:
                if os.path.exists(path):
                    schema_path = path
                    break

            if not schema_path:
                raise FileNotFoundError(f"DLQ schema not found in any of: {schema_paths}")

            with open(schema_path, 'r') as f:
                import json as json_lib
                dlq_schema_str = json_lib.dumps(json_lib.load(f))

            # Create Avro serializer for DLQ messages
            self.dlq_serializer = AvroSerializer(
                self.schema_registry_client,
                dlq_schema_str,
                to_dict=lambda obj, ctx: obj
            )

            # Create DLQ producer
            producer_config = {
                'bootstrap.servers': self.kafka_bootstrap_servers,
            }
            self.dlq_producer = Producer(producer_config)

            logger.success(f"✅ DLQ producer initialized: {self.dlq_topic}")

        except Exception as e:
            logger.error(f"Failed to initialize DLQ producer: {e}")
            logger.warning("DLQ functionality disabled")
            self.enable_dlq = False

    def _send_to_dlq(
        self,
        original_msg,
        event_data: Dict,
        error_type: str,
        error_message: str,
        error_stack_trace: Optional[str] = None,
        retry_count: int = 0
    ):
        """Send failed message to DLQ"""
        if not self.enable_dlq or not self.dlq_producer:
            logger.warning("DLQ not enabled or not initialized, cannot send message")
            return

        try:
            # Create DLQ message
            dlq_message = {
                'dlq_id': str(uuid.uuid4()),
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'original_topic': self.kafka_topic,
                'original_partition': original_msg.partition(),
                'original_offset': original_msg.offset(),
                'original_key': original_msg.key() if original_msg.key() else None,
                'original_message': json.dumps(event_data),
                'consumer_group_id': self.kafka_group_id,
                'error_type': error_type,
                'error_message': error_message,
                'error_stack_trace': error_stack_trace,
                'retry_count': retry_count,
                'metadata': {
                    'event_id': event_data.get('event_id', 'unknown'),
                    'camera_id': event_data.get('camera_id', 'unknown'),
                }
            }

            # Serialize to Avro
            ctx = SerializationContext(self.dlq_topic, MessageField.VALUE)
            value_bytes = self.dlq_serializer(dlq_message, ctx)

            # Publish to DLQ
            self.dlq_producer.produce(
                topic=self.dlq_topic,
                key=self.dlq_topic.encode('utf-8'),
                value=value_bytes
            )
            self.dlq_producer.flush(timeout=5)

            # Update stats and metrics
            self.stats['dlq_sent'] += 1
            self.metrics_dlq_sent.labels(error_type=error_type).inc()

            logger.warning(
                f"💀 Sent message to DLQ: {error_type}\n"
                f"   Event ID: {event_data.get('event_id', 'unknown')}\n"
                f"   Offset: {original_msg.offset()}\n"
                f"   Retries: {retry_count}"
            )

        except Exception as e:
            logger.error(f"Failed to send message to DLQ: {e}")

    def _process_with_retry(self, msg, event_data: Dict) -> bool:
        """
        Process message with retry logic and timeout detection

        Returns:
            True if successful, False if failed after retries
        """
        import traceback

        message_start_time = time.time()

        for attempt in range(self.max_retries):
            try:
                # Check for timeout
                elapsed = time.time() - message_start_time
                if elapsed > self.processing_timeout:
                    error_msg = f"Processing timeout after {elapsed:.1f}s (max: {self.processing_timeout}s)"
                    logger.error(f"⏱️  {error_msg}")
                    self.stats['timeout'] += 1
                    self.metrics_timeouts.inc()

                    # Send to DLQ
                    self._send_to_dlq(
                        msg,
                        event_data,
                        error_type='TIMEOUT',
                        error_message=error_msg,
                        retry_count=attempt
                    )
                    return False

                # Attempt to process event (rule evaluation + notifications)
                self._process_event(event_data)

                if attempt > 0:
                    logger.info(f"✅ Succeeded on retry attempt {attempt + 1}/{self.max_retries}")
                return True

            except Exception as e:
                self.stats['retried'] += 1
                self.metrics_retries.labels(attempt=str(attempt + 1)).inc()

                if attempt < self.max_retries - 1:
                    # Calculate exponential backoff delay
                    delay = self.retry_delay_base * (2 ** attempt)
                    logger.warning(
                        f"⚠️  Retry {attempt + 1}/{self.max_retries} failed: {e}\n"
                        f"   Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    # Final attempt failed - send to DLQ
                    error_msg = f"Failed after {self.max_retries} attempts: {str(e)}"
                    stack_trace = traceback.format_exc()

                    logger.error(
                        f"❌ Processing failed after {self.max_retries} retries\n"
                        f"   Error: {e}"
                    )

                    # Send to DLQ
                    self._send_to_dlq(
                        msg,
                        event_data,
                        error_type='PROCESSING_FAILURE',
                        error_message=error_msg,
                        error_stack_trace=stack_trace,
                        retry_count=attempt + 1
                    )
                    return False

        return False

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"\n🛑 Received signal {sig}, shutting down gracefully...")
        self.running = False

    def consume(self, timeout: float = 1.0):
        """
        Start consuming messages and processing alerts.

        Args:
            timeout: Poll timeout in seconds
        """
        self.running = True
        logger.info("🚀 Alert Engine started, waiting for events...")

        try:
            while self.running:
                try:
                    msg = self.consumer.poll(timeout=timeout)

                    if msg is None:
                        continue

                    if msg.error():
                        logger.error(f"❌ Consumer error: {msg.error()}")
                        continue

                    # Process event with retry logic
                    event = msg.value()
                    if event:
                        self.metrics_events_consumed.inc()
                        self.stats['consumed'] += 1

                        # Process with retry and timeout detection
                        success = self._process_with_retry(msg, event)

                        if not success:
                            # Error logging and DLQ handling already done in _process_with_retry
                            pass
                    else:
                        logger.warning("⚠️  Received null event, skipping")

                except KeyboardInterrupt:
                    logger.info("⏸️  Interrupted by user")
                    break
                except Exception as e:
                    logger.error(f"❌ Error processing message: {e}", exc_info=True)
                    continue

        finally:
            self._shutdown()

    def _process_event(self, event: Dict):
        """
        Process a single event through the alert pipeline.

        Args:
            event: PlateEvent data (dict)
        """
        start_time = time.time()

        try:
            # Evaluate rules
            matched_rules = self.rule_engine.evaluate(event)

            if not matched_rules:
                return  # No rules matched

            # Process each matched rule
            for matched_rule in matched_rules:
                self.metrics_rules_matched.labels(
                    rule_id=matched_rule.rule_id,
                    priority=matched_rule.priority
                ).inc()
                self.stats['rules_matched'] += 1

                # Check rate limiting
                if not self._check_rate_limit(matched_rule):
                    self.metrics_alerts_rate_limited.labels(rule_id=matched_rule.rule_id).inc()
                    self.stats['alerts_rate_limited'] += 1
                    continue

                # Send notifications
                self._send_notifications(matched_rule)
                self.metrics_alerts_triggered.labels(rule_id=matched_rule.rule_id).inc()
                self.stats['alerts_sent'] += 1

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
        finally:
            # Record processing time
            elapsed = time.time() - start_time
            self.metrics_rule_evaluation_time.observe(elapsed)

    def _check_rate_limit(self, matched_rule: MatchedRule) -> bool:
        """Check if alert should be rate-limited."""
        rate_limit_config = matched_rule.rate_limit_config

        if not rate_limit_config.get('enabled', True):
            return True  # Rate limiting disabled for this rule

        cooldown_seconds = rate_limit_config.get('cooldown_seconds', 300)
        dedup_key = rate_limit_config.get('dedup_key', 'plate.normalized_text')

        should_alert = self.rate_limiter.should_alert(
            rule_id=matched_rule.rule_id,
            event=matched_rule.event_data,
            cooldown_seconds=cooldown_seconds,
            dedup_key=dedup_key
        )

        return should_alert

    def _send_notifications(self, matched_rule: MatchedRule):
        """Send notifications to all configured channels for this rule."""
        # Format message
        message = matched_rule.message_template
        for notifier_cls in self.notifiers.values():
            if hasattr(notifier_cls, 'format_message'):
                message = notifier_cls.format_message(
                    matched_rule.message_template,
                    matched_rule.event_data
                )
                break

        # Prepare alert data
        alert_data = {
            'rule_id': matched_rule.rule_id,
            'rule_name': matched_rule.rule_name,
            'priority': matched_rule.priority,
            'message': message,
            'event': matched_rule.event_data
        }

        # Send to each configured channel
        for channel in matched_rule.notify_channels:
            if channel not in self.notifiers:
                logger.warning(f"Channel '{channel}' not available, skipping")
                continue

            notifier = self.notifiers[channel]
            if not notifier.is_enabled():
                logger.debug(f"Channel '{channel}' is disabled, skipping")
                continue

            # Send with retry
            self._send_with_retry(channel, notifier, alert_data, matched_rule.rule_id)

    def _send_with_retry(self, channel: str, notifier: Any, alert_data: Dict, rule_id: str):
        """Send notification with retry logic."""
        start_time = time.time()

        try:
            # Wrap send in retry handler
            success, error = self.retry_handler.execute_with_retry(
                notifier.send,
                alert_data
            )

            # Record metrics
            elapsed = time.time() - start_time
            self.metrics_notification_send_time.labels(channel=channel).observe(elapsed)

            if success:
                self.metrics_notifications_sent.labels(channel=channel, rule_id=rule_id).inc()
                self.stats['notifications_sent'] += 1
                logger.success(f"✅ Notification sent via {channel} for rule: {rule_id}")
            else:
                error_type = type(error).__name__ if error else 'unknown'
                self.metrics_notifications_failed.labels(channel=channel, error_type=error_type).inc()
                self.stats['notifications_failed'] += 1
                logger.error(f"❌ Failed to send notification via {channel} for rule: {rule_id}")

        except Exception as e:
            logger.error(f"Unexpected error sending notification via {channel}: {e}", exc_info=True)
            self.metrics_notifications_failed.labels(channel=channel, error_type='unexpected').inc()
            self.stats['notifications_failed'] += 1

    def _shutdown(self):
        """Clean shutdown of alert engine."""
        logger.info("🛑 Shutting down Alert Engine...")

        if self.consumer:
            try:
                self.consumer.close()
                logger.success("✅ Kafka consumer closed")
            except Exception as e:
                logger.error(f"Error closing consumer: {e}")

        # Print final stats
        logger.info(
            f"\n📊 Final Statistics:\n"
            f"   Events Consumed:      {self.stats['consumed']}\n"
            f"   Rules Matched:        {self.stats['rules_matched']}\n"
            f"   Alerts Sent:          {self.stats['alerts_sent']}\n"
            f"   Alerts Rate Limited:  {self.stats['alerts_rate_limited']}\n"
            f"   Notifications Sent:   {self.stats['notifications_sent']}\n"
            f"   Notifications Failed: {self.stats['notifications_failed']}\n"
            f"   Retried:              {self.stats['retried']}\n"
            f"   Timeout:              {self.stats['timeout']}\n"
            f"   DLQ Sent:             {self.stats['dlq_sent']}"
        )

        logger.success("✅ Alert Engine shutdown complete")


def main():
    """Main entry point."""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "/app/logs/alert_engine.log",
        rotation="100 MB",
        retention="30 days",
        level="DEBUG"
    )

    # Get configuration from environment
    kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    schema_registry = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")
    kafka_topic = os.getenv("KAFKA_TOPIC", "alpr.events.plates")
    kafka_group = os.getenv("KAFKA_GROUP_ID", "alpr-alert-engine")
    rules_config = os.getenv("RULES_CONFIG_PATH", "/app/config/alert_rules.yaml")
    auto_offset = os.getenv("AUTO_OFFSET_RESET", "latest")

    # DLQ and retry configuration
    max_retries = int(os.getenv('MAX_RETRIES', '3'))
    retry_delay_base = float(os.getenv('RETRY_DELAY_BASE', '2.0'))
    processing_timeout = float(os.getenv('PROCESSING_TIMEOUT', '30.0'))
    enable_dlq = os.getenv('ENABLE_DLQ', 'true').lower() == 'true'
    dlq_topic = os.getenv('DLQ_TOPIC', 'alpr.dlq')

    logger.info("🚀 Starting ALPR Alert Engine (with DLQ & Retry)...")
    logger.info(f"   Kafka: {kafka_bootstrap}")
    logger.info(f"   Schema Registry: {schema_registry}")
    logger.info(f"   Topic: {kafka_topic}")
    logger.info(f"   Rules: {rules_config}")
    logger.info(f"   Max Retries: {max_retries}")
    logger.info(f"   Retry Delay Base: {retry_delay_base}s")
    logger.info(f"   Processing Timeout: {processing_timeout}s")
    logger.info(f"   DLQ Enabled: {enable_dlq}")
    logger.info(f"   DLQ Topic: {dlq_topic}")

    try:
        # Create and run alert engine
        engine = AlertEngine(
            kafka_bootstrap_servers=kafka_bootstrap,
            schema_registry_url=schema_registry,
            kafka_topic=kafka_topic,
            kafka_group_id=kafka_group,
            rules_config_path=rules_config,
            auto_offset_reset=auto_offset,
            max_retries=max_retries,
            retry_delay_base=retry_delay_base,
            processing_timeout=processing_timeout,
            enable_dlq=enable_dlq,
            dlq_topic=dlq_topic,
        )

        engine.consume()

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
