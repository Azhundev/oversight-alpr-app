#!/usr/bin/env python3
"""
Prepare License Plate Training Data from Videos

This script:
1. Extracts frames from training videos
2. Uses PaddleOCR to auto-detect plate regions
3. Creates YOLO format annotations
4. Prepares dataset for YOLO11 training

Usage:
    python scripts/prepare_plate_training_data.py
"""

import cv2
import numpy as np
from pathlib import Path
from paddleocr import PaddleOCR
from loguru import logger
import yaml
import shutil
from tqdm import tqdm
import json

class PlateDatasetPreparator:
    """Prepare license plate detection dataset from videos"""

    def __init__(
        self,
        video_dir: str = "videos/training",
        output_dir: str = "datasets/plate_training",
        fps_extract: float = 1.0,
        min_confidence: float = 0.5,
        min_plate_area: int = 500
    ):
        """
        Initialize dataset preparator

        Args:
            video_dir: Directory containing training videos
            output_dir: Output directory for dataset
            fps_extract: Frames per second to extract (1.0 = every second)
            min_confidence: Minimum OCR confidence to consider as plate
            min_plate_area: Minimum area (pixels) for valid plate region
        """
        self.video_dir = Path(video_dir)
        self.output_dir = Path(output_dir)
        self.fps_extract = fps_extract
        self.min_confidence = min_confidence
        self.min_plate_area = min_plate_area

        # Create output directories
        self.images_dir = self.output_dir / "images"
        self.labels_dir = self.output_dir / "labels"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.labels_dir.mkdir(parents=True, exist_ok=True)

        # Initialize PaddleOCR for auto-detection
        logger.info("Initializing PaddleOCR for auto-labeling...")
        self.ocr = PaddleOCR(
            lang='en',
            use_angle_cls=True,
            show_log=False
        )

        self.stats = {
            'total_frames': 0,
            'frames_with_plates': 0,
            'total_plates': 0,
            'videos_processed': 0
        }

    def extract_frames(self, video_path: Path) -> list:
        """
        Extract frames from video at specified FPS

        Args:
            video_path: Path to video file

        Returns:
            List of (frame_number, frame_image) tuples
        """
        logger.info(f"Extracting frames from {video_path.name}...")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error(f"Failed to open video: {video_path}")
            return []

        # Get video properties
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / video_fps

        logger.info(
            f"Video: {video_path.name} | "
            f"FPS: {video_fps:.2f} | "
            f"Duration: {duration:.1f}s | "
            f"Frames: {total_frames}"
        )

        # Calculate frame interval
        frame_interval = int(video_fps / self.fps_extract)

        frames = []
        frame_idx = 0

        with tqdm(total=int(duration * self.fps_extract), desc="Extracting") as pbar:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Extract frame at interval
                if frame_idx % frame_interval == 0:
                    frames.append((frame_idx, frame.copy()))
                    pbar.update(1)

                frame_idx += 1

        cap.release()
        logger.success(f"Extracted {len(frames)} frames")

        return frames

    def detect_plates_paddleocr(self, frame: np.ndarray) -> list:
        """
        Use PaddleOCR to auto-detect plate regions in frame

        Args:
            frame: Image frame (BGR)

        Returns:
            List of bounding boxes [(x1, y1, x2, y2, confidence), ...]
        """
        # Run OCR detection
        result = self.ocr.ocr(frame, cls=True)

        if not result or not result[0]:
            return []

        plate_boxes = []

        for line in result[0]:
            # Extract bounding box and confidence
            bbox_points = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text, confidence = line[1]

            # Filter by confidence
            if confidence < self.min_confidence:
                continue

            # Filter by text characteristics (likely plate text)
            # Plates typically: 5-10 chars, alphanumeric, uppercase
            text_clean = ''.join(c for c in text.upper() if c.isalnum())
            if len(text_clean) < 4 or len(text_clean) > 12:
                continue

            # Convert points to bounding box
            bbox_points = np.array(bbox_points, dtype=np.int32)
            x1 = int(bbox_points[:, 0].min())
            y1 = int(bbox_points[:, 1].min())
            x2 = int(bbox_points[:, 0].max())
            y2 = int(bbox_points[:, 1].max())

            # Filter by area
            area = (x2 - x1) * (y2 - y1)
            if area < self.min_plate_area:
                continue

            # Expand bbox slightly (PaddleOCR detects text, we want full plate)
            h, w = frame.shape[:2]
            margin_x = int((x2 - x1) * 0.1)  # 10% margin
            margin_y = int((y2 - y1) * 0.2)  # 20% margin

            x1 = max(0, x1 - margin_x)
            y1 = max(0, y1 - margin_y)
            x2 = min(w, x2 + margin_x)
            y2 = min(h, y2 + margin_y)

            plate_boxes.append((x1, y1, x2, y2, confidence))

        return plate_boxes

    def save_yolo_annotation(
        self,
        image_path: Path,
        bboxes: list,
        image_width: int,
        image_height: int
    ):
        """
        Save YOLO format annotation file

        YOLO format: <class> <x_center> <y_center> <width> <height>
        All coordinates normalized to [0, 1]

        Args:
            image_path: Path to image file
            bboxes: List of bounding boxes [(x1, y1, x2, y2, conf), ...]
            image_width: Image width
            image_height: Image height
        """
        # Create label file (same name as image, .txt extension)
        label_path = self.labels_dir / (image_path.stem + ".txt")

        with open(label_path, 'w') as f:
            for x1, y1, x2, y2, conf in bboxes:
                # Convert to YOLO format (normalized center x, y, width, height)
                x_center = ((x1 + x2) / 2) / image_width
                y_center = ((y1 + y2) / 2) / image_height
                width = (x2 - x1) / image_width
                height = (y2 - y1) / image_height

                # Class 0 = license plate
                f.write(f"0 {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")

    def process_video(self, video_path: Path):
        """Process single video: extract frames and detect plates"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing video: {video_path.name}")
        logger.info(f"{'='*60}")

        # Extract frames
        frames = self.extract_frames(video_path)
        if not frames:
            logger.warning(f"No frames extracted from {video_path.name}")
            return

        # Process each frame
        video_name = video_path.stem
        frames_with_plates = 0
        total_plates = 0

        logger.info("Detecting plates using PaddleOCR...")
        for frame_idx, frame in tqdm(frames, desc="Detecting plates"):
            h, w = frame.shape[:2]

            # Detect plates
            plate_bboxes = self.detect_plates_paddleocr(frame)

            if not plate_bboxes:
                continue

            # Save image
            image_filename = f"{video_name}_frame_{frame_idx:06d}.jpg"
            image_path = self.images_dir / image_filename
            cv2.imwrite(str(image_path), frame)

            # Save YOLO annotation
            self.save_yolo_annotation(image_path, plate_bboxes, w, h)

            frames_with_plates += 1
            total_plates += len(plate_bboxes)
            self.stats['total_plates'] += len(plate_bboxes)

        self.stats['total_frames'] += len(frames)
        self.stats['frames_with_plates'] += frames_with_plates
        self.stats['videos_processed'] += 1

        logger.success(
            f"Video complete: {frames_with_plates}/{len(frames)} frames with plates "
            f"({total_plates} total plates)"
        )

    def create_dataset_yaml(self):
        """Create dataset.yaml for YOLO training"""
        dataset_config = {
            'path': str(self.output_dir.absolute()),
            'train': 'images',
            'val': 'images',  # Will split later

            'nc': 1,  # Number of classes
            'names': ['plate']  # Class names
        }

        yaml_path = self.output_dir / "dataset.yaml"
        with open(yaml_path, 'w') as f:
            yaml.dump(dataset_config, f, default_flow_style=False)

        logger.success(f"Created dataset config: {yaml_path}")

    def split_dataset(self, train_ratio: float = 0.8):
        """
        Split dataset into train/val sets

        Args:
            train_ratio: Ratio of training data (default: 0.8 = 80% train, 20% val)
        """
        logger.info(f"Splitting dataset ({train_ratio:.0%} train, {1-train_ratio:.0%} val)...")

        # Get all images
        images = list(self.images_dir.glob("*.jpg"))
        total_images = len(images)

        if total_images == 0:
            logger.warning("No images to split!")
            return

        # Shuffle
        import random
        random.shuffle(images)

        # Split
        split_idx = int(total_images * train_ratio)
        train_images = images[:split_idx]
        val_images = images[split_idx:]

        # Create train/val directories
        train_images_dir = self.output_dir / "train" / "images"
        train_labels_dir = self.output_dir / "train" / "labels"
        val_images_dir = self.output_dir / "val" / "images"
        val_labels_dir = self.output_dir / "val" / "labels"

        for d in [train_images_dir, train_labels_dir, val_images_dir, val_labels_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Move train files
        logger.info(f"Moving {len(train_images)} images to train/...")
        for img_path in tqdm(train_images, desc="Train"):
            label_path = self.labels_dir / (img_path.stem + ".txt")

            shutil.copy(img_path, train_images_dir / img_path.name)
            if label_path.exists():
                shutil.copy(label_path, train_labels_dir / label_path.name)

        # Move val files
        logger.info(f"Moving {len(val_images)} images to val/...")
        for img_path in tqdm(val_images, desc="Val"):
            label_path = self.labels_dir / (img_path.stem + ".txt")

            shutil.copy(img_path, val_images_dir / img_path.name)
            if label_path.exists():
                shutil.copy(label_path, val_labels_dir / label_path.name)

        # Update dataset.yaml
        dataset_config = {
            'path': str(self.output_dir.absolute()),
            'train': 'train/images',
            'val': 'val/images',
            'nc': 1,
            'names': ['plate']
        }

        yaml_path = self.output_dir / "dataset.yaml"
        with open(yaml_path, 'w') as f:
            yaml.dump(dataset_config, f, default_flow_style=False)

        logger.success(f"Dataset split complete: {len(train_images)} train, {len(val_images)} val")

    def save_stats(self):
        """Save processing statistics"""
        stats_path = self.output_dir / "preparation_stats.json"
        with open(stats_path, 'w') as f:
            json.dump(self.stats, f, indent=2)

        logger.info(f"\n{'='*60}")
        logger.info("Dataset Preparation Statistics")
        logger.info(f"{'='*60}")
        logger.info(f"Videos processed: {self.stats['videos_processed']}")
        logger.info(f"Total frames extracted: {self.stats['total_frames']}")
        logger.info(f"Frames with plates: {self.stats['frames_with_plates']}")
        logger.info(f"Total plates detected: {self.stats['total_plates']}")
        logger.info(f"Detection rate: {self.stats['frames_with_plates']/self.stats['total_frames']*100:.1f}%")
        logger.info(f"{'='*60}")

    def run(self):
        """Run complete dataset preparation pipeline"""
        logger.info("\n" + "="*60)
        logger.info("LICENSE PLATE TRAINING DATA PREPARATION")
        logger.info("="*60 + "\n")

        # Find all videos
        video_files = list(self.video_dir.glob("*.MOV"))
        video_files.extend(self.video_dir.glob("*.mov"))
        video_files.extend(self.video_dir.glob("*.mp4"))
        video_files.extend(self.video_dir.glob("*.MP4"))

        if not video_files:
            logger.error(f"No videos found in {self.video_dir}")
            return

        logger.info(f"Found {len(video_files)} videos to process")

        # Process each video
        for video_path in video_files:
            self.process_video(video_path)

        # Create dataset configuration
        self.create_dataset_yaml()

        # Split into train/val
        self.split_dataset(train_ratio=0.8)

        # Save statistics
        self.save_stats()

        logger.success("\n✅ Dataset preparation complete!")
        logger.info(f"Dataset location: {self.output_dir}")
        logger.info(f"Next step: Train YOLO11 model")
        logger.info(f"  python scripts/train_plate_detector.py")


if __name__ == "__main__":
    # Create dataset preparator
    preparator = PlateDatasetPreparator(
        video_dir="videos/training",
        output_dir="datasets/plate_training",
        fps_extract=1.0,  # Extract 1 frame per second
        min_confidence=0.5,  # Minimum OCR confidence
        min_plate_area=500  # Minimum plate area in pixels
    )

    # Run preparation
    preparator.run()
