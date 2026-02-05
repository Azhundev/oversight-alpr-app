#!/usr/bin/env python3
"""
Avro Kafka Consumer for ALPR Events
Consumes PlateEvent messages from Kafka using Avro deserialization with Schema Registry
"""

import signal
import sys
import time
import uuid
import json
from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger

try:
    from confluent_kafka import DeserializingConsumer, Producer
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
    from confluent_kafka.serialization import StringDeserializer, SerializationContext, MessageField
    CONFLUENT_KAFKA_AVAILABLE = True
except ImportError:
    CONFLUENT_KAFKA_AVAILABLE = False
    logger.warning("confluent-kafka not installed. Run: pip install confluent-kafka[avro]")

from storage_service import StorageService

# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, start_http_server


class AvroKafkaConsumer:
    """
    Avro Kafka consumer for ALPR events with Schema Registry integration

    Consumes Avro-serialized plate detection events from Kafka and stores them in TimescaleDB.
    Automatically deserializes using schemas from Schema Registry.
    """

    # Prometheus metrics (class-level for global access)
    metrics_consumed = Counter('kafka_consumer_messages_consumed_total', 'Total messages consumed from Kafka')
    metrics_stored = Counter('kafka_consumer_messages_stored_total', 'Total messages stored in database')
    metrics_failed = Counter('kafka_consumer_messages_failed_total', 'Total messages that failed to process')
    metrics_skipped = Counter('kafka_consumer_messages_skipped_total', 'Total messages skipped (null/invalid)')
    metrics_processing_time = Histogram('kafka_consumer_processing_time_seconds', 'Message processing time')
    metrics_db_insert_time = Histogram('kafka_consumer_db_insert_time_seconds', 'Database insert time')
    metrics_consumer_lag = Gauge('kafka_consumer_lag', 'Consumer lag (messages)')
    metrics_retries = Counter('kafka_consumer_retry_attempts_total', 'Total retry attempts', ['attempt'])
    metrics_timeouts = Counter('kafka_consumer_processing_timeout_total', 'Total processing timeouts')
    metrics_dlq_sent = Counter('kafka_consumer_dlq_messages_sent_total', 'Total messages sent to DLQ', ['error_type'])

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        schema_registry_url: str = "http://localhost:8081",
        kafka_topic: str = "alpr.events.plates",
        kafka_group_id: str = "alpr-storage-consumer",
        db_host: str = "localhost",
        db_port: int = 5432,
        db_name: str = "alpr_db",
        db_user: str = "alpr",
        db_password: str = "alpr_secure_pass",
        auto_offset_reset: str = "latest",
        max_retries: int = 3,
        retry_delay_base: float = 2.0,
        processing_timeout: float = 30.0,
        enable_dlq: bool = True,
        dlq_topic: str = "alpr.dlq",
    ):
        """
        Initialize Avro Kafka consumer

        Args:
            kafka_bootstrap_servers: Kafka broker addresses
            schema_registry_url: Schema Registry URL
            kafka_topic: Topic to consume from
            kafka_group_id: Consumer group ID
            db_host: Database host
            db_port: Database port
            db_name: Database name
            db_user: Database user
            db_password: Database password
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
        self.storage = None
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
            'stored': 0,
            'failed': 0,
            'skipped': 0,
            'retried': 0,
            'timeout': 0,
            'dlq_sent': 0,
        }

        # Initialize Schema Registry client
        self.schema_registry_client = SchemaRegistryClient({
            'url': schema_registry_url
        })

        # Create Avro deserializer
        # from_dict: Identity function returns deserialized dict as-is (obj=deserialized dict, ctx=unused)
        self.avro_deserializer = AvroDeserializer(
            self.schema_registry_client,
            from_dict=lambda obj, ctx: obj  # Events are already dicts, no transformation needed
        )

        # String deserializer for keys
        self.string_deserializer = StringDeserializer('utf_8')

        # Consumer configuration
        self.config = {
            'bootstrap.servers': kafka_bootstrap_servers,
            'group.id': kafka_group_id,
            'auto.offset.reset': auto_offset_reset,
            'enable.auto.commit': True,  # Auto-commit offsets to prevent message reprocessing on restart
            'key.deserializer': self.string_deserializer,
            'value.deserializer': self.avro_deserializer,
        }

        # Initialize storage service
        self.storage = StorageService(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password
        )

        # Initialize DLQ producer if enabled
        if self.enable_dlq:
            self._init_dlq_producer()

        # Initialize consumer
        self._connect()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start Prometheus metrics HTTP server on port 8002
        try:
            start_http_server(8002)
            logger.success("✅ Prometheus metrics endpoint started at http://localhost:8002/metrics")
        except Exception as e:
            logger.warning(f"⚠️  Failed to start Prometheus metrics server: {e}")

    def _connect(self):
        """Establish connection to Kafka broker"""
        try:
            self.consumer = DeserializingConsumer(self.config)
            logger.success(
                f"✅ Connected to Kafka (Avro): {self.kafka_bootstrap_servers}\n"
                f"   Schema Registry: {self.schema_registry_url}\n"
                f"   Group ID: {self.config['group.id']}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    def _init_dlq_producer(self):
        """Initialize DLQ producer with Avro serialization"""
        try:
            # Load DLQ schema
            import os
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
                to_dict=lambda obj, ctx: obj  # DLQ messages are already dicts
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
                key=self.dlq_topic.encode('utf-8'),  # Use original_topic as partition key
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

                # Attempt to store in database
                db_insert_start = time.time()
                success = self.storage.insert_event(event_data)
                db_insert_time = time.time() - db_insert_start

                # Record DB insert time
                self.metrics_db_insert_time.observe(db_insert_time)

                if success:
                    if attempt > 0:
                        logger.info(f"✅ Succeeded on retry attempt {attempt + 1}/{self.max_retries}")
                    return True
                else:
                    raise Exception("Database insert returned False")

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

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.warning(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def start(self):
        """
        Start consuming messages from Kafka

        This is a blocking operation that runs until stopped.
        """
        try:
            # Subscribe to topic
            self.consumer.subscribe([self.kafka_topic])
            logger.success(f"📥 Subscribed to topic: {self.kafka_topic}")

            self.running = True
            logger.info("🔄 Starting message consumption loop...")

            while self.running:
                try:
                    # Poll for messages (1s timeout balances responsiveness and CPU usage)
                    msg = self.consumer.poll(timeout=1.0)

                    if msg is None:
                        continue

                    if msg.error():
                        logger.error(f"Consumer error: {msg.error()}")
                        continue

                    # Message received - start timing
                    processing_start = time.time()

                    # Deserialize automatically by confluent-kafka
                    event_data = msg.value()
                    self.stats['consumed'] += 1

                    # Metrics: Record consumed message
                    self.metrics_consumed.inc()

                    if event_data is None:
                        logger.warning("Received null message, skipping")
                        self.stats['skipped'] += 1
                        # Metrics: Record skipped message
                        self.metrics_skipped.inc()
                        continue

                    # Log message details
                    event_id = event_data.get('event_id', 'unknown')
                    plate_text = event_data.get('plate', {}).get('normalized_text', 'unknown')
                    camera_id = event_data.get('camera_id', 'unknown')

                    logger.debug(
                        f"📨 Consumed message: "
                        f"event_id={event_id}, "
                        f"plate={plate_text}, "
                        f"camera={camera_id}"
                    )

                    # Process with retry logic and timeout detection
                    success = self._process_with_retry(msg, event_data)

                    if success:
                        self.stats['stored'] += 1
                        self.metrics_stored.inc()

                        logger.info(
                            f"✅ Stored event: {plate_text} from {camera_id} "
                            f"(offset: {msg.offset()})"
                        )
                    else:
                        self.stats['failed'] += 1
                        self.metrics_failed.inc()
                        # Error logging and DLQ handling already done in _process_with_retry

                    # Metrics: Record total processing time
                    processing_time = time.time() - processing_start
                    self.metrics_processing_time.observe(processing_time)

                    # Log stats every 100 messages (balance between visibility and log volume)
                    if self.stats['consumed'] % 100 == 0:
                        self._log_stats()

                except KeyboardInterrupt:
                    logger.warning("Interrupted by user")
                    self.running = False
                    break
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    self.stats['failed'] += 1
                    # Metrics: Record failed message
                    self.metrics_failed.inc()
                    continue

        except Exception as e:
            logger.error(f"Consumer error: {e}")
            raise
        finally:
            self.stop()

    def stop(self):
        """Stop consumer and cleanup"""
        logger.info("Stopping Avro Kafka consumer...")

        if self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer closed")

        if self.storage:
            self.storage.close()
            logger.info("Database connection closed")

        self._log_stats()
        logger.success("✅ Consumer stopped gracefully")

    def _log_stats(self):
        """Log consumer statistics"""
        logger.info(
            f"📊 Stats: consumed={self.stats['consumed']}, "
            f"stored={self.stats['stored']}, "
            f"failed={self.stats['failed']}, "
            f"skipped={self.stats['skipped']}, "
            f"retried={self.stats['retried']}, "
            f"timeout={self.stats['timeout']}, "
            f"dlq_sent={self.stats['dlq_sent']}"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics"""
        return {
            **self.stats,
            'kafka_topic': self.kafka_topic,
            'schema_registry_url': self.schema_registry_url,
            'running': self.running,
        }


