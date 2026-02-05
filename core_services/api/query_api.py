#!/usr/bin/env python3
"""
Query API for ALPR Events
REST API for retrieving historical plate detection events from TimescaleDB
"""

import os
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from loguru import logger
import uvicorn

from services.storage.storage_service import StorageService
from services.storage.image_storage_service import ImageStorageService

# OpenTelemetry Distributed Tracing
TEMPO_ENDPOINT = os.getenv("TEMPO_ENDPOINT", "tempo:4317")
ENABLE_TRACING = os.getenv("ENABLE_TRACING", "false").lower() == "true"

if ENABLE_TRACING:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource

        # Initialize tracing
        resource = Resource.create({"service.name": "alpr-query-api"})
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=TEMPO_ENDPOINT, insecure=True))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        TRACING_INITIALIZED = True
        logger.info(f"OpenTelemetry tracing initialized, exporting to {TEMPO_ENDPOINT}")
    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed, tracing disabled: {e}")
        TRACING_INITIALIZED = False
else:
    TRACING_INITIALIZED = False
    logger.info("Distributed tracing disabled (ENABLE_TRACING=false)")

# Service Manager for incremental startup control
try:
    from service_manager import router as service_manager_router
    SERVICE_MANAGER_AVAILABLE = True
except ImportError:
    SERVICE_MANAGER_AVAILABLE = False

# OpenSearch for full-text search
try:
    from opensearchpy import OpenSearch
    OPENSEARCH_AVAILABLE = True
except ImportError:
    OPENSEARCH_AVAILABLE = False
    logger.warning("opensearch-py not installed, search endpoints will be unavailable")

# Prometheus metrics
from prometheus_fastapi_instrumentator import Instrumentator


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

# Add Prometheus metrics instrumentation
# This automatically instruments all HTTP endpoints with metrics:
# - http_requests_total (counter)
# - http_request_duration_seconds (histogram)
# - http_requests_in_progress (gauge)
Instrumentator().instrument(app).expose(app)

# Add OpenTelemetry tracing instrumentation
if ENABLE_TRACING and TRACING_INITIALIZED:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI instrumented with OpenTelemetry tracing")

# Include Service Manager router for incremental startup control
if SERVICE_MANAGER_AVAILABLE:
    app.include_router(service_manager_router)
    logger.info("✅ Service Manager endpoints enabled at /services/*")

