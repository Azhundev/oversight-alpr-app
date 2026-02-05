#!/usr/bin/env python3
"""
TensorRT Engine Rebuild Script for OVR-ALPR

This script rebuilds all TensorRT engine files from PyTorch models.
Pre-building engines ensures they are cached and reused on every ALPR run,
eliminating the first-time export delay.

Usage:
    python3 scripts/tensorrt/rebuild_tensorrt_engines.py
    python3 scripts/tensorrt/rebuild_tensorrt_engines.py --precision fp16
    python3 scripts/tensorrt/rebuild_tensorrt_engines.py --precision int8 --calibration calibration.yaml
    python3 scripts/tensorrt/rebuild_tensorrt_engines.py --models vehicle  # Only rebuild vehicle model
    python3 scripts/tensorrt/rebuild_tensorrt_engines.py --models plate    # Only rebuild plate model
"""

import argparse
import time
from pathlib import Path
from ultralytics import YOLO


class TensorRTEngineBuilder:
    """Builds TensorRT engines from YOLO PyTorch models"""

    def __init__(self, precision='fp16', workspace=2, batch_size=1):
        """
        Initialize the engine builder

        Args:
            precision: 'fp16' or 'int8'
            workspace: Workspace size in GB
            batch_size: Batch size for inference
        """
        self.precision = precision.lower()
        self.workspace = workspace
        self.batch_size = batch_size

        # Model configurations
        self.models = {
            'vehicle': {
                'pt_path': 'models/yolo11n.pt',
                'engine_path': 'models/yolo11n.engine',
                'description': 'Vehicle Detection Model (YOLO11n)',
                'imgsz': 640  # Vehicle model uses 640x640 input
            },
            'plate': {
                'pt_path': 'models/yolo11n-plate.pt',
                'engine_path': 'models/yolo11n-plate.engine',
                'description': 'License Plate Detection Model (YOLO11n Custom)',
                'imgsz': 416  # Plate model was trained at 416x416
            }
        }

    def build_engine(self, model_name, calibration_yaml=None):
        """
        Build TensorRT engine for a specific model

        Args:
            model_name: 'vehicle' or 'plate'
            calibration_yaml: Path to calibration data for INT8 (optional)

        Returns:
            bool: True if successful, False otherwise
        """
        if model_name not in self.models:
            print(f"❌ Unknown model: {model_name}")
            return False

        model_config = self.models[model_name]
        pt_path = Path(model_config['pt_path'])
        engine_path = Path(model_config['engine_path'])
        imgsz = model_config['imgsz']

        # Check if PyTorch model exists
        if not pt_path.exists():
            print(f"❌ PyTorch model not found: {pt_path}")
            return False

        print(f"\n{'='*70}")
        print(f"🔨 Building TensorRT Engine: {model_config['description']}")
        print(f"{'='*70}")
        print(f"  Source:      {pt_path} ({pt_path.stat().st_size / 1024 / 1024:.1f} MB)")
        print(f"  Target:      {engine_path}")
        print(f"  Precision:   {self.precision.upper()}")
        print(f"  Input Size:  {imgsz}x{imgsz}")
        print(f"  Workspace:   {self.workspace} GB")
        print(f"  Batch Size:  {self.batch_size}")

        # Remove existing engine
        if engine_path.exists():
            print(f"  Removing existing engine: {engine_path}")
            engine_path.unlink()

        try:
            # Load YOLO model
            print(f"\n📥 Loading PyTorch model...")
            model = YOLO(str(pt_path))

            # Export to TensorRT
            print(f"⚙️  Exporting to TensorRT {self.precision.upper()}...")
            start_time = time.time()

            if self.precision == 'fp16':
                # FP16 export (default, stable)
                model.export(
                    format='engine',
                    half=True,
                    workspace=self.workspace,
                    device=0,
                    batch=self.batch_size,
                    imgsz=imgsz
                )
            elif self.precision == 'int8':
                # INT8 export (requires calibration)
                if not calibration_yaml:
                    print("⚠️  Warning: INT8 requires calibration data. Using FP16 instead.")
                    model.export(
                        format='engine',
                        half=True,
                        workspace=self.workspace,
                        device=0,
                        batch=self.batch_size,
                        imgsz=imgsz
                    )
                else:
                    print(f"📊 Using calibration data: {calibration_yaml}")
                    model.export(
                        format='engine',
                        int8=True,
                        data=calibration_yaml,
                        workspace=self.workspace,
                        device=0,
                        batch=self.batch_size,
                        imgsz=imgsz,
                        dynamic=False
                    )
            else:
                print(f"❌ Unknown precision: {self.precision}")
                return False

            elapsed_time = time.time() - start_time

            # Verify engine was created
            if engine_path.exists():
                engine_size = engine_path.stat().st_size / 1024 / 1024
                print(f"\n✅ Export successful!")
                print(f"   Engine:   {engine_path}")
                print(f"   Size:     {engine_size:.1f} MB")
                print(f"   Time:     {elapsed_time:.1f}s")
                return True
            else:
                print(f"❌ Engine file not created: {engine_path}")
                return False

        except Exception as e:
            print(f"❌ Export failed: {e}")
            return False

    def build_all(self, calibration_yaml=None):
        """
        Build TensorRT engines for all models

        Args:
            calibration_yaml: Path to calibration data for INT8 (optional)

        Returns:
            dict: Results for each model
        """
        print(f"\n{'='*70}")
        print(f"🚀 TensorRT Engine Batch Rebuild")
        print(f"{'='*70}")
        print(f"Precision:   {self.precision.upper()}")
        print(f"Workspace:   {self.workspace} GB")
        print(f"Batch Size:  {self.batch_size}")

        results = {}
        total_start = time.time()

        for model_name in self.models:
            results[model_name] = self.build_engine(model_name, calibration_yaml)

        total_elapsed = time.time() - total_start

        # Summary
        print(f"\n{'='*70}")
        print(f"📊 Build Summary")
        print(f"{'='*70}")

        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)

        for model_name, success in results.items():
            status = "✅ SUCCESS" if success else "❌ FAILED"
            print(f"  {model_name:12} {status}")

        print(f"\n  Total: {success_count}/{total_count} successful")
        print(f"  Time:  {total_elapsed:.1f}s")

        return results


