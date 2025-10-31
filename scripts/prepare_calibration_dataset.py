#!/usr/bin/env python3
"""
Prepare INT8 Calibration Dataset from Training Videos
Extracts representative frames from car videos for YOLOv11 INT8 quantization
"""

import cv2
import yaml
from pathlib import Path
from loguru import logger
import argparse


def extract_frames_from_video(video_path: Path, output_dir: Path, max_frames: int = 100, frame_interval: int = 30):
    """
    Extract frames from video for calibration dataset

    Args:
        video_path: Path to input video file
        output_dir: Directory to save extracted frames
        max_frames: Maximum number of frames to extract per video
        frame_interval: Extract every Nth frame

    Returns:
        Number of frames extracted
    """
    logger.info(f"Processing video: {video_path.name}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error(f"Failed to open video: {video_path}")
        return 0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0

    logger.info(f"  Total frames: {total_frames}, FPS: {fps:.1f}, Duration: {duration:.1f}s")

    frame_count = 0
    extracted_count = 0

    while extracted_count < max_frames:
        ret, frame = cap.read()

        if not ret:
            break

        # Extract every Nth frame
        if frame_count % frame_interval == 0:
            # Save frame
            output_filename = f"{video_path.stem}_frame_{frame_count:06d}.jpg"
            output_path = output_dir / output_filename

            cv2.imwrite(str(output_path), frame)
            extracted_count += 1

            if extracted_count % 10 == 0:
                logger.debug(f"  Extracted {extracted_count}/{max_frames} frames")

        frame_count += 1

    cap.release()
    logger.success(f"  Extracted {extracted_count} frames from {video_path.name}")

    return extracted_count


def create_calibration_yaml(dataset_path: Path, output_yaml: Path):
    """
    Create YAML configuration for calibration dataset

    Args:
        dataset_path: Path to calibration dataset directory
        output_yaml: Path to output YAML file
    """
    config = {
        'path': str(dataset_path.absolute()),
        'train': 'images',  # All calibration images in one directory
        'val': 'images',
        'names': {
            0: 'person',
            1: 'bicycle',
            2: 'car',
            3: 'motorcycle',
            4: 'airplane',
            5: 'bus',
            6: 'train',
            7: 'truck',
            8: 'boat',
            9: 'traffic light',
            10: 'fire hydrant',
            11: 'stop sign',
            12: 'parking meter',
            13: 'bench',
            14: 'bird',
            15: 'cat',
            16: 'dog',
            17: 'horse',
            18: 'sheep',
            19: 'cow',
            20: 'elephant',
            21: 'bear',
            22: 'zebra',
            23: 'giraffe',
            24: 'backpack',
            25: 'umbrella',
            26: 'handbag',
            27: 'tie',
            28: 'suitcase',
            29: 'frisbee',
            30: 'skis',
            31: 'snowboard',
            32: 'sports ball',
            33: 'kite',
            34: 'baseball bat',
            35: 'baseball glove',
            36: 'skateboard',
            37: 'surfboard',
            38: 'tennis racket',
            39: 'bottle',
            40: 'wine glass',
            41: 'cup',
            42: 'fork',
            43: 'knife',
            44: 'spoon',
            45: 'bowl',
            46: 'banana',
            47: 'apple',
            48: 'sandwich',
            49: 'orange',
            50: 'broccoli',
            51: 'carrot',
            52: 'hot dog',
            53: 'pizza',
            54: 'donut',
            55: 'cake',
            56: 'chair',
            57: 'couch',
            58: 'potted plant',
            59: 'bed',
            60: 'dining table',
            61: 'toilet',
            62: 'tv',
            63: 'laptop',
            64: 'mouse',
            65: 'remote',
            66: 'keyboard',
            67: 'cell phone',
            68: 'microwave',
            69: 'oven',
            70: 'toaster',
            71: 'sink',
            72: 'refrigerator',
            73: 'book',
            74: 'clock',
            75: 'vase',
            76: 'scissors',
            77: 'teddy bear',
            78: 'hair drier',
            79: 'toothbrush',
        }
    }

    with open(output_yaml, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    logger.success(f"Created calibration config: {output_yaml}")


def main():
    parser = argparse.ArgumentParser(
        description="Prepare INT8 calibration dataset from training videos"
    )
    parser.add_argument(
        "--video-dir",
        type=Path,
        default=Path("videos/training"),
        help="Directory containing training videos (default: videos/training)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/calibration"),
        help="Output directory for calibration dataset (default: datasets/calibration)"
    )
    parser.add_argument(
        "--max-frames-per-video",
        type=int,
        default=100,
        help="Maximum frames to extract per video (default: 100)"
    )
    parser.add_argument(
        "--frame-interval",
        type=int,
        default=30,
        help="Extract every Nth frame (default: 30, ~1 per second at 30fps)"
    )
    parser.add_argument(
        "--yaml-output",
        type=Path,
        default=Path("calibration.yaml"),
        help="Output YAML configuration file (default: calibration.yaml)"
    )

    args = parser.parse_args()

    # Create output directory
    images_dir = args.output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Calibration dataset preparation started")
    logger.info(f"  Video directory: {args.video_dir}")
    logger.info(f"  Output directory: {args.output_dir}")
    logger.info(f"  Max frames per video: {args.max_frames_per_video}")
    logger.info(f"  Frame interval: {args.frame_interval}")

    # Find all video files
    video_extensions = ['.mov', '.MOV', '.mp4', '.MP4', '.avi', '.AVI']
    video_files = []

    for ext in video_extensions:
        video_files.extend(args.video_dir.glob(f"*{ext}"))

    if not video_files:
        logger.error(f"No video files found in {args.video_dir}")
        return 1

    logger.info(f"Found {len(video_files)} video files")

    # Extract frames from each video
    total_extracted = 0
    for video_path in sorted(video_files):
        extracted = extract_frames_from_video(
            video_path,
            images_dir,
            max_frames=args.max_frames_per_video,
            frame_interval=args.frame_interval
        )
        total_extracted += extracted

    logger.success(f"Total frames extracted: {total_extracted}")

    # Create calibration YAML
    create_calibration_yaml(args.output_dir, args.yaml_output)

    # Print summary
    logger.info("\n" + "="*60)
    logger.info("Calibration dataset preparation complete!")
    logger.info(f"  Total frames: {total_extracted}")
    logger.info(f"  Images directory: {images_dir}")
    logger.info(f"  Config file: {args.yaml_output}")
    logger.info("\nNext steps:")
    logger.info("  1. Update detector_service.py line 90:")
    logger.info(f"     data='{args.yaml_output}'")
    logger.info("  2. Enable INT8 in pilot.py line 80:")
    logger.info("     int8=True")
    logger.info("  3. Run pilot.py - first run will calibrate INT8 engine")
    logger.info("="*60)

    return 0


if __name__ == "__main__":
    exit(main())
