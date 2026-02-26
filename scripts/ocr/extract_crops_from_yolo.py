"""
Extract plate crops from YOLO-annotated images for OCR training.

Reads YOLO detection labels (class cx cy w h, normalised) and crops each
plate region out of the corresponding full-frame image. The crops are saved
to an output directory ready to be labeled with label_crops.py.

Usage:
    # Extract from one dataset
    python scripts/ocr/extract_crops_from_yolo.py \
        --dataset datasets/plate_training_round2

    # Extract from multiple datasets into a shared output folder
    python scripts/ocr/extract_crops_from_yolo.py \
        --dataset datasets/plate_training_round2 datasets/plate_training_round1 \
        --output data/ocr_training/extracted_crops

    # Preview without writing anything
    python scripts/ocr/extract_crops_from_yolo.py \
        --dataset datasets/plate_training_round2 --dry-run
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# Extra padding added around the YOLO box before saving (fraction of box size).
# Helps OCR engines that struggle with characters right at the image edge.
PAD_FRACTION = 0.15

# Minimum crop dimensions — discard tiny boxes that are probably annotation errors.
MIN_WIDTH  = 40   # pixels
MIN_HEIGHT = 15   # pixels


def yolo_box_to_pixels(cx, cy, bw, bh, img_w, img_h):
    """Convert normalised YOLO box to pixel coordinates (x1, y1, x2, y2)."""
    x1 = int((cx - bw / 2) * img_w)
    y1 = int((cy - bh / 2) * img_h)
    x2 = int((cx + bw / 2) * img_w)
    y2 = int((cy + bh / 2) * img_h)
    return x1, y1, x2, y2


def apply_padding(x1, y1, x2, y2, img_w, img_h, pad_fraction):
    """Expand box by pad_fraction of its size, clamped to frame bounds."""
    pad_x = int((x2 - x1) * pad_fraction)
    pad_y = int((y2 - y1) * pad_fraction)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(img_w, x2 + pad_x)
    y2 = min(img_h, y2 + pad_y)
    return x1, y1, x2, y2


def find_splits(dataset_dir: Path):
    """
    Discover image/label split pairs inside a dataset directory.

    Supports two layouts:
      Layout A (train/val splits):
        dataset/
          train/images/*.jpg   train/labels/*.txt
          val/images/*.jpg     val/labels/*.txt

      Layout B (flat):
        dataset/
          images/*.jpg
          labels/*.txt
    """
    splits = []

    # Layout A
    for split_name in ("train", "val", "test"):
        img_dir = dataset_dir / split_name / "images"
        lbl_dir = dataset_dir / split_name / "labels"
        if img_dir.is_dir() and lbl_dir.is_dir():
            splits.append((split_name, img_dir, lbl_dir))

    # Layout B (flat)
    if not splits:
        img_dir = dataset_dir / "images"
        lbl_dir = dataset_dir / "labels"
        if img_dir.is_dir() and lbl_dir.is_dir():
            splits.append(("all", img_dir, lbl_dir))

    return splits


def extract_dataset(dataset_dir: Path, output_dir: Path, pad: float, dry_run: bool):
    """Extract all plate crops from a single dataset directory."""
    splits = find_splits(dataset_dir)
    if not splits:
        print(f"  ⚠  No image/label splits found in {dataset_dir}")
        return 0, 0

    dataset_name = dataset_dir.name
    total_saved = 0
    total_skipped = 0

    for split_name, img_dir, lbl_dir in splits:
        label_files = sorted(lbl_dir.glob("*.txt"))
        print(f"  {split_name}: {len(label_files)} label files in {lbl_dir}")

        for lbl_path in label_files:
            # Find matching image (try common extensions)
            img_path = None
            for ext in (".jpg", ".jpeg", ".png"):
                candidate = img_dir / (lbl_path.stem + ext)
                if candidate.exists():
                    img_path = candidate
                    break

            if img_path is None:
                print(f"    ⚠  No image for {lbl_path.name}, skipping")
                total_skipped += 1
                continue

            img = cv2.imread(str(img_path))
            if img is None:
                print(f"    ⚠  Cannot read {img_path.name}, skipping")
                total_skipped += 1
                continue

            img_h, img_w = img.shape[:2]

            # Parse YOLO boxes
            boxes = []
            with open(lbl_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    # class cx cy w h  (class ignored — only one class: plate)
                    _, cx, cy, bw, bh = int(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    boxes.append((cx, cy, bw, bh))

            for box_idx, (cx, cy, bw, bh) in enumerate(boxes):
                x1, y1, x2, y2 = yolo_box_to_pixels(cx, cy, bw, bh, img_w, img_h)
                x1, y1, x2, y2 = apply_padding(x1, y1, x2, y2, img_w, img_h, pad)

                crop_w = x2 - x1
                crop_h = y2 - y1

                if crop_w < MIN_WIDTH or crop_h < MIN_HEIGHT:
                    print(f"    ⚠  Box {box_idx} in {lbl_path.stem} too small ({crop_w}×{crop_h}), skipping")
                    total_skipped += 1
                    continue

                crop = img[y1:y2, x1:x2]
                if crop.size == 0:
                    total_skipped += 1
                    continue

                # Filename encodes origin so it stays unique across datasets
                filename = f"{dataset_name}__{lbl_path.stem}__plate{box_idx:02d}.jpg"
                out_path = output_dir / filename

                if not dry_run:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(out_path), crop)

                total_saved += 1

    return total_saved, total_skipped


def main():
    parser = argparse.ArgumentParser(
        description="Extract plate crops from YOLO-annotated datasets for OCR training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dataset", nargs="+", required=True, metavar="DIR",
        help="One or more YOLO dataset directories",
    )
    parser.add_argument(
        "--output", default="data/ocr_training/extracted_crops",
        help="Directory to write extracted crops (default: data/ocr_training/extracted_crops)",
    )
    parser.add_argument(
        "--pad", type=float, default=PAD_FRACTION,
        help=f"Padding fraction around each box (default: {PAD_FRACTION})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count crops without writing any files",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    grand_saved = 0
    grand_skipped = 0

    for ds_path_str in args.dataset:
        ds_path = Path(ds_path_str)
        if not ds_path.is_dir():
            print(f"Dataset not found: {ds_path}")
            sys.exit(1)

        print(f"\nDataset: {ds_path}")
        saved, skipped = extract_dataset(ds_path, output_dir, args.pad, args.dry_run)
        grand_saved += saved
        grand_skipped += skipped

    print(f"\n{'─' * 50}")
    if args.dry_run:
        print(f"  DRY RUN — no files written")
        print(f"  Would extract: {grand_saved} crops  (skipped: {grand_skipped})")
    else:
        print(f"  Extracted : {grand_saved} crops → {output_dir}")
        print(f"  Skipped   : {grand_skipped}")
        print(f"\n  Next step:")
        print(f"  python scripts/ocr/label_crops.py --crops-dir {output_dir}")
    print(f"{'─' * 50}\n")


if __name__ == "__main__":
    main()