def main():
    """Main entry point for Avro Kafka consumer"""
    import os

    # Get configuration from environment variables
    kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    schema_registry_url = os.getenv('SCHEMA_REGISTRY_URL', 'http://localhost:8081')
    kafka_topic = os.getenv('KAFKA_TOPIC', 'alpr.events.plates')
    kafka_group_id = os.getenv('KAFKA_GROUP_ID', 'alpr-storage-consumer')

    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = int(os.getenv('DB_PORT', 5432))
    db_name = os.getenv('DB_NAME', 'alpr_db')
    db_user = os.getenv('DB_USER', 'alpr')
    db_password = os.getenv('DB_PASSWORD', 'alpr_secure_pass')

    auto_offset_reset = os.getenv('AUTO_OFFSET_RESET', 'latest')

    # DLQ and retry configuration
    max_retries = int(os.getenv('MAX_RETRIES', '3'))
    retry_delay_base = float(os.getenv('RETRY_DELAY_BASE', '2.0'))
    processing_timeout = float(os.getenv('PROCESSING_TIMEOUT', '30.0'))
    enable_dlq = os.getenv('ENABLE_DLQ', 'true').lower() == 'true'
    dlq_topic = os.getenv('DLQ_TOPIC', 'alpr.dlq')

    logger.info("=" * 70)
    logger.info("🚀 ALPR Avro Kafka Consumer (with DLQ & Retry)")
    logger.info("=" * 70)
    logger.info(f"Kafka Servers: {kafka_servers}")
    logger.info(f"Schema Registry: {schema_registry_url}")
    logger.info(f"Topic: {kafka_topic}")
    logger.info(f"Group ID: {kafka_group_id}")
    logger.info(f"Database: {db_host}:{db_port}/{db_name}")
    logger.info(f"Auto Offset Reset: {auto_offset_reset}")
    logger.info(f"Max Retries: {max_retries}")
    logger.info(f"Retry Delay Base: {retry_delay_base}s")
    logger.info(f"Processing Timeout: {processing_timeout}s")
    logger.info(f"DLQ Enabled: {enable_dlq}")
    logger.info(f"DLQ Topic: {dlq_topic}")
    logger.info("=" * 70)

    # Create and start consumer
    try:
        consumer = AvroKafkaConsumer(
            kafka_bootstrap_servers=kafka_servers,
            schema_registry_url=schema_registry_url,
            kafka_topic=kafka_topic,
            kafka_group_id=kafka_group_id,
            db_host=db_host,
            db_port=db_port,
            db_name=db_name,
            db_user=db_user,
            db_password=db_password,
            auto_offset_reset=auto_offset_reset,
            max_retries=max_retries,
            retry_delay_base=retry_delay_base,
            processing_timeout=processing_timeout,
            enable_dlq=enable_dlq,
            dlq_topic=dlq_topic,
        )

        consumer.start()

    except Exception as e:
        logger.error(f"Consumer failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
