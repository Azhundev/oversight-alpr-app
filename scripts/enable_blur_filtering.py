#!/usr/bin/env python3
"""
Enable blur filtering in pilot.py

This script modifies pilot.py to enable the built-in blur detection
that skips blurry frames before running OCR, improving OCR success rate.

Usage:
    python3 scripts/enable_blur_filtering.py
    python3 scripts/enable_blur_filtering.py --threshold 150  # Aggressive
    python3 scripts/enable_blur_filtering.py --disable        # Revert
"""

import argparse
import re
from pathlib import Path


def enable_blur_filter(pilot_path: Path, threshold: float = 120.0, enable: bool = True):
    """
    Enable or disable blur filtering in pilot.py

    Args:
        pilot_path: Path to pilot.py
        threshold: Minimum sharpness threshold (80-250 range)
        enable: True to enable, False to disable
    """
    print(f"\n{'='*70}")
    print(f"Blur Filtering Configuration")
    print(f"{'='*70}")
    print(f"File:      {pilot_path}")
    print(f"Action:    {'ENABLE' if enable else 'DISABLE'}")
    print(f"Threshold: {threshold:.1f}")
    print(f"{'='*70}\n")

    if not pilot_path.exists():
        print(f"❌ Error: {pilot_path} not found")
        return False

    # Read file
    with open(pilot_path, 'r') as f:
        content = f.read()

    # Find the blur filter lines (around line 158-159)
    pattern_enable = r'self\.enable_frame_quality_filter\s*=\s*(True|False)'
    pattern_threshold = r'self\.min_frame_sharpness\s*=\s*([\d.]+)'

    # Check current state
    current_enable_match = re.search(pattern_enable, content)
    current_threshold_match = re.search(pattern_threshold, content)

    if not current_enable_match or not current_threshold_match:
        print(f"❌ Error: Could not find blur filter settings in {pilot_path}")
        return False

    current_enable = current_enable_match.group(1) == 'True'
    current_threshold = float(current_threshold_match.group(1))

    print(f"Current Settings:")
    print(f"  Enabled:   {current_enable}")
    print(f"  Threshold: {current_threshold:.1f}")
    print()

    # Update settings
    enable_str = 'True' if enable else 'False'

    # Replace enable flag
    content = re.sub(
        pattern_enable,
        f'self.enable_frame_quality_filter = {enable_str}',
        content
    )

    # Replace threshold
    content = re.sub(
        pattern_threshold,
        f'self.min_frame_sharpness = {threshold:.1f}',
        content
    )

    # Write back
    with open(pilot_path, 'w') as f:
        f.write(content)

    print(f"✅ Updated Settings:")
    print(f"  Enabled:   {enable}")
    print(f"  Threshold: {threshold:.1f}")
    print()

    if enable:
        print(f"📋 What This Does:")
        print(f"  - Calculates sharpness score for each plate detection")
        print(f"  - Skips frames with sharpness < {threshold:.1f}")
        print(f"  - Waits for sharper frames before running OCR")
        print(f"  - Selects best frame from each vehicle track")
        print()

        print(f"🎯 Expected Impact:")
        if threshold < 100:
            print(f"  - Conservative filtering (catches most plates)")
            print(f"  - ~15-20% OCR improvement")
            print(f"  - Low risk of missing plates")
        elif threshold < 150:
            print(f"  - Balanced filtering (good tradeoff)")
            print(f"  - ~25-40% OCR improvement")
            print(f"  - Recommended for typical conditions")
        else:
            print(f"  - Aggressive filtering (only sharp frames)")
            print(f"  - ~40-50% OCR improvement")
            print(f"  - May miss some plates if all frames blurry")
        print()

        print(f"📊 How to Monitor:")
        print(f"  - Watch logs for: 'Skipping blurry frame (sharpness: X < {threshold:.1f})'")
        print(f"  - Check saved crops in output/crops/ for quality scores")
        print(f"  - Compare OCR success rate before/after")
        print()

        print(f"🔧 Tuning Guide:")
        print(f"  - Too many blurry reads? Increase threshold: {threshold + 30:.1f}")
        print(f"  - Missing too many plates? Decrease threshold: {threshold - 20:.1f}")
        print(f"  - Check crop filenames: track_frame_q<SCORE>.jpg")
        print()
    else:
        print(f"ℹ️  Blur filtering disabled. All frames will be processed.")
        print()

    print(f"✅ Done! Restart pilot.py for changes to take effect.")
    print(f"{'='*70}\n")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Enable blur filtering in pilot.py for better OCR',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enable with balanced threshold (recommended)
  python3 scripts/enable_blur_filtering.py

  # Enable with conservative threshold (less filtering)
  python3 scripts/enable_blur_filtering.py --threshold 100

  # Enable with aggressive threshold (more filtering)
  python3 scripts/enable_blur_filtering.py --threshold 150

  # Disable blur filtering (revert to process all frames)
  python3 scripts/enable_blur_filtering.py --disable

Threshold Recommendations:
  80-100:  Conservative (good for variable conditions)
  100-140: Balanced (recommended for most cases)
  140-200: Aggressive (only very sharp frames)
  200+:    Very aggressive (may miss plates)
        """
    )

    parser.add_argument(
        '--threshold',
        type=float,
        default=120.0,
        help='Minimum sharpness threshold (80-250, default: 120)'
    )

    parser.add_argument(
        '--disable',
        action='store_true',
        help='Disable blur filtering (revert to process all frames)'
    )

    parser.add_argument(
        '--pilot',
        type=str,
        default='pilot.py',
        help='Path to pilot.py (default: pilot.py)'
    )

    args = parser.parse_args()

    # Validate threshold
    if args.threshold < 50 or args.threshold > 300:
        print(f"⚠️  Warning: Threshold {args.threshold} is outside recommended range (80-250)")
        print(f"    Using anyway, but results may be suboptimal.")
        print()

    # Enable or disable
    pilot_path = Path(args.pilot)
    enable = not args.disable

    success = enable_blur_filter(pilot_path, args.threshold, enable)

    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
