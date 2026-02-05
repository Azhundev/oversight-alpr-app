#!/usr/bin/env python3
"""
Collect OCR training data from your rear-view video

Usage:
    python3 scripts/collect_training_data.py --video your_video.mp4
"""
import argparse
import cv2
import csv
from pathlib import Path
from datetime import datetime

def collect_plates(video_path: str, output_dir: str = "training_data/ocr"):
    """
    Run the system to collect plate crops, then create template for labeling

    Args:
        video_path: Path to your rear-view video
        output_dir: Where to save training data
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("OCR TRAINING DATA COLLECTOR")
    print("=" * 60)
    print()
    print(f"Video: {video_path}")
    print(f"Output: {output_dir}/")
    print()

    # Step 1: Run pilot.py to collect crops
    print("[1/3] Running ALPR system to collect plate crops...")
    print("      (This will take a few minutes)")
    import subprocess

    # Run pilot with the video
    result = subprocess.run([
        "python3", "pilot.py",
        "--video", video_path,
    ], capture_output=False)

    if result.returncode != 0:
        print("❌ Error running pilot.py")
        return

    # Step 2: Find all saved crops
    print("\n[2/3] Finding saved plate crops...")
    crops_dir = Path("output/crops")

    if not crops_dir.exists():
        print("❌ No crops directory found!")
        return

    # Get all jpg files from today
    today = datetime.now().strftime('%Y-%m-%d')
    today_crops = list(crops_dir.glob(f"{today}/*.jpg"))

    if not today_crops:
        print(f"❌ No crops found for today ({today})")
        return

    print(f"✅ Found {len(today_crops)} plate crops")

    # Step 3: Create labeling template
    print("\n[3/3] Creating labeling template...")

    labels_file = output_path / "labels_template.txt"
    stats_file = output_path / "collection_stats.txt"

    with open(labels_file, 'w') as f:
        f.write("# OCR Training Labels\n")
        f.write("# Format: image_path<TAB>plate_text\n")
        f.write("# Example: output/crops/2025-12-02/plate001.jpg	ABC123\n")
        f.write("#\n")
        f.write("# Instructions:\n")
        f.write("# 1. Look at each image\n")
        f.write("# 2. Type the correct plate text after the TAB\n")
        f.write("# 3. Skip bad/blurry images (delete line or leave blank)\n")
        f.write("# 4. Save this file when done\n")
        f.write("#\n\n")

        for crop_file in sorted(today_crops):
            # Get relative path
            rel_path = crop_file.relative_to(Path.cwd())
            f.write(f"{rel_path}\t\n")

    # Write stats
    with open(stats_file, 'w') as f:
        f.write(f"Collection Date: {datetime.now()}\n")
        f.write(f"Source Video: {video_path}\n")
        f.write(f"Total Crops: {len(today_crops)}\n")
        f.write(f"Crops Location: {crops_dir / today}\n")
        f.write(f"\nNext Steps:\n")
        f.write(f"1. Open {labels_file}\n")
        f.write(f"2. Label each plate crop with correct text\n")
        f.write(f"3. Run: python3 scripts/prepare_ocr_dataset.py\n")

    print(f"\n✅ Collection complete!")
    print(f"\n📝 Next steps:")
    print(f"   1. Open: {labels_file}")
    print(f"   2. Label each image with the correct plate text")
    print(f"   3. Save the file")
    print(f"   4. Run: python3 scripts/prepare_ocr_dataset.py")
    print()
    print(f"💡 Tip: Use a text editor with image preview for faster labeling")
    print()

def main():
    parser = argparse.ArgumentParser(description="Collect OCR training data from video")
    parser.add_argument("--video", required=True, help="Path to rear-view video file")
    parser.add_argument("--output", default="training_data/ocr", help="Output directory")

    args = parser.parse_args()

    collect_plates(args.video, args.output)

if __name__ == "__main__":
    main()
