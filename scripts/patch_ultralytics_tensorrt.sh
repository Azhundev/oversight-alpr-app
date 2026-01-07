#!/bin/bash
# Patch Ultralytics 8.3.65 to fix TensorRT engine serialization bug
# This fixes the "kPLAN_MAGIC_TAG failed" error

EXPORTER_FILE="/usr/local/lib/python3.10/dist-packages/ultralytics/engine/exporter.py"

echo "=== Ultralytics TensorRT Patch ==="
echo "Fixing metadata serialization bug in $EXPORTER_FILE"
echo ""

# Backup the original file
if [ ! -f "${EXPORTER_FILE}.backup" ]; then
    echo "Creating backup: ${EXPORTER_FILE}.backup"
    sudo cp "$EXPORTER_FILE" "${EXPORTER_FILE}.backup"
else
    echo "Backup already exists: ${EXPORTER_FILE}.backup"
fi

# Apply the patch - comment out lines 943-945
echo "Applying patch to lines 943-945..."
sudo sed -i '943s/^/            # PATCHED: /' "$EXPORTER_FILE"
sudo sed -i '944s/^/            # PATCHED: /' "$EXPORTER_FILE"
sudo sed -i '945s/^/            # PATCHED: /' "$EXPORTER_FILE"

# Verify the patch
echo ""
echo "Verifying patch (lines 940-950):"
sed -n '940,950p' "$EXPORTER_FILE"

echo ""
echo "✓ Patch applied successfully!"
echo ""
echo "The TensorRT engines will now be created without metadata corruption."
echo "To revert: sudo cp ${EXPORTER_FILE}.backup $EXPORTER_FILE"
