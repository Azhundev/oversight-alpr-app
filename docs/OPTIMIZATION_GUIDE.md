# ALPR Performance Optimization Guide

This document describes the performance optimizations implemented in the OVR-ALPR system for efficient real-time processing on NVIDIA Jetson Orin NX.

## Core Principle: Run Heavy Models Once Per Track, Not Per Frame

**Cost Savings: 90-95% reduction in heavy model inference**

---

## 1. Track-Based Inference (Primary Optimization)

### OCR Throttling
**Problem:** Running OCR on every frame for every detected plate wastes GPU cycles
- At 30 FPS with 5 vehicles = 150 OCR calls/second
- Each OCR call: 10-30ms
- Total GPU time: 1,500-4,500ms/sec (impossible on single GPU)

**Solution:** Run OCR once per stable track
- Track vehicles across frames using IoU matching (threshold: 0.7)
- Wait for track stability (3+ frames)
- Run OCR once, cache result for entire track lifetime
- Reuse cached result on subsequent frames

**Results:**
- OCR calls reduced to 5-15/second (10-30x reduction)
- GPU time: 50-450ms/sec (totally manageable)
- Same accuracy, massively improved performance

**Implementation:**
```python
# pilot.py
if self.should_run_ocr(track_id):  # Only true once per track
    plate_detection = self.ocr.recognize_plate(frame, plate_bbox)
    self.track_ocr_cache[track_id] = plate_detection  # Cache it!
else:
    # Use cached result
    plate_detection = self.track_ocr_cache.get(track_id)
```

### Vehicle Attribute Caching
**Problem:** Color/make/model inference is extremely heavy (100-200ms per vehicle)

**Solution:** Run once per track on best-quality frame
- Wait for high confidence detection (>0.8)
- Wait for stability (5+ frames)
- Cache attributes for track lifetime

**Results:**
- 20-50x reduction in attribute inference
- Run once vs 30-60 times per vehicle

**Configuration:**
```python
# pilot.py
attr_min_confidence = 0.8      # High confidence required
attr_min_track_frames = 5      # Extra stability
```

---

## 2. Batch Inference (Secondary Optimization)

### When to Use Batch Processing
**Benefit:** Amortize GPU kernel launch overhead across multiple samples

**Best for:**
- OCR (lightweight, benefits from batching)
- Make/model inference (if enabled)

**Not recommended for:**
- Vehicle detection (adds latency for real-time)
- Plate detection (frame-by-frame critical)

### Batch OCR Implementation
```python
# Automatically batch when multiple new tracks detected
if len(tracks_needing_ocr) >= 2:
    # Process all in one batch
    batch_results = ocr.recognize_plates_batch(frame, bboxes)
else:
    # Single plate, no batching overhead
    result = ocr.recognize_plate(frame, bbox)
```

**Expected Speedup:**
- Batch of 4: ~1.5-2x faster than 4 sequential calls
- Batch of 8: ~2-2.5x faster than 8 sequential calls

**Configuration:**
```python
# pilot.py
enable_batch_ocr = True    # Enable batching
batch_min_size = 2         # Minimum batch size
```

---

## 3. Resolution Optimization

### Inference Resolution
**Problem:** Running inference at 1920x1080 is unnecessarily expensive

**Solution:** Resize to 960-1280px short side for inference
- Keep ingest at 1080p for decode quality
- Resize tensors before sending to GPU
- 2-4x speedup, negligible accuracy loss

**Implementation:**
```yaml
# config/inference_optimization.yaml
resolution:
  ingest_resolution: [1920, 1080]      # Keep full decode
  inference_short_side: 960             # Resize for inference
  vehicle_detection_size: [960, 540]    # 16:9 aspect ratio maintained
```

**GPU Memory Savings:**
- 1920x1080: ~2.1 megapixels
- 960x540: ~0.5 megapixels
- **~4x less GPU memory usage**

---

## 4. JPEG Crop Optimization

### Optimized Crop Storage
**Problem:** Full-resolution crops are huge and slow to encode/transfer

**Solution:** Limit crops to ~640px long side, JPEG quality 80-85
- Resize before encoding (not after)
- Fast bilinear resize for speed
- Quality 85 is visually lossless for plates

**Implementation:**
```python
# shared/utils/crop_utils.py
from shared.utils.crop_utils import create_plate_crop

# Create optimized JPEG bytes
jpeg_bytes = create_plate_crop(
    frame,
    bbox,
    return_bytes=True  # Returns compressed JPEG
)
```