# Global storage service instances
storage: Optional[StorageService] = None
image_storage: Optional[ImageStorageService] = None
opensearch_client: Optional[OpenSearch] = None


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

    # Initialize MinIO client for presigned URLs
    global image_storage
    try:
        minio_endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
        minio_access_key = os.getenv("MINIO_ACCESS_KEY", "alpr_minio")
        minio_secret_key = os.getenv("MINIO_SECRET_KEY", "alpr_minio_secure_pass_2024")
        minio_bucket = os.getenv("MINIO_BUCKET", "alpr-plate-images")

        image_storage = ImageStorageService(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            bucket_name=minio_bucket,
            local_cache_dir="",  # Not used for presigned URL generation
            thread_pool_size=1,  # Minimal, only for presigned URLs
        )
        logger.success("✅ Query API connected to MinIO")
    except Exception as e:
        logger.warning(f"⚠️  MinIO not available: {e}")
        image_storage = None

    # Initialize OpenSearch client for full-text search
    global opensearch_client
    if OPENSEARCH_AVAILABLE:
        try:
            opensearch_hosts = os.getenv("OPENSEARCH_HOSTS", "http://opensearch:9200")
            opensearch_host_list = [h.strip() for h in opensearch_hosts.split(',')]

            opensearch_client = OpenSearch(
                hosts=opensearch_host_list,
                use_ssl=False,
                verify_certs=False,
                timeout=30
            )

            # Test connection
            info = opensearch_client.info()
            logger.success(f"✅ Query API connected to OpenSearch: {info.get('version', {}).get('number', 'unknown')}")
        except Exception as e:
            logger.warning(f"⚠️  OpenSearch not available: {e}")
            opensearch_client = None
    else:
        logger.warning("⚠️  OpenSearch client not available (opensearch-py not installed)")


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection on shutdown"""
    global storage, image_storage, opensearch_client

    if opensearch_client:
        try:
            opensearch_client.close()
            logger.info("OpenSearch client closed")
        except Exception as e:
            logger.warning(f"Error closing OpenSearch client: {e}")

    if image_storage:
        image_storage.shutdown(wait=False, timeout=5)
        logger.info("MinIO client shutdown")

    if storage:
        storage.close()
        logger.info("Database connection closed")


# Helper functions
def convert_s3_to_presigned(event: dict) -> dict:
    """
    Convert S3 URLs to presigned HTTP URLs for image access.

    Args:
        event: Event dictionary from database

    Returns:
        Event dict with S3 URLs converted to presigned HTTP URLs
    """
    if not image_storage:
        return event

    # Convert plate image URL
    if event.get("plate_image_url") and event["plate_image_url"].startswith("s3://"):
        presigned = image_storage.get_presigned_url(
            event["plate_image_url"],
            expiry_hours=1
        )
        if presigned:
            event["plate_image_url"] = presigned
            logger.debug(f"Generated presigned URL for plate image")

    # Convert vehicle image URL (if implemented)
    if event.get("vehicle_image_url") and event["vehicle_image_url"].startswith("s3://"):
        presigned = image_storage.get_presigned_url(
            event["vehicle_image_url"],
            expiry_hours=1
        )
        if presigned:
            event["vehicle_image_url"] = presigned

    # Convert frame image URL (if implemented)
    if event.get("frame_image_url") and event["frame_image_url"].startswith("s3://"):
        presigned = image_storage.get_presigned_url(
            event["frame_image_url"],
            expiry_hours=1
        )
        if presigned:
            event["frame_image_url"] = presigned

    return event


@app.get("/")
async def root():
    """API root endpoint"""
    endpoints = {
        "stats": "/stats",
        "recent": "/events/recent",
        "by_id": "/events/{event_id}",
        "by_plate": "/events/plate/{plate_text}",
        "by_camera": "/events/camera/{camera_id}",
        "search_fulltext": "/search/fulltext",
        "search_facets": "/search/facets",
        "search_analytics": "/search/analytics",
        "search_query": "/search/query",
    }

    # Add service manager endpoints if available
    if SERVICE_MANAGER_AVAILABLE:
        endpoints.update({
            "service_dashboard": "/services/dashboard",
            "service_status": "/services/status",
            "service_groups": "/services/groups",
            "service_start": "/services/start/{group}",
            "service_stop": "/services/stop/{group}",
        })

    return {
        "name": "ALPR Query API",
        "version": "1.1.0",
        "endpoints": endpoints,
        "opensearch_available": opensearch_client is not None,
        "service_manager_available": SERVICE_MANAGER_AVAILABLE
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

    # Convert S3 URLs to presigned URLs
    events = [convert_s3_to_presigned(e) for e in events]

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

    # Convert S3 URLs to presigned URLs
    event = convert_s3_to_presigned(event)

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

    # Convert S3 URLs to presigned URLs
    events = [convert_s3_to_presigned(e) for e in events]

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

    # Convert S3 URLs to presigned URLs
    events = [convert_s3_to_presigned(e) for e in events]

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

    # Convert S3 URLs to presigned URLs
    events = [convert_s3_to_presigned(e) for e in events]

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


# ============================================================================
# OPENSEARCH FULL-TEXT SEARCH ENDPOINTS
# ============================================================================

@app.get("/search/fulltext")
async def search_fulltext(
    q: str = Query(..., description="Search query (supports fuzzy matching)"),
    start_time: Optional[str] = Query(None, description="Start time (ISO 8601 format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO 8601 format)"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    Full-text search across plate events with fuzzy matching.

    Searches across:
    - plate.text (full-text with fuzziness)
    - plate.normalized_text (exact match)
    - vehicle.make

    Examples:
        /search/fulltext?q=ABC123
        /search/fulltext?q=toyota&start_time=2025-01-01T00:00:00Z
        /search/fulltext?q=ABC&camera_id=cam1
    """
    if not opensearch_client:
        raise HTTPException(status_code=503, detail="Search service unavailable")

    # Build query
    query = {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": q,
                        "fields": ["plate.text", "plate.normalized_text^2", "vehicle.make"],
                        "fuzziness": "AUTO",
                        "type": "best_fields"
                    }
                }
            ],
            "filter": []
        }
    }

    # Add time range filter
    if start_time or end_time:
        time_filter = {"range": {"captured_at": {}}}
        if start_time:
            time_filter["range"]["captured_at"]["gte"] = start_time
        if end_time:
            time_filter["range"]["captured_at"]["lte"] = end_time
        query["bool"]["filter"].append(time_filter)

    # Add camera filter
    if camera_id:
        query["bool"]["filter"].append({"term": {"camera_id": camera_id}})

    # Execute search
    try:
        results = opensearch_client.search(
            index="alpr-events-*",
            body={
                "query": query,
                "from": offset,
                "size": limit,
                "sort": [{"captured_at": "desc"}]
            }
        )

        return {
            "query": q,
            "total": results["hits"]["total"]["value"],
            "took_ms": results["took"],
            "results": [hit["_source"] for hit in results["hits"]["hits"]],
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/search/facets")
async def search_facets(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    vehicle_type: Optional[str] = Query(None, description="Filter by vehicle type"),
    vehicle_color: Optional[str] = Query(None, description="Filter by vehicle color"),
    site: Optional[str] = Query(None, description="Filter by site ID"),
    start_time: Optional[str] = Query(None, description="Start time (ISO 8601)"),
    end_time: Optional[str] = Query(None, description="End time (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results")
):
    """
    Faceted search with aggregations for building drill-down UIs.

    Returns matching events plus aggregation counts for:
    - Cameras
    - Vehicle types
    - Vehicle colors
    - Sites

    Examples:
        /search/facets
        /search/facets?camera_id=cam1
        /search/facets?vehicle_type=car&vehicle_color=white
    """
    if not opensearch_client:
        raise HTTPException(status_code=503, detail="Search service unavailable")

    # Build filters
    filters = []
    if camera_id:
        filters.append({"term": {"camera_id": camera_id}})
    if vehicle_type:
        filters.append({"term": {"vehicle.type": vehicle_type}})
    if vehicle_color:
        filters.append({"term": {"vehicle.color": vehicle_color}})
    if site:
        filters.append({"term": {"node.site": site}})

    # Add time range filter
    if start_time or end_time:
        time_filter = {"range": {"captured_at": {}}}
        if start_time:
            time_filter["range"]["captured_at"]["gte"] = start_time
        if end_time:
            time_filter["range"]["captured_at"]["lte"] = end_time
        filters.append(time_filter)

    # Build query
    query_body = {
        "query": {"bool": {"filter": filters}} if filters else {"match_all": {}},
        "size": limit,
        "sort": [{"captured_at": "desc"}],
        "aggs": {
            "cameras": {"terms": {"field": "camera_id", "size": 50}},
            "vehicle_types": {"terms": {"field": "vehicle.type", "size": 20}},
            "vehicle_colors": {"terms": {"field": "vehicle.color", "size": 20}},
            "sites": {"terms": {"field": "node.site", "size": 20}}
        }
    }

    # Execute search
    try:
        results = opensearch_client.search(
            index="alpr-events-*",
            body=query_body
        )

        return {
            "total": results["hits"]["total"]["value"],
            "took_ms": results["took"],
            "results": [hit["_source"] for hit in results["hits"]["hits"]],
            "facets": {
                "cameras": results["aggregations"]["cameras"]["buckets"],
                "vehicle_types": results["aggregations"]["vehicle_types"]["buckets"],
                "vehicle_colors": results["aggregations"]["vehicle_colors"]["buckets"],
                "sites": results["aggregations"]["sites"]["buckets"]
            },
            "filters": {
                "camera_id": camera_id,
                "vehicle_type": vehicle_type,
                "vehicle_color": vehicle_color,
                "site": site
            }
        }
    except Exception as e:
        logger.error(f"Faceted search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/search/analytics")
async def search_analytics(
    metric: str = Query(..., description="Metric type: plates_per_hour | avg_confidence | top_plates"),
    interval: str = Query("1h", description="Time interval: 1m, 5m, 1h, 1d"),
    start_time: Optional[str] = Query(None, description="Start time (ISO 8601)"),
    end_time: Optional[str] = Query(None, description="End time (ISO 8601)"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID")
):
    """
    Analytics aggregations for dashboards and reporting.

    Available metrics:
    - plates_per_hour: Histogram of detection counts over time
    - avg_confidence: Average OCR confidence over time
    - top_plates: Most frequently seen plates

    Examples:
        /search/analytics?metric=plates_per_hour&interval=1h
        /search/analytics?metric=avg_confidence&interval=1h&camera_id=cam1
        /search/analytics?metric=top_plates
    """
    if not opensearch_client:
        raise HTTPException(status_code=503, detail="Search service unavailable")

    # Build base filter
    filters = []
    if camera_id:
        filters.append({"term": {"camera_id": camera_id}})

    if start_time or end_time:
        time_filter = {"range": {"captured_at": {}}}
        if start_time:
            time_filter["range"]["captured_at"]["gte"] = start_time
        if end_time:
            time_filter["range"]["captured_at"]["lte"] = end_time
        filters.append(time_filter)

    base_query = {"bool": {"filter": filters}} if filters else {"match_all": {}}

    # Build aggregation based on metric type
    aggs = {}
    if metric == "plates_per_hour":
        aggs = {
            "plates_over_time": {
                "date_histogram": {
                    "field": "captured_at",
                    "fixed_interval": interval
                }
            }
        }
    elif metric == "avg_confidence":
        aggs = {
            "confidence_over_time": {
                "date_histogram": {
                    "field": "captured_at",
                    "fixed_interval": interval
                },
                "aggs": {
                    "avg_confidence": {"avg": {"field": "plate.confidence"}}
                }
            }
        }
    elif metric == "top_plates":
        aggs = {
            "top_plates": {
                "terms": {
                    "field": "plate.normalized_text",
                    "size": 100
                }
            }
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")

    # Execute search
    try:
        results = opensearch_client.search(
            index="alpr-events-*",
            body={
                "query": base_query,
                "size": 0,  # No documents, just aggregations
                "aggs": aggs
            }
        )

        return {
            "metric": metric,
            "took_ms": results["took"],
            "total_events": results["hits"]["total"]["value"],
            "aggregations": results["aggregations"],
            "filters": {
                "camera_id": camera_id,
                "start_time": start_time,
                "end_time": end_time
            }
        }
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}")


@app.post("/search/query")
async def search_query(query_dsl: Dict[str, Any] = Body(..., description="OpenSearch Query DSL")):
    """
    Advanced search using raw OpenSearch Query DSL.

    Allows executing arbitrary OpenSearch queries for advanced use cases.

    Example request body:
    {
        "query": {
            "bool": {
                "must": [
                    {"match": {"plate.text": "ABC"}}
                ],
                "filter": [
                    {"range": {"captured_at": {"gte": "2025-01-01"}}}
                ]
            }
        },
        "size": 100
    }
    """
    if not opensearch_client:
        raise HTTPException(status_code=503, detail="Search service unavailable")

    try:
        results = opensearch_client.search(
            index="alpr-events-*",
            body=query_dsl
        )

        return {
            "took_ms": results["took"],
            "total": results["hits"]["total"]["value"],
            "results": [hit["_source"] for hit in results["hits"]["hits"]],
            "aggregations": results.get("aggregations", None)
        }
    except Exception as e:
        logger.error(f"DSL query error: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


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
