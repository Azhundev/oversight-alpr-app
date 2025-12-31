#!/usr/bin/env python3
"""
Elasticsearch Consumer for ALPR Events
Consumes PlateEvent messages from Kafka and indexes them to OpenSearch.
"""

import os
import signal
import sys
import time
import uuid
import json
from typing import Optional, Dict, Any
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

# OpenSearch components
from opensearch_client import OpenSearchClient
from index_manager import IndexManager
from bulk_indexer import BulkIndexer

# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, start_http_server


class ElasticsearchConsumer:
    """
    Kafka consumer that indexes ALPR events to OpenSearch.

    Consumes Avro-serialized plate detection events from Kafka and indexes them
    to OpenSearch with bulk indexing and monthly index rotation.
    """

    # Prometheus metrics (class-level for global access)
    metrics_consumed = Counter(
        'elasticsearch_consumer_messages_consumed_total',
        'Total messages consumed from Kafka'
    )
    metrics_indexed = Counter(
        'elasticsearch_consumer_messages_indexed_total',
        'Total messages indexed to OpenSearch'
    )
    metrics_failed = Counter(
        'elasticsearch_consumer_messages_failed_total',
        'Total messages that failed to index'
    )
    metrics_bulk_requests = Counter(
        'elasticsearch_consumer_bulk_requests_total',
        'Total bulk requests sent to OpenSearch'
    )
    metrics_bulk_size = Histogram(
        'elasticsearch_consumer_bulk_size_documents',
        'Number of documents per bulk request'
    )
    metrics_bulk_duration = Histogram(
        'elasticsearch_consumer_bulk_duration_seconds',
        'Bulk request duration in seconds'
    )
    metrics_opensearch_available = Gauge(
        'elasticsearch_consumer_opensearch_available',
        'OpenSearch cluster availability (1=up, 0=down)'
    )
    metrics_retries = Counter(
        'elasticsearch_consumer_retry_attempts_total',
        'Total retry attempts',
        ['attempt']
    )
    metrics_timeouts = Counter(
        'elasticsearch_consumer_processing_timeout_total',
        'Total processing timeouts'
    )
    metrics_dlq_sent = Counter(
        'elasticsearch_consumer_dlq_messages_sent_total',
        'Total messages sent to DLQ',
        ['error_type']
    )

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        schema_registry_url: str = "http://localhost:8081",
        kafka_topic: str = "alpr.events.plates",
        kafka_group_id: str = "alpr-elasticsearch-consumer",
        opensearch_hosts: str = "http://localhost:9200",
        opensearch_index_prefix: str = "alpr-events",
        opensearch_bulk_size: int = 50,
        opensearch_flush_interval: int = 5,
        auto_offset_reset: str = "latest",
        max_retries: int = 3,
        retry_delay_base: float = 2.0,
        processing_timeout: float = 30.0,
        enable_dlq: bool = True,
        dlq_topic: str = "alpr.dlq",
    ):
        """
        Initialize Elasticsearch Consumer.

        Args:
            kafka_bootstrap_servers: Kafka broker addresses
            schema_registry_url: Schema Registry URL
            kafka_topic: Topic to consume from
            kafka_group_id: Consumer group ID
            opensearch_hosts: OpenSearch host URLs (comma-separated)
            opensearch_index_prefix: Prefix for index names
            opensearch_bulk_size: Documents per bulk request
            opensearch_flush_interval: Flush interval in seconds
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
            'indexed': 0,
            'failed': 0,
            'skipped': 0,
            'retried': 0,
            'timeout': 0,
            'dlq_sent': 0,
        }

        # Initialize OpenSearch client
        opensearch_host_list = [h.strip() for h in opensearch_hosts.split(',')]
        self.opensearch_client = OpenSearchClient(
            hosts=opensearch_host_list,
            use_ssl=False,
            verify_certs=False,
            timeout=30
        )

        # Check OpenSearch health
        if self.opensearch_client.is_healthy():
            self.metrics_opensearch_available.set(1)
        else:
            self.metrics_opensearch_available.set(0)
            logger.warning("⚠️  OpenSearch cluster is not healthy, but continuing...")

        # Initialize index manager
        self.index_manager = IndexManager(
            opensearch_client=self.opensearch_client,
            index_prefix=opensearch_index_prefix
        )

        # Initialize bulk indexer with metrics callback
        self.bulk_indexer = BulkIndexer(
            opensearch_client=self.opensearch_client,
            index_manager=self.index_manager,
            batch_size=opensearch_bulk_size,
            flush_interval=opensearch_flush_interval,
            metrics_callback=self._bulk_metrics_callback
        )

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

        # Start Prometheus metrics HTTP server on port 8004
        try:
            start_http_server(8004)
            logger.success("✅ Prometheus metrics endpoint started at http://localhost:8004/metrics")
        except Exception as e:
            logger.warning(f"⚠️  Failed to start Prometheus metrics server: {e}")

    def _bulk_metrics_callback(self, batch_size: int, duration: float, errors: int):
        """
        Callback for bulk indexer metrics.

        Args:
            batch_size: Number of documents in batch
            duration: Bulk request duration
            errors: Number of errors
        """
        self.metrics_bulk_requests.inc()
        self.metrics_bulk_size.observe(batch_size)
        self.metrics_bulk_duration.observe(duration)
        self.metrics_indexed.inc(batch_size)
        self.metrics_failed.inc(errors)

        self.stats['indexed'] += batch_size
        self.stats['failed'] += errors

    def _connect(self):
        """Establish connection to Kafka broker."""
        try:
            self.consumer = DeserializingConsumer(self.config)
            logger.success(
                f"✅ Connected to Kafka (Avro): {self.kafka_bootstrap_servers}\n"
                f"   Schema Registry: {self.schema_registry_url}\n"
                f"   Group ID: {self.config['group.id']}"
            )
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

                # Attempt to index event to OpenSearch
                self.bulk_indexer.add(event_data)

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

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.warning(f"🛑 Received signal {signum}, shutting down gracefully...")
        self.running = False

    def start(self):
        """
        Start consuming messages from Kafka and indexing to OpenSearch.

        This is a blocking operation that runs until stopped.
        """
        try:
            # Subscribe to topic
            self.consumer.subscribe([self.kafka_topic])
            logger.success(f"📥 Subscribed to topic: {self.kafka_topic}")

            # Ensure current month's index exists
            current_index = self.index_manager.ensure_current_index_exists()
            logger.success(f"📑 Using index: {current_index}")

            self.running = True
            logger.info("🚀 Starting message consumption and indexing...")

            while self.running:
                try:
                    # Poll for messages
                    msg = self.consumer.poll(timeout=1.0)

                    if msg is None:
                        continue

                    if msg.error():
                        logger.error(f"❌ Consumer error: {msg.error()}")
                        continue

                    # Deserialize event
                    event_data = msg.value()
                    self.stats['consumed'] += 1
                    self.metrics_consumed.inc()

                    if event_data is None:
                        logger.warning("⚠️  Received null message, skipping")
                        self.stats['skipped'] += 1
                        continue

                    # Log event details
                    event_id = event_data.get('event_id', 'unknown')
                    plate_text = event_data.get('plate', {}).get('normalized_text', 'unknown')
                    camera_id = event_data.get('camera_id', 'unknown')

                    logger.debug(
                        f"📨 Consumed: event_id={event_id}, "
                        f"plate={plate_text}, camera={camera_id}"
                    )

                    # Process with retry and timeout detection
                    success = self._process_with_retry(msg, event_data)

                    if not success:
                        # Error logging and DLQ handling already done in _process_with_retry
                        pass

                    # Log stats every 100 messages
                    if self.stats['consumed'] % 100 == 0:
                        self._log_stats()

                    # Periodically check OpenSearch health
                    if self.stats['consumed'] % 500 == 0:
                        if self.opensearch_client.is_healthy():
                            self.metrics_opensearch_available.set(1)
                        else:
                            self.metrics_opensearch_available.set(0)

                except KeyboardInterrupt:
                    logger.warning("⏸️  Interrupted by user")
                    self.running = False
                    break
                except Exception as e:
                    logger.error(f"❌ Error processing message: {e}", exc_info=True)
                    self.stats['failed'] += 1
                    self.metrics_failed.inc()
                    continue

        except Exception as e:
            logger.error(f"❌ Consumer error: {e}", exc_info=True)
            raise
        finally:
            self.stop()

    def stop(self):
        """Stop consumer and cleanup."""
        logger.info("🛑 Stopping Elasticsearch Consumer...")

        # Flush any pending documents
        if self.bulk_indexer:
            pending = self.bulk_indexer.pending_count()
            if pending > 0:
                logger.info(f"Flushing {pending} pending documents...")
                self.bulk_indexer.flush_now()

        # Close Kafka consumer
        if self.consumer:
            try:
                self.consumer.close()
                logger.info("Kafka consumer closed")
            except Exception as e:
                logger.warning(f"Error closing Kafka consumer: {e}")

        # Close OpenSearch client
        if self.opensearch_client:
            self.opensearch_client.close()

        # Log final stats
        self._log_stats()

        # Log bulk indexer stats
        bulk_stats = self.bulk_indexer.get_stats()
        logger.info(
            f"\n📊 Bulk Indexer Stats:\n"
            f"   Documents Added:   {bulk_stats['documents_added']}\n"
            f"   Documents Indexed: {bulk_stats['documents_indexed']}\n"
            f"   Documents Failed:  {bulk_stats['documents_failed']}\n"
            f"   Batches Flushed:   {bulk_stats['batches_flushed']}\n"
            f"   Bulk Errors:       {bulk_stats['bulk_errors']}"
        )

        logger.success("✅ Consumer stopped gracefully")

    def _log_stats(self):
        """Log consumer statistics."""
        logger.info(
            f"📊 Stats: consumed={self.stats['consumed']}, "
            f"indexed={self.stats['indexed']}, "
            f"failed={self.stats['failed']}, "
            f"skipped={self.stats['skipped']}, "
            f"retried={self.stats['retried']}, "
            f"timeout={self.stats['timeout']}, "
            f"dlq_sent={self.stats['dlq_sent']}, "
            f"pending={self.bulk_indexer.pending_count()}"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics."""
        return {
            **self.stats,
            'kafka_topic': self.kafka_topic,
            'running': self.running,
            'bulk_indexer_stats': self.bulk_indexer.get_stats(),
        }


