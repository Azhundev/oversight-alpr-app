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


class ALPRPilot:
    """Simple pilot for testing ALPR pipeline"""

    def __init__(
        self,
        camera_config: str = "config/cameras.yaml",
        detector_model: str = "yolo11n.pt",
        use_tensorrt: bool = True,
        display: bool = True,
        save_output: bool = False,
    ):
        """
        Initialize ALPR pilot

        Args:
            camera_config: Path to camera configuration
            detector_model: YOLOv11 model path
            use_tensorrt: Enable TensorRT optimization
            display: Show visualization window
            save_output: Save annotated frames to disk
        """
        self.display = display
        self.save_output = save_output
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
            use_tensorrt=use_tensorrt,
            fp16=True,
            batch_size=1,
        )

        # Warmup detector
        logger.info("Warming up detector...")
        self.detector.warmup(iterations=10)

        # Stats
        self.frame_count = 0
        self.detection_count = 0
        self.start_time = time.time()
        self.fps_smoothed = 0.0
        self.fps_alpha = 0.1  # Smoothing factor

        logger.success("ALPR Pilot initialized successfully")

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

        # Detect plates (within vehicle bboxes)
        vehicle_bboxes = [v.bbox for v in vehicles] if vehicles else None
        plates = self.detector.detect_plates(
            frame,
            vehicle_bboxes=vehicle_bboxes,
            confidence_threshold=0.6,
            nms_threshold=0.4
        )

        # Update stats
        self.frame_count += 1
        self.detection_count += len(vehicles)

        # Visualize
        annotated_frame = self._visualize(
            frame,
            vehicles,
            plates,
            camera_id,
            processing_time=(time.time() - start_time) * 1000
        )

        return annotated_frame

    def _visualize(self, frame, vehicles, plates, camera_id, processing_time):
        """Draw detections on frame"""
        vis_frame = frame.copy()

        # Draw vehicles
        for idx, vehicle in enumerate(vehicles):
            bbox = vehicle.bbox
            x1, y1, x2, y2 = map(int, [bbox.x1, bbox.y1, bbox.x2, bbox.y2])

            # Vehicle bbox (green)
            cv2.rectangle(vis_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Vehicle label
            label = f"{vehicle.vehicle_type} {vehicle.confidence:.2f}"
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
                for plate_bbox in plates[idx]:
                    px1, py1, px2, py2 = map(int, [
                        plate_bbox.x1, plate_bbox.y1,
                        plate_bbox.x2, plate_bbox.y2
                    ])

                    # Plate bbox (yellow)
                    cv2.rectangle(vis_frame, (px1, py1), (px2, py2), (0, 255, 255), 2)

                    # Plate label
                    cv2.putText(
                        vis_frame,
                        "PLATE",
                        (px1, py1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 255),
                        1
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

        texts = [
            f"Camera: {camera_id}",
            f"FPS: {self.fps_smoothed:.1f} | Processing: {processing_time:.1f}ms",
            f"Detections: {num_detections} vehicles | Total Frames: {self.frame_count}",
            f"Total Vehicles: {self.detection_count} | Uptime: {time.time() - self.start_time:.0f}s"
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

    args = parser.parse_args()

    # Create pilot
    pilot = ALPRPilot(
        camera_config=args.config,
        detector_model=args.model,
        use_tensorrt=not args.no_tensorrt,
        display=not args.no_display,
        save_output=args.save_output,
    )

    # Run
    pilot.run()


if __name__ == "__main__":
    main()
