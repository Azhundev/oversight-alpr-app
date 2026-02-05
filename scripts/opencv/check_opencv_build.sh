#!/bin/bash
# Quick OpenCV build status checker

LOG_FILE="$HOME/OVR-ALPR/opencv_compile.log"
BUILD_DIR="$HOME/opencv_build/opencv-4.6.0/build"

echo "========================================="
echo "OpenCV Build Status"
echo "========================================="
echo ""

# Check if build process is running
if pgrep -f "make.*opencv" > /dev/null; then
    echo "Status: ✅ BUILDING"

    # Get latest percentage
    if [ -f "$LOG_FILE" ]; then
        PERCENT=$(grep -oP '\[\s*\K[0-9]+(?=%\])' "$LOG_FILE" | tail -1)
        if [ -n "$PERCENT" ]; then
            echo "Progress: ${PERCENT}%"

            # Calculate bars
            BARS=$((PERCENT / 2))
            printf "["
            for i in $(seq 1 50); do
                if [ $i -le $BARS ]; then
                    printf "="
                else
                    printf " "
                fi
            done
            printf "]\n"

            # Estimate time (very rough - assumes ~2.5 hours total)
            if [ "$PERCENT" -gt 5 ]; then
                REMAINING_MIN=$(( (100 - PERCENT) * 150 / 100 ))
                HOURS=$((REMAINING_MIN / 60))
                MINS=$((REMAINING_MIN % 60))
                echo "Est. remaining: ~${HOURS}h ${MINS}m"
            fi
        else
            echo "Progress: Starting..."
        fi

        echo ""
        echo "Latest activity:"
        tail -5 "$LOG_FILE"
    fi
else
    echo "Status: ⏸️  NOT RUNNING"

    # Check if completed
    if [ -f "$BUILD_DIR/lib/cv2/python-3.10/cv2.cpython-310-aarch64-linux-gnu.so" ]; then
        echo ""
        echo "✅ Build appears COMPLETE!"
        echo "   Next: Run installation"
    elif [ -f "$LOG_FILE" ]; then
        echo ""
        echo "Last log entries:"
        tail -10 "$LOG_FILE"
    fi
fi

echo ""
echo "========================================="
echo "Commands:"
echo "  Full log:      tail -f ~/OVR-ALPR/opencv_compile.log"
echo "  This status:   bash scripts/check_opencv_build.sh"
echo "========================================="
