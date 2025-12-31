# GPU Video Decode Optimization Guide

**Goal:** Reduce CPU usage from 15-25% to <5% by enabling NVDEC hardware video decoding

**Status:** 🟡 Partial - Hardware decode enabled for RTSP, disabled for video files

**Last Updated:** 2025-12-23

---

## Current Implementation Status

### ✅ What's Already Working

The system **already has** hardware decoding implemented via GStreamer:

```python
# edge-services/camera/camera_ingestion.py:130-151
def _build_gstreamer_pipeline(self, rtsp_url: str) -> str:
    pipeline = (
        f"rtspsrc location={rtsp_url} latency=0 ! "
        "rtph264depay ! "
        "h264parse ! "
        "nvv4l2decoder ! "  # ✅ Jetson hardware decoder
        "nvvidconv ! "
        "video/x-raw, format=BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=BGR ! "
        "appsink drop=1"
    )
    return pipeline
```

**Enabled for:**
- ✅ RTSP streams (`use_hw_decode=True` at line 342)

**Disabled for:**
- ❌ Video files (`use_hw_decode=False` at line 362)
- ❌ USB cameras (uses default cv2.VideoCapture)

---

## 🚀 Improvement 1: Enable Hardware Decode for Video Files

### Current Issue

Video files use CPU decoding:
```python
# Line 362 in camera_ingestion.py
camera = CameraSource(
    source_id=video_config['id'],
    source_uri=video_config['file_path'],
    name=video_config['name'],
    location="Video File",
    use_hw_decode=False,  # ❌ Disabled!
    loop_video=video_config.get('loop', True),
)
```

### Solution

**Step 1:** Update `_build_gstreamer_pipeline()` to support video files

```python
def _build_gstreamer_pipeline(self, source: str) -> str:
    """
    Build GStreamer pipeline for hardware-accelerated decoding on Jetson
    Supports both RTSP streams and video files

    Args:
        source: RTSP URL or video file path

    Returns:
        GStreamer pipeline string
    """
    if source.startswith("rtsp://"):
        # RTSP stream with hardware decode
        pipeline = (
            f"rtspsrc location={source} latency=0 ! "
            "rtph264depay ! "
            "h264parse ! "
            "nvv4l2decoder ! "
            "nvvidconv ! "
            "video/x-raw, format=BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=BGR ! "
            "appsink drop=1"
        )
    else:
        # Video file with hardware decode
        pipeline = (
            f"filesrc location={source} ! "
            "qtdemux ! "  # For MP4/MOV files
            "h264parse ! "
            "nvv4l2decoder ! "
            "nvvidconv ! "
            "video/x-raw, format=BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=BGR ! "
            "appsink drop=1"
        )

    return pipeline
```

**Step 2:** Enable hardware decode for video files

```python
# Line 362 - Change to:
camera = CameraSource(
    source_id=video_config['id'],
    source_uri=video_config['file_path'],
    name=video_config['name'],
    location="Video File",
    use_hw_decode=True,  # ✅ Enable hardware decode
    loop_video=video_config.get('loop', True),
    target_fps=video_config.get('settings', {}).get('fps'),
)
```

**Step 3:** Update `_initialize()` to use GStreamer for video files

```python
# Line 94-100 - Update to:
if self.use_hw_decode and isinstance(source, str):
    if source.startswith("rtsp://") or Path(source).exists():
        # Use GStreamer for RTSP or video files
        gst_pipeline = self._build_gstreamer_pipeline(source)
        self.cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
        logger.info("Using GStreamer hardware decoder")
    else:
        self.cap = cv2.VideoCapture(source)
else:
    self.cap = cv2.VideoCapture(source)
```

---

## 🚀 Improvement 2: Optimize GStreamer Pipeline

### Current Pipeline Issues

The current pipeline has unnecessary conversions:
```
nvv4l2decoder → nvvidconv → BGRx → videoconvert → BGR → appsink
```

### Optimized Pipeline

```python
def _build_optimized_pipeline(self, source: str, codec: str = "h264") -> str:
    """
    Optimized GStreamer pipeline with minimal conversions

    Args:
        source: RTSP URL or file path
        codec: Video codec (h264, h265)

    Returns:
        Optimized pipeline string
    """
    # Codec-specific parsing
    parser = "h264parse" if codec == "h264" else "h265parse"

    if source.startswith("rtsp://"):
        # RTSP with optimizations
        pipeline = (
            f"rtspsrc location={source} "
            "latency=0 "  # Low latency
            "buffer-mode=0 "  # Auto buffer mode
            "protocols=tcp ! "  # TCP for stability
            f"rtp{codec}depay ! "
            f"{parser} ! "
            "nvv4l2decoder "
            "enable-max-performance=1 "  # Max performance mode
            "drop-frame-interval=0 ! "  # Don't drop frames
            "nvvidconv ! "
            "video/x-raw(memory:NVMM), format=BGRx ! "  # Use NVMM for zero-copy
            "nvvidconv ! "
            "video/x-raw, format=BGR ! "
            "appsink "
            "max-buffers=1 "  # Minimal buffering
            "drop=true "  # Drop old frames
            "sync=false"  # Don't sync to clock
        )
    else:
        # Video file with loop support
        pipeline = (
            f"filesrc location={source} ! "
            "qtdemux ! "
            f"{parser} ! "
            "nvv4l2decoder "
            "enable-max-performance=1 ! "
            "nvvidconv ! "
            "video/x-raw, format=BGR ! "
            "appsink "
            "max-buffers=1 "
            "drop=true "
            "sync=false"
        )

    return pipeline
```

