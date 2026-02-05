#!/usr/bin/env python3
"""
Export YOLOv11 Model to TensorRT INT8 Engine
Standalone script to avoid memory issues during runtime export
"""

import argparse
import sys
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def export_int8_engine(
    model_path: str = "yolo11n.pt",
    calibration_data: str = "calibration.yaml",
    workspace: int = 2,
    batch_size: int = 1,
    device: str = "cuda:0",
):
    """
    Export YOLO model to TensorRT INT8 engine

    Args:
        model_path: Path to YOLO .pt model
        calibration_data: Path to calibration dataset YAML
        workspace: Workspace size in GB (default: 2)
        batch_size: Batch size for inference
        device: CUDA device

    Returns:
        Path to exported engine file
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("Ultralytics not installed. Run: pip install ultralytics")
        return None

    logger.info(f"Loading model: {model_path}")
    model = YOLO(model_path)

    logger.info("="*60)
    logger.info("Starting INT8 TensorRT export")
    logger.info(f"  Model: {model_path}")
    logger.info(f"  Calibration data: {calibration_data}")
    logger.info(f"  Workspace: {workspace}GB")
    logger.info(f"  Batch size: {batch_size}")
    logger.info(f"  Device: {device}")
    logger.info("="*60)

    logger.warning("This will take 10-15 minutes for INT8 calibration...")

    try:
        engine_path = model.export(
            format='engine',
            int8=True,
            device=device,
            batch=batch_size,
            workspace=workspace,
            data=calibration_data,
            imgsz=640,
            verbose=True,
        )

        logger.success("="*60)
        logger.success(f"INT8 engine exported successfully!")
        logger.success(f"Engine path: {engine_path}")
        logger.success("="*60)

        return engine_path

    except Exception as e:
        logger.error(f"Export failed: {e}")
        logger.error("Possible solutions:")
        logger.error("  1. Reduce workspace size: --workspace 1")
        logger.error("  2. Check calibration dataset exists: ls datasets/calibration/images")
        logger.error("  3. Verify CUDA/TensorRT installation")
        logger.error("  4. Reboot system to free GPU memory")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Export YOLOv11 model to TensorRT INT8 engine"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolo11n.pt",
        help="Path to YOLO model (default: yolo11n.pt)"
    )
    parser.add_argument(
        "--calibration",
        type=str,
        default="calibration.yaml",
        help="Path to calibration dataset YAML (default: calibration.yaml)"
    )
    parser.add_argument(
        "--workspace",
        type=int,
        default=2,
        help="TensorRT workspace size in GB (default: 2)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1,
        help="Batch size (default: 1)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cuda:0",
        help="CUDA device (default: cuda:0)"
    )
    parser.add_argument(
        "--plate-model",
        type=str,
        default=None,
        help="Also export plate detection model (optional)"
    )

    args = parser.parse_args()

    # Verify calibration dataset exists
    calib_path = Path(args.calibration)
    if not calib_path.exists():
        logger.error(f"Calibration file not found: {args.calibration}")
        logger.error("Run: python scripts/prepare_calibration_dataset.py")
        return 1

    # Export vehicle model
    logger.info("Exporting vehicle detection model...")
    vehicle_engine = export_int8_engine(
        model_path=args.model,
        calibration_data=args.calibration,
        workspace=args.workspace,
        batch_size=args.batch,
        device=args.device,
    )

    if not vehicle_engine:
        logger.error("Vehicle model export failed")
        return 1

    # Export plate model if provided
    if args.plate_model:
        logger.info("\nExporting plate detection model...")
        plate_engine = export_int8_engine(
            model_path=args.plate_model,
            calibration_data=args.calibration,
            workspace=args.workspace,
            batch_size=args.batch,
            device=args.device,
        )

        if not plate_engine:
            logger.warning("Plate model export failed")

    logger.info("\n" + "="*60)
    logger.info("Export complete!")
    logger.info("\nNext steps:")
    logger.info("  1. Run pilot.py - it will automatically use the .engine file")
    logger.info("  2. Check performance improvement (should be ~2x faster)")
    logger.info("  3. Verify detection quality remains acceptable")
    logger.info("="*60)

    return 0


if __name__ == "__main__":
    exit(main())
