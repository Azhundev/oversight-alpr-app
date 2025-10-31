#!/bin/bash
# Setup Manual Labeling Environment for License Plate Detection
# This script sets up LabelImg for annotating license plates

set -e

echo "=========================================="
echo "Manual Labeling Setup for Plate Detection"
echo "=========================================="
echo ""

# Check if labelImg is already installed
if command -v labelImg &> /dev/null; then
    echo "✓ LabelImg is already installed"
else
    echo "Installing LabelImg..."
    pip3 install labelImg
    echo "✓ LabelImg installed successfully"
fi

# Create directories for manual labeling
LABEL_DIR="datasets/plate_manual"
mkdir -p "$LABEL_DIR/images"
mkdir -p "$LABEL_DIR/labels"

echo ""
echo "✓ Created manual labeling directories:"
echo "  - $LABEL_DIR/images/"
echo "  - $LABEL_DIR/labels/"

# Create predefined classes file
cat > "$LABEL_DIR/classes.txt" <<EOF
plate
EOF

echo ""
echo "✓ Created classes.txt with 'plate' class"

# Copy frames from videos to labeling directory
echo ""
echo "Extracting frames from videos for manual labeling..."
python3 - <<'PYTHON_SCRIPT'
import cv2
from pathlib import Path
from tqdm import tqdm

video_dir = Path("videos/training")
output_dir = Path("datasets/plate_manual/images")

# Find all videos
videos = list(video_dir.glob("*.MOV")) + list(video_dir.glob("*.mov")) + \
         list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.MP4"))

print(f"Found {len(videos)} videos")

frame_count = 0
fps_extract = 2.0  # Extract 2 frames per second

for video_path in videos:
    print(f"\nProcessing: {video_path.name}")
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        print(f"  Failed to open {video_path.name}")
        continue

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(video_fps / fps_extract)
    video_name = video_path.stem

    frame_idx = 0
    extracted = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            output_path = output_dir / f"{video_name}_frame_{frame_idx:06d}.jpg"
            cv2.imwrite(str(output_path), frame)
            extracted += 1
            frame_count += 1

        frame_idx += 1

    cap.release()
    print(f"  Extracted {extracted} frames")

print(f"\nTotal frames extracted: {frame_count}")
PYTHON_SCRIPT

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To start labeling:"
echo "  1. Run: labelImg datasets/plate_manual/images datasets/plate_manual/classes.txt"
echo "  2. Click 'Open Dir' and select: datasets/plate_manual/images"
echo "  3. Click 'Change Save Dir' and select: datasets/plate_manual/labels"
echo "  4. In LabelImg:"
echo "     - Press 'W' to draw a bounding box around each plate"
echo "     - Select 'plate' as the class"
echo "     - Press 'Ctrl+S' to save"
echo "     - Press 'D' to go to next image"
echo ""
echo "Alternative: Use the GUI launcher script:"
echo "  ./scripts/start_labeling.sh"
echo ""
