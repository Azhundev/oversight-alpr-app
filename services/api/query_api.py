#!/usr/bin/env python3
"""
Query API for ALPR Events
REST API for retrieving historical plate detection events from TimescaleDB
"""

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from loguru import logger
import uvicorn

from services.storage.storage_service import StorageService


# Initialize FastAPI app
app = FastAPI(
    title="ALPR Query API",
    description="REST API for querying historical license plate detection events",
    version="1.0.0",
)

# Enable CORS for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage service instance
storage: Optional[StorageService] = None


# Response models
class EventResponse(BaseModel):
    """Response model for plate event"""
    event_id: str
    captured_at: str
    camera_id: str
    track_id: str
    plate_text: str
    plate_normalized_text: str
    plate_confidence: float
    plate_region: str
    vehicle_type: Optional[str]
    vehicle_make: Optional[str]
    vehicle_model: Optional[str]
    vehicle_color: Optional[str]
    plate_image_url: Optional[str]
    vehicle_image_url: Optional[str]
    frame_image_url: Optional[str]
    latency_ms: Optional[int]
    quality_score: Optional[float]
    frame_number: Optional[int]
    site_id: Optional[str]
    host_id: Optional[str]
    roi: Optional[str]
    direction: Optional[str]
    created_at: Optional[str]


class StatsResponse(BaseModel):
    """Response model for database statistics"""
    is_connected: bool
    total_events: Optional[int]
    unique_plates: Optional[int]
    active_cameras: Optional[int]
    earliest_event: Optional[str]
    latest_event: Optional[str]
    avg_confidence: Optional[float]
    avg_latency_ms: Optional[float]
    total_inserts: int
    failed_inserts: int


@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup"""
    global storage

    # Read configuration from environment variables
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME", "alpr_db")
    db_user = os.getenv("DB_USER", "alpr")
    db_password = os.getenv("DB_PASSWORD", "alpr_secure_pass")

    logger.info(f"Connecting to database: {db_host}:{db_port}/{db_name}")

    try:
        storage = StorageService(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
        )
        logger.success("✅ Query API connected to database")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection on shutdown"""
    global storage
    if storage:
        storage.close()
        logger.info("Database connection closed")


@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "ALPR Query API",
        "version": "1.0.0",
        "endpoints": {
            "stats": "/stats",
            "recent": "/events/recent",
            "by_id": "/events/{event_id}",
            "by_plate": "/events/plate/{plate_text}",
            "by_camera": "/events/camera/{camera_id}",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    if not storage or not storage.is_connected:
        raise HTTPException(status_code=503, detail="Database not connected")

    return {
        "status": "healthy",
        "database_connected": storage.is_connected
    }


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get database statistics

    Returns:
        Database statistics including total events, unique plates, etc.
    """
    if not storage:
        raise HTTPException(status_code=503, detail="Database not initialized")

    stats = storage.get_stats()
    return stats


@app.get("/events/recent")
async def get_recent_events(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return")
):
    """
    Get most recent plate detection events

    Args:
        limit: Maximum number of events (1-1000)

    Returns:
        List of recent events
    """
    if not storage:
        raise HTTPException(status_code=503, detail="Database not initialized")

    events = storage.get_recent_events(limit=limit)
    return {
        "count": len(events),
        "events": events
    }


@app.get("/events/{event_id}")
async def get_event_by_id(event_id: str):
    """
    Get event by event ID

    Args:
        event_id: Event UUID

    Returns:
        Event details or 404 if not found
    """
    if not storage:
        raise HTTPException(status_code=503, detail="Database not initialized")

    event = storage.get_event_by_id(event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


@app.get("/events/plate/{plate_text}")
async def get_events_by_plate(
    plate_text: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    Get events by plate text (normalized)

    Args:
        plate_text: Normalized plate text (e.g., "ABC123")
        limit: Maximum number of events (1-1000)
        offset: Offset for pagination

    Returns:
        List of events matching the plate text
    """
    if not storage:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Normalize plate text (uppercase, no spaces)
    plate_text_normalized = plate_text.upper().replace(" ", "").replace("-", "")

    events = storage.get_events_by_plate(
        plate_text=plate_text_normalized,
        limit=limit,
        offset=offset
    )

    return {
        "plate": plate_text_normalized,
        "count": len(events),
        "limit": limit,
        "offset": offset,
        "events": events
    }


@app.get("/events/camera/{camera_id}")
async def get_events_by_camera(
    camera_id: str,
    start_time: Optional[str] = Query(None, description="Start time (ISO 8601 format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO 8601 format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    Get events by camera ID with optional time range

    Args:
        camera_id: Camera identifier
        start_time: Start of time range (ISO 8601, optional)
        end_time: End of time range (ISO 8601, optional)
        limit: Maximum number of events (1-1000)
        offset: Offset for pagination

    Returns:
        List of events from the specified camera
    """
    if not storage:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Parse time filters
    start_dt = None
    end_dt = None

    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_time format (use ISO 8601)")

    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_time format (use ISO 8601)")

    events = storage.get_events_by_camera(
        camera_id=camera_id,
        start_time=start_dt,
        end_time=end_dt,
        limit=limit,
        offset=offset
    )

    return {
        "camera_id": camera_id,
        "start_time": start_time,
        "end_time": end_time,
        "count": len(events),
        "limit": limit,
        "offset": offset,
        "events": events
    }


@app.get("/events/search")
async def search_events(
    plate: Optional[str] = Query(None, description="Plate text to search for"),
    camera: Optional[str] = Query(None, description="Camera ID to filter by"),
    site: Optional[str] = Query(None, description="Site ID to filter by"),
    start_time: Optional[str] = Query(None, description="Start time (ISO 8601)"),
    end_time: Optional[str] = Query(None, description="End time (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
):
    """
    Search events with multiple filters (advanced search)

    Args:
        plate: Filter by plate text
        camera: Filter by camera ID
        site: Filter by site ID
        start_time: Filter by start time
        end_time: Filter by end time
        limit: Maximum results

    Returns:
        List of events matching the search criteria
    """
    if not storage:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # This is a simplified implementation
    # For production, implement a proper query builder in StorageService

    if plate:
        events = storage.get_events_by_plate(plate.upper().replace(" ", "").replace("-", ""), limit=limit)
    elif camera:
        events = storage.get_events_by_camera(camera, limit=limit)
    else:
        events = storage.get_recent_events(limit=limit)

    # Apply additional filters in memory (inefficient but simple)
    # TODO: Implement proper SQL filtering in StorageService

    return {
        "count": len(events),
        "filters": {
            "plate": plate,
            "camera": camera,
            "site": site,
            "start_time": start_time,
            "end_time": end_time,
        },
        "events": events
    }


def main():
    """
    Main entry point for running API as standalone service
    """
    logger.info("=== ALPR Query API ===")

    # Run uvicorn server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
