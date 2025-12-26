"""
Event Schema Definitions
Pydantic models for type-safe event handling across services
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID, uuid4


class BoundingBox(BaseModel):
    """
    Bounding box coordinates in pixel space

    Coordinates are in (x1, y1) = top-left, (x2, y2) = bottom-right format
    """
    x1: float  # Left edge (pixels from left)
    y1: float  # Top edge (pixels from top)
    x2: float  # Right edge (pixels from left)
    y2: float  # Bottom edge (pixels from top)

    @validator('*')
    def validate_positive(cls, v):
        """Ensure all coordinates are non-negative (pixel coordinates start at 0)"""
        if v < 0:
            raise ValueError('Coordinates must be non-negative')
        return v


class PlateDetection(BaseModel):
    """License plate detection result"""
    text: str = Field(..., description="Normalized plate text (uppercase, no spaces)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="OCR confidence score")
    bbox: BoundingBox
    crop_url: Optional[str] = Field(None, description="S3/MinIO URL for plate crop")
    raw_text: Optional[str] = Field(None, description="Original OCR output before normalization")
    country_code: Optional[str] = Field(None, description="Detected country (US, UK, etc.)")
    region: Optional[str] = Field(None, description="State/Province if applicable")

    @validator('text')
    def validate_plate_format(cls, v):
        """Ensure plate text is normalized"""
        if not v.isupper():
            raise ValueError('Plate text must be uppercase')
        if ' ' in v or '-' in v:
            raise ValueError('Plate text must not contain spaces or dashes')
        if not v.isalnum():
            raise ValueError('Plate text must be alphanumeric only')
        if len(v) < 3:
            raise ValueError('Plate text must be at least 3 characters')
        return v


class VehicleDetection(BaseModel):
    """
    Vehicle detection result from YOLO detector

    Contains bounding box, classification, and optional attributes (color, make, model)
    """
    vehicle_type: str = Field(..., description="Vehicle class: car, truck, bus, motorcycle, etc.")
    bbox: BoundingBox  # Vehicle bounding box in pixel coordinates
    confidence: float = Field(..., ge=0.0, le=1.0, description="YOLO detection confidence (0.0-1.0)")
    color: Optional[str] = None  # Vehicle color (e.g., "red", "blue", "white") - optional attribute recognition
    make: Optional[str] = None  # Vehicle make (e.g., "Toyota", "Ford") - requires additional classifier
    model: Optional[str] = None  # Vehicle model (e.g., "Camry", "F-150") - requires additional classifier
    crop_url: Optional[str] = None  # S3/MinIO URL for vehicle crop image


class DetectionEvent(BaseModel):
    """
    Complete ALPR detection event with vehicle, plate, and metadata

    This is the primary event structure used across the ALPR pipeline
    """
    # Event identification
    event_id: UUID = Field(default_factory=uuid4)  # Unique event identifier (auto-generated)
    timestamp: datetime = Field(default_factory=datetime.utcnow)  # Event capture time (UTC)
    camera_id: str  # Camera identifier (e.g., "CAM1", "north-entrance")
    location: Optional[str] = None  # Physical location (e.g., "Building A - North Gate")
    track_id: int = Field(..., description="ByteTrack tracking ID for this vehicle (unique per tracking session)")

    # Detection results
    plate: Optional[PlateDetection] = None  # License plate detection (None if no plate detected)
    vehicle: VehicleDetection  # Vehicle detection (always present)

    # Analytics metadata
    direction: Optional[str] = Field(None, description="Cardinal direction: N, S, E, W, NE, NW, SE, SW")
    speed_kmh: Optional[float] = Field(None, description="Estimated speed in km/h (from tracking velocity)")
    dwell_time_seconds: Optional[float] = None  # Time vehicle spent in frame (seconds)

    # Processing metadata
    processing_time_ms: Optional[float] = None  # Total pipeline latency (milliseconds)
    is_duplicate: bool = False  # True if event was marked as duplicate by deduplication logic

    class Config:
        """Pydantic configuration for JSON serialization"""
        json_encoders = {
            datetime: lambda v: v.isoformat(),  # Serialize datetime as ISO 8601 string
            UUID: lambda v: str(v)  # Serialize UUID as string
        }


class KafkaEvent(BaseModel):
    """
    Event structure for Kafka messages

    Wraps DetectionEvent with Kafka-specific metadata (topic, key, headers)
    """
    topic: str = "alpr.detections"  # Kafka topic name
    key: str = Field(..., description="Partition key (event_id as string) - ensures ordering within partition")
    value: DetectionEvent  # Actual event payload
    headers: Optional[dict] = None  # Optional Kafka headers for metadata (e.g., schema version, source)


class DatabaseEvent(BaseModel):
    """
    Event structure for database persistence

    Flattened structure optimized for relational database storage (TimescaleDB/PostgreSQL).
    All nested objects (BoundingBox, PlateDetection, VehicleDetection) are flattened into
    individual columns for efficient querying and indexing.
    """
    # Core event fields
    event_id: UUID  # Primary key (unique event identifier)
    timestamp: datetime  # Event timestamp (indexed for time-series queries)
    camera_id: str  # Camera identifier (indexed for per-camera queries)
    location: Optional[str]  # Physical location (human-readable)
    track_id: int  # ByteTrack tracking ID

    # Plate fields (nullable - not all vehicles have readable plates)
    plate_text: Optional[str]  # Normalized plate text (indexed for plate lookups)
    plate_confidence: Optional[float]  # OCR confidence score
    plate_bbox_x1: Optional[float]  # Plate bounding box coordinates
    plate_bbox_y1: Optional[float]
    plate_bbox_x2: Optional[float]
    plate_bbox_y2: Optional[float]
    plate_crop_url: Optional[str]  # S3/MinIO URL for plate crop
    plate_country: Optional[str]  # Country code (e.g., "US")
    plate_region: Optional[str]  # State/province (e.g., "FL", "CA")

    # Vehicle fields (always present)
    vehicle_type: str  # Vehicle classification
    vehicle_bbox_x1: float  # Vehicle bounding box coordinates
    vehicle_bbox_y1: float
    vehicle_bbox_x2: float
    vehicle_bbox_y2: float
    vehicle_confidence: float  # YOLO detection confidence
    vehicle_color: Optional[str]  # Vehicle color (optional attribute)
    vehicle_make: Optional[str]  # Vehicle make (optional attribute)
    vehicle_model: Optional[str]  # Vehicle model (optional attribute)
    vehicle_crop_url: Optional[str]  # S3/MinIO URL for vehicle crop

    # Analytics fields
    direction: Optional[str]  # Cardinal direction of travel
    speed_kmh: Optional[float]  # Estimated speed
    dwell_time_seconds: Optional[float]  # Time in frame
    processing_time_ms: Optional[float]  # Pipeline latency
    is_duplicate: bool  # Deduplication flag

    @classmethod
    def from_detection_event(cls, event: DetectionEvent) -> 'DatabaseEvent':
        """
        Convert DetectionEvent to flattened DatabaseEvent for database insertion

        Transforms nested Pydantic models into a flat structure suitable for relational DB.
        Handles optional plate detection gracefully (plate fields become NULL if no plate detected).
        """
        # Extract plate data if available (otherwise all plate fields will be NULL)
        plate_data = {}
        if event.plate:
            plate_data = {
                'plate_text': event.plate.text,
                'plate_confidence': event.plate.confidence,
                'plate_bbox_x1': event.plate.bbox.x1,
                'plate_bbox_y1': event.plate.bbox.y1,
                'plate_bbox_x2': event.plate.bbox.x2,
                'plate_bbox_y2': event.plate.bbox.y2,
                'plate_crop_url': event.plate.crop_url,
                'plate_country': event.plate.country_code,
                'plate_region': event.plate.region,
            }

        return cls(
            event_id=event.event_id,
            timestamp=event.timestamp,
            camera_id=event.camera_id,
            location=event.location,
            track_id=event.track_id,

            **plate_data,

            vehicle_type=event.vehicle.vehicle_type,
            vehicle_bbox_x1=event.vehicle.bbox.x1,
            vehicle_bbox_y1=event.vehicle.bbox.y1,
            vehicle_bbox_x2=event.vehicle.bbox.x2,
            vehicle_bbox_y2=event.vehicle.bbox.y2,
            vehicle_confidence=event.vehicle.confidence,
            vehicle_color=event.vehicle.color,
            vehicle_make=event.vehicle.make,
            vehicle_model=event.vehicle.model,
            vehicle_crop_url=event.vehicle.crop_url,

            direction=event.direction,
            speed_kmh=event.speed_kmh,
            dwell_time_seconds=event.dwell_time_seconds,
            processing_time_ms=event.processing_time_ms,
            is_duplicate=event.is_duplicate
        )
