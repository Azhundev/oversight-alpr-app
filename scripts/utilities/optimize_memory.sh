#!/bin/bash
# Memory optimization script for Jetson Orin NX
# Helps prevent TensorRT "out of memory" errors

echo "=== Jetson Memory Optimization Script ==="
echo ""

# 1. Show current memory status
echo "Current Memory Status:"
free -h
echo ""

# 2. Clear system caches (requires sudo)
echo "Clearing system caches..."
sudo sync
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
echo "Caches cleared"
echo ""

# 3. Show updated memory
echo "Updated Memory Status:"
free -h
echo ""

# 4. Check for zombie TensorRT processes
echo "Checking for stuck processes..."
ZOMBIE_PROCS=$(ps aux | grep -i tensorrt | grep -v grep | wc -l)
if [ $ZOMBIE_PROCS -gt 0 ]; then
    echo "Found $ZOMBIE_PROCS TensorRT-related processes"
    ps aux | grep -i tensorrt | grep -v grep
else
    echo "No stuck TensorRT processes found"
fi
echo ""

# 5. Show GPU memory
echo "GPU Memory Status:"
nvidia-smi
echo ""

# 6. Recommendations
echo "=== Recommendations ==="
echo "1. If running pilot.py, consider these flags:"
echo "   --skip-frames 2        # Process fewer frames"
echo "   --no-adaptive-sampling # Use fixed frame skip"
echo ""
echo "2. Close unnecessary applications:"
echo "   - Web browsers"
echo "   - Jupyter notebooks not in use"
echo "   - Other GPU applications"
echo ""
echo "3. Increase swap if needed:"
echo "   sudo systemctl restart nvzramconfig"
echo ""
echo "4. Delete old TensorRT engines to force rebuild:"
echo "   rm *.engine models/*.engine"
echo ""
echo "Done!"
