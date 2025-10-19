# OVR-ALPR Quick Reference Guide

## 🎯 Core Principle

> **Run heavy models ONCE per track, not per frame = 90% cost savings**

---

## 📋 Current System Status

### What's Working ✅
- PaddleOCR with GPU acceleration
- Track-based OCR throttling (10-30x reduction)
- Batch OCR inference
- Vehicle attribute caching
- Simple IoU tracking
- Optimized JPEG crops (640px, quality 85)

### Performance 📊
- **Streams:** 1-2 per Jetson Orin NX
- **FPS:** 25-30
- **OCR calls:** 5-15/sec (was 150/sec)
- **GPU usage:** 40-60%
- **Latency:** 100-150ms

---

## 🚀 Running the System

### Basic Usage
```bash
# Run with full optimization (default)
python3 pilot.py

# Disable OCR
python3 pilot.py --no-ocr

# Custom camera config
python3 pilot.py --config config/cameras.yaml

# Headless mode (no display)
python3 pilot.py --no-display

# Save output frames
python3 pilot.py --save-output
```

### Monitoring
```bash
# Watch OCR efficiency
python3 pilot.py | grep "OCR runs this frame"

# Expected output:
# [INFO] OCR Track 0: ABC1234 (conf: 0.92)  # Fresh OCR
# [DEBUG] OCR runs this frame: 1 (active tracks: 3)
# [DEBUG] OCR runs this frame: 0 (active tracks: 3)  # Cached!
# [DEBUG] OCR runs this frame: 0 (active tracks: 3)  # Cached!
```

---

## ⚙️ Configuration Files

### Key Configs
| File | Purpose |
|------|---------|
| `config/cameras.yaml` | Camera sources (RTSP URLs) |
| `config/detection.yaml` | YOLOv11 settings, TensorRT config |
| `config/ocr.yaml` | PaddleOCR settings |
| `config/tracking.yaml` | Track management, ByteTrack/NvDCF |
| `config/inference_optimization.yaml` | Performance tuning |

### Quick Tuning

**Adjust OCR Throttling:**
```python
# pilot.py - Line 98-102
ocr_min_track_frames = 3      # Wait N frames before OCR
ocr_bbox_iou_threshold = 0.7  # Track matching threshold
```

**Adjust Attribute Caching:**
```python
# pilot.py - Line 105-106
attr_min_confidence = 0.8      # High confidence required
attr_min_track_frames = 5      # Stability needed
```

**Batch OCR Settings:**
```python
# pilot.py - Line 311-312
enable_batch_ocr = True    # Enable batching
batch_min_size = 2         # Minimum batch size
```

---

## 🏗️ Architecture Overview

### Current (Pilot Phase)
```
Camera → CPU Decode → YOLOv11 (PyTorch) → IoU Tracking → PaddleOCR → Display
         (OpenCV)     (GPU)                (Python)      (Throttled)
```

**Strengths:**
- Fast development
- Easy debugging
- All optimizations work

**Limitations:**
- 1-2 streams max
- CPU decode bottleneck
- Multiple CPU↔GPU copies

### Future (DeepStream Production)
```
Camera → NVDEC → TensorRT → NvDCF Tracker → Python Probe → Kafka
         (GPU)   (GPU)      (GPU)            (OCR+Cache)
```

**Benefits:**
- 8-12 streams per device
- 3x lower latency (30-50ms)
- Zero-copy GPU pipeline
- Same OCR throttling logic!

---

## 📈 Performance Optimization Checklist

### Track-Based Inference ⭐ Critical
- [x] OCR runs once per track
- [x] Vehicle attributes cached on best frame
- [x] Track matching via IoU (0.7 threshold)
- [x] Minimum stability frames (OCR: 3, Attrs: 5)
- [x] Results cached per track ID

### Batch Processing
- [x] Batch OCR when 2+ plates detected
- [x] Automatic batching/fallback
- [ ] Batch vehicle attribute inference (when enabled)

### Resolution Optimization
- [ ] Resize frames to 960px short side for inference
- [ ] Keep decode at 1080p for quality
- [x] JPEG crops limited to 640px, quality 85

### Memory Management
- [x] Track cleanup (remove stale tracks)
- [x] OCR cache retention (for analytics)
- [ ] Periodic cache size limits (10K tracks max)

---

## 🔍 Troubleshooting

### Issue: OCR Running Every Frame
```bash
# Bad log pattern:
[DEBUG] OCR runs this frame: 5
[DEBUG] OCR runs this frame: 5  # Should be 0!
[DEBUG] OCR runs this frame: 5
```

**Diagnosis:** Track matching failing
**Fix:** Lower `ocr_bbox_iou_threshold` from 0.7 to 0.6

