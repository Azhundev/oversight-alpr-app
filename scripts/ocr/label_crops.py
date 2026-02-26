"""
Interactive plate crop labeling tool.

Displays each unlabeled crop in a window. Type the plate text directly
in the window using the keyboard, then press Enter to save.

Usage:
    python scripts/ocr/label_crops.py
    python scripts/ocr/label_crops.py --crops-dir output/crops --output labels.txt
    python scripts/ocr/label_crops.py --redo          # re-label already-labeled crops too
    python scripts/ocr/label_crops.py --review        # review existing labels (edit mistakes)

Controls:
    A–Z, 0–9    Type plate characters (all letters including S and Q are safe to type)
    Backspace   Delete last character
    Enter       Save label and advance
    Escape      Skip this crop (mark as unreadable)
    Ctrl+Q      Quit and save progress
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# ── Constants ────────────────────────────────────────────────────────────────

VALID_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
SKIP_LABEL = "__SKIP__"

UI_HEIGHT = 140       # pixels below the plate image for the input panel
MIN_DISPLAY_W = 520   # minimum window width
PLATE_DISPLAY_H = 200 # plate crop is scaled to this height for display

COLOR_BG        = (30, 30, 30)
COLOR_PANEL     = (50, 50, 50)
COLOR_TEXT      = (220, 220, 220)
COLOR_INPUT     = (255, 255, 255)
COLOR_HINT      = (130, 130, 130)
COLOR_PROGRESS  = (100, 200, 100)
COLOR_SAVED     = (80, 180, 80)
COLOR_SKIP      = (180, 120, 60)
COLOR_CURSOR    = (80, 200, 255)


# ── Label file helpers ────────────────────────────────────────────────────────

def load_labels(path: Path) -> dict:
    """Return {image_path_str: label_text} from a tab-separated labels file."""
    labels = {}
    if not path.exists():
        return labels
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if "\t" in line:
                img_path, text = line.split("\t", 1)
                labels[img_path] = text
    return labels


def save_labels(labels: dict, path: Path):
    """Write labels dict to file, sorted by image path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for img_path in sorted(labels):
            f.write(f"{img_path}\t{labels[img_path]}\n")


# ── Display helpers ───────────────────────────────────────────────────────────

