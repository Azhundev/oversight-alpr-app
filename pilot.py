#!/usr/bin/env python3
"""
ALPR Pilot Script
Tests complete pipeline: Camera → Detection → Visualization
Optimized for NVIDIA Jetson Orin NX
"""

import cv2
import sys
import time
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from services.camera.camera_ingestion import CameraManager
from services.detector.detector_service import YOLOv11Detector
from services.ocr.ocr_service import PaddleOCRService


class ALPRPilot:
    """Simple pilot for testing ALPR pipeline"""

    def __init__(
        self,
        camera_config: str = "config/cameras.yaml",
        detector_model: str = "yolo11n.pt",
        use_tensorrt: bool = True,
        display: bool = True,
        save_output: bool = False,
        enable_ocr: bool = True,
    ):
        """
        Initialize ALPR pilot

        Args:
            camera_config: Path to camera configuration
            detector_model: YOLOv11 model path
            use_tensorrt: Enable TensorRT optimization
            display: Show visualization window
            save_output: Save annotated frames to disk
            enable_ocr: Enable OCR for license plate recognition
        """
        self.display = display
        self.save_output = save_output
        self.enable_ocr = enable_ocr
        self.output_dir = Path("output")

        if self.save_output:
            self.output_dir.mkdir(exist_ok=True)

        # Initialize camera manager
        logger.info("Initializing camera manager...")
        self.camera_manager = CameraManager(camera_config)

        # Initialize detector
        logger.info("Initializing YOLOv11 detector...")
        self.detector = YOLOv11Detector(
            vehicle_model_path=detector_model,
            use_tensorrt=False,  # Disabled to avoid 8-min TensorRT build
            fp16=True,
            int8=False,
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

        # Stats
        self.frame_count = 0
        self.detection_count = 0
        self.plate_count = 0
        self.start_time = time.time()
        self.fps_smoothed = 0.0
        self.fps_alpha = 0.1  # Smoothing factor

        # Track-based OCR throttling and attribute caching
        self.track_ocr_cache = {}  # track_id -> PlateDetection
        self.track_attributes_cache = {}  # track_id -> {color, make, model}
        self.track_frame_count = {}  # track_id -> frame count
        self.track_last_bbox = {}  # track_id -> last bbox (for stability check)
        self.track_best_confidence = {}  # track_id -> highest detection confidence
        self.next_track_id = 0  # Simple track ID counter

        # OCR throttling parameters
        self.ocr_min_track_frames = 3  # Wait for track to stabilize
        self.ocr_bbox_iou_threshold = 0.7  # IoU threshold for same track
        self.ocr_cooldown_frames = 30  # Don't re-OCR same track for N frames

        # Attribute inference parameters
        self.attr_min_confidence = 0.8  # Run attributes on high-confidence frames
        self.attr_min_track_frames = 5  # Wait for even more stability for attributes

        logger.success("ALPR Pilot initialized successfully")

    def calculate_iou(self, bbox1, bbox2):
        """Calculate Intersection over Union between two bounding boxes"""
        # Extract coordinates
        x1_1, y1_1, x2_1, y2_1 = bbox1.x1, bbox1.y1, bbox1.x2, bbox1.y2
        x1_2, y1_2, x2_2, y2_2 = bbox2.x1, bbox2.y1, bbox2.x2, bbox2.y2

        # Calculate intersection area
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)

        if x2_i < x1_i or y2_i < y1_i:
            return 0.0

        intersection = (x2_i - x1_i) * (y2_i - y1_i)

        # Calculate union area
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection

        if union == 0:
            return 0.0

        return intersection / union

    def match_vehicle_to_track(self, vehicle_bbox):
        """
        Match a vehicle detection to an existing track or create new track

        Args:
            vehicle_bbox: BoundingBox of detected vehicle

        Returns:
            track_id: Matched or newly created track ID
        """
        best_iou = 0
        best_track_id = None

        # Try to match with existing tracks
        for track_id, last_bbox in self.track_last_bbox.items():
            iou = self.calculate_iou(vehicle_bbox, last_bbox)
            if iou > best_iou and iou >= self.ocr_bbox_iou_threshold:
                best_iou = iou
                best_track_id = track_id

        # Create new track if no match found
        if best_track_id is None:
            best_track_id = self.next_track_id
            self.next_track_id += 1
            self.track_frame_count[best_track_id] = 0
            logger.debug(f"Created new track: {best_track_id}")

        # Update track
        self.track_last_bbox[best_track_id] = vehicle_bbox
        self.track_frame_count[best_track_id] += 1

        return best_track_id

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

    def cleanup_old_tracks(self, active_track_ids):
        """
        Remove tracks that are no longer active

        Args:
            active_track_ids: Set of currently active track IDs
        """
        # Remove stale tracks
        stale_tracks = set(self.track_last_bbox.keys()) - active_track_ids

        for track_id in stale_tracks:
            self.track_last_bbox.pop(track_id, None)
            self.track_frame_count.pop(track_id, None)
            self.track_best_confidence.pop(track_id, None)
            # Keep OCR and attribute caches for historical data
            # (optional: could also remove to save memory)

        if stale_tracks:
            logger.debug(f"Cleaned up {len(stale_tracks)} stale tracks")

    def process_frame(self, frame, camera_id: str):
        """
        Process single frame through detection pipeline

        Args:
            frame: Input frame (BGR)
            camera_id: Camera identifier

        Returns:
            Annotated frame
        """
        start_time = time.time()

        # Detect vehicles
        vehicles = self.detector.detect_vehicles(
            frame,
            confidence_threshold=0.4,
            nms_threshold=0.5
        )

        # Match vehicles to tracks (simple IoU-based tracking)
        vehicle_tracks = {}  # vehicle_idx -> track_id
        active_track_ids = set()

        for idx, vehicle in enumerate(vehicles):
            track_id = self.match_vehicle_to_track(vehicle.bbox)
            vehicle_tracks[idx] = track_id
            active_track_ids.add(track_id)

            # Track best confidence for this vehicle
            current_best = self.track_best_confidence.get(track_id, 0.0)
            if vehicle.confidence > current_best:
                self.track_best_confidence[track_id] = vehicle.confidence

            # Cache vehicle attributes on first high-confidence frame
            if self.should_cache_attributes(track_id, vehicle.confidence):
                self.cache_vehicle_attributes(track_id, vehicle)

        # Cleanup old tracks
        self.cleanup_old_tracks(active_track_ids)

        # Detect plates (within vehicle bboxes)
        vehicle_bboxes = [v.bbox for v in vehicles] if vehicles else None
        plates = self.detector.detect_plates(
            frame,
            vehicle_bboxes=vehicle_bboxes,
            confidence_threshold=0.6,
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

            # Use cached OCR results for all tracks
            for vehicle_idx, plate_bboxes in plates.items():
                track_id = vehicle_tracks.get(vehicle_idx)

                if track_id and track_id in self.track_ocr_cache:
                    if vehicle_idx not in plate_texts:
                        plate_texts[vehicle_idx] = []
                    plate_texts[vehicle_idx].append(self.track_ocr_cache[track_id])

        # Update stats
        self.frame_count += 1
        self.detection_count += len(vehicles)

        # Log OCR throttling stats
        if ocr_runs_this_frame > 0:
            logger.debug(f"OCR runs this frame: {ocr_runs_this_frame} (active tracks: {len(active_track_ids)})")

        # Visualize
        annotated_frame = self._visualize(
            frame,
            vehicles,
            plates,
            plate_texts,
            vehicle_tracks,
            camera_id,
            processing_time=(time.time() - start_time) * 1000
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
        active_tracks = len(self.track_last_bbox)
        cached_ocr = len(self.track_ocr_cache)

        texts = [
            f"Camera: {camera_id} | OCR: {ocr_status} | Tracks: {active_tracks} (Cached: {cached_ocr})",
            f"FPS: {self.fps_smoothed:.1f} | Processing: {processing_time:.1f}ms",
            f"Detections: {num_detections} vehicles | Total Frames: {self.frame_count}",
            f"Total Vehicles: {self.detection_count} | Plates Read: {self.plate_count} | Uptime: {time.time() - self.start_time:.0f}s"
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
                        f"{self.detection_count} vehicles detected | "
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
            f"  Vehicles detected: {self.detection_count}\n"
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
        help="YOLOv11 model path (default: yolo11n.pt)"
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

    args = parser.parse_args()

    # Create pilot
    pilot = ALPRPilot(
        camera_config=args.config,
        detector_model=args.model,
        use_tensorrt=not args.no_tensorrt,
        display=not args.no_display,
        save_output=args.save_output,
        enable_ocr=not args.no_ocr,
    )

    # Run
    pilot.run()


if __name__ == "__main__":
    main()
