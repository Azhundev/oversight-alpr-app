#!/usr/bin/env python3
"""
ALPR Pilot Script
Tests complete pipeline: Camera → Detection → Visualization
Optimized for NVIDIA Jetson Orin NX
"""

print("=== PILOT.PY STARTING ===", flush=True)

import cv2
import sys
import time
import os
import numpy as np
from pathlib import Path
from loguru import logger
import csv
from datetime import datetime

# Add project root and service directories to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "edge_services"))
sys.path.insert(0, str(project_root / "core_services"))

from camera.camera_ingestion import CameraManager
from detector.detector_service import YOLOv11Detector
from ocr.ocr_service import PaddleOCRService
from tracker.bytetrack_service import ByteTrackService, Detection
from shared.utils.tracking_utils import bbox_to_numpy, get_track_color, draw_track_id
from event_processor.event_processor_service import EventProcessorService
from event_processor.kafka_publisher import KafkaPublisher, MockKafkaPublisher
from event_processor.avro_kafka_publisher import AvroKafkaPublisher
from storage.image_storage_service import ImageStorageService

# Prometheus metrics
from prometheus_client import Counter, Gauge, Histogram, start_http_server


class ALPRPilot:
    """Simple pilot for testing ALPR pipeline"""

    # Prometheus metrics (class-level for global access)
    metrics_frames_processed = Counter('alpr_frames_processed_total', 'Total frames processed', ['camera_id'])
    metrics_frames_skipped = Counter('alpr_frames_skipped_total', 'Total frames skipped', ['camera_id'])
    metrics_vehicles_detected = Counter('alpr_vehicles_detected_total', 'Total vehicles detected', ['camera_id'])
    metrics_plates_detected = Counter('alpr_plates_detected_total', 'Total plates detected', ['camera_id'])
    metrics_ocr_operations = Counter('alpr_ocr_operations_total', 'Total OCR operations performed', ['camera_id'])
    metrics_events_published = Counter('alpr_events_published_total', 'Total events published to Kafka', ['camera_id'])
    metrics_fps = Gauge('alpr_fps', 'Current FPS', ['camera_id'])
    metrics_processing_time = Histogram('alpr_processing_time_seconds', 'Frame processing time', ['camera_id'])
    metrics_detection_time = Histogram('alpr_detection_time_seconds', 'Detection inference time', ['camera_id'])
    metrics_ocr_time = Histogram('alpr_ocr_time_seconds', 'OCR processing time', ['camera_id'])
    metrics_active_tracks = Gauge('alpr_active_tracks', 'Number of active tracked vehicles', ['camera_id'])

    def __init__(
        self,
        camera_config: str = "config/cameras.yaml",
        detector_model: str = "yolo11n.pt",
        plate_model: str = None,
        use_tensorrt: bool = True,
        display: bool = True,
        save_output: bool = False,
        enable_ocr: bool = True,
        enable_tracking: bool = True,
        frame_skip: int = 2,
        adaptive_sampling: bool = True,
    ):
        """
        Initialize ALPR pilot

        Args:
            camera_config: Path to camera configuration
            detector_model: YOLOv11 vehicle model path
            plate_model: YOLOv11 plate detection model path (optional)
            use_tensorrt: Enable TensorRT optimization
            display: Show visualization window
            save_output: Save annotated frames to disk
            enable_ocr: Enable OCR for license plate recognition
            enable_tracking: Enable ByteTrack multi-object tracking
            frame_skip: Process every Nth frame (0=all frames, 1=every other, 2=every 3rd, etc)
            adaptive_sampling: Dynamically adjust frame skip based on vehicle presence
        """
        self.display = display
        self.save_output = save_output
        self.enable_ocr = enable_ocr
        self.enable_tracking = enable_tracking
        self.frame_skip = frame_skip
        self.adaptive_sampling = adaptive_sampling
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)  # Always create output dir for CSV

        # Create crops directory for saving plate images
        self.crops_dir = self.output_dir / "crops"
        self.crops_dir.mkdir(exist_ok=True)

        # Initialize plate reads CSV file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.plate_csv_path = self.output_dir / f"plate_reads_{timestamp}.csv"
        self._init_plate_csv()

        # Counter for saved crops
        self.crop_counter = 0

        # Initialize camera manager
        logger.info("Initializing camera manager...")
        self.camera_manager = CameraManager(camera_config)

        # Initialize detector
        logger.info("Initializing YOLOv11 detector...")
        self.detector = YOLOv11Detector(
            vehicle_model_path=detector_model,
            plate_model_path=plate_model,
            use_tensorrt=use_tensorrt,
            fp16=True,   # FP16 provides 2-3x speedup on Jetson and is stable
            int8=False,  # INT8 has TensorRT bugs with this model/Jetson combo
            batch_size=1,
        )

        # Warmup detector with 10 iterations to initialize CUDA kernels and stabilize inference times
        logger.info("Warming up detector...")
        self.detector.warmup(iterations=10)

        # Initialize OCR
        self.ocr = None
        if self.enable_ocr:
            logger.info("Initializing PaddleOCR...")
            self.ocr = PaddleOCRService(
                config_path="config/ocr.yaml",
                use_gpu=True,
                enable_tensorrt=False,
            )
            logger.info("Warming up OCR...")
            self.ocr.warmup(iterations=5)

        # Initialize Tracker
        self.tracker = None
        if self.enable_tracking:
            logger.info("Initializing ByteTrack tracker...")
            self.tracker = ByteTrackService(config_path="config/tracking.yaml")

        # Stats
        self.frame_count = 0
        self.unique_vehicles = set()  # Track unique vehicle IDs
        self.plate_count = 0
        self.start_time = time.time()
        self.fps_smoothed = 0.0
        self.fps_alpha = 0.1  # Smoothing factor

        # Track-based OCR throttling and attribute caching
        self.track_ocr_cache = {}  # track_id -> PlateDetection
        self.track_ocr_attempts = {}  # track_id -> number of OCR attempts
        self.track_attributes_cache = {}  # track_id -> {color, make, model}
        self.track_frame_count = {}  # track_id -> frame count
        self.track_plate_detected = set()  # track_ids that have had plates detected

        # Best-shot selection for gate scenario
        self.track_best_plate_quality = {}  # track_id -> best quality score
        self.track_best_plate_crop = {}  # track_id -> best plate crop image
        self.track_best_plate_bbox = {}  # track_id -> best plate bbox
        self.track_best_plate_frame = {}  # track_id -> frame number of best shot

        # OCR throttling parameters (gate scenario)
        self.ocr_min_track_frames = 2  # Wait for stable track
        self.ocr_min_confidence = 0.70  # Reasonable confidence (model needs retraining if too low)
        self.ocr_max_confidence_target = 0.90  # Target high confidence
        self.ocr_max_attempts = 20  # Reasonable attempts

        # Attribute inference parameters
        self.attr_min_confidence = 0.8  # Run attributes on high-confidence frames
        self.attr_min_track_frames = 5  # Wait for even more stability for attributes

        # Adaptive frame sampling parameters
        self.frames_since_last_detection = 0
        self.max_skip_no_vehicles = 9  # Skip more frames when no vehicles (process every 10th)
        self.min_skip_with_vehicles = max(0, frame_skip - 1)  # Reduce skip when vehicles present (but still skip some)
        self.adaptive_skip_current = self.frame_skip  # Current adaptive skip value

        # Frame quality filtering (skip blurry frames from motion video)
        self.enable_frame_quality_filter = False  # Disabled - process all frames for testing
        self.min_frame_sharpness = 120.0  # Lowered threshold (was 150)

        # Cached overlay data (for skipped frames)
        self.last_processing_time = 0.0
        self.last_num_detections = 0

        # Initialize Event Processor with deduplication and confidence filtering
        logger.info("Initializing Event Processor...")
        self.event_processor = EventProcessorService(
            site_id="DC1",  # TODO: Configure based on deployment (datacenter/location identifier)
            host_id="jetson-orin-nx",  # Unique device identifier (hostname or hardware serial)
            min_confidence=0.70,  # Minimum confidence threshold for plate detection (70%)
            dedup_similarity_threshold=0.85,  # Fuzzy match threshold for duplicate plates (85% similar)
            dedup_time_window_seconds=300,  # Time window for deduplication (5 minutes)
        )

        # Auto-reconnection state
        self.kafka_last_reconnect_attempt = 0
        self.minio_last_reconnect_attempt = 0
        self.kafka_reconnect_interval = 30  # Try reconnecting every 30 seconds
        self.minio_reconnect_interval = 30
        self.kafka_bootstrap_servers = "localhost:9092"
        self.kafka_schema_registry_url = "http://localhost:8081"
        self.minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.minio_access_key = os.getenv("MINIO_ACCESS_KEY", "alpr_minio")
        self.minio_secret_key = os.getenv("MINIO_SECRET_KEY", "alpr_minio_secure_pass_2024")
        self.minio_bucket = os.getenv("MINIO_BUCKET", "alpr-plate-images")

        # Initialize Kafka Publisher with Avro serialization and Schema Registry
        # Support both legacy single-topic and new multi-topic publishers
        use_multi_topic = os.getenv("KAFKA_USE_MULTI_TOPIC", "true").lower() == "true"
        enable_dual_publish = os.getenv("KAFKA_ENABLE_DUAL_PUBLISH", "false").lower() == "true"

        if use_multi_topic:
            logger.info("Initializing Multi-Topic Avro Kafka Publisher...")
            try:
                from edge_services.event_processor.multi_topic_publisher import MultiTopicAvroPublisher
                self.kafka_publisher = MultiTopicAvroPublisher(
                    bootstrap_servers="localhost:9092",  # Kafka broker address
                    schema_registry_url="http://localhost:8081",  # Schema Registry for Avro validation
                    client_id="alpr-jetson-producer",  # Unique client identifier for monitoring
                    compression_type="gzip",  # Compress messages to reduce network bandwidth (62% reduction)
                    acks="all",  # Wait for all replicas to acknowledge (strongest durability guarantee)
                    enable_dual_publish=enable_dual_publish,  # Publish to both old and new topics during migration
                    legacy_topic="alpr.plates.detected",  # Legacy topic for dual-publish mode
                )
                logger.success(
                    f"✅ Multi-topic Kafka publisher connected (Schema Registry: http://localhost:8081)\n"
                    f"   Dual-publish: {'enabled' if enable_dual_publish else 'disabled'}"
                )
            except Exception as e:
                # Graceful degradation: if Kafka/Schema Registry unavailable, use mock publisher
                logger.warning(f"⚠️  Kafka/Schema Registry not available, using mock publisher: {e}")
                self.kafka_publisher = MockKafkaPublisher(
                    bootstrap_servers="localhost:9092",
                    topic="alpr.events.plates",
                )
        else:
            logger.info("Initializing Legacy Single-Topic Avro Kafka Publisher...")
            try:
                self.kafka_publisher = AvroKafkaPublisher(
                    bootstrap_servers="localhost:9092",  # Kafka broker address
                    schema_registry_url="http://localhost:8081",  # Schema Registry for Avro validation
                    topic="alpr.plates.detected",  # Topic for plate detection events (legacy)
                    schema_file="schemas/plate_event.avsc",  # Avro schema definition (relative to project root)
                    client_id="alpr-jetson-producer",  # Unique client identifier for monitoring
                    compression_type="gzip",  # Compress messages to reduce network bandwidth (62% reduction)
                    acks="all",  # Wait for all replicas to acknowledge (strongest durability guarantee)
                )
                logger.success("✅ Legacy Avro Kafka publisher connected (Schema Registry: http://localhost:8081)")
            except Exception as e:
                # Graceful degradation: if Kafka/Schema Registry unavailable, use mock publisher
                # Mock publisher logs events locally without actual Kafka connectivity
                logger.warning(f"⚠️  Kafka/Schema Registry not available, using mock publisher: {e}")
                self.kafka_publisher = MockKafkaPublisher(
                    bootstrap_servers="localhost:9092",  # Not used by mock, kept for consistency
                    topic="alpr.plates.detected",
                )

        # Initialize Image Storage Service (MinIO) for S3-compatible plate image storage
        logger.info("Initializing Image Storage Service...")
        try:
            self.image_storage = ImageStorageService(
                endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),  # MinIO server address
                access_key=os.getenv("MINIO_ACCESS_KEY", "alpr_minio"),  # S3 access key
                secret_key=os.getenv("MINIO_SECRET_KEY", "alpr_minio_secure_pass_2024"),  # S3 secret key
                bucket_name=os.getenv("MINIO_BUCKET", "alpr-plate-images"),  # S3 bucket for plate images
                local_cache_dir=str(self.crops_dir.parent),  # Local cache directory (output/crops parent = output)
                cache_retention_days=int(os.getenv("MINIO_CACHE_RETENTION_DAYS", "7")),  # Keep cache for 7 days
                thread_pool_size=4,  # Concurrent upload threads (4 for balanced throughput)
            )
            logger.success("✅ Image storage service initialized")
        except Exception as e:
            # Graceful degradation: if MinIO unavailable, continue without image storage
            logger.warning(f"⚠️  MinIO not available: {e}")
            self.image_storage = None

        # Start Prometheus metrics HTTP server on port 8001
        try:
            start_http_server(8001)
            logger.success("✅ Prometheus metrics endpoint started at http://localhost:8001/metrics")
        except Exception as e:
            logger.warning(f"⚠️  Failed to start Prometheus metrics server: {e}")

        logger.success("ALPR Pilot initialized successfully")

    def _try_reconnect_kafka(self) -> bool:
        """
        Attempt to reconnect to Kafka if currently using MockKafkaPublisher
        Returns True if connected (or already connected), False otherwise
        """
        # Check if we're using mock publisher
        if not isinstance(self.kafka_publisher, MockKafkaPublisher):
            return True  # Already connected

        # Throttle reconnection attempts
        current_time = time.time()
        if current_time - self.kafka_last_reconnect_attempt < self.kafka_reconnect_interval:
            return False  # Too soon to retry

        self.kafka_last_reconnect_attempt = current_time

        # Try to connect
        logger.info("🔄 Attempting to connect to Kafka...")
        try:
            use_multi_topic = os.getenv("KAFKA_USE_MULTI_TOPIC", "true").lower() == "true"
            enable_dual_publish = os.getenv("KAFKA_ENABLE_DUAL_PUBLISH", "false").lower() == "true"

            if use_multi_topic:
                from edge_services.event_processor.multi_topic_publisher import MultiTopicAvroPublisher
                new_publisher = MultiTopicAvroPublisher(
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    schema_registry_url=self.kafka_schema_registry_url,
                    client_id="alpr-jetson-producer",
                    compression_type="gzip",
                    acks="all",
                    enable_dual_publish=enable_dual_publish,
                    legacy_topic="alpr.plates.detected",
                )
                logger.success(
                    f"✅ Connected to Kafka (multi-topic mode)\n"
                    f"   Bootstrap: {self.kafka_bootstrap_servers}\n"
                    f"   Schema Registry: {self.kafka_schema_registry_url}"
                )
            else:
                new_publisher = AvroKafkaPublisher(
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    schema_registry_url=self.kafka_schema_registry_url,
                    topic="alpr.plates.detected",
                    schema_file="schemas/plate_event.avsc",
                    client_id="alpr-jetson-producer",
                    compression_type="gzip",
                    acks="all",
                )
                logger.success(
                    f"✅ Connected to Kafka (legacy single-topic mode)\n"
                    f"   Bootstrap: {self.kafka_bootstrap_servers}\n"
                    f"   Schema Registry: {self.kafka_schema_registry_url}"
                )

            # Replace mock publisher with real one
            old_publisher = self.kafka_publisher
            self.kafka_publisher = new_publisher

            # Clean up old mock publisher
            try:
                old_publisher.close()
            except:
                pass

            return True

        except Exception as e:
            logger.debug(f"Kafka connection failed (will retry in {self.kafka_reconnect_interval}s): {e}")
            return False

    def _try_reconnect_minio(self) -> bool:
        """
        Attempt to reconnect to MinIO if currently disconnected
        Returns True if connected (or already connected), False otherwise
        """
        # Check if already connected
        if self.image_storage is not None:
            return True

        # Throttle reconnection attempts
        current_time = time.time()
        if current_time - self.minio_last_reconnect_attempt < self.minio_reconnect_interval:
            return False  # Too soon to retry

        self.minio_last_reconnect_attempt = current_time

        # Try to connect
        logger.info("🔄 Attempting to connect to MinIO...")
        try:
            self.image_storage = ImageStorageService(
                endpoint=self.minio_endpoint,
                access_key=self.minio_access_key,
                secret_key=self.minio_secret_key,
                bucket_name=self.minio_bucket,
                local_cache_dir=str(self.crops_dir.parent),
                cache_retention_days=int(os.getenv("MINIO_CACHE_RETENTION_DAYS", "7")),
                thread_pool_size=4,
            )
            logger.success(
                f"✅ Connected to MinIO\n"
                f"   Endpoint: {self.minio_endpoint}\n"
                f"   Bucket: {self.minio_bucket}"
            )
            return True

        except Exception as e:
            logger.debug(f"MinIO connection failed (will retry in {self.minio_reconnect_interval}s): {e}")
            return False

    def _init_plate_csv(self):
        """Initialize CSV file for plate reads"""
        # Always create new CSV with timestamp in filename
        with open(self.plate_csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Camera_ID', 'Track_ID', 'Plate_Text', 'Confidence', 'Frame_Number'])
        logger.info(f"Created plate reads CSV: {self.plate_csv_path}")

    def _calculate_plate_similarity(self, plate1: str, plate2: str) -> float:
        """
        Calculate similarity between two plate texts (Levenshtein distance)
        Returns similarity ratio 0.0-1.0 (1.0 = identical)
        """
        # Check for exact match first (optimization)
        if plate1 == plate2:
            return 1.0

        # Levenshtein distance: minimum number of single-character edits needed
        # to change one string into the other (insertions, deletions, substitutions)
        # Swap to ensure plate1 is longer (optimization)
        if len(plate1) < len(plate2):
            plate1, plate2 = plate2, plate1

        # Initialize distance array with column indices
        distances = range(len(plate2) + 1)

        # Iterate through each character in plate1
        for i1, c1 in enumerate(plate1):
            # Start new row with row index
            new_distances = [i1 + 1]

            # Iterate through each character in plate2
            for i2, c2 in enumerate(plate2):
                if c1 == c2:
                    # Characters match, no edit needed
                    new_distances.append(distances[i2])
                else:
                    # Characters differ, take minimum cost of:
                    # 1. Replace (distances[i2])
                    # 2. Delete (distances[i2 + 1])
                    # 3. Insert (new_distances[-1])
                    new_distances.append(1 + min((distances[i2], distances[i2 + 1], new_distances[-1])))
            distances = new_distances

        # Convert edit distance to similarity ratio (0.0-1.0)
        levenshtein_distance = distances[-1]
        max_length = max(len(plate1), len(plate2))
        similarity = 1.0 - (levenshtein_distance / max_length) if max_length > 0 else 0.0

        return similarity

    def _is_duplicate_plate(self, plate_text: str, track_id: int, similarity_threshold: float = 0.85) -> bool:
        """
        Check if this plate is a duplicate/near-duplicate of an already saved plate
        Uses fuzzy matching to handle OCR errors (e.g., ABC123 vs ABC1Z3)

        Args:
            plate_text: Plate text to check
            track_id: Track ID
            similarity_threshold: Minimum similarity to consider duplicate (0.85 = 85% match)

        Returns:
            True if duplicate, False if unique
        """
        # Check against all saved plates for this track
        if track_id in self.track_ocr_cache:
            cached_plate = self.track_ocr_cache[track_id].text
            similarity = self._calculate_plate_similarity(plate_text, cached_plate)

            if similarity >= similarity_threshold:
                logger.debug(f"Track {track_id}: Plate '{plate_text}' is {similarity:.2%} similar to cached '{cached_plate}' - skipping duplicate")
                return True

        return False

    def _merge_tracks_by_plate(self):
        """
        Merge tracks that have identical or very similar plate reads
        This catches track fragmentations that IoU-based merging misses
        """
        if len(self.track_ocr_cache) < 2:
            return

        # Group tracks by their plate text
        plate_to_tracks = {}
        for track_id, plate_detection in self.track_ocr_cache.items():
            plate_text = plate_detection.text
            if plate_text not in plate_to_tracks:
                plate_to_tracks[plate_text] = []
            plate_to_tracks[plate_text].append((track_id, plate_detection.confidence))

        # Merge tracks with same plate (keep highest confidence)
        for plate_text, track_list in plate_to_tracks.items():
            if len(track_list) > 1:
                # Sort by confidence (descending)
                track_list.sort(key=lambda x: x[1], reverse=True)
                keep_track_id = track_list[0][0]  # Keep highest confidence

                # Merge others into this one
                for merge_track_id, _ in track_list[1:]:
                    logger.info(f"Merging track {merge_track_id} → {keep_track_id} (same plate: {plate_text})")

                    # Transfer data from merged track to kept track
                    # Keep the best quality crop
                    if merge_track_id in self.track_best_plate_quality and keep_track_id in self.track_best_plate_quality:
                        if self.track_best_plate_quality[merge_track_id] > self.track_best_plate_quality[keep_track_id]:
                            self.track_best_plate_quality[keep_track_id] = self.track_best_plate_quality[merge_track_id]
                            self.track_best_plate_crop[keep_track_id] = self.track_best_plate_crop[merge_track_id]
                            self.track_best_plate_bbox[keep_track_id] = self.track_best_plate_bbox[merge_track_id]
                            self.track_best_plate_frame[keep_track_id] = self.track_best_plate_frame[merge_track_id]

                    # Remove merged track from cache
                    if merge_track_id in self.track_ocr_cache:
                        del self.track_ocr_cache[merge_track_id]
                    if merge_track_id in self.track_ocr_attempts:
                        del self.track_ocr_attempts[merge_track_id]
                    if merge_track_id in self.track_frame_count:
                        # Add frame counts
                        self.track_frame_count[keep_track_id] = self.track_frame_count.get(keep_track_id, 0) + self.track_frame_count[merge_track_id]
                        del self.track_frame_count[merge_track_id]

    def _save_plate_read(self, camera_id: str, track_id: int, plate_text: str, confidence: float, skip_duplicate_check: bool = False):
        """Save a plate read to CSV file (with deduplication) - DEPRECATED: Use _publish_plate_event instead"""
        try:
            # Check for duplicates using fuzzy matching (skip if this is a new read)
            if not skip_duplicate_check and self._is_duplicate_plate(plate_text, track_id):
                return  # Skip duplicate

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            with open(self.plate_csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, camera_id, track_id, plate_text, f"{confidence:.3f}", self.frame_count])
            logger.info(f"✅ Saved unique plate: Track {track_id} = {plate_text} (conf: {confidence:.2f})")
        except Exception as e:
            logger.error(f"Failed to save plate read: {e}")

    def _publish_plate_event(self, camera_id: str, track_id: int, plate_detection, vehicle=None, vehicle_idx=None):
        """
        Process and publish plate event to Kafka (replaces _save_plate_read)

        Args:
            camera_id: Camera identifier
            track_id: Track ID
            plate_detection: PlateDetection object from OCR
            vehicle: VehicleDetection object (optional)
            vehicle_idx: Vehicle index for looking up attributes
        """
        try:
            # Auto-reconnect to Kafka if currently using mock publisher
            self._try_reconnect_kafka()
            # Get vehicle attributes
            vehicle_type = vehicle.vehicle_type if vehicle else "unknown"
            vehicle_color = vehicle.color if vehicle else None
            vehicle_make = vehicle.make if vehicle else None
            vehicle_model = vehicle.model if vehicle else None

            # Get cached attributes if available
            if track_id in self.track_attributes_cache:
                attrs = self.track_attributes_cache[track_id]
                vehicle_color = vehicle_color or attrs.get('color')
                vehicle_make = vehicle_make or attrs.get('make')
                vehicle_model = vehicle_model or attrs.get('model')

            # Generate plate image path (will be uploaded after saving to disk)
            plate_image_path = None
            if track_id in self.track_best_plate_crop:
                date_folder = datetime.now().strftime('%Y-%m-%d')
                filename = f"{camera_id}_track{track_id}_frame{self.track_best_plate_frame.get(track_id, 0)}_q{self.track_best_plate_quality.get(track_id, 0):.2f}.jpg"
                local_image_path = str(self.crops_dir / date_folder / filename)

                # Will be updated to S3 URL after upload (in _save_best_crop_to_disk)
                plate_image_path = local_image_path

            # Get quality score
            quality_score = self.track_best_plate_quality.get(track_id, 0.0)

            # Process event through EventProcessorService
            event = self.event_processor.process_detection(
                plate_text=plate_detection.text,
                plate_confidence=plate_detection.confidence,
                camera_id=camera_id,
                track_id=track_id,
                vehicle_type=vehicle_type,
                vehicle_color=vehicle_color,
                vehicle_make=vehicle_make,
                vehicle_model=vehicle_model,
                plate_image_path=plate_image_path,
                region="US-FL",  # TODO: Make configurable via config/cameras.yaml (e.g., region: "US-CA", "US-TX")
                roi=None,  # TODO: Add Region of Interest (ROI) coordinates from YOLO detection bounding box
                direction=None,  # TODO: Add vehicle direction detection (N/S/E/W) using motion vector analysis
                quality_score=quality_score,
                frame_number=self.frame_count,
            )

            if event:
                # Publish to Kafka (support both legacy and multi-topic publishers)
                from edge_services.event_processor.multi_topic_publisher import MultiTopicAvroPublisher
                if isinstance(self.kafka_publisher, MultiTopicAvroPublisher):
                    # Use multi-topic publisher (routes to alpr.events.plates)
                    success = self.kafka_publisher.publish_plate_event(event.to_dict())
                else:
                    # Use legacy single-topic publisher (routes to alpr.plates.detected)
                    success = self.kafka_publisher.publish_event(event.to_dict())

                if success:
                    # Metrics: Record successful event publication
                    self.metrics_events_published.labels(camera_id=camera_id).inc()

                    logger.success(
                        f"📤 Published to Kafka: {event.plate['normalized_text']} "
                        f"(track: {track_id}, event: {event.event_id})"
                    )

                    # Also save to CSV for backwards compatibility
                    self._save_plate_read(camera_id, track_id, plate_detection.text, plate_detection.confidence, skip_duplicate_check=True)

                    # Save best crop to disk
                    if track_id in self.track_best_plate_crop:
                        self._save_best_crop_to_disk(track_id, camera_id)
                else:
                    logger.error("Failed to publish event to Kafka")
            else:
                logger.debug("Event rejected by processor (duplicate or invalid)")

        except Exception as e:
            logger.error(f"Failed to publish plate event: {e}")

    def _save_best_crop_to_disk(self, track_id: int, camera_id: str):
        """
        Save the best cached plate crop for a track to disk and upload to MinIO

        Args:
            track_id: Track identifier
            camera_id: Camera identifier
        """
        try:
            if track_id not in self.track_best_plate_crop:
                logger.warning(f"No cached crop for track {track_id}")
                return

            plate_crop = self.track_best_plate_crop[track_id]
            quality_score = self.track_best_plate_quality[track_id]
            frame_number = self.track_best_plate_frame[track_id]

            # Create date-based folder
            date_folder = datetime.now().strftime('%Y-%m-%d')
            date_crops_dir = self.crops_dir / date_folder
            date_crops_dir.mkdir(exist_ok=True, parents=True)

            # Generate filename with track ID, frame, and quality score
            filename = f"{camera_id}_track{track_id}_frame{frame_number}_q{quality_score:.2f}.jpg"
            filepath = date_crops_dir / filename

            # Save crop to disk first
            cv2.imwrite(str(filepath), plate_crop)
            self.crop_counter += 1
            logger.success(f"💾 Saved plate crop: {date_folder}/{filename} (quality: {quality_score:.3f})")

            # Upload to MinIO asynchronously (after file is saved)
            # Auto-reconnect to MinIO if currently disconnected
            self._try_reconnect_minio()

            if self.image_storage:
                try:
                    # Get plate text from cache if available
                    plate_text = self.track_ocr_cache[track_id].text if track_id in self.track_ocr_cache else ""

                    s3_url = self.image_storage.upload_image_async(
                        local_file_path=str(filepath),
                        metadata={
                            "camera_id": camera_id,
                            "track_id": str(track_id),
                            "plate_text": plate_text,
                            "quality_score": str(quality_score),
                            "frame_number": str(frame_number),
                        }
                    )
                    logger.success(f"☁️  Queued upload to MinIO: {filename} → {s3_url}")
                except Exception as e:
                    logger.error(f"MinIO upload failed: {e}")

        except Exception as e:
            logger.error(f"Failed to save best crop to disk: {e}")

    def _save_plate_crop(self, frame, plate_bbox, track_id: int, camera_id: str, force_save: bool = False):
        """
        Save cropped plate image (best-shot selection for gate scenario)
        Only saves if this is the best quality shot seen for this track

        Args:
            frame: Input frame
            plate_bbox: Plate bounding box
            track_id: Track identifier
            camera_id: Camera identifier
            force_save: Force save (used when track is ending)
        """
        try:
            # Calculate quality score for this detection
            quality_score = self.calculate_plate_quality(frame, plate_bbox)

            # Check if this is the best shot for this track
            current_best = self.track_best_plate_quality.get(track_id, 0.0)

            if quality_score > current_best or force_save:
                # Extract plate region from frame with padding for better OCR
                x1, y1, x2, y2 = map(int, [plate_bbox.x1, plate_bbox.y1, plate_bbox.x2, plate_bbox.y2])

                # Add 50% padding on all sides (balanced crop size)
                # Enough context without wasting space on background
                bbox_width = x2 - x1
                bbox_height = y2 - y1
                pad_x = int(bbox_width * 0.5)
                pad_y = int(bbox_height * 0.5)

                # Expand bbox with padding
                x1 = x1 - pad_x
                y1 = y1 - pad_y
                x2 = x2 + pad_x
                y2 = y2 + pad_y

                # Ensure coordinates are within frame bounds
                h, w = frame.shape[:2]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                # Skip if invalid bbox
                if x2 <= x1 or y2 <= y1:
                    return

                plate_crop = frame[y1:y2, x1:x2]

                # Cache this as the best shot for this track
                self.track_best_plate_quality[track_id] = quality_score
                self.track_best_plate_crop[track_id] = plate_crop.copy()
                self.track_best_plate_bbox[track_id] = plate_bbox
                self.track_best_plate_frame[track_id] = self.frame_count

                logger.debug(f"Track {track_id}: New best plate quality {quality_score:.3f} (frame {self.frame_count})")

                # Only save to disk when forced (track ending or high confidence reached)
                if force_save:
                    # Create date-based folder (e.g., output/crops/2025-11-25/)
                    date_folder = datetime.now().strftime('%Y-%m-%d')
                    date_crops_dir = self.crops_dir / date_folder
                    date_crops_dir.mkdir(exist_ok=True)

                    # Generate filename with track ID and best frame number
                    filename = f"{camera_id}_track{track_id}_frame{self.track_best_plate_frame[track_id]}_q{quality_score:.2f}.jpg"
                    filepath = date_crops_dir / filename

                    # Save best crop for this track
                    cv2.imwrite(str(filepath), plate_crop)
                    self.crop_counter += 1
                    logger.info(f"Saved BEST plate crop for track {track_id}: {date_folder}/{filename} (quality: {quality_score:.3f})")

        except Exception as e:
            logger.error(f"Failed to save plate crop: {e}")

    def _compute_iou_np(self, bbox1: np.ndarray, bbox2: np.ndarray) -> float:
        """
        Compute Intersection over Union (IoU) between two numpy bboxes [x1, y1, x2, y2]
        IoU measures overlap between bounding boxes, used for matching detections to tracks

        Returns:
            float: IoU score between 0.0 (no overlap) and 1.0 (perfect overlap)
        """
        # Find intersection rectangle coordinates
        x1_i = max(bbox1[0], bbox2[0])  # Leftmost edge of intersection
        y1_i = max(bbox1[1], bbox2[1])  # Topmost edge of intersection
        x2_i = min(bbox1[2], bbox2[2])  # Rightmost edge of intersection
        y2_i = min(bbox1[3], bbox2[3])  # Bottommost edge of intersection

        # Check if there's no overlap (invalid intersection)
        if x2_i < x1_i or y2_i < y1_i:
            return 0.0

        # Calculate areas
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union = area1 + area2 - intersection

        # Return IoU ratio
        return intersection / union if union > 0 else 0.0

    def _find_nearby_cached_plate(self, track_id, current_bbox, iou_threshold=0.3):
        """
        Find if any nearby tracks (likely same vehicle) already have cached OCR results
        This prevents redundant OCR on fragmented tracks

        Args:
            track_id: Current track ID to check
            current_bbox: Current vehicle bounding box (BoundingBox object)
            iou_threshold: Minimum IoU overlap to consider tracks as "nearby" (default: 0.3)

        Returns:
            PlateDetection object if nearby cached plate found, None otherwise
        """
        # Convert current bbox to numpy for IoU computation
        current_bbox_np = np.array([current_bbox.x1, current_bbox.y1, current_bbox.x2, current_bbox.y2])

        # Search through all tracks with cached OCR results
        best_iou = 0.0
        best_plate = None

        for other_track_id, plate_detection in self.track_ocr_cache.items():
            # Skip self
            if other_track_id == track_id:
                continue

            # Get the bbox where this plate was detected (if available)
            # We need to look up the current vehicle position for this track
            # For now, we'll check against recently cached plate bboxes
            if other_track_id in self.track_best_plate_bbox:
                other_plate_bbox = self.track_best_plate_bbox[other_track_id]

                # Estimate vehicle bbox from plate bbox (plate is typically in lower portion of vehicle)
                # Rough heuristic: vehicle is ~4x height and ~2x width of plate
                plate_height = other_plate_bbox.y2 - other_plate_bbox.y1
                plate_width = other_plate_bbox.x2 - other_plate_bbox.x1

                estimated_vehicle_x1 = other_plate_bbox.x1 - plate_width * 0.5
                estimated_vehicle_y1 = other_plate_bbox.y1 - plate_height * 3.0  # Plate is near bottom
                estimated_vehicle_x2 = other_plate_bbox.x2 + plate_width * 0.5
                estimated_vehicle_y2 = other_plate_bbox.y2 + plate_height * 0.5

                other_bbox_np = np.array([estimated_vehicle_x1, estimated_vehicle_y1,
                                         estimated_vehicle_x2, estimated_vehicle_y2])

                # Compute IoU between current vehicle and estimated other vehicle
                iou = self._compute_iou_np(current_bbox_np, other_bbox_np)

                if iou > best_iou and iou >= iou_threshold:
                    best_iou = iou
                    best_plate = plate_detection

        if best_plate is not None:
            logger.debug(f"Track {track_id}: Found nearby cached plate (IoU: {best_iou:.3f})")

        return best_plate

    def should_run_ocr(self, track_id, current_bbox=None):
        """
        Determine if OCR should be run for this track (gate scenario: continuous improvement)
        Now includes spatial deduplication to prevent redundant OCR on fragmented tracks

        Args:
            track_id: Track identifier
            current_bbox: Current bounding box (BoundingBox object) for spatial checking

        Returns:
            bool: True if OCR should run
        """
        # Track stable enough (minimum frames)?
        if self.track_frame_count.get(track_id, 0) < self.ocr_min_track_frames:
            return False

        # Already reached maximum target confidence?
        if track_id in self.track_ocr_cache:
            cached_result = self.track_ocr_cache[track_id]
            # Only stop if we've reached the max target (0.95)
            if cached_result.confidence >= self.ocr_max_confidence_target:
                return False

        # Check if we've exceeded max attempts
        attempts = self.track_ocr_attempts.get(track_id, 0)
        if attempts >= self.ocr_max_attempts:
            return False

        # PROACTIVE DEDUPLICATION: Check if nearby tracks already have cached plate reads
        # This prevents redundant OCR on fragmented tracks (same car, multiple track IDs)
        if current_bbox is not None:
            nearby_plate = self._find_nearby_cached_plate(track_id, current_bbox)
            if nearby_plate is not None:
                # Found a nearby track with cached OCR - reuse it instead of running OCR again
                logger.info(f"Track {track_id}: Reusing cached plate from nearby track (spatial deduplication)")
                self.track_ocr_cache[track_id] = nearby_plate
                self.track_ocr_attempts[track_id] = 0  # Mark as reused, not attempted
                return False

        return True

    def should_cache_attributes(self, track_id, vehicle_confidence):
        """
        Determine if we should cache vehicle attributes for this track

        Args:
            track_id: Track identifier
            vehicle_confidence: Current detection confidence

        Returns:
            bool: True if attributes should be cached
        """
        # Already have attributes for this track?
        if track_id in self.track_attributes_cache:
            return False

        # Track stable enough?
        if self.track_frame_count.get(track_id, 0) < self.attr_min_track_frames:
            return False

        # High confidence detection?
        if vehicle_confidence < self.attr_min_confidence:
            return False

        return True

    def cache_vehicle_attributes(self, track_id, vehicle):
        """
        Cache vehicle attributes (color, make, model) for a track

        Args:
            track_id: Track identifier
            vehicle: VehicleDetection object
        """
        # For now, just cache what we have from the detection
        # In a full system, this is where you'd run color/make/model inference
        attributes = {
            'color': vehicle.color,
            'make': vehicle.make,
            'model': vehicle.model,
            'confidence': vehicle.confidence,
        }

        self.track_attributes_cache[track_id] = attributes
        logger.debug(f"Cached attributes for track {track_id}: {attributes}")

    def calculate_plate_sharpness(self, frame, plate_bbox):
        """
        Calculate sharpness score for a plate detection

        Args:
            frame: Input frame
            plate_bbox: Plate bounding box

        Returns:
            float: Sharpness score (Laplacian variance)
        """
        try:
            # Extract plate region
            x1, y1, x2, y2 = map(int, [plate_bbox.x1, plate_bbox.y1, plate_bbox.x2, plate_bbox.y2])
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 <= x1 or y2 <= y1:
                return 0.0

            plate_crop = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

            return laplacian_var

        except Exception as e:
            logger.debug(f"Failed to calculate plate sharpness: {e}")
            return 0.0

    def calculate_plate_quality(self, frame, plate_bbox):
        """
        Calculate quality score for a plate detection (gate scenario: best-shot selection)

        Uses multiple factors to determine optimal plate capture for OCR:
        - Sharpness (Laplacian variance) - most important for OCR accuracy
        - Size (larger plates have more detail)
        - Aspect ratio (validates proper plate detection)

        Args:
            frame: Input frame
            plate_bbox: Plate bounding box

        Returns:
            float: Quality score 0.0-1.0 (higher is better)
        """
        try:
            # Extract plate region with bounds checking
            x1, y1, x2, y2 = map(int, [plate_bbox.x1, plate_bbox.y1, plate_bbox.x2, plate_bbox.y2])
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            # Validate bbox
            if x2 <= x1 or y2 <= y1:
                return 0.0

            plate_crop = frame[y1:y2, x1:x2]

            # 1. Size score - larger plates capture more detail for OCR
            #    Typical plate at optimal distance: ~8000 pixels area
            plate_area = (x2 - x1) * (y2 - y1)
            size_score = min(plate_area / 8000.0, 1.0)  # Normalize to 0-1, cap at 1.0

            # 2. Sharpness score (CRITICAL for OCR accuracy)
            #    Uses Laplacian operator to detect edges - higher variance = sharper image
            #    Motion blur significantly reduces OCR accuracy
            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            # Empirical thresholds from testing:
            # - Good frames: 200+ variance
            # - Blurry frames: <150 variance
            # Normalize to 0-1 using 300 as reference maximum
            sharpness_score = min(laplacian_var / 300.0, 1.0)

            # 3. Aspect ratio score - validates correct plate detection
            #    Florida plates have standard 2.3:1 width:height ratio
            plate_width = x2 - x1
            plate_height = y2 - y1
            aspect_ratio = plate_width / plate_height if plate_height > 0 else 0
            ideal_ratio = 2.3  # Florida standard license plate
            # Penalize deviation from ideal ratio
            aspect_score = 1.0 - min(abs(aspect_ratio - ideal_ratio) / ideal_ratio, 1.0)

            # Weighted combination optimized for motion video OCR
            # Sharpness is 70% - critical for reading text in motion
            # Size is 20% - helps with character recognition
            # Aspect ratio is 10% - validates detection accuracy
            quality = (sharpness_score * 0.70) + (size_score * 0.20) + (aspect_score * 0.10)

            return quality

        except Exception as e:
            logger.debug(f"Failed to calculate plate quality: {e}")
            return 0.0

    def process_frame(self, frame, camera_id: str):
        """
        Process single frame through detection pipeline

        Args:
            frame: Input frame (BGR)
            camera_id: Camera identifier

        Returns:
            Annotated frame
        """
        # Adaptive or fixed frame skipping for performance
        current_skip = self.adaptive_skip_current if self.adaptive_sampling else self.frame_skip

        if current_skip > 0 and self.frame_count % (current_skip + 1) != 0:
            # Skip processing, but still draw overlay for visual consistency
            self.frame_count += 1
            # Metrics: Record skipped frame
            self.metrics_frames_skipped.labels(camera_id=camera_id).inc()
            vis_frame = frame.copy()
            # Use cached values from last processed frame
            self._draw_overlay(vis_frame, camera_id, self.last_num_detections, self.last_processing_time)
            return vis_frame

        start_time = time.time()
        detection_start = time.time()  # Track detection time separately

        # Detect vehicles
        vehicles = self.detector.detect_vehicles(
            frame,
            confidence_threshold=0.25,  # Standard threshold
            nms_threshold=0.4  # Lower NMS = more aggressive suppression of overlapping boxes (was 0.5)
        )

        # Metrics: Record detection time and vehicle count
        detection_time = time.time() - detection_start
        self.metrics_detection_time.labels(camera_id=camera_id).observe(detection_time)
        self.metrics_vehicles_detected.labels(camera_id=camera_id).inc(len(vehicles))

        # Adaptive frame sampling: dynamically adjust frame skip rate based on vehicle presence
        # This optimizes performance by processing fewer frames when no vehicles are present
        if self.adaptive_sampling:
            if len(vehicles) > 0:
                # Vehicles detected - process more frequently to capture details
                self.frames_since_last_detection = 0
                self.adaptive_skip_current = self.min_skip_with_vehicles
            else:
                # No vehicles - increase skip rate gradually to save processing power
                self.frames_since_last_detection += 1
                if self.frames_since_last_detection > 30:  # After 30 frames (~1 sec @ 30fps) without vehicles
                    # Use maximum skip rate (process every 10th frame)
                    self.adaptive_skip_current = self.max_skip_no_vehicles
                else:
                    # Gradual transition period - use baseline skip rate
                    self.adaptive_skip_current = self.frame_skip

        # Update tracker with vehicle detections
        # Maps vehicle detection index to persistent track ID for cross-frame association
        vehicle_tracks = {}  # vehicle_idx -> track_id

        if self.enable_tracking and self.tracker:
            # Convert detections to ByteTrack format
            detections = []
            for vehicle in vehicles:
                det = Detection(
                    bbox=bbox_to_numpy(vehicle.bbox),  # Convert to [x1, y1, x2, y2] numpy array
                    confidence=vehicle.confidence,
                    class_id=0  # All vehicles treated as single class for now
                )
                detections.append(det)

            # Update tracker - associates detections with existing tracks or creates new ones
            # ByteTrack uses Kalman filtering and IoU matching for robust tracking
            active_tracks = self.tracker.update(detections)

            # Periodic debug logging
            if self.frame_count % 30 == 0:
                logger.info(f"Frame {self.frame_count}: {len(vehicles)} detections → {len(active_tracks)} tracks, Unique: {len(self.unique_vehicles)}")

            # Map vehicle detections to track IDs using IoU matching
            # ByteTrack internally assigns tracks, but we need to match them back to our detections
            # This allows us to associate OCR results with specific vehicle detections
            for idx, vehicle in enumerate(vehicles):
                vehicle_bbox_np = bbox_to_numpy(vehicle.bbox)

                # Find best matching track by computing IoU with all active tracks
                best_iou = 0.0
                best_track_id = None

                for track in active_tracks:
                    track_bbox = track.tlbr  # Top-left, bottom-right format
                    iou = self._compute_iou_np(vehicle_bbox_np, track_bbox)
                    if iou > best_iou:
                        best_iou = iou
                        best_track_id = track.track_id

                # Assign track ID if we found a reasonable match
                # IoU threshold of 0.25 is lenient enough to handle:
                # - Bbox variations between detector and tracker
                # - Slight position changes in motion video
                # - Partial occlusions
                if best_track_id is not None and best_iou >= 0.25:
                    vehicle_tracks[idx] = best_track_id

                    # Increment frame count for this track (used for OCR throttling)
                    if best_track_id not in self.track_frame_count:
                        self.track_frame_count[best_track_id] = 0
                    self.track_frame_count[best_track_id] += 1

                    # Cache vehicle attributes (color, make, model) on first high-confidence frame
                    # Avoids running expensive attribute inference on every frame
                    if self.should_cache_attributes(best_track_id, vehicle.confidence):
                        self.cache_vehicle_attributes(best_track_id, vehicle)
                else:
                    # No good match found - likely a false detection or tracking error
                    logger.debug(f"Vehicle {idx}: No track match (best IoU: {best_iou:.3f})")
        else:
            # Tracking disabled - assign sequential IDs (no cross-frame association)
            for idx, vehicle in enumerate(vehicles):
                vehicle_tracks[idx] = idx


        # Detect plates (within vehicle bboxes)
        vehicle_bboxes = [v.bbox for v in vehicles] if vehicles else None
        plates = self.detector.detect_plates(
            frame,
            vehicle_bboxes=vehicle_bboxes,
            confidence_threshold=0.20,  # Standard threshold
            nms_threshold=0.4
        )

        # Track plates detected per track and update best-shot selection
        if plates:
            for vehicle_idx, plate_bboxes in plates.items():
                track_id = vehicle_tracks.get(vehicle_idx)

                if track_id is None:
                    continue

                # Track that this track has a plate detected
                if track_id not in self.track_plate_detected:
                    self.track_plate_detected.add(track_id)

                # Update best plate crop for this track (always evaluate quality)
                plate_bbox = plate_bboxes[0]  # Use first plate
                # Don't force save yet - wait for better quality or OCR success
                self._save_plate_crop(frame, plate_bbox, track_id, camera_id, force_save=False)

        # Run OCR on detected plates (CONTINUOUS IMPROVEMENT - gate scenario)
        # Keep trying until we reach max confidence target (0.95) or max attempts
        plate_texts = {}  # Map vehicle index to plate text
        ocr_runs_this_frame = 0

        if self.ocr and plates:
            # Process each track individually (NO BATCHING for gate control)
            for vehicle_idx, plate_bboxes in plates.items():
                track_id = vehicle_tracks.get(vehicle_idx)

                if track_id is None:
                    continue

                # Get vehicle bbox for spatial deduplication check
                vehicle_bbox = vehicles[vehicle_idx].bbox if vehicle_idx < len(vehicles) else None

                # Check if we should run OCR for this track (includes spatial deduplication)
                if self.should_run_ocr(track_id, current_bbox=vehicle_bbox):
                    # Use first plate only (assumes one plate per vehicle)
                    plate_bbox = plate_bboxes[0]

                    # Frame quality check - skip blurry frames (motion video)
                    if self.enable_frame_quality_filter:
                        plate_quality = self.calculate_plate_quality(frame, plate_bbox)
                        # Extract sharpness component (70% of quality score)
                        plate_sharpness = self.calculate_plate_sharpness(frame, plate_bbox)

                        if plate_sharpness < self.min_frame_sharpness:
                            logger.debug(f"Track {track_id}: Skipping blurry frame (sharpness: {plate_sharpness:.1f} < {self.min_frame_sharpness})")
                            continue

                    ocr_runs_this_frame += 1

                    # Track OCR attempts
                    if track_id not in self.track_ocr_attempts:
                        self.track_ocr_attempts[track_id] = 0
                    self.track_ocr_attempts[track_id] += 1

                    # SINGLE OCR - continuous improvement for gate control
                    # Metrics: Time OCR operation
                    ocr_start = time.time()
                    plate_detection = self.ocr.recognize_plate(
                        frame,
                        plate_bbox,
                        preprocess=True
                    )
                    ocr_time = time.time() - ocr_start

                    # Metrics: Record OCR operation and timing
                    self.metrics_ocr_operations.labels(camera_id=camera_id).inc()
                    self.metrics_ocr_time.labels(camera_id=camera_id).observe(ocr_time)

                    if plate_detection:
                        # Update cache (may overwrite low-confidence result with better one)
                        is_new_read = track_id not in self.track_ocr_cache
                        is_better = (track_id in self.track_ocr_cache and
                                   plate_detection.confidence > self.track_ocr_cache[track_id].confidence)

                        if is_new_read or is_better:
                            old_confidence = self.track_ocr_cache[track_id].confidence if track_id in self.track_ocr_cache else 0.0
                            self.track_ocr_cache[track_id] = plate_detection

                            # Only count unique high-confidence reads
                            if is_new_read:
                                self.plate_count += 1

                            # Log with improvement indicator
                            if is_better:
                                improvement = plate_detection.confidence - old_confidence
                                conf_indicator = "HIGH" if plate_detection.confidence >= self.ocr_min_confidence else "IMPROVING"
                                logger.info(f"OCR Track {track_id} [{conf_indicator}]: {plate_detection.text} (conf: {plate_detection.confidence:.2f} +{improvement:.2f}, attempt: {self.track_ocr_attempts[track_id]})")
                            else:
                                conf_indicator = "HIGH" if plate_detection.confidence >= self.ocr_min_confidence else "LOW"
                                logger.info(f"OCR Track {track_id} [{conf_indicator}]: {plate_detection.text} (conf: {plate_detection.confidence:.2f}, attempt: {self.track_ocr_attempts[track_id]})")

                            # Publish to Kafka and save once when reaching high confidence
                            if plate_detection.confidence >= self.ocr_min_confidence and is_new_read:
                                logger.debug(f"Attempting to publish plate: track={track_id}, text={plate_detection.text}, conf={plate_detection.confidence:.2f}")
                                # Get vehicle object for metadata
                                vehicle = vehicles[vehicle_idx] if vehicle_idx < len(vehicles) else None
                                # Publish plate event to Kafka
                                self._publish_plate_event(camera_id, track_id, plate_detection, vehicle=vehicle, vehicle_idx=vehicle_idx)

                            # Also save if we reached max target confidence (even if already saved)
                            elif plate_detection.confidence >= self.ocr_max_confidence_target:
                                if track_id in self.track_best_plate_crop:
                                    logger.success(f"Track {track_id}: Reached target confidence {plate_detection.confidence:.2f} - saving best crop!")
                                    self._save_best_crop_to_disk(track_id, camera_id)
                    else:
                        logger.debug(f"OCR Track {track_id}: No text detected (attempt: {self.track_ocr_attempts[track_id]})")

            # Use cached OCR results for all tracks
            for vehicle_idx, plate_bboxes in plates.items():
                track_id = vehicle_tracks.get(vehicle_idx)

                if track_id and track_id in self.track_ocr_cache:
                    if vehicle_idx not in plate_texts:
                        plate_texts[vehicle_idx] = []
                    plate_texts[vehicle_idx].append(self.track_ocr_cache[track_id])

        # Merge tracks with identical plate reads (same vehicle, fragmented tracking)
        self._merge_tracks_by_plate()

        # Update stats - count unique tracks only
        self.frame_count += 1
        for track_id in vehicle_tracks.values():
            if track_id is not None:
                self.unique_vehicles.add(track_id)

        # Log OCR throttling stats
        if ocr_runs_this_frame > 0:
            logger.debug(f"OCR runs this frame: {ocr_runs_this_frame} (active tracks: {len(vehicle_tracks)})")

        # Cache values for overlay on skipped frames
        processing_time = (time.time() - start_time) * 1000
        self.last_processing_time = processing_time
        self.last_num_detections = len(vehicles)

        # Metrics: Record processing metrics
        processing_time_seconds = processing_time / 1000.0
        self.metrics_processing_time.labels(camera_id=camera_id).observe(processing_time_seconds)
        self.metrics_frames_processed.labels(camera_id=camera_id).inc()

        # Count plates detected in this frame
        num_plates_this_frame = sum(len(plate_list) for plate_list in plates.values()) if plates else 0
        self.metrics_plates_detected.labels(camera_id=camera_id).inc(num_plates_this_frame)

        # Update active tracks gauge
        self.metrics_active_tracks.labels(camera_id=camera_id).set(len(vehicle_tracks))

        # Update FPS gauge (calculate smoothed FPS)
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            current_fps = self.frame_count / elapsed
            self.fps_smoothed = (self.fps_alpha * current_fps) + ((1 - self.fps_alpha) * self.fps_smoothed)
            self.metrics_fps.labels(camera_id=camera_id).set(self.fps_smoothed)

        # Visualize
        annotated_frame = self._visualize(
            frame,
            vehicles,
            plates,
            plate_texts,
            vehicle_tracks,
            camera_id,
            processing_time=processing_time
        )

        return annotated_frame

    def _visualize(self, frame, vehicles, plates, plate_texts, vehicle_tracks, camera_id, processing_time):
        """Draw detections on frame"""
        vis_frame = frame.copy()

        # Draw vehicles
        for idx, vehicle in enumerate(vehicles):
            bbox = vehicle.bbox
            x1, y1, x2, y2 = map(int, [bbox.x1, bbox.y1, bbox.x2, bbox.y2])

            # Get track ID
            track_id = vehicle_tracks.get(idx, -1)

            # Vehicle bbox (green)
            cv2.rectangle(vis_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Vehicle label with track ID
            label = f"ID:{track_id} {vehicle.vehicle_type} {vehicle.confidence:.2f}"
            cv2.putText(
                vis_frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

            # Draw plates for this vehicle
            if idx in plates:
                for plate_idx, plate_bbox in enumerate(plates[idx]):
                    px1, py1, px2, py2 = map(int, [
                        plate_bbox.x1, plate_bbox.y1,
                        plate_bbox.x2, plate_bbox.y2
                    ])

                    # Plate bbox (yellow)
                    cv2.rectangle(vis_frame, (px1, py1), (px2, py2), (0, 255, 255), 2)

                    # Plate label with OCR text if available
                    if idx in plate_texts and plate_idx < len(plate_texts[idx]):
                        plate_detection = plate_texts[idx][plate_idx]
                        track_id = vehicle_tracks.get(idx, -1)

                        # Check if this is cached (track already had OCR run)
                        frame_count = self.track_frame_count.get(track_id, 0)
                        is_cached = frame_count > self.ocr_min_track_frames

                        # Add indicator for cached vs fresh OCR
                        cache_indicator = "[C]" if is_cached else "[F]"
                        plate_label = f"{cache_indicator} {plate_detection.text} ({plate_detection.confidence:.2f})"
                        label_color = (0, 255, 255)  # Yellow for successful OCR
                    else:
                        plate_label = "PLATE"
                        label_color = (0, 165, 255)  # Orange for no OCR

                    cv2.putText(
                        vis_frame,
                        plate_label,
                        (px1, py1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        label_color,
                        2
                    )

        # Draw info overlay
        self._draw_overlay(vis_frame, camera_id, len(vehicles), processing_time)

        return vis_frame

    def _draw_overlay(self, frame, camera_id, num_detections, processing_time):
        """Draw info overlay on frame"""
        h, w = frame.shape[:2]

        # Semi-transparent background for text
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 120), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # Update FPS calculation (smoothed)
        current_fps = 1000 / processing_time if processing_time > 0 else 0
        self.fps_smoothed = (self.fps_alpha * current_fps +
                             (1 - self.fps_alpha) * self.fps_smoothed)

        # Draw text
        y_offset = 25
        line_height = 25

        ocr_status = "ON" if self.enable_ocr else "OFF"
        tracking_status = "ON" if self.enable_tracking else "OFF"
        active_tracks = len(self.track_frame_count) if self.enable_tracking else 0
        cached_ocr = len(self.track_ocr_cache)

        # Frame sampling info
        if self.adaptive_sampling:
            sampling_info = f"Adaptive: skip={self.adaptive_skip_current}"
        else:
            sampling_info = f"Fixed: skip={self.frame_skip}"

        texts = [
            f"Camera: {camera_id} | OCR: {ocr_status} | Tracking: {tracking_status} | {sampling_info}",
            f"FPS: {self.fps_smoothed:.1f} | Processing: {processing_time:.1f}ms",
            f"Detections: {num_detections} vehicles | Active Tracks: {active_tracks} | Cached OCR: {cached_ocr}",
            f"Unique Vehicles: {len(self.unique_vehicles)} | Plates Recognized: {self.plate_count} | Uptime: {time.time() - self.start_time:.0f}s"
        ]

        for idx, text in enumerate(texts):
            cv2.putText(
                frame,
                text,
                (10, y_offset + idx * line_height),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

    def run(self):
        """Main processing loop"""
        logger.info("Starting ALPR pilot...")
        logger.info("Press 'q' to quit, 's' to save screenshot")

        # Start cameras
        self.camera_manager.start_all()

        try:
            while True:
                # Process each camera
                for camera_id, camera in self.camera_manager.get_all_cameras().items():
                    ret, frame = camera.read()

                    if not ret or frame is None:
                        continue

                    # Process frame
                    annotated_frame = self.process_frame(frame, camera_id)

                    # Save output
                    if self.save_output and self.frame_count % 30 == 0:
                        output_path = self.output_dir / f"{camera_id}_{self.frame_count:06d}.jpg"
                        cv2.imwrite(str(output_path), annotated_frame)
                        logger.debug(f"Saved frame: {output_path}")

                    # Display
                    if self.display:
                        # Resize for display if too large
                        display_h, display_w = annotated_frame.shape[:2]
                        if display_w > 1280:
                            scale = 1280 / display_w
                            display_frame = cv2.resize(
                                annotated_frame,
                                (1280, int(display_h * scale))
                            )
                        else:
                            display_frame = annotated_frame

                        cv2.imshow(f"ALPR Pilot - {camera_id}", display_frame)

                # Handle keyboard input
                if self.display:
                    # Use very short wait time to keep display responsive
                    # This allows the display to update frequently even if processing is slow
                    key = cv2.waitKey(10) & 0xFF

                    if key == ord('q'):
                        logger.info("Quit requested")
                        break
                    elif key == ord('s'):
                        # Save screenshot
                        screenshot_path = self.output_dir / f"screenshot_{int(time.time())}.jpg"
                        cv2.imwrite(str(screenshot_path), annotated_frame)
                        logger.info(f"Screenshot saved: {screenshot_path}")

                # Log stats periodically
                if self.frame_count % 100 == 0:
                    logger.info(
                        f"Processed {self.frame_count} frames | "
                        f"{len(self.unique_vehicles)} unique vehicles | "
                        f"Avg FPS: {self.fps_smoothed:.1f}"
                    )

        except KeyboardInterrupt:
            logger.info("Interrupted by user")

        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up...")

        # Wait for pending image uploads
        if hasattr(self, 'image_storage') and self.image_storage:
            logger.info("Waiting for pending image uploads...")
            self.image_storage.shutdown(wait=True, timeout=30)

        # Flush and close Kafka publisher
        if hasattr(self, 'kafka_publisher'):
            logger.info("Flushing Kafka publisher...")
            self.kafka_publisher.flush()
            self.kafka_publisher.close()

        self.camera_manager.stop_all()
        if self.display:
            cv2.destroyAllWindows()

        # Print final stats
        elapsed = time.time() - self.start_time
        avg_fps = self.frame_count / elapsed if elapsed > 0 else 0

        logger.success(
            f"Pilot complete:\n"
            f"  Frames processed: {self.frame_count}\n"
            f"  Unique vehicles: {len(self.unique_vehicles)}\n"
            f"  Plates recognized: {self.plate_count}\n"
            f"  Runtime: {elapsed:.1f}s\n"
            f"  Average FPS: {avg_fps:.2f}"
        )


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="ALPR Pilot - Test Detection Pipeline")
    parser.add_argument(
        "--config",
        default="config/cameras.yaml",
        help="Path to camera config (default: config/cameras.yaml)"
    )
    parser.add_argument(
        "--model",
        default="models/yolo11n.pt",
        help="YOLOv11 vehicle model path (default: models/yolo11n.pt)"
    )
    parser.add_argument(
        "--plate-model",
        default="models/yolo11n-plate.pt",
        help="YOLOv11 plate detection model path (default: models/yolo11n-plate.pt)"
    )
    parser.add_argument(
        "--no-tensorrt",
        action="store_true",
        help="Disable TensorRT optimization"
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable visualization window (headless mode)"
    )
    parser.add_argument(
        "--save-output",
        action="store_true",
        help="Save annotated frames to output/ directory"
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR for license plate recognition"
    )
    parser.add_argument(
        "--no-tracking",
        action="store_true",
        help="Disable ByteTrack multi-object tracking"
    )
    parser.add_argument(
        "--skip-frames",
        type=int,
        default=0,
        help="Process every Nth frame (0=all, 1=every other, 2=every 3rd, etc.) - default: 0 for gate control (process all frames)"
    )
    parser.add_argument(
        "--no-adaptive-sampling",
        action="store_true",
        default=True,
        help="Disable adaptive frame sampling (use fixed skip rate) - default: disabled for gate control"
    )

    args = parser.parse_args()

    # Create pilot
    pilot = ALPRPilot(
        camera_config=args.config,
        detector_model=args.model,
        plate_model=args.plate_model,
        use_tensorrt=not args.no_tensorrt,
        display=not args.no_display,
        save_output=args.save_output,
        enable_ocr=not args.no_ocr,
        enable_tracking=not args.no_tracking,
        frame_skip=args.skip_frames,
        adaptive_sampling=not args.no_adaptive_sampling,
    )

    # Run
    pilot.run()


if __name__ == "__main__":
    main()
