#!/usr/bin/env python3
"""
Fine-tune YOLOv11 for Florida License Plate Detection
"""

import argparse
from pathlib import Path
from ultralytics import YOLO
from loguru import logger


def train_plate_detector(
    data_yaml: str,
    base_model: str = "yolo11n.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    device: str = "0",
    output_dir: str = "models/plate_detector",
):
    """
    Train YOLOv11 plate detector

    Args:
        data_yaml: Path to dataset YAML config
        base_model: Base YOLOv11 model (n, s, m, l, x)
        epochs: Number of training epochs
        imgsz: Input image size
        batch: Batch size
        device: Device ID (0 for GPU, cpu for CPU)
        output_dir: Output directory for trained model
    """
    logger.info("=== YOLOv11 Plate Detector Training ===")
    logger.info(f"Base model: {base_model}")
    logger.info(f"Dataset: {data_yaml}")
    logger.info(f"Epochs: {epochs}")
    logger.info(f"Image size: {imgsz}")
    logger.info(f"Batch size: {batch}")
    logger.info(f"Device: {device}")

    # Load base model
    logger.info("Loading base model...")
    model = YOLO(base_model)

    # Train
    logger.info("Starting training...")
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=output_dir,
        name="florida_plates",

        # Optimization settings
        patience=20,  # Early stopping patience
        save=True,
        save_period=10,  # Save checkpoint every 10 epochs

        # Data augmentation
        augment=True,
        hsv_h=0.015,  # Hue augmentation
        hsv_s=0.7,    # Saturation
        hsv_v=0.4,    # Value
        degrees=10,   # Rotation
        translate=0.1,  # Translation
        scale=0.5,    # Scale
        shear=0.0,    # Shear
        perspective=0.0,  # Perspective
        flipud=0.0,   # Flip up-down (plates shouldn't flip)
        fliplr=0.5,   # Flip left-right (OK for plates)
        mosaic=1.0,   # Mosaic augmentation
        mixup=0.0,    # Mixup augmentation

        # Performance
        workers=4,
        close_mosaic=10,  # Disable mosaic in last 10 epochs

        # Validation
        val=True,
        plots=True,  # Save training plots
    )

    logger.success("Training complete!")
    logger.info(f"Results saved to: {output_dir}/florida_plates")

    # Export to TensorRT for Jetson
    logger.info("Exporting to TensorRT (FP16)...")

    # Load best weights
    best_model = YOLO(f"{output_dir}/florida_plates/weights/best.pt")

    # Export
    export_path = best_model.export(
        format='engine',  # TensorRT
        half=True,        # FP16
        device=device,
        workspace=4,      # GB
        simplify=True,
        dynamic=False,    # Static batch size for Jetson
        batch=1,          # Batch size 1 for edge
    )

    logger.success(f"TensorRT model exported: {export_path}")
    logger.info("You can now use this model in your ALPR system!")

    return export_path


def main():
    parser = argparse.ArgumentParser(
        description="Train YOLOv11 for Florida plate detection"
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Path to dataset YAML file"
    )
    parser.add_argument(
        "--model",
        default="yolo11n.pt",
        help="Base model (yolo11n.pt, yolo11s.pt, etc.)"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Number of epochs (default: 100)"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Input image size (default: 640)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=16,
        help="Batch size (default: 16)"
    )
    parser.add_argument(
        "--device",
        default="0",
        help="Device (0 for GPU, cpu for CPU)"
    )
    parser.add_argument(
        "--output",
        default="models/plate_detector",
        help="Output directory"
    )

    args = parser.parse_args()

    train_plate_detector(
        data_yaml=args.data,
        base_model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()
