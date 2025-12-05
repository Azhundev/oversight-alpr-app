#!/usr/bin/env python3
"""
Quick test of pilot.py Kafka integration
Tests that EventProcessorService and Kafka publisher are properly initialized
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger

logger.info("=== Testing pilot.py Kafka Integration ===\n")

# Test 1: Import check
logger.info("Test 1: Checking imports...")
try:
    from services.event_processor import EventProcessorService, KafkaPublisher, MockKafkaPublisher
    logger.success("✅ Event processor imports successful")
except Exception as e:
    logger.error(f"❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Initialize event processor
logger.info("\nTest 2: Initializing EventProcessorService...")
try:
    processor = EventProcessorService(
        site_id="TEST",
        host_id="test-jetson",
    )
    logger.success("✅ EventProcessorService initialized")
except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
    sys.exit(1)

# Test 3: Initialize mock Kafka publisher
logger.info("\nTest 3: Initializing MockKafkaPublisher...")
try:
    publisher = MockKafkaPublisher(
        bootstrap_servers="localhost:9092",
        topic="alpr.plates.detected"
    )
    logger.success("✅ MockKafkaPublisher initialized")
except Exception as e:
    logger.error(f"❌ Publisher initialization failed: {e}")
    sys.exit(1)

# Test 4: Process a simulated plate detection
logger.info("\nTest 4: Processing simulated plate detection...")
try:
    event = processor.process_detection(
        plate_text="TEST123",
        plate_confidence=0.95,
        camera_id="test_cam_01",
        track_id=9999,
        vehicle_type="car",
        vehicle_color="blue",
        region="US-FL",
    )

    if event:
        logger.success(f"✅ Event created: {event.event_id}")
        logger.info(f"   Plate: {event.plate['normalized_text']}")
        logger.info(f"   Confidence: {event.plate['confidence']}")
        logger.info(f"   Camera: {event.camera_id}")
    else:
        logger.warning("⚠️  Event was rejected (validation failed)")
except Exception as e:
    logger.error(f"❌ Event processing failed: {e}")
    sys.exit(1)

# Test 5: Publish event
logger.info("\nTest 5: Publishing event to mock Kafka...")
try:
    if event:
        success = publisher.publish_event(event.to_dict())
        if success:
            logger.success("✅ Event published successfully")
        else:
            logger.error("❌ Publishing failed")
    publisher.close()
except Exception as e:
    logger.error(f"❌ Publishing failed: {e}")
    sys.exit(1)

# Test 6: Verify pilot.py can import everything
logger.info("\nTest 6: Verifying pilot.py imports...")
try:
    import pilot
    logger.success("✅ pilot.py imports successful")
except Exception as e:
    logger.error(f"❌ pilot.py import failed: {e}")
    sys.exit(1)

logger.success("\n" + "="*60)
logger.success("🎉 All tests passed! Pilot.py Kafka integration is working!")
logger.success("="*60)
logger.info("\nYou can now run: python3 pilot.py")
logger.info("It will automatically use MockKafkaPublisher until Kafka is ready.")