def build_display(plate_img: np.ndarray, typed: str, index: int, total: int,
                  filename: str, last_saved: str) -> np.ndarray:
    """
    Compose the labeling UI frame:
      - top:    plate crop scaled to PLATE_DISPLAY_H
      - bottom: input panel (typed text, progress, instructions)
    """
    # Scale plate crop to display height, keep aspect ratio
    h, w = plate_img.shape[:2]
    scale = PLATE_DISPLAY_H / h
    new_w = max(int(w * scale), MIN_DISPLAY_W)
    plate_scaled = cv2.resize(plate_img, (new_w, PLATE_DISPLAY_H), interpolation=cv2.INTER_CUBIC)

    win_w = max(new_w, MIN_DISPLAY_W)

    # Plate area with dark background
    plate_canvas = np.full((PLATE_DISPLAY_H, win_w, 3), COLOR_BG, dtype=np.uint8)
    x_off = (win_w - new_w) // 2
    plate_canvas[:, x_off:x_off + new_w] = plate_scaled

    # Input panel
    panel = np.full((UI_HEIGHT, win_w, 3), COLOR_PANEL, dtype=np.uint8)

    # Filename (top-left of panel)
    cv2.putText(panel, filename, (12, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_HINT, 1, cv2.LINE_AA)

    # Progress (top-right of panel)
    progress_str = f"{index}/{total}"
    (pw, _), _ = cv2.getTextSize(progress_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.putText(panel, progress_str, (win_w - pw - 12, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_PROGRESS, 1, cv2.LINE_AA)

    # Typed text + blinking cursor
    display_text = typed + "_"
    cv2.putText(panel, display_text, (12, 72),
                cv2.FONT_HERSHEY_DUPLEX, 1.6, COLOR_INPUT, 2, cv2.LINE_AA)

    # Last saved hint
    if last_saved:
        saved_str = f"saved: {last_saved}"
        cv2.putText(panel, saved_str, (12, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_SAVED, 1, cv2.LINE_AA)

    # Key hints
    hints = "Enter=save   Esc=skip   Backspace=delete   Ctrl+Q=quit"
    cv2.putText(panel, hints, (12, UI_HEIGHT - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, COLOR_HINT, 1, cv2.LINE_AA)

    return np.vstack([plate_canvas, panel])


# ── Core labeling loop ────────────────────────────────────────────────────────

def run_labeler(crops_dir: Path, output_path: Path, redo: bool, review: bool):
    # Collect all crop images
    all_images = sorted(crops_dir.rglob("*.jpg"))
    if not all_images:
        print(f"No .jpg files found under {crops_dir}")
        sys.exit(1)

    labels = load_labels(output_path)

    if review:
        # Only show already-labeled images (for correcting mistakes)
        queue = [p for p in all_images if str(p) in labels and labels[str(p)] != SKIP_LABEL]
        mode_label = "REVIEW"
    elif redo:
        queue = list(all_images)
        mode_label = "REDO ALL"
    else:
        # Skip already-labeled (including skipped ones)
        queue = [p for p in all_images if str(p) not in labels]
        mode_label = "LABEL NEW"

    total = len(queue)
    already_done = len(labels) - sum(1 for v in labels.values() if v == SKIP_LABEL)
    skipped_count = sum(1 for v in labels.values() if v == SKIP_LABEL)

    print(f"\n{'─' * 50}")
    print(f"  Mode          : {mode_label}")
    print(f"  Crops found   : {len(all_images)}")
    print(f"  Already labeled: {already_done}  (skipped: {skipped_count})")
    print(f"  To process    : {total}")
    print(f"  Output file   : {output_path}")
    print(f"{'─' * 50}")
    print("  Controls: type plate text → Enter to save, Esc to skip, Ctrl+Q to quit")
    print(f"{'─' * 50}\n")

    if total == 0:
        print("Nothing to label. Use --redo to re-label all crops.")
        sys.exit(0)

    cv2.namedWindow("Plate Labeler", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Plate Labeler", MIN_DISPLAY_W, PLATE_DISPLAY_H + UI_HEIGHT)

    typed = ""
    last_saved = labels.get(str(queue[0]), "") if review else ""
    if review and queue:
        typed = last_saved if last_saved != SKIP_LABEL else ""

    saved_this_session = 0
    skipped_this_session = 0
    i = 0

    while i < total:
        img_path = queue[i]
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"  ⚠ Cannot read {img_path}, skipping.")
            i += 1
            continue

        if review:
            existing = labels.get(str(img_path), "")
            typed = existing if existing != SKIP_LABEL else ""
        # (for new labeling, typed already set to "" or carries over from loop)

        while True:
            frame = build_display(img, typed, i + 1, total, img_path.name, last_saved)
            cv2.imshow("Plate Labeler", frame)
            key = cv2.waitKey(50) & 0xFF  # 50ms poll so cursor blink feels responsive

            if key == 255:
                # No key pressed this tick — just refresh display
                continue

            if key in (13, 10):  # Enter
                if typed:
                    labels[str(img_path)] = typed.upper()
                    save_labels(labels, output_path)
                    last_saved = typed.upper()
                    saved_this_session += 1
                    typed = ""
                    i += 1
                    break
                # Enter with no text — same as skip
                labels[str(img_path)] = SKIP_LABEL
                save_labels(labels, output_path)
                last_saved = ""
                skipped_this_session += 1
                typed = ""
                i += 1
                break

            elif key == 27:  # Escape — skip unreadable crop
                labels[str(img_path)] = SKIP_LABEL
                save_labels(labels, output_path)
                last_saved = ""
                skipped_this_session += 1
                typed = ""
                i += 1
                break

            elif key == 17:  # Ctrl+Q — quit
                cv2.destroyAllWindows()
                _print_summary(saved_this_session, skipped_this_session, output_path, labels)
                return

            elif key in (8, 127):  # Backspace / Delete
                typed = typed[:-1]

            elif key in (ord('['),):  # Go back one image
                if i > 0:
                    i -= 1
                    typed = ""
                    break

            else:
                char = chr(key).upper() if 32 <= key <= 126 else None
                if char and char in VALID_CHARS and len(typed) < 10:
                    typed += char

    cv2.destroyAllWindows()
    _print_summary(saved_this_session, skipped_this_session, output_path, labels)


def _print_summary(saved: int, skipped: int, output_path: Path, labels: dict):
    real_labels = {k: v for k, v in labels.items() if v != SKIP_LABEL}
    print(f"\n{'─' * 50}")
    print(f"  Session: saved={saved}  skipped={skipped}")
    print(f"  Total labeled in file: {len(real_labels)}")
    print(f"  Output: {output_path}")
    print(f"{'─' * 50}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Interactive plate crop labeling tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--crops-dir", default="output/crops",
        help="Root directory containing plate crop images (default: output/crops)",
    )
    parser.add_argument(
        "--output", default="data/ocr_training/labels.txt",
        help="Output labels file (default: data/ocr_training/labels.txt)",
    )
    parser.add_argument(
        "--redo", action="store_true",
        help="Re-label all crops, including already-labeled ones",
    )
    parser.add_argument(
        "--review", action="store_true",
        help="Review and correct existing labels (shows already-labeled crops)",
    )
    args = parser.parse_args()

    crops_dir = Path(args.crops_dir)
    if not crops_dir.exists():
        print(f"Error: crops directory not found: {crops_dir}")
        sys.exit(1)

    run_labeler(
        crops_dir=crops_dir,
        output_path=Path(args.output),
        redo=args.redo,
        review=args.review,
    )


if __name__ == "__main__":
    main()