**Key Optimizations:**
- ✅ `enable-max-performance=1` on decoder
- ✅ `max-buffers=1` to reduce latency
- ✅ `sync=false` for realtime processing
- ✅ `protocols=tcp` for RTSP stability
- ✅ NVMM memory for zero-copy (optional)

---

## 🚀 Improvement 3: Add H.265 (HEVC) Support

Many modern cameras use H.265 for better compression.

```python
def _detect_codec(self, source: str) -> str:
    """
    Auto-detect video codec

    Args:
        source: RTSP URL or file path

    Returns:
        Codec type: "h264" or "h265"
    """
    # For RTSP, you might need to probe or configure per-camera
    # For video files, probe with ffprobe or gstreamer

    if source.startswith("rtsp://"):
        # Check camera config or default to h264
        return "h264"  # Or read from config
    else:
        # Probe video file (simplified)
        import subprocess
        try:
            result = subprocess.run(
                ["gst-discoverer-1.0", source],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "h265" in result.stdout or "hevc" in result.stdout:
                return "h265"
        except:
            pass
        return "h264"
```

Then update pipeline builder:
```python
codec = self._detect_codec(source)
pipeline = self._build_optimized_pipeline(source, codec)
```

---

## 🚀 Improvement 4: Add Camera Configuration Options

Update `config/cameras.yaml` to support hardware decode settings:

```yaml
cameras:
  - id: "cam_01"
    name: "Front Gate"
    rtsp_url: "rtsp://192.168.1.100:554/stream"
    enabled: true
    hardware_decode:
      enabled: true
      codec: "h264"  # or "h265"
      max_performance: true
    settings:
      resolution: [1920, 1080]
      fps: 30

video_sources:
  - id: "video_01"
    name: "Test Video"
    file_path: "/path/to/video.mp4"
    enabled: true
    hardware_decode:
      enabled: true  # ✅ Enable for video files
      codec: "h264"
    settings:
      fps: 30  # Playback speed
    loop: true
```

Then read in CameraManager:
```python
# For cameras
hw_config = cam_config.get('hardware_decode', {})
camera = CameraSource(
    source_id=cam_config['id'],
    source_uri=cam_config['rtsp_url'],
    name=cam_config['name'],
    location=cam_config.get('location'),
    use_hw_decode=hw_config.get('enabled', True),
    codec=hw_config.get('codec', 'h264'),
    max_performance=hw_config.get('max_performance', True),
    ...
)
```

---

## 🚀 Improvement 5: Verify Hardware Decode is Active

### Check at Runtime

Add logging to verify hardware decode:

```python
def _initialize(self):
    """Initialize video capture"""
    logger.info(f"Initializing camera source: {self.name} ({self.source_id})")

    try:
        # ... existing code ...

        if self.use_hw_decode and isinstance(source, str):
            gst_pipeline = self._build_gstreamer_pipeline(source)
            logger.info(f"GStreamer pipeline: {gst_pipeline}")  # ✅ Log pipeline
            self.cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)

            if self.cap.isOpened():
                logger.success("✅ Hardware decoder initialized successfully")
            else:
                logger.error("❌ Hardware decoder failed, falling back to CPU")
                self.cap = cv2.VideoCapture(source)
```

### Monitor GPU Usage

```bash
# Check NVDEC usage (should be > 0% when hardware decode active)
tegrastats

# Output shows:
# NVDEC 45%  <-- Hardware decoder utilization
# CPU [15%@1190,12%@1190,8%@1190,10%@1190]  <-- CPU should be lower
```

### Compare CPU Usage

**Before (CPU decode):**
```bash
# CPU usage with 1 camera
CPU [25%@1190,22%@1190,18%@1190,20%@1190]
NVDEC 0%  # Not using hardware decoder
```

**After (GPU decode):**
```bash
# CPU usage with 1 camera
CPU [8%@1190,6%@1190,5%@1190,7%@1190]  # ✅ Much lower!
NVDEC 40%  # ✅ Using hardware decoder
```

---

## 🚀 Improvement 6: Alternative - Use gpu_camera_ingestion.py

The codebase already has an alternative GPU-accelerated implementation:

```bash
# Check if it exists
ls -lh edge-services/camera/gpu_camera_ingestion.py
```

If it exists, you can:
1. Review its implementation
2. Compare with current camera_ingestion.py
3. Merge best features from both

