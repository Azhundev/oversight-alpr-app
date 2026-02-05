#!/usr/bin/env python3
"""
Advanced Annotation Review Tool with Per-Box Editing

This tool allows you to:
- Review images with multiple bounding boxes
- Click on individual boxes to select/deselect them
- Delete bad boxes while keeping good ones
- Mark entire images as good/bad
- Navigate through dataset efficiently

Usage:
    python scripts/review_annotations_advanced.py [--dataset train|val]

Controls:
    - LEFT CLICK on box: Toggle box selection (selected = will be deleted)
    - Press 'd': Delete all selected boxes
    - Press 'a': Keep all boxes (mark image as good)
    - Press 'x': Delete all boxes (mark image as bad)
    - Press SPACE or 'n': Next image
    - Press 'b': Previous image
    - Press 's': Save current changes
    - Press 'q': Quit and save
    - Press 'u': Undo last deletion
"""

import cv2
import numpy as np
from pathlib import Path
import yaml
import argparse
import json
from loguru import logger
from typing import List, Tuple, Optional


class Box:
    """Represents a single bounding box"""
    def __init__(self, x1: int, y1: int, x2: int, y2: int, idx: int):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.idx = idx
        self.selected = False  # Selected for deletion
        self.deleted = False   # Already deleted

    def contains_point(self, x: int, y: int) -> bool:
        """Check if point is inside box"""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def to_yolo(self, img_width: int, img_height: int) -> str:
        """Convert to YOLO format string"""
        x_center = ((self.x1 + self.x2) / 2) / img_width
        y_center = ((self.y1 + self.y2) / 2) / img_height
        width = (self.x2 - self.x1) / img_width
        height = (self.y2 - self.y1) / img_height
        return f"0 {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


