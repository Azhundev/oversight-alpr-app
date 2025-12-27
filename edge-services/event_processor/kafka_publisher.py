#!/usr/bin/env python3
"""
Kafka Publisher for ALPR Events
Publishes PlateEvent objects to Kafka topics
"""

import json
from typing import Optional, Dict, Any
from loguru import logger

try:
    from kafka import KafkaProducer
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("kafka-python not installed. Run: pip install kafka-python")


class KafkaPublisher:
    """
    Kafka publisher for ALPR events
    Handles connection, serialization, and publishing to Kafka topics
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic: str = "alpr.plates.detected",
        client_id: str = "alpr-jetson-producer",
        compression_type: str = "gzip",  # gzip, snappy, lz4, or None
        max_request_size: int = 1048576,  # 1MB
        acks: str = "all",  # 'all', '0', '1'
        retries: int = 3,
        enable_idempotence: bool = True,
    ):
        """
        Initialize Kafka publisher

        Args:
            bootstrap_servers: Kafka broker addresses (comma-separated)
            topic: Default topic for plate events
            client_id: Client identifier for Kafka
            compression_type: Compression algorithm (gzip recommended)
            max_request_size: Maximum message size in bytes
            acks: Acknowledgment level ('all' for strongest guarantee)
            retries: Number of retries on failure
            enable_idempotence: Enable idempotent producer (exactly-once)
        """
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python not installed. Run: pip install kafka-python")

        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.producer = None
        self.is_connected = False

        # Producer configuration
        self.config = {
            'bootstrap_servers': bootstrap_servers.split(','),
            'client_id': client_id,
            'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
            'compression_type': compression_type,
            'max_request_size': max_request_size,
            'acks': acks,
            'retries': retries,
            'enable_idempotence': enable_idempotence,
        }

        # Initialize producer
        self._connect()

    def _connect(self):
        """Establish connection to Kafka broker"""
        try:
            self.producer = KafkaProducer(**self.config)
            self.is_connected = True
            logger.success(f"✅ Connected to Kafka: {self.bootstrap_servers}")
        except Exception as e:
            self.is_connected = False
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    def publish_event(
        self,
        event_dict: Dict[str, Any],
        topic: Optional[str] = None,
        key: Optional[str] = None,
    ) -> bool:
        """
        Publish a single event to Kafka

        Args:
            event_dict: Event payload as dictionary (from PlateEvent.to_dict())
            topic: Topic to publish to (defaults to configured topic)
            key: Optional partition key (e.g., camera_id for ordering)

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected:
            logger.error("Not connected to Kafka")
            return False

        topic = topic or self.topic

        try:
            # Use camera_id as partition key if not provided (ensures ordering per camera)
            if key is None and 'camera_id' in event_dict:
                key = event_dict['camera_id']

            # Encode key
            key_bytes = key.encode('utf-8') if key else None

            # Send to Kafka (async)
            future = self.producer.send(
                topic=topic,
                value=event_dict,
                key=key_bytes,
            )

            # Block until message is sent (for reliability)
            record_metadata = future.get(timeout=10)

            logger.debug(
                f"📤 Published to Kafka: topic={record_metadata.topic}, "
                f"partition={record_metadata.partition}, offset={record_metadata.offset}"
            )

            return True

        except KafkaError as e:
            logger.error(f"Kafka error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            return False

    def publish_batch(
        self,
        events: list,
        topic: Optional[str] = None,
    ) -> int:
        """
        Publish multiple events in a batch

        Args:
            events: List of event dictionaries
            topic: Topic to publish to

        Returns:
            Number of successfully published events
        """
        success_count = 0
        for event in events:
            if self.publish_event(event, topic=topic):
                success_count += 1

        return success_count

    def flush(self, timeout: int = 30):
        """
        Flush pending messages (block until all sent)

        Args:
            timeout: Timeout in seconds
        """
        if self.is_connected and self.producer:
            self.producer.flush(timeout=timeout)
            logger.debug("Flushed Kafka producer queue")

    def close(self):
        """Close Kafka producer connection"""
        if self.producer:
            self.producer.flush()
            self.producer.close()
            self.is_connected = False
            logger.info("Kafka producer closed")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get publisher statistics

        Returns:
            Dictionary of stats
        """
        return {
            'is_connected': self.is_connected,
            'bootstrap_servers': self.bootstrap_servers,
            'topic': self.topic,
        }

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


class MockKafkaPublisher:
    """
    Mock Kafka publisher for testing without Kafka broker
    Prints events to console instead of publishing
    """

    def __init__(self, bootstrap_servers: str = "localhost:9092", topic: str = "alpr.plates.detected", **kwargs):
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.is_connected = True
        self.published_events = []  # Store for testing
        logger.warning(f"🔧 Using MockKafkaPublisher (no real Kafka connection)")

    def publish_event(self, event_dict: Dict[str, Any], topic: Optional[str] = None, key: Optional[str] = None) -> bool:
        topic = topic or self.topic
        self.published_events.append(event_dict)

        logger.info(
            f"📤 [MOCK] Would publish to Kafka:\n"
            f"  Topic: {topic}\n"
            f"  Key: {key or event_dict.get('camera_id', 'none')}\n"
            f"  Event ID: {event_dict.get('event_id', 'unknown')}\n"
            f"  Plate: {event_dict.get('plate', {}).get('normalized_text', 'unknown')}"
        )

        return True

    def publish_batch(self, events: list, topic: Optional[str] = None) -> int:
        for event in events:
            self.publish_event(event, topic=topic)
        return len(events)

    def flush(self, timeout: int = 30):
        logger.debug("[MOCK] Flush called (no-op)")

    def close(self):
        logger.info(f"[MOCK] Kafka publisher closed. Total events: {len(self.published_events)}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            'is_connected': self.is_connected,
            'bootstrap_servers': self.bootstrap_servers,
            'topic': self.topic,
            'total_published': len(self.published_events),
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
