#!/bin/bash
# Collect training samples from multiple videos
# Usage: ./collect_from_multiple_videos.sh

OUTPUT_DIR="training_data/florida_raw"

echo "=== Florida Plate Sample Collection ==="
echo "Output directory: $OUTPUT_DIR"
echo ""

# Collect from 720p.mp4
if [ -f "720p.mp4" ]; then
    echo "Collecting from 720p.mp4..."
    python3 tools/collect_plate_samples.py 720p.mp4 \
        --output $OUTPUT_DIR \
        --max-samples 200 \
        --skip-frames 10 \
        --min-confidence 0.5 \
        --no-preview
    echo "✓ 720p.mp4 complete"
    echo ""
fi

# Collect from a.mp4
if [ -f "a.mp4" ]; then
    echo "Collecting from a.mp4..."
    python3 tools/collect_plate_samples.py a.mp4 \
        --output $OUTPUT_DIR \
        --max-samples 150 \
        --skip-frames 3 \
        --min-confidence 0.5 \
        --no-preview
    echo "✓ a.mp4 complete"
    echo ""
fi

# Add more videos here as needed
# if [ -f "video3.mp4" ]; then
#     echo "Collecting from video3.mp4..."
#     python3 tools/collect_plate_samples.py video3.mp4 \
#         --output $OUTPUT_DIR \
#         --max-samples 100 \
#         --no-preview
# fi

# Count total samples
TOTAL_IMAGES=$(ls $OUTPUT_DIR/images/*.jpg 2>/dev/null | wc -l)
TOTAL_LABELS=$(ls $OUTPUT_DIR/labels/*.txt 2>/dev/null | wc -l)

echo "=== Collection Summary ==="
echo "Total images: $TOTAL_IMAGES"
echo "Total labels: $TOTAL_LABELS"
echo "Output: $OUTPUT_DIR"
echo ""
echo "Next steps:"
echo "  1. python3 tools/prepare_dataset.py $OUTPUT_DIR"
echo "  2. python3 tools/train_plate_detector.py --data datasets/florida_plates/florida_plates.yaml"
