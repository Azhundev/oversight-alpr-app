"""
Image Storage Service - MinIO Integration for Plate Crop Images

This service manages async background uploads of plate crop images to MinIO (S3-compatible storage).
Provides local cache management, retry logic, and presigned URL generation.

Features:
- Async background uploads using ThreadPoolExecutor
- Retry logic with exponential backoff
- Local cache with automatic cleanup (date-based retention)
- Presigned URL generation for secure image access
- Graceful degradation if MinIO unavailable

Usage:
    storage = ImageStorageService(
        endpoint="localhost:9000",
        access_key="alpr_minio",
        secret_key="alpr_minio_secure_pass_2024",
        bucket_name="alpr-plate-images",
        local_cache_dir="output/crops",
        cache_retention_days=7
    )

    # Upload image (non-blocking)
    s3_url = storage.upload_image_async(
        local_file_path="output/crops/2025-12-24/camera1_track42.jpg",
        metadata={"camera_id": "camera1", "track_id": "42"}
    )

    # Get presigned URL (1-hour expiry)
    http_url = storage.get_presigned_url(s3_url, expiry_hours=1)

    # Shutdown gracefully
    storage.shutdown(wait=True, timeout=30)
"""

import os
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional, Dict, Any
from loguru import logger

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    logger.warning("⚠️  minio library not installed. Run: pip install minio>=7.2.0")
    MINIO_AVAILABLE = False


