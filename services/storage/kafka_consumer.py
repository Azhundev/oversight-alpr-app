#!/usr/bin/env python3
"""
Kafka Consumer for ALPR Events
Consumes plate detection events from Kafka and persists to TimescaleDB
"""

import json
import os
import signal
import sys
from typing import Optional
from loguru import logger
from time import sleep

try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("kafka-python not installed. Run: pip install kafka-python")

from services.storage.storage_service import StorageService


class KafkaStorageConsumer:
    """
    Kafka consumer that reads plate events and stores them in TimescaleDB
    Runs as a background service with graceful shutdown
    """

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "alpr.plates.detected",
        kafka_group_id: str = "alpr-storage-consumer",
        db_host: str = "localhost",
        db_port: int = 5432,
        db_name: str = "alpr_db",
        db_user: str = "alpr",
        db_password: str = "alpr_secure_pass",
        auto_offset_reset: str = "latest",  # Where to start if no offset exists: 'latest' (only new messages) or 'earliest' (replay all from beginning)
        enable_auto_commit: bool = True,  # Auto-commit offsets to prevent message reprocessing on restart (committed every 5s by default)
        max_poll_records: int = 100,  # Maximum records fetched per poll (balance between throughput and memory usage)
    ):
        """
        Initialize Kafka consumer and storage service

        Args:
            kafka_bootstrap_servers: Kafka broker addresses
            kafka_topic: Topic to subscribe to
            kafka_group_id: Consumer group ID
            db_host: Database host
            db_port: Database port
            db_name: Database name
            db_user: Database user
            db_password: Database password
            auto_offset_reset: Where to start consuming ('earliest' or 'latest')
            enable_auto_commit: Enable automatic offset commits
            max_poll_records: Maximum records per poll
        """
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python not installed. Run: pip install kafka-python")

        self.topic = kafka_topic
        self.consumer: Optional[KafkaConsumer] = None
        self.storage: Optional[StorageService] = None
        self.is_running = False

        # Stats
        self.total_consumed = 0
        self.total_stored = 0
        self.failed_stores = 0

        # Kafka configuration for JSON message consumption
        self.kafka_config = {
            'bootstrap_servers': kafka_bootstrap_servers.split(','),  # Split comma-separated broker list into array
            'group_id': kafka_group_id,  # Consumer group for offset coordination across multiple consumers
            'auto_offset_reset': auto_offset_reset,  # Offset reset policy when no committed offset exists
            'enable_auto_commit': enable_auto_commit,  # Automatically commit offsets periodically (prevents duplicate processing)
            'value_deserializer': lambda m: json.loads(m.decode('utf-8')),  # Deserialize JSON messages: bytes → UTF-8 string → dict
            'max_poll_records': max_poll_records,  # Limit records per poll to control batch size and memory
        }

        # Database configuration
        self.db_config = {
            'host': db_host,
            'port': db_port,
            'database': db_name,
            'user': db_user,
            'password': db_password,
        }

        # Initialize storage service
        logger.info("Initializing storage service...")
        self.storage = StorageService(**self.db_config)

        # Initialize Kafka consumer
        logger.info("Initializing Kafka consumer...")
        self._connect_kafka()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _connect_kafka(self):
        """Connect to Kafka broker"""
        try:
            self.consumer = KafkaConsumer(
                self.topic,
                **self.kafka_config
            )
            logger.success(f"✅ Connected to Kafka topic: {self.topic}")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)

    def start(self):
        """
        Start consuming messages from Kafka
        Runs in an infinite loop until stopped
        """
        if not self.consumer or not self.storage:
            logger.error("Consumer or storage not initialized")
            return

        self.is_running = True
        logger.info(f"🚀 Starting Kafka consumer (topic: {self.topic})")

        try:
            # Consume messages in an infinite loop (blocking iterator)
            # KafkaConsumer.poll() is called internally, fetching batches up to max_poll_records
            for message in self.consumer:
                if not self.is_running:
                    break

                try:
                    # Deserialize event from Kafka message (automatically deserialized by value_deserializer)
                    event_dict = message.value
                    self.total_consumed += 1

                    # Extract metadata for logging
                    event_id = event_dict.get('event_id', 'unknown')
                    plate_text = event_dict.get('plate', {}).get('normalized_text', 'unknown')
                    camera_id = event_dict.get('camera_id', 'unknown')

                    logger.debug(
                        f"📥 Consumed from Kafka: partition={message.partition}, "
                        f"offset={message.offset}, plate={plate_text}"
                    )

                    # Store event in database
                    success = self.storage.insert_event(event_dict)

                    if success:
                        self.total_stored += 1
                        logger.success(
                            f"💾 Stored event: {plate_text} "
                            f"(event: {event_id}, camera: {camera_id})"
                        )
                    else:
                        self.failed_stores += 1
                        logger.warning(f"Failed to store event: {event_id}")

                    # Log stats periodically every 100 messages (balance between visibility and log volume)
                    if self.total_consumed % 100 == 0:
                        self._log_stats()

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message: {e}")

                except Exception as e:
                    self.failed_stores += 1
                    logger.error(f"Error processing message: {e}")

        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")

        except Exception as e:
            logger.error(f"Consumer error: {e}")

        finally:
            self.stop()

    def stop(self):
        """Stop consumer and close connections gracefully"""
        logger.info("Stopping Kafka consumer...")
        self.is_running = False

        if self.consumer:
            # Close consumer (commits pending offsets if auto_commit enabled, leaves consumer group)
            self.consumer.close()
            logger.info("Kafka consumer closed")

        if self.storage:
            self.storage.close()

        self._log_stats()

    def _log_stats(self):
        """Log consumer statistics"""
        logger.info(
            f"📊 Consumer Stats: "
            f"Consumed={self.total_consumed}, "
            f"Stored={self.total_stored}, "
            f"Failed={self.failed_stores}"
        )

    def get_stats(self) -> dict:
        """
        Get consumer statistics

        Returns:
            Dictionary of stats
        """
        stats = {
            'total_consumed': self.total_consumed,
            'total_stored': self.total_stored,
            'failed_stores': self.failed_stores,
            'is_running': self.is_running,
        }

        # Add storage stats
        if self.storage:
            storage_stats = self.storage.get_stats()
            stats['storage'] = storage_stats

        return stats


def main():
    """
    Main entry point for running consumer as standalone service

    Reads configuration from environment variables with fallback to defaults.
    This allows Docker containers to override settings without code changes.
    """
    logger.info("=== ALPR Kafka Storage Consumer ===")

    # Read configuration from environment variables (with defaults for local development)
    kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic = os.getenv("KAFKA_TOPIC", "alpr.plates.detected")
    kafka_group_id = os.getenv("KAFKA_GROUP_ID", "alpr-storage-consumer")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME", "alpr_db")
    db_user = os.getenv("DB_USER", "alpr")
    db_password = os.getenv("DB_PASSWORD", "alpr_secure_pass")
    auto_offset_reset = os.getenv("AUTO_OFFSET_RESET", "latest")

    logger.info(f"Kafka: {kafka_bootstrap_servers} | Topic: {kafka_topic}")
    logger.info(f"Database: {db_host}:{db_port}/{db_name}")

    # Create consumer
    consumer = KafkaStorageConsumer(
        kafka_bootstrap_servers=kafka_bootstrap_servers,
        kafka_topic=kafka_topic,
        kafka_group_id=kafka_group_id,
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_password,
        auto_offset_reset=auto_offset_reset,
    )

    # Start consuming
    try:
        consumer.start()
    except Exception as e:
        logger.error(f"Consumer failed: {e}")
        consumer.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
