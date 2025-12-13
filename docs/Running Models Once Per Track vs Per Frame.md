# Running Models Once Per Track vs Per Frame

## Overview

The OVR-ALPR system runs heavy models (specifically OCR) **once per track** instead of on every frame. This document explains the implementation, benefits, and configuration of this approach.

---

## Current Implementation

### Yes, the system runs heavy models (OCR) once per track instead of on every frame.

### Track-Based OCR Throttling (pilot.py:126-143)

The system implements intelligent caching and throttling:

- **OCR results are cached per track** (`self.track_ocr_cache`)
- **OCR attempts are counted per track** (`self.track_ocr_attempts`)
- **Each track has a limit of 20 OCR attempts** (`ocr_max_attempts`)
- **OCR only runs when specific conditions are met** (see `should_run_ocr()` at pilot.py:411-437)

### OCR Execution Logic

The system operates at two different levels:

#### Frame-Level Processing
- **Detection models** (YOLO for vehicles and plates) run on **every processed frame** (pilot.py:590-678)
- These are lightweight and needed for continuous tracking

#### Track-Level Processing
- **OCR** (PaddleOCR) runs **selectively based on track state** (pilot.py:711-780)
- This is the expensive operation that gets throttled

---

## What "Once Per Track" Means

Instead of running OCR on **every frame** where a plate is detected (which could be 30-60+ frames for a single vehicle), the system:

1. **Waits for track stability** - minimum 2 frames (`ocr_min_track_frames`)
2. **Runs OCR periodically** - up to 20 attempts per track
3. **Stops when satisfied** - when confidence reaches 0.90 (`ocr_max_confidence_target`)
4. **Caches the best result** - reuses the cached OCR text for visualization

---

## Example Scenario

Here's a concrete example of how this works:

- **Vehicle enters frame** and is tracked as **Track ID 42**
- **Track appears in frames**: 100, 101, 102... 150 (50 frames total)

### Without Throttling ❌
- OCR would run **50 times** (once per frame)

### With Track-Based Throttling ✅
- OCR runs **~10-20 times** (based on conditions)
- Once good result found (conf > 0.90): OCR **stops completely** for that track

---

## Performance Benefits

**OCR is expensive** (~50-200ms per plate on Jetson Orin NX):

### Computation Comparison

**Per-frame approach:**
- 50 frames × 150ms = **7,500ms** (7.5 seconds of compute)

**Per-track approach:**
- 15 attempts × 150ms = **2,250ms** (2.25 seconds of compute)

**Savings: ~70% reduction in OCR computation**

---

## Current Configuration

From pilot.py:139-143:

```python
self.ocr_min_track_frames = 2      # Wait 2 frames before first OCR
self.ocr_min_confidence = 0.70     # Accept results above 70%
self.ocr_max_confidence_target = 0.90  # Stop at 90% confidence
self.ocr_max_attempts = 20         # Max 20 tries per track
```

### Configuration Parameters Explained

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `ocr_min_track_frames` | 2 | Minimum frames before running first OCR (ensures stable track) |
| `ocr_min_confidence` | 0.70 | Minimum confidence to accept a result (70%) |
| `ocr_max_confidence_target` | 0.90 | Target confidence to stop trying (90%) |
| `ocr_max_attempts` | 20 | Maximum OCR attempts per track |

---

## Why This Matters

The architecture separates model execution based on computational cost:

### Lightweight Models (YOLO Detection)
- **Run every frame** for tracking continuity
- Fast enough (~10-30ms) to maintain real-time performance
- Essential for maintaining track associations

### Heavy Models (PaddleOCR)
- **Run selectively per track** to save resources
- Expensive (~50-200ms) so must be throttled
- Only need one good read per vehicle

### Gate Control Scenario
- Optimized to get **one good read per vehicle**
- Avoids running OCR hundreds of times for the same plate
- Balances accuracy and real-time performance on Jetson Orin NX

---

## Key Code References

### Track OCR Decision Logic (pilot.py:411-437)

```python
def should_run_ocr(self, track_id):
    """
    Determine if OCR should be run for this track (gate scenario: continuous improvement)
    """
    # Track stable enough (minimum frames)?
    if self.track_frame_count.get(track_id, 0) < self.ocr_min_track_frames:
        return False

    # Already reached maximum target confidence?
    if track_id in self.track_ocr_cache:
        cached_result = self.track_ocr_cache[track_id]
        if cached_result.confidence >= self.ocr_max_confidence_target:
            return False

    # Check if we've exceeded max attempts
    attempts = self.track_ocr_attempts.get(track_id, 0)
    if attempts >= self.ocr_max_attempts:
        return False

    return True
```

### Track-Based Caching (pilot.py:126-137)

```python
# Track-based OCR throttling and attribute caching
self.track_ocr_cache = {}  # track_id -> PlateDetection
self.track_ocr_attempts = {}  # track_id -> number of OCR attempts
self.track_attributes_cache = {}  # track_id -> {color, make, model}
self.track_frame_count = {}  # track_id -> frame count
self.track_plate_detected = set()  # track_ids that have had plates detected

# Best-shot selection for gate scenario
self.track_best_plate_quality = {}  # track_id -> best quality score
self.track_best_plate_crop = {}  # track_id -> best plate crop image
self.track_best_plate_bbox = {}  # track_id -> best plate bbox
self.track_best_plate_frame = {}  # track_id -> frame number of best shot
```

---

## Summary

The OVR-ALPR system is specifically designed for the Jetson Orin NX to:

1. ✅ **Run lightweight detection models** (YOLO) on every frame for continuous tracking
2. ✅ **Run heavy OCR models** (PaddleOCR) selectively per track (10-20 times instead of 50+)
3. ✅ **Cache and reuse results** to avoid redundant computation
4. ✅ **Stop early** when good results are achieved (90% confidence)
5. ✅ **Balance accuracy and performance** for real-time gate control

This architecture achieves **~70% reduction in OCR computation** while maintaining high accuracy for license plate recognition in gate control scenarios.
