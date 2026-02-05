#!/usr/bin/env python3
"""
Multi-Topic Avro Kafka Publisher for ALPR Events
Routes events to appropriate Kafka topics based on event type
Supports PlateEvent, VehicleEvent, MetricEvent, and DLQMessage
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger

try:
    from confluent_kafka import Producer
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroSerializer
    from confluent_kafka.serialization import StringSerializer, SerializationContext, MessageField
    CONFLUENT_KAFKA_AVAILABLE = True
except ImportError:
    CONFLUENT_KAFKA_AVAILABLE = False
    logger.warning("confluent-kafka not installed. Run: pip install confluent-kafka")


class MultiTopicAvroPublisher:
    """
    Multi-topic Avro publisher with schema registry support

    Routes events to appropriate topics based on event type:
    - PlateEvent -> alpr.events.plates
    - VehicleEvent -> alpr.events.vehicles
    - MetricEvent -> alpr.metrics
    - DLQMessage -> alpr.dlq

    Supports dual-publish mode for migration from legacy topic.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        schema_registry_url: str = "http://localhost:8081",
        client_id: str = "alpr-multi-topic-producer",
        compression_type: str = "gzip",
        acks: str = "all",
        enable_dual_publish: bool = False,
        legacy_topic: str = "alpr.plates.detected",
    ):
        """
        Initialize multi-topic Avro publisher

        Args:
            bootstrap_servers: Kafka broker addresses
            schema_registry_url: Schema Registry URL
            client_id: Client identifier
            compression_type: Compression algorithm (gzip, snappy, lz4, zstd)
            acks: Acknowledgment level ('all', '0', '1')
            enable_dual_publish: If True, also publish PlateEvents to legacy topic
            legacy_topic: Legacy topic name for dual-publish mode
        """
        if not CONFLUENT_KAFKA_AVAILABLE:
            raise ImportError(
                "confluent-kafka not installed. "
                "Run: pip install confluent-kafka"
            )

        self.bootstrap_servers = bootstrap_servers
        self.schema_registry_url = schema_registry_url
        self.enable_dual_publish = enable_dual_publish
        self.legacy_topic = legacy_topic
        self.is_connected = False

        # Initialize Schema Registry client
        self.schema_registry_client = SchemaRegistryClient({
            'url': schema_registry_url
        })

        # Topic routing map
        self.topic_map = {
            'plate': 'alpr.events.plates',
            'vehicle': 'alpr.events.vehicles',
            'metric': 'alpr.metrics',
            'dlq': 'alpr.dlq',
        }

        # Load all schemas
        self.schemas = {}
        self.serializers = {}
        self._load_schemas()

        # Producer configuration (shared for all topics)
        # Note: We manually serialize values, so no value.serializer in config
        self.config = {
            'bootstrap.servers': bootstrap_servers,
            'client.id': client_id,
            'compression.type': compression_type,
            'acks': acks,
        }

        # Initialize producer
        self._connect()

    def _load_schemas(self):
        """Load all Avro schemas and create serializers"""
        schemas_dir = Path(__file__).parent.parent.parent / "schemas"

        schema_files = {
            'plate': schemas_dir / "plate_event.avsc",
            'vehicle': schemas_dir / "vehicle_event.avsc",
            'metric': schemas_dir / "metric_event.avsc",
            'dlq': schemas_dir / "dlq_message.avsc",
        }

        for event_type, schema_file in schema_files.items():
            try:
                with open(schema_file, 'r') as f:
                    schema_dict = json.load(f)
                schema_str = json.dumps(schema_dict)
                self.schemas[event_type] = schema_str

                # Create Avro serializer for this schema
                self.serializers[event_type] = AvroSerializer(
                    self.schema_registry_client,
                    schema_str,
                    to_dict=lambda obj, ctx: obj  # Events are already dicts
                )

                logger.success(f"✅ Loaded schema: {schema_file.name}")
            except FileNotFoundError:
                logger.error(f"Schema file not found: {schema_file}")
                raise
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in schema {schema_file}: {e}")
                raise

    def _connect(self):
        """Establish connection to Kafka broker"""
        try:
            # Create regular producer (we handle Avro serialization manually per-topic)
            self.producer = Producer(self.config)
            self.is_connected = True

            logger.success(
                f"✅ Multi-topic Kafka producer connected: {self.bootstrap_servers}\n"
                f"   Schema Registry: {self.schema_registry_url}\n"
                f"   Topics: {', '.join(self.topic_map.values())}\n"
                f"   Dual-publish: {'enabled' if self.enable_dual_publish else 'disabled'}"
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
            msg: Message object (can be None if error during produce)
        """
        if err is not None:
            logger.error(f"❌ Delivery failed: {err}")
        elif msg is not None:
            logger.debug(
                f"📤 Delivered: topic={msg.topic()}, "
                f"partition={msg.partition()}, offset={msg.offset()}"
            )
        else:
            logger.warning("⚠️  Delivery callback called with no message")

    def _publish(
        self,
        event_dict: Dict[str, Any],
        event_type: str,
        key: Optional[str] = None,
    ) -> bool:
        """
        Internal publish method with topic routing

        Args:
            event_dict: Event payload as dictionary
            event_type: Event type ('plate', 'vehicle', 'metric', 'dlq')
            key: Optional partition key

        Returns:
            True if queued successfully, False otherwise
        """
        if not self.is_connected:
            logger.error("Not connected to Kafka")
            return False

        topic = self.topic_map[event_type]
        serializer = self.serializers[event_type]

        try:
            # Use appropriate field as partition key if not provided
            if key is None:
                if event_type in ['plate', 'vehicle']:
                    key = event_dict.get('camera_id')
                elif event_type == 'metric':
                    key = event_dict.get('host_id')
                elif event_type == 'dlq':
                    key = event_dict.get('original_topic')

            # Create serialization context with topic name
            ctx = SerializationContext(topic, MessageField.VALUE)

            # Serialize value to Avro bytes
            value_bytes = serializer(event_dict, ctx)

            # Encode key as UTF-8 bytes (required for regular Producer)
            key_bytes = key.encode('utf-8') if key else None

            # Publish
            self.producer.produce(
                topic=topic,
                key=key_bytes,
                value=value_bytes,
                on_delivery=self._delivery_report
            )

            # Trigger delivery callbacks (non-blocking)
            self.producer.poll(0)

            return True

        except Exception as e:
            import traceback
            logger.error(f"Failed to publish {event_type} event: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return False

    def publish_plate_event(
        self,
        event_dict: Dict[str, Any],
        key: Optional[str] = None,
    ) -> bool:
        """
        Publish plate detection event to alpr.events.plates

        Args:
            event_dict: PlateEvent as dictionary
            key: Optional partition key (defaults to camera_id)

        Returns:
            True if published successfully
        """
        success = self._publish(event_dict, 'plate', key)

        # Dual-publish to legacy topic if enabled (for migration)
        if success and self.enable_dual_publish:
            try:
                # Create serialization context for legacy topic
                legacy_ctx = SerializationContext(self.legacy_topic, MessageField.VALUE)

                # Use legacy serializer (plate schema)
                value_bytes = self.serializers['plate'](event_dict, legacy_ctx)
                camera_id = event_dict.get('camera_id')
                key_bytes = camera_id.encode('utf-8') if camera_id else None

                self.producer.produce(
                    topic=self.legacy_topic,
                    key=key_bytes,
                    value=value_bytes,
                    on_delivery=self._delivery_report
                )
                self.producer.poll(0)
                logger.debug(f"📤 Dual-published to legacy topic: {self.legacy_topic}")
            except Exception as e:
                logger.warning(f"Failed to dual-publish to legacy topic: {e}")

        return success

    def publish_vehicle_event(
        self,
        event_dict: Dict[str, Any],
        key: Optional[str] = None,
    ) -> bool:
        """
        Publish vehicle tracking event to alpr.events.vehicles

        Args:
            event_dict: VehicleEvent as dictionary
            key: Optional partition key (defaults to camera_id)

        Returns:
            True if published successfully
        """
        return self._publish(event_dict, 'vehicle', key)

    def publish_metric_event(
        self,
        event_dict: Dict[str, Any],
        key: Optional[str] = None,
    ) -> bool:
        """
        Publish system metric event to alpr.metrics

        Args:
            event_dict: MetricEvent as dictionary
            key: Optional partition key (defaults to host_id)

        Returns:
            True if published successfully
        """
        return self._publish(event_dict, 'metric', key)

    def publish_dlq_message(
        self,
        dlq_dict: Dict[str, Any],
        key: Optional[str] = None,
    ) -> bool:
        """
        Publish dead letter queue message to alpr.dlq

        Args:
            dlq_dict: DLQMessage as dictionary
            key: Optional partition key (defaults to original_topic)

        Returns:
            True if published successfully
        """
        return self._publish(dlq_dict, 'dlq', key)

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
            logger.info("Multi-topic Kafka producer closed")

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
            'topics': self.topic_map,
            'dual_publish_enabled': self.enable_dual_publish,
            'legacy_topic': self.legacy_topic if self.enable_dual_publish else None,
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
    import uuid
    from datetime import datetime

    # Create multi-topic publisher
    publisher = MultiTopicAvroPublisher(
        bootstrap_servers="localhost:9092",
        schema_registry_url="http://localhost:8081",
        enable_dual_publish=False  # Disable for testing
    )

    # Test PlateEvent
    plate_event = {
        "event_id": str(uuid.uuid4()),
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "camera_id": "CAM1",
        "track_id": "t-test-1",
        "plate": {
            "text": "TEST123",
            "normalized_text": "TEST123",
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
            "plate_url": "s3://test/plate.jpg",
            "vehicle_url": None,
            "frame_url": None
        },
        "latency_ms": 100,
        "node": {
            "site": "DC1",
            "host": "jetson-orin-nx"
        },
        "extras": {
            "roi": None,
            "direction": None,
            "quality_score": 0.85,
            "frame_number": 100
        }
    }

    # Test MetricEvent
    metric_event = {
        "metric_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "host_id": "jetson-orin-nx",
        "site_id": "DC1",
        "metric_type": "FPS",
        "metric_name": "pipeline_fps",
        "value": 28.5,
        "unit": "fps",
        "tags": {"camera_id": "CAM1", "service": "pilot"}
    }

    # Publish test events
    print("Publishing test events...")
    publisher.publish_plate_event(plate_event)
    publisher.publish_metric_event(metric_event)

    # Flush and close
    publisher.flush()
    publisher.close()

    print("✅ Test events published successfully!")
