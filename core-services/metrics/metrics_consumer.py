#!/usr/bin/env python3
"""
Metrics Consumer for ALPR System
Consumes system metrics from alpr.metrics topic and exposes for Prometheus scraping
"""

import os
import signal
import sys
from typing import Dict
from loguru import logger

from confluent_kafka import DeserializingConsumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import StringDeserializer

from prometheus_client import Gauge, Counter, start_http_server


class MetricsConsumer:
    """
    Consumer for system metrics from Kafka
    Exposes metrics in Prometheus format
    """

    # Consumer-level metrics
    metrics_consumed = Counter(
        'metrics_consumer_messages_consumed_total',
        'Total metrics messages consumed'
    )
    metrics_processed = Counter(
        'metrics_consumer_messages_processed_total',
        'Total metrics messages processed successfully',
        ['metric_type']
    )
    metrics_failed = Counter(
        'metrics_consumer_messages_failed_total',
        'Total metrics messages that failed processing'
    )

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        schema_registry_url: str = "http://localhost:8081",
        kafka_topic: str = "alpr.metrics",
        kafka_group_id: str = "alpr-metrics-consumer",
        auto_offset_reset: str = "latest",
        metrics_port: int = 8006,
    ):
        self.kafka_topic = kafka_topic
        self.running = False

        # Schema Registry client
        self.schema_registry_client = SchemaRegistryClient({'url': schema_registry_url})

        # Avro deserializer
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

        # Dynamic Prometheus gauges (created based on metric_name)
        self.metric_gauges: Dict[str, Gauge] = {}

        # Statistics
        self.stats = {
            'consumed': 0,
            'processed': 0,
            'failed': 0,
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
        """Start consuming metrics"""
        self.consumer.subscribe([self.kafka_topic])
        logger.success(f"✅ Subscribed to metrics topic: {self.kafka_topic}")

        self.running = True
        logger.info("📊 Starting metrics consumption...")

        while self.running:
            try:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue

                # Process metric
                metric_data = msg.value()
                if metric_data:
                    self.metrics_consumed.inc()
                    self.stats['consumed'] += 1

                    success = self._process_metric(metric_data)

                    if success:
                        self.stats['processed'] += 1
                    else:
                        self.stats['failed'] += 1
                        self.metrics_failed.inc()

                    # Log stats every 100 messages
                    if self.stats['consumed'] % 100 == 0:
                        self._log_stats()

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error processing metric: {e}", exc_info=True)
                self.stats['failed'] += 1
                self.metrics_failed.inc()
                continue

        self.stop()

    def _process_metric(self, metric_data: Dict) -> bool:
        """Process and expose metric"""
        try:
            metric_name = metric_data.get('metric_name')
            value = metric_data.get('value')
            host_id = metric_data.get('host_id')
            site_id = metric_data.get('site_id', 'unknown')
            metric_type = metric_data.get('metric_type', 'CUSTOM')
            unit = metric_data.get('unit', '')
            tags = metric_data.get('tags', {})

            if not metric_name or value is None:
                logger.warning(f"Invalid metric: missing metric_name or value")
                return False

            # Create gauge if not exists
            if metric_name not in self.metric_gauges:
                # Build label names from tags
                label_names = ['host_id', 'site_id'] + list(tags.keys())

                self.metric_gauges[metric_name] = Gauge(
                    f'alpr_{metric_name}',
                    f'ALPR metric: {metric_name} ({unit})',
                    label_names
                )

                logger.info(f"📈 Created new metric gauge: alpr_{metric_name}")

            # Update gauge value
            label_values = [host_id, site_id] + list(tags.values())

            try:
                self.metric_gauges[metric_name].labels(*label_values).set(value)

                logger.debug(
                    f"📊 Updated metric: {metric_name}={value} {unit} "
                    f"(host={host_id}, site={site_id}, tags={tags})"
                )

                # Update processed counter
                self.metrics_processed.labels(metric_type=metric_type).inc()

                return True

            except Exception as e:
                logger.error(f"Error setting gauge value: {e}")
                return False

        except Exception as e:
            logger.error(f"Error processing metric: {e}")
            return False

    def _log_stats(self):
        """Log metrics consumer statistics"""
        logger.info(
            f"📊 Metrics Consumer Stats:\n"
            f"   Total Consumed: {self.stats['consumed']}\n"
            f"   Processed: {self.stats['processed']}\n"
            f"   Failed: {self.stats['failed']}\n"
            f"   Active Gauges: {len(self.metric_gauges)}"
        )

    def stop(self):
        """Stop consumer"""
        logger.info("Stopping metrics consumer...")
        self._log_stats()  # Final stats

        if self.consumer:
            self.consumer.close()

        logger.success("✅ Metrics consumer stopped")


def main():
    """Main entry point"""
    kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    schema_registry_url = os.getenv('SCHEMA_REGISTRY_URL', 'http://localhost:8081')
    kafka_topic = os.getenv('KAFKA_TOPIC', 'alpr.metrics')
    kafka_group_id = os.getenv('KAFKA_GROUP_ID', 'alpr-metrics-consumer')
    auto_offset_reset = os.getenv('AUTO_OFFSET_RESET', 'latest')
    metrics_port = int(os.getenv('METRICS_PORT', '8006'))

    logger.info("=" * 70)
    logger.info("ALPR Metrics Consumer")
    logger.info("=" * 70)
    logger.info(f"Kafka: {kafka_servers}")
    logger.info(f"Schema Registry: {schema_registry_url}")
    logger.info(f"Topic: {kafka_topic}")
    logger.info(f"Group ID: {kafka_group_id}")
    logger.info(f"Offset Reset: {auto_offset_reset}")
    logger.info(f"Metrics Port: {metrics_port}")
    logger.info("=" * 70)

    try:
        consumer = MetricsConsumer(
            kafka_bootstrap_servers=kafka_servers,
            schema_registry_url=schema_registry_url,
            kafka_topic=kafka_topic,
            kafka_group_id=kafka_group_id,
            auto_offset_reset=auto_offset_reset,
            metrics_port=metrics_port,
        )
        consumer.start()
    except Exception as e:
        logger.error(f"Metrics consumer failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
