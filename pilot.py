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
import numpy as np
from pathlib import Path
from loguru import logger
import csv
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from services.camera.camera_ingestion import CameraManager
from services.detector.detector_service import YOLOv11Detector
from services.ocr.ocr_service import PaddleOCRService
from services.tracker.bytetrack_service import ByteTrackService, Detection
from shared.utils.tracking_utils import bbox_to_numpy, get_track_color, draw_track_id


class ALPRPilot:
    """Simple pilot for testing ALPR pipeline"""

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

        # Initialize plate reads CSV file
        self.plate_csv_path = self.output_dir / "plate_reads.csv"
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

        # Warmup detector
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
        self.track_attributes_cache = {}  # track_id -> {color, make, model}
        self.track_frame_count = {}  # track_id -> frame count

        # OCR throttling parameters
        self.ocr_min_track_frames = 3  # Wait for track to stabilize

        # Attribute inference parameters
        self.attr_min_confidence = 0.8  # Run attributes on high-confidence frames
        self.attr_min_track_frames = 5  # Wait for even more stability for attributes

        # Adaptive frame sampling parameters
        self.frames_since_last_detection = 0
        self.max_skip_no_vehicles = 9  # Skip more frames when no vehicles (process every 10th)
        self.min_skip_with_vehicles = max(0, frame_skip - 1)  # Reduce skip when vehicles present (but still skip some)
        self.adaptive_skip_current = self.frame_skip  # Current adaptive skip value

        # Cached overlay data (for skipped frames)
        self.last_processing_time = 0.0
        self.last_num_detections = 0

        logger.success("ALPR Pilot initialized successfully")

    def _init_plate_csv(self):
        """Initialize CSV file for plate reads"""
        # Create CSV with headers if it doesn't exist
        if not self.plate_csv_path.exists():
            with open(self.plate_csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Timestamp', 'Camera_ID', 'Track_ID', 'Plate_Text', 'Confidence', 'Frame_Number'])
            logger.info(f"Created plate reads CSV: {self.plate_csv_path}")
        else:
            logger.info(f"Appending to existing CSV: {self.plate_csv_path}")

    def _save_plate_read(self, camera_id: str, track_id: int, plate_text: str, confidence: float):
        """Save a plate read to CSV file"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            with open(self.plate_csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, camera_id, track_id, plate_text, f"{confidence:.3f}", self.frame_count])
        except Exception as e:
            logger.error(f"Failed to save plate read: {e}")

    def _save_plate_crop(self, frame, plate_bbox, track_id: int, camera_id: str):
        """Save cropped plate image to output/crops directory"""
        try:
            # Extract plate region from frame
            x1, y1, x2, y2 = map(int, [plate_bbox.x1, plate_bbox.y1, plate_bbox.x2, plate_bbox.y2])

            # Ensure coordinates are within frame bounds
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            # Skip if invalid bbox
            if x2 <= x1 or y2 <= y1:
                return

            plate_crop = frame[y1:y2, x1:x2]

            # Generate filename with timestamp and track ID
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
            filename = f"{camera_id}_track{track_id}_{timestamp}_{self.crop_counter:04d}.jpg"
            filepath = self.crops_dir / filename

            # Save crop
            cv2.imwrite(str(filepath), plate_crop)
            self.crop_counter += 1
            logger.debug(f"Saved plate crop: {filename}")

        except Exception as e:
            logger.error(f"Failed to save plate crop: {e}")

    def _compute_iou_np(self, bbox1: np.ndarray, bbox2: np.ndarray) -> float:
        """Compute IoU between two numpy bboxes [x1, y1, x2, y2]"""
        x1_i = max(bbox1[0], bbox2[0])
        y1_i = max(bbox1[1], bbox2[1])
        x2_i = min(bbox1[2], bbox2[2])
        y2_i = min(bbox1[3], bbox2[3])

        if x2_i < x1_i or y2_i < y1_i:
            return 0.0

        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0.0

    def should_run_ocr(self, track_id):
        """
        Determine if OCR should be run for this track

        Args:
            track_id: Track identifier

        Returns:
            bool: True if OCR should run
        """
        # Already have OCR result for this track?
        if track_id in self.track_ocr_cache:
            return False

        # Track stable enough (minimum frames)?
        if self.track_frame_count.get(track_id, 0) < self.ocr_min_track_frames:
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
            vis_frame = frame.copy()
            # Use cached values from last processed frame
            self._draw_overlay(vis_frame, camera_id, self.last_num_detections, self.last_processing_time)
            return vis_frame

        start_time = time.time()

        # Detect vehicles
        vehicles = self.detector.detect_vehicles(
            frame,
            confidence_threshold=0.3,  # Lowered to detect more vehicles
            nms_threshold=0.5
        )

        # Adaptive frame sampling: adjust skip rate based on vehicle presence
        if self.adaptive_sampling:
            if len(vehicles) > 0:
                # Vehicles detected - process more frequently
                self.frames_since_last_detection = 0
                self.adaptive_skip_current = self.min_skip_with_vehicles
            else:
                # No vehicles - increase skip rate gradually
                self.frames_since_last_detection += 1
                if self.frames_since_last_detection > 30:  # After 30 frames (~1 sec) without vehicles
                    self.adaptive_skip_current = self.max_skip_no_vehicles
                else:
                    # Gradual transition to max skip
                    self.adaptive_skip_current = self.frame_skip

        # Update tracker with detections
        vehicle_tracks = {}  # vehicle_idx -> track_id

        if self.enable_tracking and self.tracker:
            # Convert detections to tracker format
            detections = []
            for vehicle in vehicles:
                det = Detection(
                    bbox=bbox_to_numpy(vehicle.bbox),
                    confidence=vehicle.confidence,
                    class_id=0  # All vehicles for now
                )
                detections.append(det)

            # Update tracker
            active_tracks = self.tracker.update(detections)

            # Map vehicle detections to track IDs
            for idx, vehicle in enumerate(vehicles):
                # Find matching track by IoU
                best_iou = 0
                best_track = None
                vehicle_bbox_np = bbox_to_numpy(vehicle.bbox)

                for track in active_tracks:
                    # Simple IoU matching between detection and track
                    track_bbox = track.tlbr
                    iou = self._compute_iou_np(vehicle_bbox_np, track_bbox)
                    if iou > best_iou:
                        best_iou = iou
                        best_track = track

                if best_track:
                    track_id = best_track.track_id
                    vehicle_tracks[idx] = track_id

                    # Update track frame count
                    if track_id not in self.track_frame_count:
                        self.track_frame_count[track_id] = 0
                    self.track_frame_count[track_id] += 1

                    # Cache vehicle attributes on first high-confidence frame
                    if self.should_cache_attributes(track_id, vehicle.confidence):
                        self.cache_vehicle_attributes(track_id, vehicle)
        else:
            # No tracking - assign sequential IDs
            for idx, vehicle in enumerate(vehicles):
                vehicle_tracks[idx] = idx


        # Detect plates (within vehicle bboxes)
        vehicle_bboxes = [v.bbox for v in vehicles] if vehicles else None
        plates = self.detector.detect_plates(
            frame,
            vehicle_bboxes=vehicle_bboxes,
            confidence_threshold=0.25,  # Lowered from 0.6 to detect more plates
            nms_threshold=0.4
        )

        # Run OCR on detected plates (THROTTLED - once per stable track)
        # Use BATCH inference when multiple tracks need OCR
        plate_texts = {}  # Map vehicle index to plate text
        ocr_runs_this_frame = 0

        # Batch OCR configuration
        enable_batch_ocr = True  # Set to False to disable batching
        batch_min_size = 2  # Only batch if 2+ plates need OCR

        if self.ocr and plates:
            # Collect all tracks that need OCR
            tracks_needing_ocr = []  # List of (vehicle_idx, track_id, plate_bbox)

            for vehicle_idx, plate_bboxes in plates.items():
                track_id = vehicle_tracks.get(vehicle_idx)

                if track_id is None:
                    continue

                # Check if we should run OCR for this track
                if self.should_run_ocr(track_id):
                    # Use first plate only (assumes one plate per vehicle)
                    plate_bbox = plate_bboxes[0]
                    tracks_needing_ocr.append((vehicle_idx, track_id, plate_bbox))

            # Run OCR: batch if multiple plates, single if just one
            if tracks_needing_ocr:
                ocr_runs_this_frame = len(tracks_needing_ocr)

                if enable_batch_ocr and len(tracks_needing_ocr) >= batch_min_size:
                    # BATCH OCR
                    logger.debug(f"Running batch OCR on {len(tracks_needing_ocr)} plates")

                    bboxes = [item[2] for item in tracks_needing_ocr]
                    batch_results = self.ocr.recognize_plates_batch(
                        frame,
                        bboxes,
                        preprocess=True
                    )

                    # Cache results
                    for idx, (vehicle_idx, track_id, _) in enumerate(tracks_needing_ocr):
                        plate_detection = batch_results[idx]

                        if plate_detection:
                            self.track_ocr_cache[track_id] = plate_detection
                            self.plate_count += 1
                            logger.info(f"OCR Track {track_id}: {plate_detection.text} (conf: {plate_detection.confidence:.2f})")
                            # Save to CSV
                            self._save_plate_read(camera_id, track_id, plate_detection.text, plate_detection.confidence)
                else:
                    # SINGLE OCR (one at a time)
                    for vehicle_idx, track_id, plate_bbox in tracks_needing_ocr:
                        plate_detection = self.ocr.recognize_plate(
                            frame,
                            plate_bbox,
                            preprocess=True
                        )

                        if plate_detection:
                            self.track_ocr_cache[track_id] = plate_detection
                            self.plate_count += 1
                            logger.info(f"OCR Track {track_id}: {plate_detection.text} (conf: {plate_detection.confidence:.2f})")
                            # Save to CSV
                            self._save_plate_read(camera_id, track_id, plate_detection.text, plate_detection.confidence)

            # Use cached OCR results for all tracks
            for vehicle_idx, plate_bboxes in plates.items():
                track_id = vehicle_tracks.get(vehicle_idx)

                if track_id and track_id in self.track_ocr_cache:
                    if vehicle_idx not in plate_texts:
                        plate_texts[vehicle_idx] = []
                    plate_texts[vehicle_idx].append(self.track_ocr_cache[track_id])

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

                    # Save plate crop
                    track_id = vehicle_tracks.get(idx, -1)
                    self._save_plate_crop(frame, plate_bbox, track_id, camera_id)

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
            f"Unique Vehicles: {len(self.unique_vehicles)} | Plates Read: {self.plate_count} | Uptime: {time.time() - self.start_time:.0f}s"
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
                    key = cv2.waitKey(1) & 0xFF

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
            f"  Plates read: {self.plate_count}\n"
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
        default="yolo11n.pt",
        help="YOLOv11 vehicle model path (default: yolo11n.pt)"
    )
    parser.add_argument(
        "--plate-model",
        default="models/yolo11n-plate-custom.engine",
        help="YOLOv11 plate detection model path (default: models/yolo11n-plate-custom.engine - TensorRT FP16)"
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
        default=2,
        help="Process every Nth frame (0=all, 1=every other, 2=every 3rd, etc.) - default: 2 for parking gates"
    )
    parser.add_argument(
        "--no-adaptive-sampling",
        action="store_true",
        help="Disable adaptive frame sampling (use fixed skip rate)"
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
