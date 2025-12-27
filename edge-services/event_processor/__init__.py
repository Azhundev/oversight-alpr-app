"""Event Processor Service - ALPR Event Processing and Validation"""

from .event_processor_service import EventProcessorService, PlateEvent
from .kafka_publisher import KafkaPublisher, MockKafkaPublisher

__all__ = ["EventProcessorService", "PlateEvent", "KafkaPublisher", "MockKafkaPublisher"]
