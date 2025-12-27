#!/usr/bin/env python3
"""
Avro Kafka Consumer for ALPR Events
Consumes PlateEvent messages from Kafka using Avro deserialization with Schema Registry
"""

import signal
import sys
import time
from typing import Optional, Dict, Any
from loguru import logger

try:
    from confluent_kafka import DeserializingConsumer
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroDeserializer
    from confluent_kafka.serialization import StringDeserializer
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

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        schema_registry_url: str = "http://localhost:8081",
        kafka_topic: str = "alpr.plates.detected",
        kafka_group_id: str = "alpr-avro-consumer",
        db_host: str = "localhost",
        db_port: int = 5432,
        db_name: str = "alpr_db",
        db_user: str = "alpr",
        db_password: str = "alpr_secure_pass",
        auto_offset_reset: str = "latest",
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
        """
        if not CONFLUENT_KAFKA_AVAILABLE:
            raise ImportError(
                "confluent-kafka not installed. "
                "Run: pip install confluent-kafka[avro]"
            )

        self.kafka_topic = kafka_topic
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.schema_registry_url = schema_registry_url
        self.consumer = None
        self.storage = None
        self.running = False

        # Statistics
        self.stats = {
            'consumed': 0,
            'stored': 0,
            'failed': 0,
            'skipped': 0,
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

                    # Store in database - time the operation
                    db_insert_start = time.time()
                    success = self.storage.insert_event(event_data)
                    db_insert_time = time.time() - db_insert_start

                    # Metrics: Record DB insert time
                    self.metrics_db_insert_time.observe(db_insert_time)

                    if success:
                        self.stats['stored'] += 1
                        # Metrics: Record stored message
                        self.metrics_stored.inc()

                        logger.info(
                            f"✅ Stored event: {plate_text} from {camera_id} "
                            f"(offset: {msg.offset()})"
                        )
                    else:
                        self.stats['failed'] += 1
                        # Metrics: Record failed message
                        self.metrics_failed.inc()

                        logger.error(f"❌ Failed to store event: {event_id}")

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
            f"skipped={self.stats['skipped']}"
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
    kafka_topic = os.getenv('KAFKA_TOPIC', 'alpr.plates.detected')
    kafka_group_id = os.getenv('KAFKA_GROUP_ID', 'alpr-avro-consumer')

    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = int(os.getenv('DB_PORT', 5432))
    db_name = os.getenv('DB_NAME', 'alpr_db')
    db_user = os.getenv('DB_USER', 'alpr')
    db_password = os.getenv('DB_PASSWORD', 'alpr_secure_pass')

    auto_offset_reset = os.getenv('AUTO_OFFSET_RESET', 'latest')

    logger.info("=" * 70)
    logger.info("🚀 ALPR Avro Kafka Consumer")
    logger.info("=" * 70)
    logger.info(f"Kafka Servers: {kafka_servers}")
    logger.info(f"Schema Registry: {schema_registry_url}")
    logger.info(f"Topic: {kafka_topic}")
    logger.info(f"Group ID: {kafka_group_id}")
    logger.info(f"Database: {db_host}:{db_port}/{db_name}")
    logger.info(f"Auto Offset Reset: {auto_offset_reset}")
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
        )

        consumer.start()

    except Exception as e:
        logger.error(f"Consumer failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
