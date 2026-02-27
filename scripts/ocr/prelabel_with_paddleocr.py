"""
Pre-label plate crops using PaddleOCR to bootstrap labels.txt.
Run label_crops.py --review afterwards to correct mistakes.
"""
import argparse
import re
import sys
from pathlib import Path

import cv2


def load_labels(path: Path) -> dict:
    labels = {}
    if not path.exists():
        return labels
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if "\t" in line:
                img, text = line.split("\t", 1)
                labels[img] = text
    return labels


def save_labels(labels: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for img_path in sorted(labels):
            f.write(f"{img_path}\t{labels[img_path]}\n")


def normalize(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def main():
    parser = argparse.ArgumentParser(description="Pre-label crops with PaddleOCR")
    parser.add_argument("--crops-dir", required=True)
    parser.add_argument("--output", default="data/ocr_training/labels.txt")
    parser.add_argument("--min-len", type=int, default=4)
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-label crops that already have a label")
    args = parser.parse_args()

    crops_dir = Path(args.crops_dir)
    output_path = Path(args.output)

    print("Initialising PaddleOCR...")
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=True,
                    show_log=False, det_db_thresh=0.3, det_db_box_thresh=0.5)

    labels = load_labels(output_path)
    images = sorted(crops_dir.rglob("*.jpg"))

    to_process = [p for p in images
                  if args.overwrite or str(p) not in labels]

    print(f"Crops: {len(images)}  Already labeled: {len(labels)}  To process: {len(to_process)}")

    saved = skipped = failed = 0
    for i, img_path in enumerate(to_process, 1):
        img = cv2.imread(str(img_path))
        if img is None:
            failed += 1
            continue

        try:
            result = ocr.ocr(img, cls=True)
            texts = []
            if result and result[0]:
                for line in result[0]:
                    if len(line) >= 2:
                        text, conf = line[1]
                        clean = normalize(text)
                        if len(clean) >= args.min_len:
                            texts.append((clean, float(conf)))

            if texts:
                best = max(texts, key=lambda x: x[1])
                labels[str(img_path)] = best[0]
                saved += 1
                print(f"  [{i}/{len(to_process)}] {img_path.name} → {best[0]} ({best[1]:.2f})")
            else:
                labels[str(img_path)] = "__SKIP__"
                skipped += 1
                print(f"  [{i}/{len(to_process)}] {img_path.name} → (no read)")
        except Exception as e:
            print(f"  [{i}/{len(to_process)}] {img_path.name} → ERROR: {e}")
            failed += 1

        # Save every 10 images
        if i % 10 == 0:
            save_labels(labels, output_path)

    save_labels(labels, output_path)

    print(f"\n{'─'*50}")
    print(f"  Pre-labeled : {saved}")
    print(f"  No read     : {skipped}  (marked __SKIP__)")
    print(f"  Errors      : {failed}")
    print(f"  Output      : {output_path}")
    print(f"\n  Review and correct with:")
    print(f"  python scripts/ocr/label_crops.py --crops-dir {crops_dir} --output {output_path} --review")
    print(f"{'─'*50}\n")


if __name__ == "__main__":
    main()