class ImageStorageService:
    """
    Manages async uploads of plate crop images to MinIO S3-compatible storage.

    Attributes:
        endpoint: MinIO server endpoint (e.g., "localhost:9000")
        access_key: MinIO access key
        secret_key: MinIO secret key
        bucket_name: S3 bucket name for plate images
        local_cache_dir: Local directory for image cache
        cache_retention_days: Days to keep local cache before cleanup
        thread_pool_size: Number of upload worker threads
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str = "alpr-plate-images",
        local_cache_dir: str = "output/crops",
        cache_retention_days: int = 7,
        thread_pool_size: int = 4,
        secure: bool = False,
    ):
        """
        Initialize Image Storage Service.

        Args:
            endpoint: MinIO endpoint (host:port)
            access_key: MinIO access key
            secret_key: MinIO secret key
            bucket_name: S3 bucket name
            local_cache_dir: Local cache directory path
            cache_retention_days: Days to retain local cache
            thread_pool_size: Number of background upload threads
            secure: Use HTTPS (True) or HTTP (False)

        Raises:
            ImportError: If minio library not installed
            Exception: If MinIO connection fails
        """
        if not MINIO_AVAILABLE:
            raise ImportError("minio library not installed")

        self.endpoint = endpoint
        self.bucket_name = bucket_name
        self.local_cache_dir = Path(local_cache_dir)
        self.cache_retention_days = cache_retention_days
        self.thread_pool_size = thread_pool_size

        # Initialize MinIO client
        try:
            self.client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure
            )

            # Verify bucket exists
            if not self.client.bucket_exists(bucket_name):
                logger.warning(f"Bucket '{bucket_name}' does not exist. It should be created by minio-init.")
            else:
                logger.success(f"✅ Connected to MinIO bucket: {bucket_name}")

        except Exception as e:
            logger.error(f"❌ Failed to connect to MinIO at {endpoint}: {e}")
            raise

        # Thread pool for async uploads
        self.executor = ThreadPoolExecutor(max_workers=thread_pool_size, thread_name_prefix="minio-upload")
        self.shutdown_event = threading.Event()

        # Upload statistics
        self.upload_count = 0
        self.upload_failures = 0
        self._stats_lock = threading.Lock()

        # Start cache cleanup thread
        self.cleanup_thread = threading.Thread(
            target=self._cache_cleanup_worker,
            daemon=True,
            name="cache-cleanup"
        )
        self.cleanup_thread.start()

        logger.info(f"Image Storage Service initialized with {thread_pool_size} upload threads")

    def upload_image_async(
        self,
        local_file_path: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Queue image upload to MinIO (non-blocking).

        Returns S3 URL immediately and uploads in background.

        Args:
            local_file_path: Path to local image file
            metadata: Optional metadata dict (camera_id, track_id, etc.)

        Returns:
            S3 URL in format: s3://bucket-name/YYYY-MM-DD/filename.jpg

        Raises:
            FileNotFoundError: If local file doesn't exist
        """
        local_path = Path(local_file_path)

        if not local_path.exists():
            raise FileNotFoundError(f"Local image not found: {local_file_path}")

        # Generate S3 object key (preserving date folder structure)
        # Example: 2025-12-24/CAM-001_track42_frame123_q0.85.jpg
        if local_path.parent.name.count('-') == 2:  # Date folder (YYYY-MM-DD)
            date_folder = local_path.parent.name
        else:
            date_folder = datetime.now().strftime('%Y-%m-%d')

        object_key = f"{date_folder}/{local_path.name}"
        s3_url = f"s3://{self.bucket_name}/{object_key}"

        # Queue upload in background
        future = self.executor.submit(
            self._upload_with_retry,
            local_path=local_path,
            object_key=object_key,
            metadata=metadata or {}
        )

        # Don't wait for completion - return URL immediately
        logger.debug(f"Queued upload: {local_file_path} → {s3_url}")

        return s3_url

    def _upload_with_retry(
        self,
        local_path: Path,
        object_key: str,
        metadata: Dict[str, str],
        max_retries: int = 3
    ) -> bool:
        """
        Upload file with retry logic (exponential backoff).

        Args:
            local_path: Path to local file
            object_key: S3 object key
            metadata: Metadata dict
            max_retries: Maximum retry attempts

        Returns:
            True if upload succeeded, False otherwise
        """
        for attempt in range(1, max_retries + 1):
            try:
                # Upload file to MinIO
                self.client.fput_object(
                    bucket_name=self.bucket_name,
                    object_name=object_key,
                    file_path=str(local_path),
                    metadata=metadata
                )

                # Success
                with self._stats_lock:
                    self.upload_count += 1

                logger.debug(f"✅ Uploaded: {object_key} (attempt {attempt})")
                return True

            except S3Error as e:
                logger.warning(f"Upload failed (attempt {attempt}/{max_retries}): {e}")

                if attempt < max_retries:
                    # Exponential backoff: 2s, 4s, 8s
                    sleep_time = 2 ** attempt
                    time.sleep(sleep_time)
                else:
                    # Final failure
                    with self._stats_lock:
                        self.upload_failures += 1
                    logger.error(f"❌ Upload failed after {max_retries} attempts: {object_key}")
                    return False

            except Exception as e:
                logger.error(f"Unexpected upload error: {e}")
                with self._stats_lock:
                    self.upload_failures += 1
                return False

        return False

    def get_presigned_url(
        self,
        s3_url: str,
        expiry_hours: int = 1
    ) -> Optional[str]:
        """
        Generate presigned HTTP URL for S3 object.

        Args:
            s3_url: S3 URL (s3://bucket-name/path/to/object.jpg)
            expiry_hours: URL expiry time in hours (default: 1)

        Returns:
            HTTP presigned URL or None if generation fails

        Example:
            s3_url = "s3://alpr-plate-images/2025-12-24/camera1_track42.jpg"
            http_url = service.get_presigned_url(s3_url, expiry_hours=1)
            # Returns: http://localhost:9000/alpr-plate-images/2025-12-24/camera1_track42.jpg?X-Amz-...
        """
        try:
            # Parse S3 URL
            if not s3_url.startswith("s3://"):
                logger.warning(f"Invalid S3 URL format: {s3_url}")
                return None

            # Extract object key from s3://bucket-name/path/to/object
            parts = s3_url.replace("s3://", "").split("/", 1)
            if len(parts) != 2:
                logger.warning(f"Invalid S3 URL structure: {s3_url}")
                return None

            bucket, object_key = parts

            if bucket != self.bucket_name:
                logger.warning(f"Bucket mismatch: {bucket} != {self.bucket_name}")
                return None

            # Generate presigned URL
            url = self.client.presigned_get_object(
                bucket_name=bucket,
                object_name=object_key,
                expires=timedelta(hours=expiry_hours)
            )

            logger.debug(f"Generated presigned URL for {object_key} (expires in {expiry_hours}h)")
            return url

        except S3Error as e:
            logger.warning(f"Failed to generate presigned URL for {s3_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating presigned URL: {e}")
            return None

    def _cache_cleanup_worker(self):
        """
        Background worker that periodically cleans up old cached images.

        Runs hourly, removes folders older than cache_retention_days.
        """
        while not self.shutdown_event.is_set():
            try:
                self._cleanup_old_cache()
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

            # Sleep for 1 hour (or until shutdown)
            self.shutdown_event.wait(timeout=3600)

    def _cleanup_old_cache(self):
        """
        Remove local cache folders older than retention period.

        Preserves today's folder and recent days within retention window.
        """
        if not self.local_cache_dir.exists():
            return

        cutoff_date = datetime.now() - timedelta(days=self.cache_retention_days)
        removed_count = 0

        for date_folder in self.local_cache_dir.iterdir():
            if not date_folder.is_dir():
                continue

            # Check if folder name is a date (YYYY-MM-DD)
            try:
                folder_date = datetime.strptime(date_folder.name, '%Y-%m-%d')

                if folder_date < cutoff_date:
                    # Remove old folder
                    import shutil
                    shutil.rmtree(date_folder)
                    removed_count += 1
                    logger.info(f"Removed old cache folder: {date_folder.name}")

            except ValueError:
                # Not a date folder, skip
                continue

        if removed_count > 0:
            logger.success(f"✅ Cache cleanup: removed {removed_count} old folders")

    def shutdown(self, wait: bool = True, timeout: int = 30):
        """
        Shutdown service gracefully.

        Args:
            wait: Wait for pending uploads to complete
            timeout: Max wait time in seconds
        """
        logger.info("Shutting down Image Storage Service...")

        # Signal cleanup thread to stop
        self.shutdown_event.set()

        # Wait for pending uploads
        if wait:
            logger.info(f"Waiting for pending uploads (timeout: {timeout}s)...")
            # Note: ThreadPoolExecutor.shutdown() in Python 3.10 doesn't support timeout parameter
            # We rely on the tasks completing within a reasonable time
            self.executor.shutdown(wait=True)
        else:
            self.executor.shutdown(wait=False)

        # Log final statistics
        with self._stats_lock:
            logger.info(f"Upload statistics: {self.upload_count} succeeded, {self.upload_failures} failed")

        logger.success("✅ Image Storage Service shutdown complete")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get upload statistics.

        Returns:
            Dict with upload_count and upload_failures
        """
        with self._stats_lock:
            return {
                "upload_count": self.upload_count,
                "upload_failures": self.upload_failures,
                "success_rate": self.upload_count / max(1, self.upload_count + self.upload_failures)
            }
