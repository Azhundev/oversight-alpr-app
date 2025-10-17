"""
Event Schema Definitions
Pydantic models for type-safe event handling across services
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID, uuid4


class BoundingBox(BaseModel):
    """Bounding box coordinates"""
    x1: float
    y1: float
    x2: float
    y2: float

    @validator('*')
    def validate_positive(cls, v):
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
    """Vehicle detection result"""
    vehicle_type: str = Field(..., description="car, truck, bus, motorcycle, etc.")
    bbox: BoundingBox
    confidence: float = Field(..., ge=0.0, le=1.0)
    color: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    crop_url: Optional[str] = None


class DetectionEvent(BaseModel):
    """Complete ALPR detection event"""
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    camera_id: str
    location: Optional[str] = None
    track_id: int = Field(..., description="Unique tracking ID for this vehicle")

    # Detection results
    plate: Optional[PlateDetection] = None
    vehicle: VehicleDetection

    # Metadata
    direction: Optional[str] = Field(None, description="N, S, E, W, NE, NW, SE, SW")
    speed_kmh: Optional[float] = Field(None, description="Estimated speed in km/h")
    dwell_time_seconds: Optional[float] = None

    # Processing info
    processing_time_ms: Optional[float] = None
    is_duplicate: bool = False

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class KafkaEvent(BaseModel):
    """Event structure for Kafka messages"""
    topic: str = "alpr.detections"
    key: str = Field(..., description="event_id as string for partitioning")
    value: DetectionEvent
    headers: Optional[dict] = None


class DatabaseEvent(BaseModel):
    """Event structure for database persistence"""
    # Flattened structure for relational DB
    event_id: UUID
    timestamp: datetime
    camera_id: str
    location: Optional[str]
    track_id: int

    # Plate fields
    plate_text: Optional[str]
    plate_confidence: Optional[float]
    plate_bbox_x1: Optional[float]
    plate_bbox_y1: Optional[float]
    plate_bbox_x2: Optional[float]
    plate_bbox_y2: Optional[float]
    plate_crop_url: Optional[str]
    plate_country: Optional[str]
    plate_region: Optional[str]

    # Vehicle fields
    vehicle_type: str
    vehicle_bbox_x1: float
    vehicle_bbox_y1: float
    vehicle_bbox_x2: float
    vehicle_bbox_y2: float
    vehicle_confidence: float
    vehicle_color: Optional[str]
    vehicle_make: Optional[str]
    vehicle_model: Optional[str]
    vehicle_crop_url: Optional[str]

    # Analytics
    direction: Optional[str]
    speed_kmh: Optional[float]
    dwell_time_seconds: Optional[float]
    processing_time_ms: Optional[float]
    is_duplicate: bool

    @classmethod
    def from_detection_event(cls, event: DetectionEvent) -> 'DatabaseEvent':
        """Convert DetectionEvent to flattened DatabaseEvent"""
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
