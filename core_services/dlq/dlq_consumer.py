#!/usr/bin/env python3
"""
Dead Letter Queue Consumer
Monitors DLQ topic, logs failed messages, exposes metrics, and optionally replays messages
"""

import os
import signal
import sys
from typing import Dict, Any
from loguru import logger

from confluent_kafka import DeserializingConsumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import StringDeserializer

from prometheus_client import Counter, Gauge, start_http_server


class DLQConsumer:
    """
    Consumer for dead letter queue monitoring and alerting
    """

    # Prometheus metrics
    metrics_dlq_messages = Counter(
        'dlq_messages_total',
        'Total DLQ messages processed',
        ['error_type', 'original_topic']
    )
    metrics_dlq_age = Gauge(
        'dlq_oldest_message_age_seconds',
        'Age of oldest unprocessed DLQ message'
    )

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        schema_registry_url: str = "http://localhost:8081",
        kafka_topic: str = "alpr.dlq",
        kafka_group_id: str = "alpr-dlq-consumer",
        auto_offset_reset: str = "earliest",  # Process all DLQ messages from beginning
        metrics_port: int = 8005,
    ):
        self.kafka_topic = kafka_topic
        self.running = False

        # Schema Registry client
        self.schema_registry_client = SchemaRegistryClient({'url': schema_registry_url})

        # Avro deserializer for DLQ messages
        self.avro_deserializer = AvroDeserializer(
            self.schema_registry_client,
            from_dict=lambda obj, ctx: obj
        )

        # Consumer configuration
        self.config = {
            'bootstrap.servers': kafka_bootstrap_servers,
            'group.id': kafka_group_id,
            'auto.offset.reset': auto_offset_reset,
            'enable.auto.commit': True,
            'key.deserializer': StringDeserializer('utf_8'),
            'value.deserializer': self.avro_deserializer,
        }

        # Initialize consumer
        self.consumer = DeserializingConsumer(self.config)

        # Statistics
        self.stats = {
            'consumed': 0,
            'schema_validation': 0,
            'processing_failure': 0,
            'timeout': 0,
            'business_logic': 0,
            'unknown': 0,
        }

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start metrics server
        start_http_server(metrics_port)
        logger.success(f"✅ Prometheus metrics server started at http://localhost:{metrics_port}/metrics")

    def _signal_handler(self, signum, frame):
        logger.warning(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def start(self):
        """Start consuming DLQ messages"""
        self.consumer.subscribe([self.kafka_topic])
        logger.success(f"✅ Subscribed to DLQ topic: {self.kafka_topic}")

        self.running = True
        logger.info("🔍 Starting DLQ monitoring...")

        while self.running:
            try:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue

                # Process DLQ message
                dlq_data = msg.value()
                if dlq_data:
                    self._process_dlq_message(dlq_data)
                    self.stats['consumed'] += 1

                    # Log stats every 100 messages
                    if self.stats['consumed'] % 100 == 0:
                        self._log_stats()

            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error processing DLQ message: {e}", exc_info=True)
                continue

        self.stop()

    def _process_dlq_message(self, dlq_data: Dict):
        """Process and log DLQ message"""
        try:
            dlq_id = dlq_data.get('dlq_id', 'unknown')
            error_type = dlq_data.get('error_type', 'UNKNOWN')
            original_topic = dlq_data.get('original_topic', 'unknown')
            error_message = dlq_data.get('error_message', '')
            consumer_group = dlq_data.get('consumer_group_id', 'unknown')
            retry_count = dlq_data.get('retry_count', 0)
            timestamp = dlq_data.get('timestamp', 'unknown')

            # Update statistics
            error_type_lower = error_type.lower()
            if error_type_lower in self.stats:
                self.stats[error_type_lower] += 1

            # Log DLQ entry
            logger.error(
                f"💀 DLQ Message Received\n"
                f"   ID: {dlq_id}\n"
                f"   Error Type: {error_type}\n"
                f"   Original Topic: {original_topic}\n"
                f"   Consumer Group: {consumer_group}\n"
                f"   Timestamp: {timestamp}\n"
                f"   Retries: {retry_count}\n"
                f"   Error: {error_message}\n"
                f"   Original Message Preview: {dlq_data.get('original_message', '')[:200]}..."
            )

            # Stack trace if available
            if dlq_data.get('error_stack_trace'):
                logger.debug(f"Stack trace:\n{dlq_data['error_stack_trace']}")

            # Update Prometheus metrics
            self.metrics_dlq_messages.labels(
                error_type=error_type,
                original_topic=original_topic
            ).inc()

            # Trigger alert for critical errors
            if error_type in ['SCHEMA_VALIDATION', 'TIMEOUT']:
                self._trigger_dlq_alert(dlq_data)

        except Exception as e:
            logger.error(f"Error processing DLQ entry: {e}")

    def _trigger_dlq_alert(self, dlq_data: Dict):
        """Trigger alert for critical DLQ messages"""
        error_type = dlq_data.get('error_type')
        error_message = dlq_data.get('error_message')
        original_topic = dlq_data.get('original_topic')

        logger.critical(
            f"🚨 CRITICAL DLQ ALERT\n"
            f"   Error Type: {error_type}\n"
            f"   Original Topic: {original_topic}\n"
            f"   Message: {error_message}\n"
            f"   Action Required: Investigate and resolve immediately"
        )

        # TODO: Integrate with alert engine or send email/Slack notification
        # For now, just log critically

    def _log_stats(self):
        """Log DLQ consumer statistics"""
        logger.info(
            f"📊 DLQ Consumer Stats:\n"
            f"   Total Consumed: {self.stats['consumed']}\n"
            f"   Schema Validation: {self.stats['schema_validation']}\n"
            f"   Processing Failure: {self.stats['processing_failure']}\n"
            f"   Timeout: {self.stats['timeout']}\n"
            f"   Business Logic: {self.stats['business_logic']}\n"
            f"   Unknown: {self.stats['unknown']}"
        )

    def stop(self):
        """Stop consumer and cleanup"""
        logger.info("Stopping DLQ consumer...")
        self._log_stats()  # Final stats

        if self.consumer:
            self.consumer.close()

        logger.success("✅ DLQ consumer stopped")


def main():
    """Main entry point"""
    kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    schema_registry_url = os.getenv('SCHEMA_REGISTRY_URL', 'http://localhost:8081')
    kafka_topic = os.getenv('KAFKA_TOPIC', 'alpr.dlq')
    kafka_group_id = os.getenv('KAFKA_GROUP_ID', 'alpr-dlq-consumer')
    auto_offset_reset = os.getenv('AUTO_OFFSET_RESET', 'earliest')
    metrics_port = int(os.getenv('METRICS_PORT', '8005'))

    logger.info("=" * 70)
    logger.info("ALPR Dead Letter Queue Consumer")
    logger.info("=" * 70)
    logger.info(f"Kafka: {kafka_servers}")
    logger.info(f"Schema Registry: {schema_registry_url}")
    logger.info(f"Topic: {kafka_topic}")
    logger.info(f"Group ID: {kafka_group_id}")
    logger.info(f"Offset Reset: {auto_offset_reset}")
    logger.info(f"Metrics Port: {metrics_port}")
    logger.info("=" * 70)

    try:
        consumer = DLQConsumer(
            kafka_bootstrap_servers=kafka_servers,
            schema_registry_url=schema_registry_url,
            kafka_topic=kafka_topic,
            kafka_group_id=kafka_group_id,
            auto_offset_reset=auto_offset_reset,
            metrics_port=metrics_port,
        )
        consumer.start()
    except Exception as e:
        logger.error(f"DLQ consumer failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
