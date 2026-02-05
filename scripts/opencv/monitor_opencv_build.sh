#!/bin/bash
# Monitor OpenCV build progress

LOG_FILE="opencv_build.log"

echo "========================================="
echo "OpenCV Build Progress Monitor"
echo "========================================="
echo ""

# Check if build is running
if ! pgrep -f "build_opencv_gstreamer.sh" > /dev/null; then
    echo "⚠️  Build process not running"
    echo ""
    echo "Last 20 lines of log:"
    tail -20 $LOG_FILE
    exit 1
fi

echo "✅ Build process is running"
echo ""

# Check current stage
if grep -q "Building OpenCV" $LOG_FILE; then
    echo "Current Stage: 🔨 Compiling (this takes 2-3 hours)"

    # Try to estimate progress from build output
    if grep -q "\[.*%\]" $LOG_FILE; then
        LAST_PERCENT=$(grep -oP '\[\s*\K[0-9]+(?=%\])' $LOG_FILE | tail -1)
        echo "Progress: ${LAST_PERCENT}%"

        # Estimate time remaining (rough estimate)
        if [ "$LAST_PERCENT" -gt 0 ]; then
            ELAPSED_MIN=$(( ($(date +%s) - $(stat -c %Y $LOG_FILE)) / 60 ))
            TOTAL_MIN=$(( $ELAPSED_MIN * 100 / $LAST_PERCENT ))
            REMAINING_MIN=$(( $TOTAL_MIN - $ELAPSED_MIN ))
            echo "Estimated time remaining: ~${REMAINING_MIN} minutes"
        fi
    else
        echo "Progress: Starting compilation..."
    fi
elif grep -q "Configuring OpenCV" $LOG_FILE; then
    echo "Current Stage: ⚙️  Configuring build"
elif grep -q "Downloading OpenCV" $LOG_FILE; then
    echo "Current Stage: ⬇️  Downloading source code"
else
    echo "Current Stage: 🚀 Initializing"
fi

echo ""
echo "Key Configuration:"
grep -E "GStreamer:|CUDA:|Video I/O" $LOG_FILE | head -10 || echo "  (configuration not yet logged)"

echo ""
echo "Recent activity (last 10 lines):"
tail -10 $LOG_FILE

echo ""
echo "========================================="
echo "Monitor commands:"
echo "  Watch full log:     tail -f opencv_build.log"
echo "  Check build errors: grep -i error opencv_build.log"
echo "  Run this monitor:   bash scripts/monitor_opencv_build.sh"
echo "========================================="
