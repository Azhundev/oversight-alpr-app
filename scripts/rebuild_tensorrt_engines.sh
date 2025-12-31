#!/bin/bash
# TensorRT Engine Rebuild Script
# Use this if engines need to be manually rebuilt after system updates

set -e

echo "============================================"
echo "TensorRT Engine Rebuild Script"
echo "============================================"
echo ""

# Get TensorRT version
TRT_VERSION=$(python3 -c "import tensorrt as trt; print(trt.__version__)")
echo "Current TensorRT version: $TRT_VERSION"
echo ""

# Check if engines exist
if [ -f "models/yolo11n.engine" ]; then
    echo "Found existing vehicle detection engine"
    if [ -f "models/yolo11n.engine.version" ]; then
        echo "  Version file exists:"
        cat models/yolo11n.engine.version | grep tensorrt_version
    fi
fi

if [ -f "models/yolo11n-plate.engine" ]; then
    echo "Found existing plate detection engine"
    if [ -f "models/yolo11n-plate.engine.version" ]; then
        echo "  Version file exists:"
        cat models/yolo11n-plate.engine.version | grep tensorrt_version
    fi
fi
echo ""

# Ask for confirmation
read -p "Do you want to rebuild TensorRT engines? This will take ~15-20 minutes. (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rebuild cancelled."
    exit 0
fi

echo ""
echo "Step 1/3: Removing old engines..."
rm -f models/yolo11n.engine models/yolo11n.engine.version
rm -f models/yolo11n-plate.engine models/yolo11n-plate.engine.version
echo "  ✓ Old engines removed"

echo ""
echo "Step 2/3: Rebuilding vehicle detection engine (7-10 minutes)..."
yolo export model=models/yolo11n.pt format=engine device=0 half=True batch=1 workspace=1 imgsz=640
echo "  ✓ Vehicle engine rebuilt"

echo ""
echo "Step 3/3: Rebuilding plate detection engine (7-10 minutes)..."
yolo export model=models/yolo11n-plate.pt format=engine device=0 half=True batch=1 workspace=1 imgsz=640
echo "  ✓ Plate engine rebuilt"

echo ""
echo "Creating version files..."
python3 <<'EOF'
import json
import tensorrt as trt
import torch
import time

version_info = {
    'tensorrt_version': trt.__version__,
    'cuda_version': torch.version.cuda,
    'torch_version': torch.__version__,
    'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
}

for engine in ['models/yolo11n.engine', 'models/yolo11n-plate.engine']:
    version_file = engine + '.version'
    with open(version_file, 'w') as f:
        json.dump(version_info, f, indent=2)
    print(f"  ✓ Created: {version_file}")
EOF

echo ""
echo "============================================"
echo "✅ Rebuild complete!"
echo "============================================"
echo ""
echo "Engine files:"
ls -lh models/*.engine
echo ""
echo "Version files:"
ls -lh models/*.engine.version
echo ""
echo "You can now run pilot.py"