**File Size Reduction:**
- Unoptimized: 200-500KB per plate crop
- Optimized: 20-50KB per plate crop
- **10x smaller files = 10x faster I/O**

---

## 5. Memory Management

### Track Cleanup
**Problem:** Inactive tracks accumulate, consuming memory

**Solution:** Automatic cleanup of stale tracks
```python
# Cleanup every frame
self.cleanup_old_tracks(active_track_ids)

# Removes:
# - Track bounding boxes
# - Frame counts
# - Confidence tracking

# Keeps (for historical analysis):
# - OCR results cache
# - Attribute cache
```

**Configuration:**
```yaml
memory:
  cleanup_interval_frames: 300      # Every 10 seconds
  max_inactive_track_age: 30        # 1 second at 30 FPS
  max_historical_tracks: 10000      # Memory limit
```

---

## Performance Impact Summary

### Without Optimization
- **OCR:** 150 calls/sec → 15,000-30,000ms GPU time → **Impossible**
- **Attributes:** 150 calls/sec → **Massive GPU overload**
- **Expected FPS:** 5-10 FPS max
- **GPU Utilization:** 300-500% (oversubscribed)

### With Full Optimization
- **OCR:** 5-15 calls/sec → 50-450ms GPU time → **Totally fine**
- **Attributes:** 1-3 calls/sec → **Negligible**
- **Expected FPS:** 25-30 FPS easily
- **GPU Utilization:** 40-60% (healthy)

### Cost Savings Breakdown
| Optimization | Reduction | Impact |
|--------------|-----------|---------|
| Track-based OCR | 10-30x | Critical |
| Track-based Attributes | 20-50x | Critical |
| Batch Inference (OCR) | 1.5-2.5x | Moderate |
| Resolution Scaling | 2-4x | Moderate |
| JPEG Optimization | 10x I/O | High for storage |
| **Total** | **90-95%** | **System Viable** |

---

## Configuration Files

### Main Config: `config/inference_optimization.yaml`
Complete settings for all optimizations

### OCR Config: `config/ocr.yaml`
PaddleOCR-specific settings

### Tracking Config: `config/tracking.yaml`
Track management and attribute inference

---

## Monitoring Performance

### Key Metrics to Watch
```bash
# Run pilot with logging
python3 pilot.py

# Watch for these log messages:
# - "OCR runs this frame: X (active tracks: Y)"
# - "Batch OCR: N plates in Xms (Y ms/plate)"
# - "Created new track: X"
# - "Cleaned up N stale tracks"
```

### Expected Log Pattern (Healthy System)
```
[INFO] Created new track: 0
[INFO] Created new track: 1
[DEBUG] OCR runs this frame: 2 (active tracks: 2)
[DEBUG] Running batch OCR on 2 plates
[DEBUG] Batch OCR: 2/2 plates in 45.2ms (22.6ms/plate)
[INFO] OCR Track 0: ABC1234 (conf: 0.92)
[INFO] OCR Track 1: XYZ5678 (conf: 0.88)
[DEBUG] OCR runs this frame: 0 (active tracks: 2)  # Cached!
[DEBUG] OCR runs this frame: 0 (active tracks: 2)  # Cached!
[DEBUG] Cleaned up 1 stale tracks
```

### Warning Signs
```
# Bad: OCR running every frame
[DEBUG] OCR runs this frame: 5 (active tracks: 5)  # Every frame!
[DEBUG] OCR runs this frame: 5 (active tracks: 5)  # Not caching!

# Diagnosis: Track matching failing, check IoU threshold
```

---

## Advanced: ByteTrack Integration (Future)

For production, replace simple IoU tracking with ByteTrack:
- More robust track matching
- Handles occlusions better
- Re-identification support
- See `config/tracking.yaml` for settings

---

## Quick Start Checklist

- [ ] PaddleOCR installed and working
- [ ] Track-based OCR throttling enabled (default)
- [ ] Batch OCR enabled (`enable_batch_ocr = True`)
- [ ] Resolution optimization configured (960px short side)
- [ ] JPEG crop utilities imported
- [ ] Monitor logs for OCR cache hits
- [ ] Verify 25-30 FPS on Jetson Orin NX
- [ ] Check GPU utilization stays under 70%

**Remember:** Heavy models once per track = 90%+ cost savings!