class AdvancedAnnotationReviewer:
    """Advanced annotation reviewer with per-box editing"""

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

        # Current image state
        self.current_boxes: List[Box] = []
        self.undo_stack = []
        self.changes_made = False

        # Review state
        self.review_file = self.dataset_path / f"review_{split}_advanced.json"
        self.review_state = self.load_review_state()

        # Mouse state
        self.mouse_x = 0
        self.mouse_y = 0

        # Stats
        self.stats = {
            'images_reviewed': 0,
            'boxes_deleted': 0,
            'images_kept': 0,
            'images_rejected': 0
        }

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

    def load_annotation(self, label_path: Path, img_width: int, img_height: int) -> List[Box]:
        """
        Load YOLO format annotation as Box objects

        Args:
            label_path: Path to label file
            img_width: Image width
            img_height: Image height

        Returns:
            List of Box objects
        """
        if not label_path.exists():
            return []

        boxes = []
        with open(label_path, 'r') as f:
            for idx, line in enumerate(f):
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

                boxes.append(Box(x1, y1, x2, y2, idx))

        return boxes

    def save_annotation(self, label_path: Path, boxes: List[Box], img_width: int, img_height: int):
        """
        Save boxes to YOLO format file

        Args:
            label_path: Path to label file
            boxes: List of Box objects (only non-deleted)
            img_width: Image width
            img_height: Image height
        """
        # Only save non-deleted boxes
        active_boxes = [b for b in boxes if not b.deleted]

        if not active_boxes:
            # No boxes left, delete label file
            if label_path.exists():
                label_path.unlink()
            return

        with open(label_path, 'w') as f:
            for box in active_boxes:
                f.write(box.to_yolo(img_width, img_height) + '\n')

    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events"""
        self.mouse_x = x
        self.mouse_y = y

        if event == cv2.EVENT_LBUTTONDOWN:
            # Check if clicked on any box
            for box in self.current_boxes:
                if not box.deleted and box.contains_point(x, y):
                    box.selected = not box.selected
                    logger.info(f"Box #{box.idx}: {'SELECTED' if box.selected else 'DESELECTED'}")
                    break

    def draw_annotations(self, image: np.ndarray, boxes: List[Box]) -> np.ndarray:
        """
        Draw bounding boxes on image with visual feedback

        Args:
            image: Input image
            boxes: List of Box objects

        Returns:
            Image with annotations drawn
        """
        img_vis = image.copy()

        # Draw all boxes
        for box in boxes:
            if box.deleted:
                continue

            # Determine color and style
            if box.selected:
                color = (0, 0, 255)  # Red = selected for deletion
                thickness = 3
                label = f"Box #{box.idx} [DELETE]"
            else:
                # Check if mouse is hovering
                hovering = box.contains_point(self.mouse_x, self.mouse_y)
                if hovering:
                    color = (0, 255, 255)  # Yellow = hovering
                    thickness = 3
                    label = f"Box #{box.idx} [CLICK TO SELECT]"
                else:
                    color = (0, 255, 0)  # Green = normal
                    thickness = 2
                    label = f"Box #{box.idx}"

            # Draw box
            cv2.rectangle(img_vis, (box.x1, box.y1), (box.x2, box.y2), color, thickness)

            # Draw label
            cv2.putText(img_vis, label, (box.x1, box.y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Draw info overlay
        info_y = 30
        cv2.putText(img_vis, f"Image {self.current_idx + 1}/{len(self.image_files)}",
                   (10, info_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        info_y += 30
        active_boxes = [b for b in boxes if not b.deleted]
        selected_boxes = [b for b in boxes if b.selected and not b.deleted]
        cv2.putText(img_vis, f"Boxes: {len(active_boxes)} active, {len(selected_boxes)} selected",
                   (10, info_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Draw controls help at bottom
        h = img_vis.shape[0]
        help_lines = [
            "CLICK=Select | d=Delete selected | a=Keep all | x=Delete all",
            "SPACE/n=Next | b=Back | u=Undo | s=Save | q=Quit"
        ]
        for i, line in enumerate(help_lines):
            cv2.putText(img_vis, line, (10, h - 40 + i*25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        return img_vis

    def delete_selected_boxes(self):
        """Delete all selected boxes"""
        deleted_count = 0
        deleted_boxes = []

        for box in self.current_boxes:
            if box.selected and not box.deleted:
                box.deleted = True
                box.selected = False
                deleted_count += 1
                deleted_boxes.append(box.idx)

        if deleted_count > 0:
            self.undo_stack.append(deleted_boxes)
            self.changes_made = True
            self.stats['boxes_deleted'] += deleted_count
            logger.warning(f"Deleted {deleted_count} box(es): {deleted_boxes}")
        else:
            logger.info("No boxes selected for deletion")

    def delete_all_boxes(self):
        """Delete all boxes (reject entire image)"""
        deleted_boxes = []
        for box in self.current_boxes:
            if not box.deleted:
                box.deleted = True
                deleted_boxes.append(box.idx)

        if deleted_boxes:
            self.undo_stack.append(deleted_boxes)
            self.changes_made = True
            self.stats['boxes_deleted'] += len(deleted_boxes)
            self.stats['images_rejected'] += 1
            logger.warning(f"Deleted ALL {len(deleted_boxes)} boxes")

    def keep_all_boxes(self):
        """Keep all boxes (accept entire image)"""
        active_boxes = [b for b in self.current_boxes if not b.deleted]
        if active_boxes:
            self.stats['images_kept'] += 1
            logger.success(f"Kept all {len(active_boxes)} boxes")

    def undo_last_deletion(self):
        """Undo last deletion"""
        if not self.undo_stack:
            logger.info("Nothing to undo")
            return

        deleted_indices = self.undo_stack.pop()
        for box in self.current_boxes:
            if box.idx in deleted_indices:
                box.deleted = False

        logger.success(f"Undone deletion of {len(deleted_indices)} box(es)")

    def save_current_image(self):
        """Save changes to current image"""
        if not self.changes_made:
            return

        img_path = self.image_files[self.current_idx]
        label_path = self.labels_dir / (img_path.stem + ".txt")

        # Load image to get dimensions
        image = cv2.imread(str(img_path))
        h, w = image.shape[:2]

        # Save annotation
        self.save_annotation(label_path, self.current_boxes, w, h)

        # Update review state
        active_boxes = [b for b in self.current_boxes if not b.deleted]
        self.review_state[img_path.name] = {
            'boxes_remaining': len(active_boxes),
            'boxes_deleted': sum(1 for b in self.current_boxes if b.deleted)
        }

        self.changes_made = False
        logger.success(f"Saved changes to {label_path.name}")

    def review(self):
        """Start interactive review"""
        logger.info("Starting advanced annotation review...")
        logger.info("Controls:")
        logger.info("  LEFT CLICK on box - Toggle selection (red = will delete)")
        logger.info("  'd' - Delete selected boxes")
        logger.info("  'a' - Keep all boxes (accept image)")
        logger.info("  'x' - Delete all boxes (reject image)")
        logger.info("  SPACE or 'n' - Next image")
        logger.info("  'b' - Previous image")
        logger.info("  'u' - Undo last deletion")
        logger.info("  's' - Save changes")
        logger.info("  'q' - Quit and save")

        window_name = f"Advanced Review - {self.split.upper()}"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, self.mouse_callback)

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
            self.current_boxes = self.load_annotation(label_path, w, h)
            self.undo_stack = []
            self.changes_made = False

            # Review loop for current image
            while True:
                # Draw annotations
                img_vis = self.draw_annotations(image, self.current_boxes)

                # Display
                cv2.imshow(window_name, img_vis)

                # Wait for key press
                key = cv2.waitKey(30) & 0xFF

                if key == ord('q'):
                    # Quit
                    logger.info("Quitting review...")
                    self.save_current_image()
                    cv2.destroyAllWindows()
                    self.save_review_state()
                    self.print_summary()
                    return

                elif key == ord('n') or key == 32:  # 'n' or SPACE
                    # Next image
                    self.save_current_image()
                    self.stats['images_reviewed'] += 1
                    self.current_idx += 1
                    break

                elif key == ord('b'):
                    # Previous image
                    self.save_current_image()
                    self.current_idx = max(0, self.current_idx - 1)
                    break

                elif key == ord('d'):
                    # Delete selected boxes
                    self.delete_selected_boxes()

                elif key == ord('a'):
                    # Keep all boxes
                    self.keep_all_boxes()
                    self.save_current_image()
                    self.stats['images_reviewed'] += 1
                    self.current_idx += 1
                    break

                elif key == ord('x'):
                    # Delete all boxes
                    self.delete_all_boxes()
                    self.save_current_image()
                    self.stats['images_reviewed'] += 1
                    self.current_idx += 1
                    break

                elif key == ord('u'):
                    # Undo
                    self.undo_last_deletion()

                elif key == ord('s'):
                    # Save
                    self.save_current_image()
                    self.save_review_state()

        cv2.destroyAllWindows()
        self.save_review_state()
        self.print_summary()

    def print_summary(self):
        """Print review summary"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Review Summary - {self.split.upper()} Set")
        logger.info(f"{'='*60}")
        logger.info(f"Images reviewed: {self.stats['images_reviewed']}")
        logger.info(f"Images kept (all boxes): {self.stats['images_kept']}")
        logger.info(f"Images rejected (all boxes deleted): {self.stats['images_rejected']}")
        logger.info(f"Total boxes deleted: {self.stats['boxes_deleted']}")
        logger.info(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Advanced plate detection annotation review")
    parser.add_argument(
        '--dataset',
        type=str,
        default='datasets/plate_training_round2',
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
    reviewer = AdvancedAnnotationReviewer(
        dataset_path=args.dataset,
        split=args.split
    )

    # Start review
    reviewer.review()


if __name__ == "__main__":
    main()
