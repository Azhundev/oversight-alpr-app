#!/usr/bin/env python3
"""
Event Processor Service
Handles normalization, validation, deduplication, and metadata enrichment
for ALPR plate detection events before publishing to Kafka/MQTT
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class PlateEvent:
    """
    Structured event payload for Kafka/MQTT publishing
    Represents a fully processed and validated plate detection
    """
    event_id: str
    captured_at: str  # ISO 8601 timestamp
    camera_id: str
    track_id: str
    plate: Dict[str, Any]  # {text, confidence, region, normalized_text}
    vehicle: Dict[str, Any]  # {type, make, model, color}
    images: Dict[str, str]  # {plate_url, vehicle_url, frame_url}
    latency_ms: int
    node: Dict[str, str]  # {site, host}
    extras: Dict[str, Any]  # {roi, direction, quality_score, etc.}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string for Kafka/MQTT"""
        import json
        return json.dumps(self.to_dict(), indent=2)


class EventProcessorService:
    """
    Central service for processing ALPR events
    Handles: normalization, validation, deduplication, metadata enrichment
    """

    # US State plate format patterns (regex)
    # Format: {region: (pattern, description)}
    # Florida plates: 3-4 letters followed by 2-4 numbers, or similar combinations (6-7 chars total)
    PLATE_FORMATS = {
        "US-FL": (r"^[A-Z]{2,4}[0-9]{2,4}$|^[0-9]{2,4}[A-Z]{2,4}$", "Florida standard (e.g., ABC123, 123ABC)"),
        "US-CA": (r"^[0-9][A-Z]{3}[0-9]{3}$", "California standard (e.g., 1ABC234)"),
        "US-TX": (r"^[A-Z]{3}[0-9]{4}$", "Texas standard (e.g., ABC1234)"),
        "US-NY": (r"^[A-Z]{3}[0-9]{4}$", "New York standard (e.g., ABC1234)"),
        # Add more states/countries as needed
    }

    # Common OCR character misreads (mapping: wrong -> correct)
    OCR_CHAR_CORRECTIONS = {
        '0': 'O',  # Zero to letter O (context-dependent)
        'O': '0',  # Letter O to zero (context-dependent)
        '1': 'I',  # One to letter I
        'I': '1',  # Letter I to one
        '8': 'B',  # Eight to letter B
        'B': '8',  # Letter B to eight
        '5': 'S',  # Five to letter S
        'S': '5',  # Letter S to five
    }

    def __init__(
        self,
        site_id: str = "DC1",
        host_id: str = "jetson-orin-nx",
        min_confidence: float = 0.70,
        dedup_similarity_threshold: float = 0.85,
        dedup_time_window_seconds: int = 300,  # 5 minutes
    ):
        """
        Initialize Event Processor Service

        Args:
            site_id: Site/datacenter identifier
            host_id: Host machine identifier
            min_confidence: Minimum OCR confidence to accept (0.0-1.0)
            dedup_similarity_threshold: Minimum similarity to consider duplicate (0.0-1.0)
            dedup_time_window_seconds: Time window for deduplication (seconds)
        """
        self.site_id = site_id
        self.host_id = host_id
        self.min_confidence = min_confidence
        self.dedup_similarity_threshold = dedup_similarity_threshold
        self.dedup_time_window_seconds = dedup_time_window_seconds

        # Deduplication cache: {plate_text: (timestamp, track_id, event_id)}
        self.dedup_cache: Dict[str, Tuple[datetime, str, str]] = {}

        logger.info(f"EventProcessorService initialized (site={site_id}, host={host_id})")

    def normalize_plate_text(self, raw_text: str) -> str:
        """
        Normalize plate text for consistency
        - Remove spaces, hyphens, special characters
        - Convert to uppercase
        - Trim whitespace

        Args:
            raw_text: Raw OCR text

        Returns:
            Normalized plate text (uppercase, no spaces)
        """
        if not raw_text:
            return ""

        # Convert to uppercase
        normalized = raw_text.upper()

        # Remove common separators (spaces, hyphens, dots)
        normalized = re.sub(r'[\s\-\.]', '', normalized)

        # Remove any non-alphanumeric characters
        normalized = re.sub(r'[^A-Z0-9]', '', normalized)

        # Trim whitespace
        normalized = normalized.strip()

        return normalized

    def validate_plate_format(self, normalized_text: str, region: str = "US-FL") -> Tuple[bool, Optional[str]]:
        """
        Validate plate text against known formats for a region

        Args:
            normalized_text: Normalized plate text
            region: Region code (e.g., "US-FL", "US-CA")

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not normalized_text:
            return False, "Empty plate text"

        # Check if region is known
        if region not in self.PLATE_FORMATS:
            logger.warning(f"Unknown region: {region} - skipping format validation")
            return True, None  # Pass through if unknown region

        # Get pattern for region
        pattern, description = self.PLATE_FORMATS[region]

        # Validate against pattern
        if re.match(pattern, normalized_text):
            return True, None
        else:
            return False, f"Does not match {region} format: {description}"

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate Levenshtein similarity between two plate texts
        Returns similarity ratio 0.0-1.0 (1.0 = identical)

        Args:
            text1: First plate text
            text2: Second plate text

        Returns:
            Similarity score (0.0-1.0)
        """
        if text1 == text2:
            return 1.0

        # Ensure text1 is longer
        if len(text1) < len(text2):
            text1, text2 = text2, text1

        # Levenshtein distance algorithm
        distances = range(len(text2) + 1)
        for i1, c1 in enumerate(text1):
            new_distances = [i1 + 1]
            for i2, c2 in enumerate(text2):
                if c1 == c2:
                    new_distances.append(distances[i2])
                else:
                    new_distances.append(1 + min((distances[i2], distances[i2 + 1], new_distances[-1])))
            distances = new_distances

        levenshtein_distance = distances[-1]
        max_length = max(len(text1), len(text2))
        similarity = 1.0 - (levenshtein_distance / max_length) if max_length > 0 else 0.0

        return similarity

    def is_duplicate(self, normalized_text: str, track_id: str, timestamp: datetime) -> Tuple[bool, Optional[str]]:
        """
        Check if plate is a duplicate based on:
        1. Fuzzy text matching (Levenshtein similarity)
        2. Time window (prevent same plate from being logged multiple times)

        Args:
            normalized_text: Normalized plate text
            track_id: Current track ID
            timestamp: Event timestamp

        Returns:
            Tuple of (is_duplicate, duplicate_event_id)
        """
        # Clean up expired entries from cache
        self._cleanup_dedup_cache(timestamp)

        # Check cache for similar plates
        for cached_text, (cached_timestamp, cached_track_id, cached_event_id) in self.dedup_cache.items():
            # Calculate similarity
            similarity = self.calculate_similarity(normalized_text, cached_text)

            # Check if within time window
            time_diff = (timestamp - cached_timestamp).total_seconds()

            if similarity >= self.dedup_similarity_threshold and time_diff <= self.dedup_time_window_seconds:
                logger.debug(
                    f"Duplicate detected: '{normalized_text}' ~= '{cached_text}' "
                    f"(similarity: {similarity:.2%}, time_diff: {time_diff:.1f}s, track: {cached_track_id})"
                )
                return True, cached_event_id

        return False, None

    def _cleanup_dedup_cache(self, current_time: datetime):
        """
        Remove expired entries from deduplication cache

        Args:
            current_time: Current timestamp
        """
        expired_keys = []
        for key, (timestamp, _, _) in self.dedup_cache.items():
            time_diff = (current_time - timestamp).total_seconds()
            if time_diff > self.dedup_time_window_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            del self.dedup_cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired dedup cache entries")

    def _add_to_dedup_cache(self, normalized_text: str, track_id: str, event_id: str, timestamp: datetime):
        """
        Add entry to deduplication cache

        Args:
            normalized_text: Normalized plate text
            track_id: Track ID
            event_id: Event ID
            timestamp: Event timestamp
        """
        self.dedup_cache[normalized_text] = (timestamp, track_id, event_id)

    def process_detection(
        self,
        plate_text: str,
        plate_confidence: float,
        camera_id: str,
        track_id: int,
        vehicle_type: str = "car",
        vehicle_make: str = None,
        vehicle_model: str = None,
        vehicle_color: str = None,
        plate_image_path: str = None,
        vehicle_image_path: str = None,
        frame_image_path: str = None,
        region: str = "US-FL",
        roi: str = None,
        direction: str = None,
        quality_score: float = None,
        processing_latency_ms: int = 0,
        frame_number: int = None,
    ) -> Optional[PlateEvent]:
        """
        Process a raw plate detection into a validated PlateEvent

        Args:
            plate_text: Raw OCR text
            plate_confidence: OCR confidence (0.0-1.0)
            camera_id: Camera identifier
            track_id: Vehicle track ID
            vehicle_type: Vehicle type (car, truck, motorcycle, etc.)
            vehicle_make: Vehicle make (optional)
            vehicle_model: Vehicle model (optional)
            vehicle_color: Vehicle color (optional)
            plate_image_path: Path to saved plate crop
            vehicle_image_path: Path to saved vehicle crop
            frame_image_path: Path to saved frame
            region: Plate region/country (default: US-FL)
            roi: Region of interest (lane-1, gate-2, etc.)
            direction: Direction of travel (inbound, outbound)
            quality_score: Plate quality score (0.0-1.0)
            processing_latency_ms: Processing latency in milliseconds
            frame_number: Frame number in video stream

        Returns:
            PlateEvent if valid, None if rejected
        """
        timestamp = datetime.now(timezone.utc)

        # Step 1: Check minimum confidence
        if plate_confidence < self.min_confidence:
            logger.debug(f"Rejected: Low confidence {plate_confidence:.2f} < {self.min_confidence}")
            return None

        # Step 2: Normalize plate text
        normalized_text = self.normalize_plate_text(plate_text)
        if not normalized_text:
            logger.debug(f"Rejected: Empty normalized text (raw: '{plate_text}')")
            return None

        # Step 3: Validate plate format
        is_valid, error_msg = self.validate_plate_format(normalized_text, region)
        if not is_valid:
            logger.warning(f"Rejected: Invalid format - {error_msg} (text: '{normalized_text}')")
            return None

        # Step 4: Check for duplicates
        is_dup, dup_event_id = self.is_duplicate(normalized_text, str(track_id), timestamp)
        if is_dup:
            logger.info(f"Rejected: Duplicate plate '{normalized_text}' (original event: {dup_event_id})")
            return None

        # Step 5: Generate event ID and build payload
        event_id = str(uuid.uuid4())

        # Build plate object
        plate_obj = {
            "text": plate_text,  # Original OCR text
            "normalized_text": normalized_text,  # Cleaned/standardized text
            "confidence": round(plate_confidence, 3),
            "region": region,
        }

        # Build vehicle object
        vehicle_obj = {
            "type": vehicle_type,
            "make": vehicle_make,
            "model": vehicle_model,
            "color": vehicle_color,
        }

        # Build images object (URLs or paths)
        images_obj = {
            "plate_url": plate_image_path or "",
            "vehicle_url": vehicle_image_path or "",
            "frame_url": frame_image_path or "",
        }

        # Build node object
        node_obj = {
            "site": self.site_id,
            "host": self.host_id,
        }

        # Build extras object
        extras_obj = {
            "roi": roi,
            "direction": direction,
            "quality_score": round(quality_score, 3) if quality_score else None,
            "frame_number": frame_number,
        }

        # Create PlateEvent
        event = PlateEvent(
            event_id=event_id,
            captured_at=timestamp.isoformat(),
            camera_id=camera_id,
            track_id=f"t-{track_id}",
            plate=plate_obj,
            vehicle=vehicle_obj,
            images=images_obj,
            latency_ms=processing_latency_ms,
            node=node_obj,
            extras=extras_obj,
        )

        # Step 6: Add to dedup cache
        self._add_to_dedup_cache(normalized_text, str(track_id), event_id, timestamp)

        logger.success(
            f"✅ Event created: {event_id} | {normalized_text} | "
            f"Track: {track_id} | Confidence: {plate_confidence:.2f}"
        )

        return event

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current processor statistics

        Returns:
            Dictionary of stats
        """
        return {
            "dedup_cache_size": len(self.dedup_cache),
            "min_confidence": self.min_confidence,
            "dedup_similarity_threshold": self.dedup_similarity_threshold,
            "dedup_time_window_seconds": self.dedup_time_window_seconds,
        }
