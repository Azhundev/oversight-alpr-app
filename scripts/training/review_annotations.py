#!/usr/bin/env python3
"""
Review Auto-Generated Plate Annotations

This script displays images with their auto-generated bounding boxes
so you can verify the quality of the PaddleOCR auto-labeling.

Usage:
    python scripts/review_annotations.py [--dataset train|val]

Controls:
    - Press SPACE or 'n' to go to next image
    - Press 'b' to go back to previous image
    - Press 'd' to mark for deletion (bad annotation)
    - Press 'g' to mark as good
    - Press 'q' to quit and save review
    - Press 's' to save current review state
"""

import cv2
import numpy as np
from pathlib import Path
import yaml
import argparse
import json
from loguru import logger


class AnnotationReviewer:
    """Review and validate YOLO annotations"""

    def __init__(self, dataset_path: str, split: str = "train"):
        """
        Initialize reviewer

        Args:
            dataset_path: Path to dataset directory
            split: Which split to review ('train' or 'val')
        """
        self.dataset_path = Path(dataset_path)
        self.split = split

        # Paths
        self.images_dir = self.dataset_path / split / "images"
        self.labels_dir = self.dataset_path / split / "labels"

        # Get all images
        self.image_files = sorted(list(self.images_dir.glob("*.jpg")))
        self.current_idx = 0

        # Review state
        self.review_file = self.dataset_path / f"review_{split}.json"
        self.review_state = self.load_review_state()

        logger.info(f"Found {len(self.image_files)} images in {split} set")

    def load_review_state(self) -> dict:
        """Load previous review state if exists"""
        if self.review_file.exists():
            with open(self.review_file, 'r') as f:
                state = json.load(f)
                logger.info(f"Loaded previous review state with {len(state)} entries")
                return state
        return {}

    def save_review_state(self):
        """Save review state to file"""
        with open(self.review_file, 'w') as f:
            json.dump(self.review_state, f, indent=2)
        logger.success(f"Review state saved to {self.review_file}")

    def load_annotation(self, label_path: Path, img_width: int, img_height: int) -> list:
        """
        Load YOLO format annotation

        Args:
            label_path: Path to label file
            img_width: Image width
            img_height: Image height

        Returns:
            List of bounding boxes in pixel coordinates
        """
        if not label_path.exists():
            return []

        bboxes = []
        with open(label_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 5:
                    continue

                # Parse YOLO format: class x_center y_center width height (normalized)
                cls, x_center, y_center, width, height = map(float, parts)

                # Convert to pixel coordinates
                x_center_px = x_center * img_width
                y_center_px = y_center * img_height
                width_px = width * img_width
                height_px = height * img_height

                # Convert to corner coordinates
                x1 = int(x_center_px - width_px / 2)
                y1 = int(y_center_px - height_px / 2)
                x2 = int(x_center_px + width_px / 2)
                y2 = int(y_center_px + height_px / 2)

                bboxes.append((x1, y1, x2, y2))

        return bboxes

    def draw_annotations(self, image: np.ndarray, bboxes: list, status: str = None) -> np.ndarray:
        """
        Draw bounding boxes on image

        Args:
            image: Input image
            bboxes: List of bounding boxes
            status: Review status ('good', 'bad', or None)

        Returns:
            Image with annotations drawn
        """
        img_vis = image.copy()

        # Draw bounding boxes
        for x1, y1, x2, y2 in bboxes:
            # Color based on status
            if status == 'good':
                color = (0, 255, 0)  # Green
                thickness = 3
            elif status == 'bad':
                color = (0, 0, 255)  # Red
                thickness = 3
            else:
                color = (0, 255, 255)  # Yellow (not reviewed)
                thickness = 2

            cv2.rectangle(img_vis, (x1, y1), (x2, y2), color, thickness)

        # Add text overlay
        info_text = f"Image {self.current_idx + 1}/{len(self.image_files)}"
        cv2.putText(img_vis, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                   0.8, (255, 255, 255), 2)

        if status:
            status_text = f"Status: {status.upper()}"
            status_color = (0, 255, 0) if status == 'good' else (0, 0, 255)
            cv2.putText(img_vis, status_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX,
                       0.8, status_color, 2)

        # Add plate count
        plate_text = f"Plates: {len(bboxes)}"
        cv2.putText(img_vis, plate_text, (10, 90), cv2.FONT_HERSHEY_SIMPLEX,
                   0.8, (255, 255, 255), 2)

        # Add controls help
        help_text = "SPACE/n=Next | b=Back | g=Good | d=Bad | s=Save | q=Quit"
        cv2.putText(img_vis, help_text, (10, img_vis.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        return img_vis

    def review(self):
        """Start interactive review"""
        logger.info("Starting annotation review...")
        logger.info("Controls:")
        logger.info("  SPACE or 'n' - Next image")
        logger.info("  'b' - Previous image")
        logger.info("  'g' - Mark as good")
        logger.info("  'd' - Mark as bad (for deletion)")
        logger.info("  's' - Save review state")
        logger.info("  'q' - Quit and save")

        window_name = f"Review {self.split.upper()} Annotations"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        while self.current_idx < len(self.image_files):
            # Load image
            img_path = self.image_files[self.current_idx]
            image = cv2.imread(str(img_path))

            if image is None:
                logger.error(f"Failed to load image: {img_path}")
                self.current_idx += 1
                continue

            h, w = image.shape[:2]

            # Load annotation
            label_path = self.labels_dir / (img_path.stem + ".txt")
            bboxes = self.load_annotation(label_path, w, h)

            # Get review status
            img_name = img_path.name
            status = self.review_state.get(img_name)

            # Draw annotations
            img_vis = self.draw_annotations(image, bboxes, status)

            # Display
            cv2.imshow(window_name, img_vis)

            # Wait for key press
            key = cv2.waitKey(0) & 0xFF

            if key == ord('q'):
                # Quit
                logger.info("Quitting review...")
                break
            elif key == ord('n') or key == 32:  # 'n' or SPACE
                # Next image
                self.current_idx += 1
            elif key == ord('b'):
                # Previous image
                self.current_idx = max(0, self.current_idx - 1)
            elif key == ord('g'):
                # Mark as good
                self.review_state[img_name] = 'good'
                logger.success(f"Marked {img_name} as GOOD")
                self.current_idx += 1
            elif key == ord('d'):
                # Mark as bad
                self.review_state[img_name] = 'bad'
                logger.warning(f"Marked {img_name} as BAD")
                self.current_idx += 1
            elif key == ord('s'):
                # Save state
                self.save_review_state()

        cv2.destroyAllWindows()

        # Save final state
        self.save_review_state()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print review summary"""
        total = len(self.image_files)
        reviewed = len(self.review_state)
        good = sum(1 for v in self.review_state.values() if v == 'good')
        bad = sum(1 for v in self.review_state.values() if v == 'bad')
        not_reviewed = total - reviewed

        logger.info(f"\n{'='*60}")
        logger.info(f"Review Summary - {self.split.upper()} Set")
        logger.info(f"{'='*60}")
        logger.info(f"Total images: {total}")
        logger.info(f"Reviewed: {reviewed} ({reviewed/total*100:.1f}%)")
        logger.info(f"  Good: {good}")
        logger.info(f"  Bad: {bad}")
        logger.info(f"Not reviewed: {not_reviewed}")
        logger.info(f"{'='*60}\n")

        if bad > 0:
            logger.warning(f"\n{bad} images marked as BAD. Consider:")
            logger.warning("  1. Manually correcting annotations")
            logger.warning("  2. Deleting bad images/labels")
            logger.warning("  3. Re-generating with different parameters")

    def get_bad_images(self) -> list:
        """Get list of images marked as bad"""
        return [img for img, status in self.review_state.items() if status == 'bad']


def main():
    parser = argparse.ArgumentParser(description="Review plate detection annotations")
    parser.add_argument(
        '--dataset',
        type=str,
        default='datasets/plate_training',
        help='Path to dataset directory'
    )
    parser.add_argument(
        '--split',
        type=str,
        default='train',
        choices=['train', 'val'],
        help='Which split to review (train or val)'
    )

    args = parser.parse_args()

    # Create reviewer
    reviewer = AnnotationReviewer(
        dataset_path=args.dataset,
        split=args.split
    )

    # Start review
    reviewer.review()

    # Show bad images if any
    bad_images = reviewer.get_bad_images()
    if bad_images:
        logger.warning(f"\nBad images to review:")
        for img_name in bad_images:
            logger.warning(f"  - {img_name}")


if __name__ == "__main__":
    main()