---

## 📊 Expected Performance Improvements

| Metric | CPU Decode (Current) | GPU Decode (Optimized) | Improvement |
|--------|----------------------|------------------------|-------------|
| CPU Usage (1 cam) | 15-25% | 5-8% | **60-70% reduction** |
| CPU Usage (2 cams) | 30-50% | 10-16% | **60-70% reduction** |
| NVDEC Usage | 0% | 30-50% | GPU utilized |
| Memory Bandwidth | High | Medium | Reduced PCIe traffic |
| Max Streams | 1-2 | 2-4 | **2x capacity** |
| Decode Latency | 10-15ms | 3-5ms | **3x faster** |

---

## 🔧 Implementation Priority

### Quick Win (1-2 hours)
1. ✅ Enable `use_hw_decode=True` for video files (line 362)
2. ✅ Update `_build_gstreamer_pipeline()` to support video files
3. ✅ Update `_initialize()` to use GStreamer for video files
4. ✅ Test with existing video files

### Medium Effort (1 day)
5. ✅ Optimize GStreamer pipeline (max-performance, minimal buffering)
6. ✅ Add H.265 support
7. ✅ Add runtime verification logging
8. ✅ Update config/cameras.yaml schema

### Advanced (2-3 days)
9. ✅ Auto-detect codec
10. ✅ Add codec selection per camera in config
11. ✅ Implement NVMM zero-copy memory
12. ✅ Add fallback to CPU on decoder failure

---

## 🧪 Testing Plan

### 1. Test RTSP Hardware Decode

```bash
# Run with RTSP camera
python3 pilot.py

# Monitor in another terminal
tegrastats

# Verify NVDEC shows usage
```

### 2. Test Video File Hardware Decode

```bash
# After enabling hw decode for video files
python3 pilot.py

# Check logs for "Using GStreamer hardware decoder"
# Monitor tegrastats for NVDEC usage
```

### 3. Benchmark CPU Usage

```bash
# Before optimization
tegrastats --interval 1000 > before.log &
python3 pilot.py --no-display
# Let run for 30 seconds
killall tegrastats

# After optimization
tegrastats --interval 1000 > after.log &
python3 pilot.py --no-display
# Let run for 30 seconds
killall tegrastats

# Compare average CPU usage
grep "CPU" before.log | awk '{print $2}' | sed 's/%//' | awk '{sum+=$1; count++} END {print sum/count}'
grep "CPU" after.log | awk '{print $2}' | sed 's/%//' | awk '{sum+=$1; count++} END {print sum/count}'
```

---

## 🐛 Troubleshooting

### Issue: GStreamer pipeline fails

**Error:**
```
Failed to open camera source
```

**Solution:**
```bash
# Check GStreamer plugins installed
gst-inspect-1.0 nvv4l2decoder

# Should output plugin details
# If not found, install:
sudo apt-get install nvidia-l4t-gstreamer
```

### Issue: NVDEC shows 0% usage

**Possible causes:**
1. `use_hw_decode=False` in code
2. Video codec not supported (try H.264)
3. GStreamer pipeline not used

**Debug:**
```bash
# Test GStreamer pipeline directly
gst-launch-1.0 filesrc location=test.mp4 ! qtdemux ! h264parse ! nvv4l2decoder ! nvvidconv ! 'video/x-raw, format=BGR' ! autovideosink

# Check for errors
```

### Issue: Higher CPU usage than expected

**Check:**
1. `videoconvert` element in pipeline (slow)
2. `sync=true` causing unnecessary work
3. Multiple format conversions
4. Buffer size too large

**Fix:** Use optimized pipeline from Improvement 2

---

## 📝 Code Changes Summary

### File: `edge-services/camera/camera_ingestion.py`

**Line 130-151:** Update `_build_gstreamer_pipeline()`
```python
# Add video file support and optimization
```

**Line 94-100:** Update `_initialize()`
```python
# Enable GStreamer for video files too
if self.use_hw_decode and isinstance(source, str):
    if source.startswith("rtsp://") or Path(source).exists():
        gst_pipeline = self._build_gstreamer_pipeline(source)
        ...
```

**Line 362:** Change `use_hw_decode`
```python
use_hw_decode=True,  # Enable for video files
```

---

## ✅ Success Criteria

After implementing these improvements, you should see:

1. ✅ NVDEC usage 30-50% when decoding video
2. ✅ CPU usage reduced by 60-70%
3. ✅ Logs show "Using GStreamer hardware decoder"
4. ✅ No performance degradation
5. ✅ Ability to run 2-4 streams (vs 1-2 before)

---

## 🚀 Next Steps After This

Once hardware decode is optimized:
1. You're ready for Phase 3 (MinIO, Monitoring, Alerts)
2. Can handle 2-4 streams per Jetson
3. For 8-12 streams, migrate to DeepStream (Phase 5)

**This optimization alone doubles your camera capacity without DeepStream migration!**