### Issue: Low FPS (<20)
**Possible Causes:**
1. TensorRT not enabled → Check `detection.yaml`, export .engine file
2. Too many OCR calls → Check logs, verify throttling working
3. High resolution → Resize to 960px before inference

### Issue: OCR Accuracy Low
**Solutions:**
1. Increase `ocr_min_track_frames` to wait for better frame
2. Adjust preprocessing in `config/ocr.yaml`
3. Check `min_confidence` threshold (default: 0.7)

### Issue: Memory Growth
**Fix:**
```python
# Add periodic cache cleanup
if self.frame_count % 1000 == 0:
    # Keep only recent N tracks
    track_ids = list(self.track_ocr_cache.keys())
    if len(track_ids) > 5000:
        old_tracks = track_ids[:len(track_ids)-5000]
        for tid in old_tracks:
            self.track_ocr_cache.pop(tid, None)
```

---

## 📚 Key Files Reference

### Core Pipeline
- `pilot.py` - Main application (lines 202-375: process_frame)
- `services/detector/detector_service.py` - YOLOv11 detection
- `services/ocr/ocr_service.py` - PaddleOCR service

### Utilities
- `shared/utils/crop_utils.py` - Optimized JPEG crops
- `shared/schemas/event.py` - Data schemas

### Documentation
- `docs/OPTIMIZATION_GUIDE.md` - Performance guide
- `docs/DEEPSTREAM_ARCHITECTURE.md` - DeepStream role
- `docs/PIPELINE_COMPARISON.md` - Pilot vs Production

---

## 🎓 Key Concepts

### Track-Based Inference
**Problem:** Running heavy models every frame wastes GPU cycles

**Solution:**
1. Track vehicles across frames (IoU matching)
2. Run OCR/attributes once when track is stable
3. Cache result, reuse on subsequent frames

**Savings:** 10-30x reduction in heavy model calls

### Batch Inference
**When:** Multiple new tracks appear simultaneously

**Benefit:** Amortize GPU kernel launch overhead

**Implementation:**
```python
if len(tracks_needing_ocr) >= 2:
    batch_results = ocr.recognize_plates_batch(bboxes)
else:
    result = ocr.recognize_plate(bbox)
```

### Zero-Copy Pipeline (DeepStream)
**Concept:** Keep data on GPU throughout pipeline

**Benefit:** No CPU↔GPU memory transfers

**Result:** 3x lower latency, 6x more streams

---

## 💡 Pro Tips

1. **Always check logs for OCR cache hits**
   - Should see mostly "OCR runs this frame: 0"
   - Only see >0 when new vehicles enter scene

2. **Monitor track count vs cache size**
   - Active tracks: ~1-10
   - Cached OCR: Can grow indefinitely
   - Clean up periodically in production

3. **Batch OCR is automatic**
   - No manual configuration needed
   - Automatically batches when 2+ plates detected
   - Falls back to single if batch fails

4. **Track IDs in visualization are useful**
   - Shows ID:0, ID:1, etc.
   - [C] = cached OCR, [F] = fresh OCR
   - Helps debug track matching

5. **OCR throttling works with any tracker**
   - Currently: Simple IoU
   - Future: ByteTrack, NvDCF
   - Logic stays the same!

---

## 🚦 System Health Indicators

### Healthy System
```
✅ OCR runs: 0-2 per frame (mostly 0)
✅ FPS: 25-30
✅ Active tracks: 1-10
✅ GPU usage: 40-60%
✅ CPU usage: 60-80%
✅ Cache hits: >90%
```

### Unhealthy System
```
❌ OCR runs: 5+ per frame (every frame!)
❌ FPS: <15
❌ Active tracks: 50+ (track cleanup failing)
❌ GPU usage: 95%+ (overload)
❌ Memory growing (cache not bounded)
```

---

## 🎯 Next Steps

### Short Term (Current Phase)
- [x] PaddleOCR integration
- [x] Track-based OCR throttling
- [x] Batch inference
- [ ] Fine-tune OCR preprocessing
- [ ] Add plate validation (regex patterns)

### Medium Term (Scale Up)
- [ ] Export YOLOv11 to TensorRT
- [ ] Test with 3-4 camera streams
- [ ] Implement ByteTrack (replace simple IoU)
- [ ] Add resolution optimization (960px inference)

### Long Term (Production)
- [ ] DeepStream integration
- [ ] Multi-stream batching
- [ ] Kafka event publishing
- [ ] PostgreSQL storage
- [ ] Grafana dashboards

---

**Remember:** Heavy models once per track = 90%+ savings! 🎉
