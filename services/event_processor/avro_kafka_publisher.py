#!/usr/bin/env python3
"""
Avro Kafka Publisher for ALPR Events
Publishes PlateEvent objects to Kafka using Avro serialization with Schema Registry
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger

try:
    from confluent_kafka import SerializingProducer
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroSerializer
    from confluent_kafka.serialization import StringSerializer
    CONFLUENT_KAFKA_AVAILABLE = True
except ImportError:
    CONFLUENT_KAFKA_AVAILABLE = False
    logger.warning("confluent-kafka not installed. Run: pip install confluent-kafka")


class AvroKafkaPublisher:
    """
    Avro Kafka publisher for ALPR events with Schema Registry integration

    Uses Confluent Kafka with Avro serialization for schema validation and evolution.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        schema_registry_url: str = "http://localhost:8081",
        topic: str = "alpr.plates.detected",
        schema_file: Optional[str] = None,
        client_id: str = "alpr-avro-producer",
        compression_type: str = "gzip",
        acks: str = "all",
    ):
        """
        Initialize Avro Kafka publisher

        Args:
            bootstrap_servers: Kafka broker addresses
            schema_registry_url: Schema Registry URL
            topic: Topic for plate events
            schema_file: Path to Avro schema file (.avsc)
            client_id: Client identifier
            compression_type: Compression algorithm (gzip, snappy, lz4, zstd)
            acks: Acknowledgment level ('all', '0', '1')
        """
        if not CONFLUENT_KAFKA_AVAILABLE:
            raise ImportError(
                "confluent-kafka not installed. "
                "Run: pip install confluent-kafka"
            )

        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.schema_registry_url = schema_registry_url
        self.producer = None
        self.is_connected = False

        # Initialize Schema Registry client
        self.schema_registry_client = SchemaRegistryClient({
            'url': schema_registry_url
        })

        # Load Avro schema
        if schema_file is None:
            # Default to plate_event.avsc in schemas directory
            schema_file = Path(__file__).parent.parent.parent / "schemas" / "plate_event.avsc"

        self.schema_str = self._load_schema(schema_file)

        # Create Avro serializer
        self.avro_serializer = AvroSerializer(
            self.schema_registry_client,
            self.schema_str,
            to_dict=lambda obj, ctx: obj  # Events are already dicts
        )

        # String serializer for keys
        self.string_serializer = StringSerializer('utf_8')

        # Producer configuration
        self.config = {
            'bootstrap.servers': bootstrap_servers,
            'client.id': client_id,
            'compression.type': compression_type,
            'acks': acks,
            'key.serializer': self.string_serializer,
            'value.serializer': self.avro_serializer,
        }

        # Initialize producer
        self._connect()

    def _load_schema(self, schema_file: Path) -> str:
        """
        Load Avro schema from file

        Args:
            schema_file: Path to .avsc file

        Returns:
            Schema as JSON string
        """
        try:
            with open(schema_file, 'r') as f:
                schema_dict = json.load(f)
            schema_str = json.dumps(schema_dict)
            logger.success(f"✅ Loaded Avro schema: {schema_file}")
            return schema_str
        except FileNotFoundError:
            logger.error(f"Schema file not found: {schema_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in schema file: {e}")
            raise

    def _connect(self):
        """Establish connection to Kafka broker"""
        try:
            self.producer = SerializingProducer(self.config)
            self.is_connected = True
            logger.success(
                f"✅ Connected to Kafka (Avro): {self.bootstrap_servers}\n"
                f"   Schema Registry: {self.schema_registry_url}"
            )
        except Exception as e:
            self.is_connected = False
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    def _delivery_report(self, err, msg):
        """
        Delivery callback for async publishing

        Args:
            err: Error object (None if successful)
            msg: Message object
        """
        if err is not None:
            logger.error(f"❌ Delivery failed: {err}")
        else:
            logger.debug(
                f"📤 Delivered to Kafka: topic={msg.topic()}, "
                f"partition={msg.partition()}, offset={msg.offset()}"
            )

    def publish_event(
        self,
        event_dict: Dict[str, Any],
        topic: Optional[str] = None,
        key: Optional[str] = None,
    ) -> bool:
        """
        Publish a single event to Kafka with Avro serialization

        Args:
            event_dict: Event payload as dictionary (from PlateEvent.to_dict())
            topic: Topic to publish to (defaults to configured topic)
            key: Optional partition key (e.g., camera_id for ordering)

        Returns:
            True if queued successfully, False otherwise
        """
        if not self.is_connected:
            logger.error("Not connected to Kafka")
            return False

        topic = topic or self.topic

        try:
            # Use camera_id as partition key if not provided
            if key is None and 'camera_id' in event_dict:
                key = event_dict['camera_id']

            # Publish (async with callback)
            self.producer.produce(
                topic=topic,
                key=key,
                value=event_dict,
                on_delivery=self._delivery_report
            )

            # Trigger any available delivery callbacks
            self.producer.poll(0)

            return True

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
            Number of successfully queued events
        """
        success_count = 0
        for event in events:
            if self.publish_event(event, topic=topic):
                success_count += 1

        # Trigger delivery for all pending messages
        self.producer.poll(0.1)

        return success_count

    def flush(self, timeout: float = 30.0):
        """
        Flush pending messages (block until all sent)

        Args:
            timeout: Timeout in seconds
        """
        if self.is_connected and self.producer:
            remaining = self.producer.flush(timeout=timeout)
            if remaining > 0:
                logger.warning(f"⚠️  {remaining} messages still pending after flush")
            else:
                logger.debug("✅ All messages flushed successfully")

    def close(self):
        """Close Kafka producer connection"""
        if self.producer:
            self.producer.flush()
            self.is_connected = False
            logger.info("Avro Kafka producer closed")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get publisher statistics

        Returns:
            Dictionary of stats
        """
        return {
            'is_connected': self.is_connected,
            'bootstrap_servers': self.bootstrap_servers,
            'schema_registry_url': self.schema_registry_url,
            'topic': self.topic,
            'serialization': 'avro',
        }

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


# Example usage
if __name__ == "__main__":
    # Create publisher
    publisher = AvroKafkaPublisher(
        bootstrap_servers="localhost:9092",
        schema_registry_url="http://localhost:8081",
        topic="alpr.plates.detected"
    )

    # Example event (matching Avro schema)
    test_event = {
        "event_id": "test-uuid-123",
        "captured_at": "2025-12-25T16:00:00Z",
        "camera_id": "CAM1",
        "track_id": "t-42",
        "plate": {
            "text": "ABC1234",
            "normalized_text": "ABC1234",
            "confidence": 0.95,
            "region": "US-FL"
        },
        "vehicle": {
            "type": "car",
            "make": None,
            "model": None,
            "color": None
        },
        "images": {
            "plate_url": "s3://bucket/plate.jpg",
            "vehicle_url": None,
            "frame_url": None
        },
        "latency_ms": 85,
        "node": {
            "site": "DC1",
            "host": "jetson-orin-nx"
        },
        "extras": {
            "roi": None,
            "direction": None,
            "quality_score": 0.85,
            "frame_number": 123
        }
    }

    # Publish
    publisher.publish_event(test_event)
    publisher.flush()
    publisher.close()

    print("✅ Test event published successfully!")