def main():
    """Main entry point for Elasticsearch Consumer."""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "/app/logs/elasticsearch_consumer.log",
        rotation="100 MB",
        retention="30 days",
        level="DEBUG"
    )

    # Get configuration from environment variables
    kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    schema_registry_url = os.getenv('SCHEMA_REGISTRY_URL', 'http://localhost:8081')
    kafka_topic = os.getenv('KAFKA_TOPIC', 'alpr.events.plates')
    kafka_group_id = os.getenv('KAFKA_GROUP_ID', 'alpr-elasticsearch-consumer')

    opensearch_hosts = os.getenv('OPENSEARCH_HOSTS', 'http://localhost:9200')
    opensearch_index_prefix = os.getenv('OPENSEARCH_INDEX_PREFIX', 'alpr-events')
    opensearch_bulk_size = int(os.getenv('OPENSEARCH_BULK_SIZE', '50'))
    opensearch_flush_interval = int(os.getenv('OPENSEARCH_FLUSH_INTERVAL', '5'))

    auto_offset_reset = os.getenv('AUTO_OFFSET_RESET', 'latest')

    # DLQ and retry configuration
    max_retries = int(os.getenv('MAX_RETRIES', '3'))
    retry_delay_base = float(os.getenv('RETRY_DELAY_BASE', '2.0'))
    processing_timeout = float(os.getenv('PROCESSING_TIMEOUT', '30.0'))
    enable_dlq = os.getenv('ENABLE_DLQ', 'true').lower() == 'true'
    dlq_topic = os.getenv('DLQ_TOPIC', 'alpr.dlq')

    logger.info("=" * 70)
    logger.info("🚀 ALPR Elasticsearch Consumer (with DLQ & Retry)")
    logger.info("=" * 70)
    logger.info(f"Kafka Servers: {kafka_servers}")
    logger.info(f"Schema Registry: {schema_registry_url}")
    logger.info(f"Topic: {kafka_topic}")
    logger.info(f"Group ID: {kafka_group_id}")
    logger.info(f"OpenSearch: {opensearch_hosts}")
    logger.info(f"Index Prefix: {opensearch_index_prefix}")
    logger.info(f"Bulk Size: {opensearch_bulk_size}")
    logger.info(f"Flush Interval: {opensearch_flush_interval}s")
    logger.info(f"Auto Offset Reset: {auto_offset_reset}")
    logger.info(f"Max Retries: {max_retries}")
    logger.info(f"Retry Delay Base: {retry_delay_base}s")
    logger.info(f"Processing Timeout: {processing_timeout}s")
    logger.info(f"DLQ Enabled: {enable_dlq}")
    logger.info(f"DLQ Topic: {dlq_topic}")
    logger.info("=" * 70)

    # Create and start consumer
    try:
        consumer = ElasticsearchConsumer(
            kafka_bootstrap_servers=kafka_servers,
            schema_registry_url=schema_registry_url,
            kafka_topic=kafka_topic,
            kafka_group_id=kafka_group_id,
            opensearch_hosts=opensearch_hosts,
            opensearch_index_prefix=opensearch_index_prefix,
            opensearch_bulk_size=opensearch_bulk_size,
            opensearch_flush_interval=opensearch_flush_interval,
            auto_offset_reset=auto_offset_reset,
            max_retries=max_retries,
            retry_delay_base=retry_delay_base,
            processing_timeout=processing_timeout,
            enable_dlq=enable_dlq,
            dlq_topic=dlq_topic,
        )

        consumer.start()

    except Exception as e:
        logger.error(f"❌ Consumer failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
