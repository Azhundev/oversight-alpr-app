#!/usr/bin/env python3
"""
Jetson Installation Verification Script
Checks all dependencies and configurations for ALPR system
"""

import sys
from typing import Tuple

def check_module(name: str, min_version: str = None) -> Tuple[bool, str]:
    """Check if a module is installed and optionally verify version."""
    try:
        module = __import__(name)
        version = getattr(module, '__version__', 'unknown')

        if min_version and version != 'unknown':
            # For alpha/dev versions, just check major.minor
            try:
                # Extract major.minor from version string (e.g., "2.5.0a0..." -> "2.5")
                version_parts = version.split('.')[:2]
                version_short = '.'.join(version_parts)
                min_parts = min_version.split('.')[:2]
                min_short = '.'.join(min_parts)

                if version_short < min_short:
                    return False, f"{version} (needs >= {min_version})"
            except:
                pass  # If parsing fails, just accept the version

        return True, version
    except ImportError:
        return False, "not installed"

def main():
    print("=" * 60)
    print("ALPR System - Installation Verification")
    print("=" * 60)
    print()

    all_checks_passed = True

    # Core dependencies
    print("Core Dependencies:")
    print("-" * 60)

    checks = [
        ("torch", "2.5.0"),
        ("torchvision", "0.20.0"),
        ("numpy", "1.23.5"),
        ("cv2", None),
        ("onnxruntime", None),
        ("ultralytics", None),
    ]

    for module, min_ver in checks:
        success, version = check_module(module, min_ver)
        status = "✓" if success else "✗"
        color = "\033[92m" if success else "\033[91m"
        reset = "\033[0m"

        print(f"{color}{status}{reset} {module:20s} {version}")

        if not success:
            all_checks_passed = False

    print()

    # CUDA checks
    print("CUDA Configuration:")
    print("-" * 60)

    try:
        import torch

        cuda_available = torch.cuda.is_available()
        print(f"{'✓' if cuda_available else '✗'} CUDA available:      {cuda_available}")

        if cuda_available:
            print(f"✓ CUDA version:        {torch.version.cuda}")
            print(f"✓ cuDNN version:       {torch.backends.cudnn.version()}")
            print(f"✓ Device count:        {torch.cuda.device_count()}")
            print(f"✓ Current device:      {torch.cuda.current_device()}")
            print(f"✓ Device name:         {torch.cuda.get_device_name(0)}")

            # Memory check
            total_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"✓ Total GPU memory:    {total_mem:.1f} GB")
        else:
            print("✗ CUDA not available - check installation!")
            all_checks_passed = False

    except Exception as e:
        print(f"✗ Error checking CUDA: {e}")
        all_checks_passed = False

    print()

    # ALPR dependencies
    print("ALPR Dependencies:")
    print("-" * 60)

    alpr_deps = [
        ("pydantic", None),
        ("loguru", None),
        ("yaml", None),
        ("redis", None),
    ]

    for module, min_ver in alpr_deps:
        success, version = check_module(module, min_ver)
        status = "✓" if success else "✗"
        color = "\033[92m" if success else "\033[91m"
        reset = "\033[0m"

        print(f"{color}{status}{reset} {module:20s} {version}")

        if not success:
            all_checks_passed = False

    print()

    # Version-specific checks
    print("Version-Specific Checks:")
    print("-" * 60)

    try:
        import numpy
        numpy_version = numpy.__version__
        numpy_ok = numpy_version == "1.23.5"

        status = "✓" if numpy_ok else "⚠"
        color = "\033[92m" if numpy_ok else "\033[93m"
        reset = "\033[0m"

        print(f"{color}{status}{reset} Numpy version:       {numpy_version} {'(correct!)' if numpy_ok else '(should be 1.23.5)'}")

        if not numpy_ok:
            print(f"  {color}→{reset} Run: pip3 install numpy==1.23.5")
    except:
        print("✗ Numpy check failed")
        all_checks_passed = False

    print()

    # Model availability
    print("Model Files:")
    print("-" * 60)

    import os
    models = [
        "yolo11n.pt",
        "yolo11n.engine",
    ]

    for model in models:
        exists = os.path.exists(model)
        status = "✓" if exists else "○"
        color = "\033[92m" if exists else "\033[90m"
        reset = "\033[0m"

        print(f"{color}{status}{reset} {model:20s} {'found' if exists else 'not found (will download)'}")

    print()

    # Performance check
    print("Quick Performance Test:")
    print("-" * 60)

    try:
        from ultralytics import YOLO
        import numpy as np
        import time

        print("Loading YOLOv11n...")
        model = YOLO('yolo11n.pt')

        print("Running warmup (5 iterations)...")
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        for _ in range(5):
            model(dummy, verbose=False)

        print("Benchmarking (20 iterations)...")
        times = []
        for _ in range(20):
            start = time.time()
            model(dummy, verbose=False)
            times.append(time.time() - start)

        avg_time = np.mean(times) * 1000
        fps = 1 / np.mean(times)

        print(f"✓ Average inference:   {avg_time:.1f}ms")
        print(f"✓ Estimated FPS:       {fps:.1f}")

        if fps < 20:
            print("⚠ FPS is low - check power mode (sudo nvpmodel -m 0)")
        elif fps >= 25:
            print("✓ Performance is good!")

    except Exception as e:
        print(f"✗ Performance test failed: {e}")
        all_checks_passed = False

    print()

    # JetPack info
    print("System Information:")
    print("-" * 60)

    try:
        with open('/etc/nv_tegra_release', 'r') as f:
            tegra = f.read().strip()
            print(f"✓ Tegra release:       {tegra}")
    except:
        print("○ Not running on Jetson (or file not found)")

    try:
        import subprocess
        jetpack = subprocess.check_output(
            ["sudo", "apt-cache", "show", "nvidia-jetpack"],
            stderr=subprocess.DEVNULL
        ).decode()

        for line in jetpack.split('\n'):
            if line.startswith('Version:'):
                version = line.split(':')[1].strip()
                print(f"✓ JetPack version:     {version}")
                break
    except:
        pass

    print()
    print("=" * 60)

    if all_checks_passed:
        print("\033[92m✓ All checks passed! System ready for ALPR.\033[0m")
        print()
        print("Next steps:")
        print("  1. cd /home/jetson/OVR-ALPR")
        print("  2. python3 pilot.py")
        print()
        return 0
    else:
        print("\033[91m✗ Some checks failed. Please fix issues above.\033[0m")
        print()
        print("Common fixes:")
        print("  - Missing modules: pip3 install <module>")
        print("  - CUDA not available: Check PyTorch installation")
        print("  - Wrong numpy: pip3 install numpy==1.23.5")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
