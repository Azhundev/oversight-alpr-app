#!/usr/bin/env python3
"""
Collect License Plate Samples for Training
Extracts detected plates from video for creating training dataset
"""

import cv2
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.detector.detector_service import YOLOv11Detector


class PlateDataCollector:
    """Collect plate samples from video for training dataset"""

    def __init__(
        self,
        video_path: str,
        output_dir: str = "training_data/plates",
        min_confidence: float = 0.6,
        min_width: int = 50,
        min_height: int = 20,
    ):
        """
        Initialize plate collector

        Args:
            video_path: Path to video file
            output_dir: Output directory for samples
            min_confidence: Minimum detection confidence
            min_width: Minimum plate width in pixels
            min_height: Minimum plate height in pixels
        """
        self.video_path = video_path
        self.output_dir = Path(output_dir)
        self.min_confidence = min_confidence
        self.min_width = min_width
        self.min_height = min_height

        # Create output directories
        self.images_dir = self.output_dir / "images"
        self.labels_dir = self.output_dir / "labels"
        self.crops_dir = self.output_dir / "crops"

        for dir_path in [self.images_dir, self.labels_dir, self.crops_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Initialize detector
        logger.info("Loading YOLOv11 detector...")
        self.detector = YOLOv11Detector(
            vehicle_model_path="yolo11n.pt",
            use_tensorrt=False,
            fp16=True
        )

        # Stats
        self.frame_count = 0
        self.sample_count = 0
        self.metadata = []

    def collect(
        self,
        max_samples: int = 1000,
        frame_skip: int = 5,
        show_preview: bool = True
    ):
        """
        Collect plate samples from video

        Args:
            max_samples: Maximum number of samples to collect
            frame_skip: Process every Nth frame
            show_preview: Show preview window
        """
        logger.info(f"Opening video: {self.video_path}")
        cap = cv2.VideoCapture(self.video_path)

        if not cap.isOpened():
            logger.error(f"Failed to open video: {self.video_path}")
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        logger.info(f"Video: {total_frames} frames @ {fps:.1f} FPS")
        logger.info(f"Collecting up to {max_samples} samples...")
        logger.info("Press 's' to save current detections, 'q' to quit")

        while self.sample_count < max_samples:
            ret, frame = cap.read()

            if not ret:
                logger.info("End of video reached")
                break

            self.frame_count += 1

            # Skip frames for speed
            if self.frame_count % (frame_skip + 1) != 0:
                continue

            # Detect vehicles
            vehicles = self.detector.detect_vehicles(
                frame,
                confidence_threshold=0.4
            )

            if not vehicles:
                continue

            # Detect plates
            vehicle_bboxes = [v.bbox for v in vehicles]
            plates = self.detector.detect_plates(
                frame,
                vehicle_bboxes,
                confidence_threshold=self.min_confidence
            )

            if not plates:
                continue

            # Visualize detections
            vis_frame = frame.copy()
            plate_count_this_frame = 0

            for vehicle_idx, plate_bboxes in plates.items():
                if vehicle_idx >= len(vehicles):
                    continue

                for plate_bbox in plate_bboxes:
                    # Check size
                    width = plate_bbox.x2 - plate_bbox.x1
                    height = plate_bbox.y2 - plate_bbox.y1

                    if width < self.min_width or height < self.min_height:
                        continue

                    plate_count_this_frame += 1

                    # Draw on preview
                    x1, y1, x2, y2 = map(int, [
                        plate_bbox.x1, plate_bbox.y1,
                        plate_bbox.x2, plate_bbox.y2
                    ])
                    cv2.rectangle(vis_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(
                        vis_frame,
                        f"Plate {plate_count_this_frame}",
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2
                    )

            if plate_count_this_frame > 0:
                # Show preview
                if show_preview:
                    info_text = (
                        f"Frame: {self.frame_count} | "
                        f"Plates: {plate_count_this_frame} | "
                        f"Samples: {self.sample_count}/{max_samples} | "
                        f"Press 's' to save, 'q' to quit"
                    )
                    cv2.putText(
                        vis_frame,
                        info_text,
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2
                    )

                    cv2.imshow("Plate Collector", vis_frame)
                    key = cv2.waitKey(1) & 0xFF

                    if key == ord('q'):
                        logger.info("Quit by user")
                        break
                    elif key == ord('s'):
                        # Save this frame
                        self._save_sample(frame, vehicles, plates)

                # Auto-save if high quality detections
                elif plate_count_this_frame >= 1:
                    self._save_sample(frame, vehicles, plates)

            # Progress update
            if self.frame_count % 100 == 0:
                logger.info(
                    f"Progress: Frame {self.frame_count}/{total_frames} | "
                    f"Samples: {self.sample_count}/{max_samples}"
                )

        cap.release()
        cv2.destroyAllWindows()

        # Save metadata
        self._save_metadata()

        logger.success(f"Collection complete!")
        logger.info(f"Total samples: {self.sample_count}")
        logger.info(f"Output directory: {self.output_dir}")

    def _save_sample(self, frame, vehicles, plates):
        """Save a sample with YOLO format annotations"""
        sample_id = f"plate_{self.sample_count:05d}"

        # Save full frame
        image_path = self.images_dir / f"{sample_id}.jpg"
        cv2.imwrite(str(image_path), frame)

        # Save YOLO format labels
        label_path = self.labels_dir / f"{sample_id}.txt"

        h, w = frame.shape[:2]

        with open(label_path, 'w') as f:
            for vehicle_idx, plate_bboxes in plates.items():
                if vehicle_idx >= len(vehicles):
                    continue

                for plate_bbox in plate_bboxes:
                    # Check size
                    width = plate_bbox.x2 - plate_bbox.x1
                    height = plate_bbox.y2 - plate_bbox.y1

                    if width < self.min_width or height < self.min_height:
                        continue

                    # Convert to YOLO format (normalized center x, y, width, height)
                    x_center = ((plate_bbox.x1 + plate_bbox.x2) / 2) / w
                    y_center = ((plate_bbox.y1 + plate_bbox.y2) / 2) / h
                    box_width = (plate_bbox.x2 - plate_bbox.x1) / w
                    box_height = (plate_bbox.y2 - plate_bbox.y1) / h

                    # Class 0 = license_plate
                    f.write(f"0 {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}\n")

                    # Save plate crop
                    x1, y1, x2, y2 = map(int, [
                        plate_bbox.x1, plate_bbox.y1,
                        plate_bbox.x2, plate_bbox.y2
                    ])
                    plate_crop = frame[y1:y2, x1:x2]
                    crop_path = self.crops_dir / f"{sample_id}_crop.jpg"
                    cv2.imwrite(str(crop_path), plate_crop)

                    # Metadata
                    self.metadata.append({
                        "sample_id": sample_id,
                        "frame_number": self.frame_count,
                        "image_path": str(image_path.relative_to(self.output_dir)),
                        "label_path": str(label_path.relative_to(self.output_dir)),
                        "crop_path": str(crop_path.relative_to(self.output_dir)),
                        "bbox": {
                            "x1": float(plate_bbox.x1),
                            "y1": float(plate_bbox.y1),
                            "x2": float(plate_bbox.x2),
                            "y2": float(plate_bbox.y2),
                        },
                        "width": int(width),
                        "height": int(height),
                    })

        self.sample_count += 1
        logger.info(f"Saved sample {sample_id} (frame {self.frame_count})")

    def _save_metadata(self):
        """Save collection metadata"""
        metadata_path = self.output_dir / "metadata.json"

        summary = {
            "collection_date": datetime.utcnow().isoformat() + "Z",
            "video_path": self.video_path,
            "total_frames_processed": self.frame_count,
            "total_samples": self.sample_count,
            "samples": self.metadata,
        }

        with open(metadata_path, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Metadata saved: {metadata_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Collect license plate samples for training"
    )
    parser.add_argument(
        "video",
        help="Path to video file"
    )
    parser.add_argument(
        "--output",
        default="training_data/plates",
        help="Output directory (default: training_data/plates)"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=1000,
        help="Maximum samples to collect (default: 1000)"
    )
    parser.add_argument(
        "--skip-frames",
        type=int,
        default=5,
        help="Process every Nth frame (default: 5)"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.6,
        help="Minimum detection confidence (default: 0.6)"
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable preview window (auto-save mode)"
    )

    args = parser.parse_args()

    collector = PlateDataCollector(
        video_path=args.video,
        output_dir=args.output,
        min_confidence=args.min_confidence
    )

    collector.collect(
        max_samples=args.max_samples,
        frame_skip=args.skip_frames,
        show_preview=not args.no_preview
    )


if __name__ == "__main__":
    main()