def main():
    parser = argparse.ArgumentParser(
        description='Rebuild TensorRT engines for OVR-ALPR models',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rebuild all models with FP16 precision (recommended)
  python3 scripts/tensorrt/rebuild_tensorrt_engines.py

  # Rebuild with INT8 precision (requires calibration data)
  python3 scripts/tensorrt/rebuild_tensorrt_engines.py --precision int8 --calibration calibration.yaml

  # Rebuild only vehicle detection model
  python3 scripts/tensorrt/rebuild_tensorrt_engines.py --models vehicle

  # Rebuild only plate detection model
  python3 scripts/tensorrt/rebuild_tensorrt_engines.py --models plate

  # Custom workspace size (for systems with more GPU memory)
  python3 scripts/tensorrt/rebuild_tensorrt_engines.py --workspace 4
        """
    )

    parser.add_argument(
        '--precision',
        type=str,
        choices=['fp16', 'int8'],
        default='fp16',
        help='TensorRT precision mode (default: fp16)'
    )

    parser.add_argument(
        '--workspace',
        type=int,
        default=2,
        help='Workspace size in GB (default: 2)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=1,
        help='Batch size for inference (default: 1)'
    )

    parser.add_argument(
        '--calibration',
        type=str,
        help='Path to calibration YAML for INT8 mode'
    )

    parser.add_argument(
        '--models',
        type=str,
        choices=['all', 'vehicle', 'plate'],
        default='all',
        help='Which models to rebuild (default: all)'
    )

    args = parser.parse_args()

    # Validate INT8 requirements
    if args.precision == 'int8' and not args.calibration:
        print("⚠️  Warning: INT8 precision requires --calibration argument")
        print("    Falling back to FP16 mode")
        args.precision = 'fp16'

    # Create builder
    builder = TensorRTEngineBuilder(
        precision=args.precision,
        workspace=args.workspace,
        batch_size=args.batch_size
    )

    # Build engines
    if args.models == 'all':
        results = builder.build_all(args.calibration)
    else:
        results = {
            args.models: builder.build_engine(args.models, args.calibration)
        }

    # Exit with appropriate code
    all_success = all(results.values())
    exit(0 if all_success else 1)


if __name__ == '__main__':
    main()
