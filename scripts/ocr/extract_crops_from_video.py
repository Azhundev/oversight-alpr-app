"""
Extract plate crops from training videos using the YOLO plate detector.

Runs YOLOv11 on every Nth frame, saves detected plate crops, and
pre-labels them with PaddleOCR. Crops already in labels.txt are skipped.

Usage:
    python scripts/ocr/extract_crops_from_video.py \\
        --videos videos/training/*.MOV \\
        --output data/ocr_training/extracted_crops \\
        --labels data/ocr_training/labels.txt \\
        --frame-step 15

    # Preview without saving
    python scripts/ocr/extract_crops_from_video.py \\
        --videos videos/training/IMG_6941.MOV --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "edge_services"))


# ── Sign fragment filter (same logic as label filter) ─────────────────────────

SIGN_FRAGMENTS = (
    "RESERV", "SUITE", "SULT", "SUII", "SUIT", "UITE", "UIT",
    "ITE", "LITE", "JITE", "EXIT", "ENTR", "PARK", "HAND",
    "VISI", "LOVEN", "ORIDA", "KENDALL", "JERVED", "ESERVED",
    "IESER", "OGDEAT",
)
_SIGN_PATTERNS = [re.compile(r"^TE\d{3}"), re.compile(r"^IE\d{2}")]


def _is_real_plate(text: str) -> bool:
    if not text or text == "__SKIP__":
        return False
    text = re.sub(r"[^A-Z0-9]", "", text.upper())
    if not any(c.isdigit() for c in text):
        return False
    if not any(c.isalpha() for c in text):
        return False
    if not (4 <= len(text) <= 8):
        return False
    for frag in SIGN_FRAGMENTS:
        if frag in text:
            return False
    for pat in _SIGN_PATTERNS:
        if pat.match(text):
            return False
    if sum(c.isdigit() for c in text) < 2:
        return False
    return True


# ── Load existing labels ───────────────────────────────────────────────────────

def _load_labels(labels_path: Path) -> dict:
    """Return {image_path: text} for all existing entries."""
    if not labels_path.exists():
        return {}
    labels = {}
    for line in labels_path.read_text().splitlines():
        if "\t" not in line:
            continue
        path, text = line.split("\t", 1)
        labels[path.strip()] = text.strip()
    return labels


def _append_label(labels_path: Path, image_path: str, text: str):
    with open(labels_path, "a") as f:
        f.write(f"{image_path}\t{text}\n")


# ── PaddleOCR pre-labeler ──────────────────────────────────────────────────────

def _init_paddle():
    try:
        from paddleocr import PaddleOCR
        return PaddleOCR(use_angle_cls=True, lang="en", use_gpu=True, show_log=False)
    except Exception as e:
        print(f"  ⚠  PaddleOCR unavailable: {e}")
        return None


def _paddle_read(paddle, img: np.ndarray) -> tuple:
    """Returns (text, conf) or (None, 0.0)."""
    if paddle is None:
        return None, 0.0
    try:
        result = paddle.ocr(img, cls=True)
        if not result or not result[0]:
            return None, 0.0
        lines = [(t, float(c)) for _, (t, c) in result[0]]
        lines.sort(key=lambda x: -x[1])
        text = re.sub(r"[^A-Z0-9]", "", lines[0][0].upper()) if lines else ""
        conf = lines[0][1] if lines else 0.0
        return (text, conf) if text else (None, 0.0)
    except Exception:
        return None, 0.0


# ── Main extraction ───────────────────────────────────────────────────────────

def extract(args):
    out_dir = Path(args.output)
    labels_path = Path(args.labels)

    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    # Load YOLO plate detector
    print("Loading YOLO plate detector...")
    from detector.detector_service import YOLOv11Detector
    detector = YOLOv11Detector(
        vehicle_model_path="yolo11n.pt",
        plate_model_path="models/yolo11n-plate.pt",
        use_tensorrt=False,   # avoid TRT rebuild overhead for a one-off script
        use_mlflow=False,
    )
    detector.warmup(iterations=3)
    print("Detector ready.\n")

    # Load PaddleOCR for pre-labeling
    paddle = _init_paddle() if not args.dry_run else None

    # Load existing labels so we don't re-process already-labeled crops
    existing_labels = _load_labels(labels_path)

    total_saved = 0
    total_real  = 0
    total_sign  = 0

    for video_path in args.videos:
        video_path = Path(video_path)
        if not video_path.exists():
            print(f"  ⚠  Not found: {video_path}")
            continue

        cap = cv2.VideoCapture(str(video_path))
        fps       = cap.get(cv2.CAP_PROP_FPS) or 30
        n_frames  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_stem = video_path.stem

        print(f"Video: {video_path.name}  ({n_frames} frames @ {fps:.0f}fps)")

        frame_idx  = 0
        saved_this = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % args.frame_step != 0:
                frame_idx += 1
                continue

            # Run plate detector — returns Dict[int, List[BoundingBox]]
            try:
                plate_detections = detector.detect_plates(
                    frame, confidence_threshold=args.min_det_conf
                )
            except Exception:
                frame_idx += 1
                continue

            for veh_idx, plate_list in plate_detections.items():
                for box_idx, bbox in enumerate(plate_list):
                    x1, y1, x2, y2 = (
                        int(bbox.x1), int(bbox.y1),
                        int(bbox.x2), int(bbox.y2),
                    )

                    # Clamp to frame
                    h, w = frame.shape[:2]
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    if x2 <= x1 or y2 <= y1:
                        continue

                    # Reject tiny crops
                    cw, ch = x2 - x1, y2 - y1
                    if cw < 40 or ch < 12:
                        continue

                    crop = frame[y1:y2, x1:x2]

                    # Build filename
                    fname = f"{video_stem}__f{frame_idx:06d}__p{veh_idx:02d}_{box_idx:02d}.jpg"
                    out_path = out_dir / fname
                    label_key = str(out_path)

                    if label_key in existing_labels:
                        continue  # already labeled

                    if args.dry_run:
                        print(f"  [dry] {fname}  size={cw}x{ch}")
                        total_saved += 1
                        continue

                    # Pre-label with PaddleOCR
                    text, ocr_conf = _paddle_read(paddle, crop)

                    if text and _is_real_plate(text):
                        label = text
                        total_real += 1
                        marker = "plate"
                    elif text:
                        label = "__SKIP__"
                        total_sign += 1
                        marker = "sign"
                    else:
                        label = "__SKIP__"
                        total_sign += 1
                        marker = "no-read"

                    cv2.imwrite(str(out_path), crop)
                    _append_label(labels_path, label_key, label)
                    existing_labels[label_key] = label
                    saved_this += 1
                    total_saved += 1

                    if not args.quiet:
                        print(f"  [{marker}] {fname}  ocr={text or '-':10s}  size={cw}x{ch}")

            frame_idx += 1

            if frame_idx % (args.frame_step * 50) == 0:
                pct = frame_idx / n_frames * 100
                print(f"  ... {frame_idx}/{n_frames} frames ({pct:.0f}%)  "
                      f"saved so far: {saved_this}")

        cap.release()
        print(f"  Done: {saved_this} crops from {video_path.name}\n")

    print("─" * 60)
    if args.dry_run:
        print(f"Dry run — would save ~{total_saved} crops")
    else:
        print(f"Saved : {total_saved} crops → {out_dir}")
        print(f"  Real plates  : {total_real}")
        print(f"  Signs/no-read: {total_sign}")
        print()
        print("Next steps:")
        print(f"  Review plates: python scripts/ocr/label_crops.py "
              f"--crops-dir {out_dir} --output {labels_path} --review")
        print(f"  Train model:   python scripts/ocr/train_crnn.py "
              f"--labels {labels_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract plate crops from training videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--videos", nargs="+", required=True,
        help="Video files to process (supports glob patterns)",
    )
    parser.add_argument(
        "--output", default="data/ocr_training/extracted_crops",
        help="Directory to save crops (default: data/ocr_training/extracted_crops)",
    )
    parser.add_argument(
        "--labels", default="data/ocr_training/labels.txt",
        help="Labels file to append to (default: data/ocr_training/labels.txt)",
    )
    parser.add_argument(
        "--frame-step", type=int, default=15,
        help="Process every Nth frame (default: 15 = 2 fps from 30fps video)",
    )
    parser.add_argument(
        "--min-det-conf", type=float, default=0.40,
        help="Minimum YOLO detection confidence to keep a crop (default: 0.40)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count detections without saving anything",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Only print sign/plate lines on plates (suppress sign output)",
    )
    args = parser.parse_args()

    # Expand any glob patterns in video paths
    import glob
    expanded = []
    for pattern in args.videos:
        matches = glob.glob(pattern)
        expanded.extend(matches if matches else [pattern])
    args.videos = expanded

    extract(args)


if __name__ == "__main__":
    main()
