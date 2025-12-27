#!/usr/bin/env python3
"""
Storage Service for ALPR Events
Handles persistence of plate events to TimescaleDB (PostgreSQL)
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from loguru import logger
import json


class StorageService:
    """
    Database storage service for ALPR plate events
    Handles connection pooling, inserts, queries, and error handling
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "alpr_db",
        user: str = "alpr",
        password: str = "alpr_secure_pass",
        min_conn: int = 1,
        max_conn: int = 10,
    ):
        """
        Initialize storage service with connection pool

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_conn: Minimum connections in pool
            max_conn: Maximum connections in pool
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password

        # Connection pool for thread-safe database access
        self.pool: Optional[ThreadedConnectionPool] = None
        self.is_connected = False

        # Stats
        self.total_inserts = 0
        self.failed_inserts = 0

        # Initialize connection pool
        self._connect(min_conn, max_conn)

    def _connect(self, min_conn: int, max_conn: int):
        """
        Establish database connection pool

        Args:
            min_conn: Minimum connections
            max_conn: Maximum connections
        """
        try:
            self.pool = ThreadedConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )
            self.is_connected = True
            logger.success(f"✅ Connected to TimescaleDB: {self.host}:{self.port}/{self.database}")

            # Test connection
            self._test_connection()

        except Exception as e:
            self.is_connected = False
            logger.error(f"Failed to connect to TimescaleDB: {e}")
            raise

    def _test_connection(self):
        """Test database connection with simple query"""
        conn = None
        try:
            conn = self.pool.getconn()
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            logger.debug(f"Database version: {version}")
            cursor.close()
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def insert_event(self, event_dict: Dict[str, Any]) -> bool:
        """
        Insert a single plate event into database

        Args:
            event_dict: Event payload from PlateEvent.to_dict()

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected:
            logger.error("Not connected to database")
            return False

        conn = None
        try:
            # Extract fields from event dictionary
            plate = event_dict.get('plate', {})
            vehicle = event_dict.get('vehicle', {})
            images = event_dict.get('images', {})
            node = event_dict.get('node', {})
            extras = event_dict.get('extras', {})

            # Prepare SQL insert
            sql = """
                INSERT INTO plate_events (
                    event_id,
                    captured_at,
                    camera_id,
                    track_id,
                    plate_text,
                    plate_normalized_text,
                    plate_confidence,
                    plate_region,
                    vehicle_type,
                    vehicle_make,
                    vehicle_model,
                    vehicle_color,
                    plate_image_url,
                    vehicle_image_url,
                    frame_image_url,
                    latency_ms,
                    quality_score,
                    frame_number,
                    site_id,
                    host_id,
                    roi,
                    direction
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (event_id, captured_at) DO NOTHING
            """

            values = (
                event_dict.get('event_id'),
                event_dict.get('captured_at'),
                event_dict.get('camera_id'),
                event_dict.get('track_id'),
                plate.get('text'),
                plate.get('normalized_text'),
                plate.get('confidence'),
                plate.get('region'),
                vehicle.get('type'),
                vehicle.get('make'),
                vehicle.get('model'),
                vehicle.get('color'),
                images.get('plate_url'),
                images.get('vehicle_url'),
                images.get('frame_url'),
                event_dict.get('latency_ms'),
                extras.get('quality_score'),
                extras.get('frame_number'),
                node.get('site'),
                node.get('host'),
                extras.get('roi'),
                extras.get('direction'),
            )

            # Get connection from pool
            conn = self.pool.getconn()
            cursor = conn.cursor()

            # Execute insert
            cursor.execute(sql, values)
            conn.commit()

            cursor.close()

            self.total_inserts += 1

            logger.debug(
                f"💾 Saved to DB: {plate.get('normalized_text')} "
                f"(event: {event_dict.get('event_id')}, track: {event_dict.get('track_id')})"
            )

            return True

        except psycopg2.IntegrityError as e:
            if conn:
                conn.rollback()
            logger.warning(f"Duplicate event (already in DB): {e}")
            return False

        except Exception as e:
            if conn:
                conn.rollback()
            self.failed_inserts += 1
            logger.error(f"Failed to insert event: {e}")
            return False

        finally:
            if conn:
                self.pool.putconn(conn)

    def insert_batch(self, events: List[Dict[str, Any]]) -> int:
        """
        Insert multiple events in a batch

        Args:
            events: List of event dictionaries

        Returns:
            Number of successfully inserted events
        """
        success_count = 0
        for event in events:
            if self.insert_event(event):
                success_count += 1

        return success_count

    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve event by event_id

        Args:
            event_id: Event UUID

        Returns:
            Event dictionary or None if not found
        """
        if not self.is_connected:
            return None

        conn = None
        try:
            conn = self.pool.getconn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            sql = "SELECT * FROM plate_events WHERE event_id = %s"
            cursor.execute(sql, (event_id,))

            result = cursor.fetchone()
            cursor.close()

            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Failed to query event: {e}")
            return None

        finally:
            if conn:
                self.pool.putconn(conn)

    def get_events_by_plate(
        self,
        plate_text: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events by plate text (normalized)

        Args:
            plate_text: Normalized plate text
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of event dictionaries
        """
        if not self.is_connected:
            return []

        conn = None
        try:
            conn = self.pool.getconn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            sql = """
                SELECT * FROM plate_events
                WHERE plate_normalized_text = %s
                ORDER BY captured_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(sql, (plate_text, limit, offset))

            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to query events by plate: {e}")
            return []

        finally:
            if conn:
                self.pool.putconn(conn)

    def get_events_by_camera(
        self,
        camera_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events by camera and optional time range

        Args:
            camera_id: Camera identifier
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of event dictionaries
        """
        if not self.is_connected:
            return []

        conn = None
        try:
            conn = self.pool.getconn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Build query dynamically based on time filters
            if start_time and end_time:
                sql = """
                    SELECT * FROM plate_events
                    WHERE camera_id = %s
                      AND captured_at >= %s
                      AND captured_at <= %s
                    ORDER BY captured_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (camera_id, start_time, end_time, limit, offset))
            elif start_time:
                sql = """
                    SELECT * FROM plate_events
                    WHERE camera_id = %s
                      AND captured_at >= %s
                    ORDER BY captured_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (camera_id, start_time, limit, offset))
            else:
                sql = """
                    SELECT * FROM plate_events
                    WHERE camera_id = %s
                    ORDER BY captured_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (camera_id, limit, offset))

            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to query events by camera: {e}")
            return []

        finally:
            if conn:
                self.pool.putconn(conn)

    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve most recent events (by insertion time)

        Args:
            limit: Maximum number of results

        Returns:
            List of event dictionaries ordered by created_at (most recently inserted first)
        """
        if not self.is_connected:
            return []

        conn = None
        try:
            conn = self.pool.getconn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            sql = """
                SELECT * FROM plate_events
                ORDER BY created_at DESC
                LIMIT %s
            """
            cursor.execute(sql, (limit,))

            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to query recent events: {e}")
            return []

        finally:
            if conn:
                self.pool.putconn(conn)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics

        Returns:
            Dictionary of stats
        """
        if not self.is_connected:
            return {
                'is_connected': False,
                'total_inserts': self.total_inserts,
                'failed_inserts': self.failed_inserts,
            }

        conn = None
        try:
            conn = self.pool.getconn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            sql = "SELECT * FROM plate_events_stats"
            cursor.execute(sql)

            result = cursor.fetchone()
            cursor.close()

            stats = dict(result) if result else {}
            stats['is_connected'] = self.is_connected
            stats['total_inserts'] = self.total_inserts
            stats['failed_inserts'] = self.failed_inserts

            return stats

        except Exception as e:
            logger.error(f"Failed to query stats: {e}")
            return {
                'is_connected': self.is_connected,
                'total_inserts': self.total_inserts,
                'failed_inserts': self.failed_inserts,
            }

        finally:
            if conn:
                self.pool.putconn(conn)

    def close(self):
        """Close all database connections"""
        if self.pool:
            self.pool.closeall()
            self.is_connected = False
            logger.info("Database connections closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


class MockStorageService:
    """
    Mock storage service for testing without database
    Stores events in memory instead
    """

    def __init__(self, **kwargs):
        self.is_connected = True
        self.events = []  # In-memory storage
        self.total_inserts = 0
        self.failed_inserts = 0
        logger.warning("🔧 Using MockStorageService (no real database connection)")

    def insert_event(self, event_dict: Dict[str, Any]) -> bool:
        self.events.append(event_dict)
        self.total_inserts += 1

        plate = event_dict.get('plate', {})
        logger.info(
            f"💾 [MOCK] Would save to DB:\n"
            f"  Event ID: {event_dict.get('event_id')}\n"
            f"  Plate: {plate.get('normalized_text')}\n"
            f"  Camera: {event_dict.get('camera_id')}\n"
            f"  Track: {event_dict.get('track_id')}"
        )

        return True

    def insert_batch(self, events: List[Dict[str, Any]]) -> int:
        for event in events:
            self.insert_event(event)
        return len(events)

    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        for event in self.events:
            if event.get('event_id') == event_id:
                return event
        return None

    def get_events_by_plate(self, plate_text: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        results = [e for e in self.events if e.get('plate', {}).get('normalized_text') == plate_text]
        return results[offset:offset+limit]

    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.events[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        return {
            'is_connected': self.is_connected,
            'total_inserts': self.total_inserts,
            'failed_inserts': self.failed_inserts,
            'total_events': len(self.events),
        }

    def close(self):
        logger.info(f"[MOCK] Storage closed. Total events: {len(self.events)}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
