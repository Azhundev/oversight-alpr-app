#!/usr/bin/env python3
"""
Patch Ultralytics 8.3.65 to fix TensorRT engine serialization bug
This fixes the "kPLAN_MAGIC_TAG failed" error
"""
import shutil
from pathlib import Path

EXPORTER_FILE = Path("/usr/local/lib/python3.10/dist-packages/ultralytics/engine/exporter.py")
BACKUP_FILE = EXPORTER_FILE.with_suffix('.py.backup')

print("=== Ultralytics TensorRT Patch ===")
print(f"Fixing metadata serialization bug in {EXPORTER_FILE}")
print()

# Check if we can write
if not EXPORTER_FILE.exists():
    print(f"ERROR: File not found: {EXPORTER_FILE}")
    exit(1)

# Create backup
if not BACKUP_FILE.exists():
    print(f"Creating backup: {BACKUP_FILE}")
    try:
        shutil.copy2(EXPORTER_FILE, BACKUP_FILE)
    except PermissionError:
        print("ERROR: Need sudo permissions. Run with: sudo python3 scripts/patch_ultralytics.py")
        exit(1)
else:
    print(f"Backup already exists: {BACKUP_FILE}")

# Read file
print("Reading file...")
with open(EXPORTER_FILE, 'r') as f:
    lines = f.readlines()

# Apply patch - comment out lines 943-945 (0-indexed: 942-944)
print("Applying patch to lines 943-945...")
if 942 < len(lines) and 'meta = json.dumps' in lines[942]:
    lines[942] = '            # PATCHED: ' + lines[942]
    lines[943] = '            # PATCHED: ' + lines[943]
    lines[944] = '            # PATCHED: ' + lines[944]

    # Write patched file
    print("Writing patched file...")
    try:
        with open(EXPORTER_FILE, 'w') as f:
            f.writelines(lines)
    except PermissionError:
        print("ERROR: Need sudo permissions. Run with: sudo python3 scripts/patch_ultralytics.py")
        exit(1)

    print()
    print("Verifying patch (lines 940-950):")
    for i in range(939, min(950, len(lines))):
        print(f"{i+1:4d}: {lines[i]}", end='')

    print()
    print("✓ Patch applied successfully!")
    print()
    print("The TensorRT engines will now be created without metadata corruption.")
    print(f"To revert: sudo cp {BACKUP_FILE} {EXPORTER_FILE}")
else:
    print("ERROR: Could not find expected code at line 943. File may already be patched or version mismatch.")
    print(f"Line 943 contains: {lines[942] if 942 < len(lines) else 'N/A'}")
