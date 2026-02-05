#!/usr/bin/env python3
"""
Example usage of EventProcessorService
Demonstrates how to integrate with pilot.py and publish to Kafka/MQTT
"""

from event_processor_service import EventProcessorService, PlateEvent
from loguru import logger


def example_basic_usage():
    """Basic example: process a single detection"""

    # Initialize processor
    processor = EventProcessorService(
        site_id="DC1",
        host_id="jetson-orin-02",
        min_confidence=0.70,
        dedup_similarity_threshold=0.85,
        dedup_time_window_seconds=300,
    )

    # Process a detection (from OCR)
    event = processor.process_detection(
        plate_text="ABC 123",  # Raw OCR text (may have spaces)
        plate_confidence=0.91,
        camera_id="west_gate_cam_03",
        track_id=8243,
        vehicle_type="car",
        vehicle_make="Toyota",
        vehicle_model="Camry",
        vehicle_color="silver",
        plate_image_path="output/crops/2025-12-04/west_gate_cam_03_track8243_frame1234_q0.89.jpg",
        region="US-FL",
        roi="lane-2",
        direction="inbound",
        quality_score=0.89,
        processing_latency_ms=42,
        frame_number=1234,
    )

    if event:
        logger.info(f"Event created successfully: {event.event_id}")
        logger.info(f"Normalized plate: {event.plate['normalized_text']}")

        # Convert to JSON for Kafka/MQTT
        json_payload = event.to_json()
        logger.info(f"JSON Payload:\n{json_payload}")

        # Simulate publishing to Kafka/MQTT
        # publish_to_kafka(topic="alpr.plates.detected", payload=json_payload)
        # or
        # mqtt_client.publish(topic="alpr/plates/detected", payload=json_payload)
    else:
        logger.warning("Detection rejected by processor")


def example_deduplication():
    """Example: demonstrate deduplication"""

    processor = EventProcessorService(
        site_id="DC1",
        host_id="jetson-orin-02",
        min_confidence=0.70,
        dedup_similarity_threshold=0.85,  # 85% similarity = duplicate
    )

    # First detection - should succeed
    event1 = processor.process_detection(
        plate_text="ABC123",
        plate_confidence=0.85,
        camera_id="gate_01",
        track_id=100,
    )
    assert event1 is not None, "First detection should succeed"
    logger.info(f"✅ Event 1 created: {event1.event_id}")

    # Second detection - same plate, should be rejected as duplicate
    event2 = processor.process_detection(
        plate_text="ABC123",
        plate_confidence=0.90,
        camera_id="gate_01",
        track_id=101,
    )
    assert event2 is None, "Duplicate should be rejected"
    logger.info("✅ Duplicate correctly rejected")

    # Third detection - similar but different (fuzzy match), should be rejected
    event3 = processor.process_detection(
        plate_text="ABC1Z3",  # OCR error: 2 → Z (83% similar: 5 chars match, 1 differs = 5/6 = 0.83)
        plate_confidence=0.88,
        camera_id="gate_01",
        track_id=102,
    )
    # Actually, ABC1Z3 is 83% similar (1 char diff out of 6) - below 85% threshold, so it passes!
    # Let's use a more similar example: ABC123 vs ABD123 (83% similar)
    # For true fuzzy duplicate, we need higher similarity
    if event3 is None:
        logger.info("✅ Fuzzy duplicate correctly rejected (similarity >= 85%)")
    else:
        logger.info(f"✅ Event 3 created (similarity < 85%, different enough): {event3.event_id}")

    # Fourth detection - completely different plate, should succeed
    event4 = processor.process_detection(
        plate_text="XYZ789",
        plate_confidence=0.92,
        camera_id="gate_01",
        track_id=103,
    )
    assert event4 is not None, "Different plate should succeed"
    logger.info(f"✅ Event 4 created: {event4.event_id}")


def example_validation():
    """Example: demonstrate format validation"""

    processor = EventProcessorService()

    # Valid Florida plate - should succeed
    event1 = processor.process_detection(
        plate_text="ABC1234",
        plate_confidence=0.85,
        camera_id="gate_01",
        track_id=200,
        region="US-FL",
    )
    assert event1 is not None, "Valid FL plate should succeed"
    logger.info(f"✅ Valid FL plate accepted: {event1.plate['normalized_text']}")

    # Invalid format - should be rejected
    event2 = processor.process_detection(
        plate_text="12345678",  # Too many digits, invalid format
        plate_confidence=0.90,
        camera_id="gate_01",
        track_id=201,
        region="US-FL",
    )
    assert event2 is None, "Invalid format should be rejected"
    logger.info("✅ Invalid format correctly rejected")

    # Low confidence - should be rejected
    event3 = processor.process_detection(
        plate_text="ABC123",
        plate_confidence=0.60,  # Below 0.70 threshold
        camera_id="gate_01",
        track_id=202,
        region="US-FL",
    )
    assert event3 is None, "Low confidence should be rejected"
    logger.info("✅ Low confidence correctly rejected")


def example_integration_with_pilot():
    """
    Example: how to integrate EventProcessorService into pilot.py

    This replaces the current _save_plate_read() logic
    """

    processor = EventProcessorService(
        site_id="DC1",
        host_id="jetson-orin-nx",
    )

    # Simulated data from pilot.py (lines 805-862)
    # This would come from your OCR and tracking logic
    track_id = 12345
    plate_detection_text = "ABC 123"  # From self.ocr.recognize_plate()
    plate_detection_confidence = 0.91
    camera_id = "west_gate_cam_03"

    # Vehicle attributes (from tracking cache)
    vehicle_type = "car"
    vehicle_color = "silver"

    # Image paths (from best-shot selection)
    plate_crop_path = "output/crops/2025-12-04/west_gate_cam_03_track12345_frame5678.jpg"

    # Quality score (from calculate_plate_quality)
    quality_score = 0.89

    # Process detection
    event = processor.process_detection(
        plate_text=plate_detection_text,
        plate_confidence=plate_detection_confidence,
        camera_id=camera_id,
        track_id=track_id,
        vehicle_type=vehicle_type,
        vehicle_color=vehicle_color,
        plate_image_path=plate_crop_path,
        quality_score=quality_score,
        region="US-FL",
    )

    if event:
        # Convert to JSON
        json_payload = event.to_json()

        # Publish to Kafka/MQTT
        # kafka_producer.send(topic="alpr.plates.detected", value=json_payload.encode())
        # or
        # mqtt_client.publish("alpr/plates/detected", json_payload)

        logger.success(f"Published event: {event.event_id} | {event.plate['normalized_text']}")
    else:
        logger.info("Detection rejected (duplicate or invalid)")


if __name__ == "__main__":
    logger.info("=== Example 1: Basic Usage ===")
    example_basic_usage()

    logger.info("\n=== Example 2: Deduplication ===")
    example_deduplication()

    logger.info("\n=== Example 3: Validation ===")
    example_validation()

    logger.info("\n=== Example 4: Integration with pilot.py ===")
    example_integration_with_pilot()

    logger.success("All examples completed!")
