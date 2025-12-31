# Performance Optimization Guide - Enterprise-Grade ALPR for Parking Gates

This guide provides advanced optimization techniques to maximize FPS for the OVR-ALPR pipeline on NVIDIA Jetson platforms, specifically designed for **enterprise-grade parking gate deployments** where OCR and tracking are mission-critical.

## Overview

With proper optimization, the OVR-ALPR system can achieve:
- **60-80 FPS** on Jetson Orin NX with full pipeline (detection + OCR + tracking)
- **100+ FPS** on Jetson Orin or AGX with optimizations
- **~15-20ms total latency** (detection + OCR + tracking combined)

## Enterprise Requirements

For parking gate deployment, the following features are **NON-NEGOTIABLE**:
- ✅ **OCR** - License plate text recognition is mandatory
- ✅ **Tracking** - Multi-object tracking for vehicle identification across frames
- ✅ **High accuracy** - Enterprise-grade detection (95%+ accuracy)
- ✅ **Low latency** - Real-time processing (<50ms per frame)

This guide focuses on optimizations that **preserve these critical features** while maximizing performance.

## Performance Baseline

Starting point (default configuration):
- **FP16 precision**: ~20-30 FPS
- **Frame skip**: Every 3rd frame (skip_frames=2)
- **Full pipeline**: Vehicle detection + Plate detection + OCR + Tracking

Target after optimizations (with OCR + Tracking):
- **INT8 precision**: ~60-80 FPS (Jetson Orin NX)
- **Parallel pipeline**: Overlapped processing
- **Optimized resolution**: 416x416 for parking gates

---

## Platform Scalability

### Jetson Orin NX (Current - Pilot Testing)
- **Resolution**: 416x416 (optimal for close-range parking gates)
- **Expected FPS**: 60-80 FPS with full pipeline
- **Use case**: Initial deployment, pilot testing, single-lane gates

### Jetson Orin or AGX Orin (Production Upgrade Path)
- **Resolution**: 640x640 or higher (better accuracy at distance)
- **Expected FPS**: 100-150+ FPS with full pipeline
- **Use case**: Multi-lane gates, high-traffic areas, make/model/color detection
- **Additional capabilities**:
  - Higher resolution for vehicle attribute detection
  - Multiple camera streams per device
  - Real-time analytics and AI processing

**Upgrade strategy**: Start with 416x416 on Orin NX, then scale to higher resolutions on Orin/AGX when deploying production systems.

---

## 1. INT8 Quantization (Highest Impact)

**Expected gain**: 2-3x FPS improvement
**Enterprise impact**: ✅ **CRITICAL** - Maintains accuracy while maximizing throughput

### Why INT8 for Enterprise?

INT8 quantization leverages Jetson's dedicated tensor cores for integer math, providing:
- **Faster inference**: 8-bit operations are 3-4x faster than 16-bit
- **Lower power consumption**: Important for edge deployment
- **Minimal accuracy loss**: <1-2% with proper calibration using domain-specific data
- **Smaller memory footprint**: Enables multi-camera processing

### Implementation

Edit `pilot.py` lines 75-82:

```python
self.detector = YOLOv11Detector(
    vehicle_model_path=detector_model,
    plate_model_path=plate_model,
    use_tensorrt=use_tensorrt,
    fp16=False,      # <-- Disable FP16
    int8=True,       # <-- Enable INT8
    batch_size=1,
)
```

**Performance impact**:
- **Before**: ~25ms inference → **After**: ~10ms inference
- **FPS**: 40 FPS → 100+ FPS (detection only)
- **With OCR+Tracking**: 25 FPS → 60-80 FPS (full pipeline)

### Calibration with Your Data

For best results, calibrate INT8 with your actual parking gate videos:

```bash
# Extract frames from your calibration videos
mkdir -p datasets/calibration
ffmpeg -i your_parking_gate_video.mp4 -vf fps=1 datasets/calibration/frame_%04d.jpg

# Use 100-500 representative frames showing:
# - Different lighting conditions (day, night, shadows)
# - Various vehicle types (cars, trucks, motorcycles)
# - Different angles and distances
# - Weather conditions (rain, fog, clear)
```

This domain-specific calibration ensures INT8 maintains enterprise-grade accuracy for your specific deployment environment.

See `docs/INT8_PRECISION_GUIDE.md` for detailed calibration instructions.

---

## 2. Input Resolution Optimization

**Expected gain**: 30-60% FPS improvement
**Enterprise impact**: ✅ **RECOMMENDED** - Optimized for parking gate use case

### Resolution Strategy by Platform

**Parking gates (close range, 2-5 meters)**:
- Vehicles fill most of the frame
- License plates are clearly visible
- Lower resolution sufficient for accurate detection

| Platform | Resolution | FPS (Full Pipeline) | Accuracy | Use Case |
|----------|-----------|---------------------|----------|----------|
| **Orin NX** | **416x416** | **60-80 FPS** | 95%+ | Pilot, single-lane gates |
| Orin/AGX | 640x640 | 100-120 FPS | 97%+ | Production, multi-lane |
| AGX Orin | 1280x1280 | 60-80 FPS | 99%+ | Make/model/color detection |

**Recommended for pilot**: Start with **416x416** on Jetson Orin NX

### Why 416x416 Works for Parking Gates

1. **Close proximity**: Vehicles are 2-5 meters from camera, filling 60-80% of frame
2. **Large features**: License plates appear as 80-120 pixels wide (easily readable)
3. **Speed advantage**: 2.3x faster inference than 640x640
4. **Accuracy maintained**: Minimal loss for large, close objects

### Implementation

Add resolution parameter to `YOLOv11Detector.__init__` in `edge-services/detector/detector_service.py`:

```python
def __init__(
    self,
    vehicle_model_path: str = "yolo11n.pt",
    plate_model_path: Optional[str] = None,
    device: str = "cuda:0",
    use_tensorrt: bool = True,
    fp16: bool = True,
    int8: bool = False,
    batch_size: int = 1,
    input_size: int = 416,  # <-- Add this, default to 416 for parking gates
):
    self.input_size = input_size
    # ... rest of init
```

Then update predict calls (lines 136, 211, 237):

```python
results = self.vehicle_model.predict(
    frame,
    conf=confidence_threshold,
    iou=nms_threshold,
    classes=list(self.vehicle_classes.keys()),
    verbose=False,
    device=self.device,
    half=self.fp16,
    imgsz=self.input_size  # <-- Use configurable resolution
)
```

---

## 3. Multi-Camera Architecture (Enterprise Deployment)

**Expected gain**: Better accuracy + specialized detection
**Enterprise impact**: ✅ **HIGHLY RECOMMENDED** - Production-ready architecture

### Dual-Camera Setup

For enterprise parking gates, deploy **two specialized cameras**:

#### Camera 1: Rear License Plate Camera
- **Purpose**: Dedicated ALPR (license plate detection + OCR)
- **Position**: Focused on rear of vehicle at gate barrier
- **Resolution**: 720p or 1080p (down-sampled to 416x416 for inference)
- **Processing**: YOLOv11 detection → OCR → Tracking
- **Priority**: High accuracy plate reading

#### Camera 2: Front Vehicle Overview Camera
- **Purpose**: Vehicle attributes (make, model, color, type)
- **Position**: Front-facing, captures full vehicle
- **Resolution**: 1080p or higher (processed at 640x640 or 1280x1280)
- **Processing**: Vehicle classification, attribute detection
- **Priority**: Vehicle identification and analytics

### Why Dual-Camera?

1. **Specialization**: Each camera optimized for specific task
2. **Better angles**: Rear camera gets clean plate view, front gets vehicle details
3. **Redundancy**: If one camera fails, basic operation continues
4. **Higher accuracy**: Dedicated cameras outperform single multi-purpose camera
5. **Parallel processing**: Both cameras can be processed simultaneously

### Multi-Camera Implementation

See **Section 10: Multi-Camera Batching** below for batch processing implementation.

---

## 4. Smart Adaptive Sampling

**Expected gain**: 2-5x processing FPS (maintains detection accuracy)
**Enterprise impact**: ⚠️ **USE WITH CAUTION** - Must not miss vehicles

### Adaptive Frame Skipping for Parking Gates

Current implementation processes every 3rd frame. For slow-moving parking gate traffic:

```bash
# Conservative (recommended for enterprise)
python pilot.py --skip-frames 2  # Process every 3rd frame (~10 FPS @ 30 FPS camera)

# Moderate (good for single-lane gates)
python pilot.py --skip-frames 4  # Process every 5th frame (~6 FPS @ 30 FPS camera)

# Aggressive (test only, not recommended for production)
python pilot.py --skip-frames 9  # Process every 10th frame (~3 FPS @ 30 FPS camera)
```

### Why Frame Skipping Works

At parking gates:
- Vehicles approach slowly (5-15 km/h)
- Vehicles stop at barrier (2-5 second dwell time)
- High frame overlap (vehicle appears in 30-90+ consecutive frames)

**Example**: At 30 FPS camera with vehicle stopped for 3 seconds:
- Total frames with vehicle: ~90 frames
- With skip_frames=4 (every 5th frame): Still process ~18 frames per vehicle
- Result: 18 detection opportunities per vehicle (more than sufficient)

### Testing Adaptive Sampling

**Recommendation**: Test on your actual parking gate videos to find optimal skip rate:

```bash
# Test different skip rates and measure:
# 1. Detection rate (% of vehicles detected)
# 2. OCR accuracy (% of plates correctly read)
# 3. Processing FPS

python pilot.py --skip-frames 2  # Baseline
python pilot.py --skip-frames 4  # Moderate
python pilot.py --skip-frames 6  # Aggressive
```

**Enterprise guideline**: Choose the highest skip rate that maintains **100% vehicle detection** and **>95% OCR accuracy**.

---

## 5. Scene-Aware Frame Skipping

**Expected gain**: Variable (scene-dependent)
**Enterprise impact**: ⚠️ **NOT RECOMMENDED FOR PARKING GATES**

### Why Motion Detection Doesn't Work for Gates

Motion-based frame skipping has a **critical flaw** for parking gate scenarios:

**Problem**: When a vehicle **parks at the gate** (waiting for barrier to open):
- Vehicle is stationary for 2-5 seconds
- Motion detector sees no movement
- **System skips processing**
- **Result**: Plate is NOT read, vehicle is NOT logged ❌

### Failure Scenario

```
1. Vehicle approaches gate → Motion detected → Processing starts ✓
2. Vehicle stops at barrier → No motion → Processing STOPS ✗
3. Plate is clearly visible but NOT processed ✗
4. Vehicle waits 3 seconds at barrier → Still no motion ✗
5. Barrier opens, vehicle leaves → Missed opportunity ✗
```

This is **unacceptable** for enterprise parking systems where every vehicle must be logged.

### Alternative: Region-of-Interest (ROI) Detection

Instead of motion detection, use **ROI-based processing**:

```python
class ROIDetector:
    """Process only when vehicle in detection zone"""

    def __init__(self, roi_bbox):
        """
        roi_bbox: (x1, y1, x2, y2) - Detection zone at gate barrier
        """
        self.roi = roi_bbox

    def vehicle_in_roi(self, frame, detector):
        """Check if vehicle present in ROI (gate area)"""
        # Run fast detection on ROI only
        roi_frame = frame[self.roi[1]:self.roi[3], self.roi[0]:self.roi[2]]
        vehicles = detector.detect_vehicles(roi_frame, confidence_threshold=0.5)
        return len(vehicles) > 0
```

**Benefit**: Processes frames when vehicle is in gate area (even if stationary) while skipping empty frames.

**Recommendation for enterprise**: Use ROI detection instead of motion detection for parking gates.

---

## 6. Pipeline Parallelization (CRITICAL FOR ENTERPRISE)

**Expected gain**: 30-50% throughput improvement
**Enterprise impact**: ✅ **HIGHLY RECOMMENDED** - Essential for maintaining FPS with OCR+Tracking

### Why Parallelization Matters

The ALPR pipeline has three main stages:
1. **Detection** (GPU-bound): Vehicle + plate detection (~10-15ms)
2. **OCR** (GPU/CPU-bound): Text recognition (~15-30ms per plate)
3. **Tracking** (CPU-bound): ByteTrack multi-object tracking (~3-5ms)

**Sequential processing** (current):
```
Frame N: Detection (15ms) → OCR (25ms) → Tracking (5ms) = 45ms total
Frame N+1: Wait for Frame N to complete...
```

**Parallel processing** (optimized):
```
Frame N:   Detection (15ms) → Queue OCR → Return (15ms) ✓
           OCR runs in background thread (25ms)
Frame N+1: Detection (15ms) → Queue OCR → Return (15ms) ✓
Frame N+2: Detection (15ms) → Queue OCR → Return (15ms) ✓
```

**Result**: Detection runs at ~66 FPS while OCR processes plates in background.

### Implementation: Threaded OCR Processing

Create `edge-services/ocr/async_ocr_service.py`:

```python
import threading
from queue import Queue, Empty
from typing import Callable, Optional
import numpy as np
from loguru import logger

class AsyncOCRService:
    """
    Asynchronous OCR service for parallel plate processing

    Queues plate images for background OCR processing while
    main detection pipeline continues running.
    """

    def __init__(self, ocr_engine, num_workers=2, max_queue_size=10):
        """
        Args:
            ocr_engine: The OCR engine instance (PaddleOCR, EasyOCR, etc.)
            num_workers: Number of worker threads (default: 2)
            max_queue_size: Maximum queued plates (default: 10)
        """
        self.ocr_engine = ocr_engine
        self.queue = Queue(maxsize=max_queue_size)
        self.workers = []
        self.running = True

        # Start worker threads
        for i in range(num_workers):
            worker = threading.Thread(
                target=self._ocr_worker,
                name=f"OCR-Worker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        logger.info(f"AsyncOCR service started with {num_workers} workers")

    def _ocr_worker(self):
        """Background worker that processes OCR requests"""
        while self.running:
            try:
                # Get plate image and callback from queue (timeout 1s)
                item = self.queue.get(timeout=1.0)
                if item is None:  # Poison pill
                    break

                plate_img, metadata, callback = item

                # Perform OCR
                result = self.ocr_engine.recognize(plate_img)

                # Execute callback with result
                if callback:
                    callback(result, metadata)

                self.queue.task_done()

            except Empty:
                continue
            except Exception as e:
                logger.error(f"OCR worker error: {e}")
                self.queue.task_done()

    def process_plate_async(
        self,
        plate_img: np.ndarray,
        metadata: dict,
        callback: Optional[Callable] = None
    ) -> bool:
        """
        Queue plate image for asynchronous OCR processing

        Args:
            plate_img: Cropped plate image (numpy array)
            metadata: Associated metadata (vehicle_id, timestamp, bbox, etc.)
            callback: Function to call with results: callback(ocr_result, metadata)

        Returns:
            True if queued successfully, False if queue is full
        """
        try:
            self.queue.put((plate_img, metadata, callback), block=False)
            return True
        except:
            logger.warning("OCR queue full, dropping plate")
            return False

    def shutdown(self):
        """Gracefully shutdown OCR workers"""
        logger.info("Shutting down AsyncOCR service...")
        self.running = False

        # Send poison pills
        for _ in self.workers:
            self.queue.put(None)

        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5.0)

        logger.success("AsyncOCR service stopped")
```

### Integration in `pilot.py`

```python
from services.ocr.async_ocr_service import AsyncOCRService

class ALPRPilot:
    def __init__(self, ...):
        # ... existing init code ...

        # Replace synchronous OCR with async version
        if self.enable_ocr:
            from services.ocr.ocr_service import PaddleOCRService
            base_ocr = PaddleOCRService()
            self.ocr = AsyncOCRService(base_ocr, num_workers=2)

    def _handle_ocr_result(self, ocr_result, metadata):
        """Callback for async OCR results"""
        vehicle_id = metadata['vehicle_id']
        plate_text = ocr_result.get('text', '')
        confidence = ocr_result.get('confidence', 0.0)

        logger.info(
            f"Vehicle {vehicle_id}: Plate '{plate_text}' "
            f"(conf: {confidence:.2f})"
        )

        # Store result, trigger events, update database, etc.
        # This runs in background thread, so be thread-safe!

    def process_frame(self, frame):
        # Detection (main thread, fast)
        vehicles = self.detector.detect_vehicles(frame)
        plates = self.detector.detect_plates(frame, [v.bbox for v in vehicles])

        # Tracking (main thread, fast)
        if self.enable_tracking:
            tracked_vehicles = self.tracker.update(vehicles)

        # OCR (background thread, slow)
        if self.enable_ocr and plates:
            for vehicle_idx, plate_bboxes in plates.items():
                for plate_bbox in plate_bboxes:
                    # Crop plate image
                    x1, y1, x2, y2 = map(int, [
                        plate_bbox.x1, plate_bbox.y1,
                        plate_bbox.x2, plate_bbox.y2
                    ])
                    plate_img = frame[y1:y2, x1:x2]

                    # Queue for async processing
                    metadata = {
                        'vehicle_id': tracked_vehicles[vehicle_idx].track_id,
                        'timestamp': time.time(),
                        'bbox': plate_bbox,
                    }
                    self.ocr.process_plate_async(
                        plate_img,
                        metadata,
                        self._handle_ocr_result
                    )

        # Return immediately, OCR continues in background
        return tracked_vehicles, plates
```

### Performance Impact

**Before (sequential)**:
- Detection: 15ms
- OCR: 25ms (blocks detection)
- Tracking: 5ms
- **Total**: 45ms → **22 FPS**

**After (parallel)**:
- Detection: 15ms
- Tracking: 5ms
- **Total**: 20ms → **50 FPS** ✓
- OCR: 25ms (background, doesn't block)

**Result**: 2.3x FPS improvement while maintaining full OCR functionality!

---

## 7. Processing & Post-Processing

**Expected gain**: Improved accuracy and reduced false positives
**Enterprise impact**: ✅ **CRITICAL** - Essential for production data quality

### Why Post-Processing Matters

Raw OCR results often contain:
- Inconsistent formatting (mixed case, spaces, special characters)
- Invalid plate patterns (wrong length, invalid characters)
- Duplicate detections (same vehicle logged multiple times)
- Missing metadata (no camera ID, timestamp, or confidence)

**Enterprise requirement**: All plate data must be normalized, validated, and deduplicated before logging.

### Implementation: Plate Text Normalization

Create `edge-services/ocr/plate_processor.py`:

```python
import re
from typing import Optional, Dict
from loguru import logger

class PlateProcessor:
    """
    Post-processing for license plate text
    - Normalization (uppercase, remove spaces/dashes)
    - Validation against country/state patterns
    - Format standardization
    """

    def __init__(self, country_code: str = "US"):
        """
        Args:
            country_code: Country code for validation patterns (US, CA, etc.)
        """
        self.country_code = country_code
        self.validation_patterns = self._load_patterns(country_code)

    def _load_patterns(self, country_code: str) -> Dict[str, re.Pattern]:
        """Load regex patterns for license plate validation"""
        patterns = {
            # United States patterns
            "US": {
                # Florida: ABC1234 or ABC-1234
                "FL": re.compile(r'^[A-Z]{3}[A-Z0-9]{4}$'),
                # California: 1ABC234
                "CA": re.compile(r'^[0-9][A-Z]{3}[0-9]{3}$'),
                # Texas: ABC1234 or ABC-1234
                "TX": re.compile(r'^[A-Z]{3}[0-9]{4}$'),
                # New York: ABC1234
                "NY": re.compile(r'^[A-Z]{3}[0-9]{4}$'),
                # Generic US (7-8 alphanumeric)
                "GENERIC": re.compile(r'^[A-Z0-9]{7,8}$'),
            },
            # Canada patterns
            "CA": {
                # Ontario: ABCD123
                "ON": re.compile(r'^[A-Z]{4}[0-9]{3}$'),
                # Quebec: A12BCD
                "QC": re.compile(r'^[A-Z][0-9]{2}[A-Z]{3}$'),
                # Generic Canada
                "GENERIC": re.compile(r'^[A-Z0-9]{6,7}$'),
            }
        }
        return patterns.get(country_code, patterns["US"])

    def normalize(self, plate_text: str) -> str:
        """
        Normalize plate text to standard format

        Transformations:
        - Convert to uppercase
        - Remove spaces, dashes, dots
        - Remove special characters
        - Trim whitespace

        Args:
            plate_text: Raw OCR result

        Returns:
            Normalized plate text (uppercase, no spaces/special chars)
        """
        if not plate_text:
            return ""

        # Convert to uppercase
        normalized = plate_text.upper()

        # Remove common separators and special characters
        normalized = re.sub(r'[  \-\.\,\:\;]', '', normalized)

        # Remove non-alphanumeric characters
        normalized = re.sub(r'[^A-Z0-9]', '', normalized)

        # Trim whitespace
        normalized = normalized.strip()

        logger.debug(f"Normalized '{plate_text}' → '{normalized}'")

        return normalized

    def validate(
        self,
        plate_text: str,
        state_code: Optional[str] = None
    ) -> bool:
        """
        Validate plate text against format patterns

        Args:
            plate_text: Normalized plate text
            state_code: Optional state/province code (FL, CA, ON, etc.)

        Returns:
            True if plate matches expected format, False otherwise
        """
        if not plate_text:
            return False

        # Try state-specific pattern first
        if state_code and state_code in self.validation_patterns:
            pattern = self.validation_patterns[state_code]
            if pattern.match(plate_text):
                logger.debug(f"Plate '{plate_text}' matches {state_code} format")
                return True

        # Fall back to generic pattern
        generic_pattern = self.validation_patterns.get("GENERIC")
        if generic_pattern and generic_pattern.match(plate_text):
            logger.debug(f"Plate '{plate_text}' matches generic format")
            return True

        logger.warning(f"Plate '{plate_text}' does not match any valid format")
        return False

    def process(
        self,
        raw_text: str,
        state_code: Optional[str] = None,
        min_length: int = 5,
        max_length: int = 8
    ) -> Optional[str]:
        """
        Complete processing pipeline: normalize + validate

        Args:
            raw_text: Raw OCR result
            state_code: Optional state/province code
            min_length: Minimum plate length (default: 5)
            max_length: Maximum plate length (default: 8)

        Returns:
            Normalized plate text if valid, None if invalid
        """
        # Normalize
        normalized = self.normalize(raw_text)

        # Check length
        if len(normalized) < min_length or len(normalized) > max_length:
            logger.warning(
                f"Plate '{raw_text}' rejected: "
                f"length {len(normalized)} not in range [{min_length}, {max_length}]"
            )
            return None

        # Validate format
        if not self.validate(normalized, state_code):
            return None

        return normalized
```

### Deduplication Service

Create `edge-services/tracker/deduplication_service.py`:

```python
import time
from typing import Dict, Set, Optional
from dataclasses import dataclass
from collections import defaultdict
from loguru import logger

@dataclass
class PlateRecord:
    """Record of a detected plate"""
    plate_text: str
    camera_id: str
    timestamp: float
    confidence: float
    vehicle_id: int

class DeduplicationService:
    """
    Prevent logging the same vehicle multiple times

    Tracks recently seen plates and suppresses duplicates
    within a time window (e.g., same car staying in view).
    """

    def __init__(
        self,
        dedup_window: float = 5.0,
        cleanup_interval: int = 100
    ):
        """
        Args:
            dedup_window: Time window in seconds for deduplication (default: 5s)
            cleanup_interval: Frames between cleanup cycles (default: 100)
        """
        self.dedup_window = dedup_window
        self.cleanup_interval = cleanup_interval
        self.frame_count = 0

        # Track recent plates: {plate_text: {camera_id: last_timestamp}}
        self.recent_plates: Dict[str, Dict[str, float]] = defaultdict(dict)

        # Track unique plates logged (for statistics)
        self.unique_plates: Set[str] = set()
        self.total_detections = 0
        self.duplicate_detections = 0

    def is_duplicate(
        self,
        plate_text: str,
        camera_id: str,
        current_time: Optional[float] = None
    ) -> bool:
        """
        Check if plate was recently seen on this camera

        Args:
            plate_text: Normalized plate text
            camera_id: Camera identifier
            current_time: Current timestamp (default: time.time())

        Returns:
            True if duplicate, False if new/expired
        """
        if current_time is None:
            current_time = time.time()

        self.total_detections += 1

        # Check if plate exists in recent history
        if plate_text in self.recent_plates:
            camera_history = self.recent_plates[plate_text]

            # Check if seen on this camera recently
            if camera_id in camera_history:
                last_seen = camera_history[camera_id]
                time_elapsed = current_time - last_seen

                # Within deduplication window?
                if time_elapsed < self.dedup_window:
                    self.duplicate_detections += 1
                    logger.debug(
                        f"Duplicate: '{plate_text}' on {camera_id} "
                        f"(last seen {time_elapsed:.1f}s ago)"
                    )
                    return True

        # Not a duplicate - update history
        self.recent_plates[plate_text][camera_id] = current_time
        self.unique_plates.add(plate_text)

        logger.debug(f"New detection: '{plate_text}' on {camera_id}")
        return False

    def cleanup_expired(self, current_time: Optional[float] = None):
        """
        Remove expired entries from recent_plates

        Call periodically to prevent unbounded memory growth.
        """
        if current_time is None:
            current_time = time.time()

        expired_plates = []

        for plate_text, camera_history in self.recent_plates.items():
            # Remove expired camera entries
            expired_cameras = [
                cam_id for cam_id, timestamp in camera_history.items()
                if current_time - timestamp > self.dedup_window
            ]

            for cam_id in expired_cameras:
                del camera_history[cam_id]

            # If no cameras remain, mark plate for removal
            if not camera_history:
                expired_plates.append(plate_text)

        # Remove plates with no active cameras
        for plate_text in expired_plates:
            del self.recent_plates[plate_text]

        if expired_plates:
            logger.debug(f"Cleaned up {len(expired_plates)} expired plate entries")

    def update(
        self,
        plate_text: str,
        camera_id: str,
        current_time: Optional[float] = None
    ) -> bool:
        """
        Update and check for duplicates (with auto-cleanup)

        Args:
            plate_text: Normalized plate text
            camera_id: Camera identifier
            current_time: Current timestamp

        Returns:
            True if should be logged (not duplicate), False if duplicate
        """
        self.frame_count += 1

        # Periodic cleanup to prevent memory growth
        if self.frame_count % self.cleanup_interval == 0:
            self.cleanup_expired(current_time)

        # Check if duplicate
        is_dup = self.is_duplicate(plate_text, camera_id, current_time)

        return not is_dup  # Return True if should log (not duplicate)

    def get_stats(self) -> Dict:
        """Get deduplication statistics"""
        return {
            'total_detections': self.total_detections,
            'duplicate_detections': self.duplicate_detections,
            'unique_plates': len(self.unique_plates),
            'dedup_rate': (
                self.duplicate_detections / self.total_detections * 100
                if self.total_detections > 0 else 0
            ),
            'recent_plates_tracked': len(self.recent_plates)
        }
```

### Metadata Enrichment

Update `pilot.py` to add metadata to all detections:

```python
from services.ocr.plate_processor import PlateProcessor
from services.tracking.deduplication_service import DeduplicationService

class ALPRPilot:
    def __init__(self, ...):
        # ... existing init ...

        # Add post-processing services
        self.plate_processor = PlateProcessor(country_code="US")
        self.deduplicator = DeduplicationService(dedup_window=5.0)

    def _handle_ocr_result(self, ocr_result, metadata):
        """Enhanced callback with post-processing"""
        raw_text = ocr_result.get('text', '')
        confidence = ocr_result.get('confidence', 0.0)

        # 1. Normalize and validate plate text
        plate_text = self.plate_processor.process(
            raw_text,
            state_code='FL',  # Configure based on location
            min_length=5,
            max_length=8
        )

        if not plate_text:
            logger.warning(f"Invalid plate rejected: '{raw_text}'")
            return

        # 2. Check for duplicates
        camera_id = metadata.get('camera_id', 'CAM-001')
        timestamp = metadata.get('timestamp', time.time())

        should_log = self.deduplicator.update(
            plate_text,
            camera_id,
            timestamp
        )

        if not should_log:
            # Duplicate - skip logging
            return

        # 3. Enrich with metadata
        detection_record = {
            # Core plate data
            'plate_text': plate_text,
            'raw_text': raw_text,
            'confidence': confidence,

            # Metadata
            'timestamp': timestamp,
            'camera_id': camera_id,
            'location': metadata.get('location', 'Main Gate'),
            'vehicle_id': metadata.get('vehicle_id'),

            # Bounding boxes
            'vehicle_bbox': metadata.get('vehicle_bbox'),
            'plate_bbox': metadata.get('plate_bbox'),

            # Vehicle attributes (if available)
            'vehicle_type': metadata.get('vehicle_type'),
            'vehicle_color': metadata.get('vehicle_color'),
            'vehicle_make': metadata.get('vehicle_make'),

            # Processing info
            'processing_time_ms': metadata.get('processing_time'),
            'frame_number': metadata.get('frame_number'),
        }

        # 4. Log to database/file/API
        self._log_detection(detection_record)

        # 5. Trigger events (gate control, notifications, etc.)
        self._trigger_events(detection_record)

        logger.success(
            f"✓ Plate logged: {plate_text} "
            f"(conf: {confidence:.2f}, camera: {camera_id})"
        )

    def _log_detection(self, record: dict):
        """Log detection to database/file"""
        # TODO: Implement database logging
        # TODO: Implement file logging (CSV, JSON)
        # TODO: Implement API webhook
        logger.info(f"Logging detection: {record}")

    def _trigger_events(self, record: dict):
        """Trigger external events (gate control, notifications)"""
        # TODO: Implement gate barrier control
        # TODO: Implement security alerts
        # TODO: Implement access control integration
        pass
```

### Performance Impact

**Benefits**:
- ✅ **Data quality**: Normalized, consistent plate format
- ✅ **Reduced false positives**: Invalid plates filtered out
- ✅ **No duplicates**: Same vehicle only logged once
- ✅ **Rich metadata**: Full context for every detection
- ✅ **Audit trail**: Complete record for compliance

**Processing overhead**: Minimal (~1-2ms per plate)

**Enterprise value**: Critical for production systems where data quality and auditability are mandatory.

---

## 8. GPU Stream Optimization

**Expected gain**: 10-20% with multiple cameras
**Enterprise impact**: ✅ **RECOMMENDED** - Essential for multi-camera deployments

### CUDA Streams Explained

CUDA streams allow **concurrent GPU operations**. Instead of serializing all GPU work:

**Without streams** (default):
```
Camera 1 Detection → Camera 1 Complete → Camera 2 Detection → Camera 2 Complete
```

**With streams**:
```
Camera 1 Detection ─┐
                    ├→ GPU processes both in parallel
Camera 2 Detection ─┘
```

### Implementation

Update `edge-services/detector/detector_service.py`:

```python
import torch

class YOLOv11Detector:
    def __init__(self, ..., stream_id=0):
        # ... existing init ...

        # Create dedicated CUDA stream for this detector instance
        self.stream = torch.cuda.Stream(device=self.device)
        self.stream_id = stream_id

        logger.info(f"Detector initialized with CUDA stream {stream_id}")

    def detect_vehicles(self, frame, **kwargs):
        """Run detection on dedicated CUDA stream"""
        with torch.cuda.stream(self.stream):
            results = self.vehicle_model.predict(
                frame,
                conf=kwargs.get('confidence_threshold', 0.4),
                iou=kwargs.get('nms_threshold', 0.5),
                classes=list(self.vehicle_classes.keys()),
                verbose=False,
                device=self.device,
                half=self.fp16,
                imgsz=self.input_size,
                stream=True  # Enable stream mode
            )
        return results
```

### Multi-Camera with Streams

```python
class MultiCameraALPR:
    def __init__(self):
        # Create separate detector instance per camera
        # Each detector gets its own CUDA stream
        self.rear_detector = YOLOv11Detector(..., stream_id=0)  # Plate camera
        self.front_detector = YOLOv11Detector(..., stream_id=1)  # Vehicle camera

    def process_frames(self, rear_frame, front_frame):
        # Both detections run in parallel on GPU
        rear_results = self.rear_detector.detect_vehicles(rear_frame)
        front_results = self.front_detector.detect_vehicles(front_frame)

        # Synchronize before returning
        torch.cuda.synchronize()

        return rear_results, front_results
```

---

## 8. Confidence Threshold Tuning

**Expected gain**: 5-15% FPS (fewer post-processing operations)
**Enterprise impact**: ✅ **RECOMMENDED** - Reduces false positives and speeds up NMS

### How Confidence Affects Performance

Higher confidence threshold:
- ✅ Fewer detections to process (faster NMS - Non-Maximum Suppression)
- ✅ Fewer false positives (cleaner results)
- ✅ Less OCR processing (only high-confidence plates)
- ⚠️ May miss some valid detections if set too high

### Recommended Thresholds for Parking Gates

```python
# Vehicle detection (close range, clear view)
vehicle_confidence = 0.6  # Up from default 0.4
# Rationale: Vehicles at gates are close and clear,
# high confidence ensures only real vehicles trigger processing

# Plate detection
plate_confidence = 0.65  # Up from default 0.6
# Rationale: Only process clearly visible plates,
# reduces OCR load on partial/unclear plates
```

### Implementation

Edit `pilot.py` in the `process_frame` method:

```python
def process_frame(self, frame):
    # Detect vehicles with higher confidence
    vehicles = self.detector.detect_vehicles(
        frame,
        confidence_threshold=0.6,  # <-- Increase from 0.4
        nms_threshold=0.5
    )

    # Extract vehicle bboxes for plate detection
    vehicle_bboxes = [v.bbox for v in vehicles] if vehicles else None

    # Detect plates with higher confidence
    plates = self.detector.detect_plates(
        frame,
        vehicle_bboxes=vehicle_bboxes,
        confidence_threshold=0.65,  # <-- Increase from 0.6
        nms_threshold=0.4
    )
```

### Testing and Tuning

**Process**:
1. Start with conservative thresholds (0.4 vehicle, 0.6 plate)
2. Gradually increase and test on real parking gate footage
3. Monitor detection rate (must remain 100%)
4. Find highest threshold that maintains full detection

```bash
# Test on recorded video
python pilot.py --model yolo11n.engine --save-output

# Review output/ folder for missed vehicles
# Adjust thresholds accordingly
```

---

## 9. Headless Mode (No Display)

**Expected gain**: 5-10% GPU/CPU resources
**Enterprise impact**: ✅ **REQUIRED FOR PRODUCTION**

### What is Headless Mode?

**Headless mode** means running without GUI display (no OpenCV windows, no visualization).

**Why disable display in production?**
1. **GPU resources**: Drawing bounding boxes, text, and rendering uses GPU
2. **CPU overhead**: Window management, event handling adds latency
3. **Memory**: Frame buffers for display consume RAM
4. **Stability**: No risk of GUI crashes affecting detection
5. **Deployment**: Production servers rarely have displays attached

### Current Implementation

```bash
# Run with display (development/testing)
python pilot.py

# Run headless (production)
python pilot.py --no-display
```

### What Happens in Headless Mode

```python
if not self.no_display:
    # Display window exists - render visualizations
    cv2.rectangle(annotated_frame, ...)  # Draw boxes
    cv2.putText(annotated_frame, ...)     # Draw text
    cv2.imshow('ALPR', annotated_frame)   # Show window
    cv2.waitKey(1)                         # Process events
else:
    # Headless - skip all visualization
    # Results still logged, events still triggered
    pass
```

**Enterprise deployment**: Always use `--no-display` in production. Use web dashboard or API for monitoring instead.

---

## 10. Memory Optimization

**Expected gain**: Reduced latency, better multi-camera performance
**Enterprise impact**: ✅ **RECOMMENDED** - Critical for 24/7 operation

### Why Pre-allocate Buffers?

**Problem with dynamic allocation**:
```python
# Bad: Creates new array every frame
for frame in video:
    processed = np.zeros((720, 1280, 3))  # Allocation overhead!
    # ... process frame
```

**Issue**: Python's garbage collector runs periodically, causing:
- Latency spikes (50-200ms pauses)
- Memory fragmentation over time
- Unpredictable performance

**Solution**: Pre-allocate buffers once, reuse forever.

### Implementation

```python
class OptimizedALPRPilot(ALPRPilot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pre-allocate frame buffers (one per camera)
        self.frame_buffer = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.annotated_buffer = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Pre-allocate plate crop buffers (max 5 plates per frame)
        self.plate_buffers = [
            np.zeros((200, 400, 3), dtype=np.uint8)
            for _ in range(5)
        ]

        logger.info("Pre-allocated memory buffers for zero-copy operation")

    def process_stream(self):
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            # Copy to pre-allocated buffer (faster than creating new array)
            np.copyto(self.frame_buffer, frame)

            # Process using buffer
            results = self.process_frame(self.frame_buffer)

            # Annotate using pre-allocated buffer
            if not self.no_display:
                np.copyto(self.annotated_buffer, self.frame_buffer)
                self.draw_detections(self.annotated_buffer, results)
                cv2.imshow('ALPR', self.annotated_buffer)
```

### Additional Memory Optimizations

**1. Limit result history**:
```python
from collections import deque

# Instead of unlimited list
# self.results = []

# Use fixed-size deque (keeps only last N results)
self.results = deque(maxlen=100)  # Keep only last 100 frames
```

**2. Lazy OCR result storage**:
```python
# Only store successful OCR results, not every attempt
if ocr_confidence > 0.7:
    self.store_result(plate_text, vehicle_id)
```

**3. Periodic cleanup**:
```python
import gc

# Every 1000 frames, force garbage collection
if frame_count % 1000 == 0:
    gc.collect()
    torch.cuda.empty_cache()  # Clear GPU cache
```

---

## 11. Multi-Camera Batching (ENTERPRISE CRITICAL)

**Expected gain**: 2-3x throughput for multiple cameras
**Enterprise impact**: ✅ **ESSENTIAL** - Required for dual-camera architecture

### Batch Processing Explained

Instead of processing cameras sequentially:

**Sequential** (slow):
```
Camera 1: Detect → Wait 15ms
Camera 2: Detect → Wait 15ms
Total: 30ms for 2 cameras
```

**Batched** (fast):
```
Cameras 1+2: Detect both together → Wait 18ms
Total: 18ms for 2 cameras (1.7x faster!)
```

### Why Batching Works

GPUs are **massively parallel**. A single detection only uses ~40% of GPU. Batching 2-4 frames together:
- Saturates GPU utilization (80-95%)
- Amortizes kernel launch overhead
- Better memory bandwidth utilization

### Implementation: Batch Detection

Update `edge-services/detector/detector_service.py`:

```python
def detect_vehicles_batch(
    self,
    frames: List[np.ndarray],
    confidence_threshold: float = 0.6,
    nms_threshold: float = 0.5
) -> List[List[VehicleDetection]]:
    """
    Batch vehicle detection for multiple frames/cameras

    Args:
        frames: List of frames (numpy arrays) from different cameras
        confidence_threshold: Minimum confidence score
        nms_threshold: NMS IoU threshold

    Returns:
        List of detection lists (one per input frame)
    """
    if not frames:
        return []

    start_time = time.time()
    batch_size = len(frames)

    # Run batched inference
    results = self.vehicle_model.predict(
        frames,  # List of frames
        conf=confidence_threshold,
        iou=nms_threshold,
        classes=list(self.vehicle_classes.keys()),
        verbose=False,
        device=self.device,
        half=self.fp16,
        imgsz=self.input_size,
        batch=batch_size  # Batch size
    )

    # Parse results for each frame
    all_detections = []
    for result in results:
        frame_detections = []
        boxes = result.boxes

        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            cls_id = int(box.cls[0].cpu().numpy())
            conf = float(box.conf[0].cpu().numpy())

            detection = VehicleDetection(
                vehicle_type=self.vehicle_classes.get(cls_id, 'vehicle'),
                bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                confidence=conf
            )
            frame_detections.append(detection)

        all_detections.append(frame_detections)

    inference_time = (time.time() - start_time) * 1000
    logger.debug(
        f"Batch detection: {sum(len(d) for d in all_detections)} vehicles "
        f"in {batch_size} frames ({inference_time:.1f}ms)"
    )

    return all_detections
```

### Dual-Camera Integration

```python
class DualCameraALPR:
    """
    Enterprise dual-camera ALPR system
    - Camera 1: Rear plate camera (ALPR focus)
    - Camera 2: Front overview camera (vehicle attributes)
    """

    def __init__(self, rear_camera_config, front_camera_config):
        # Initialize cameras
        self.rear_camera = CameraManager(rear_camera_config)
        self.front_camera = CameraManager(front_camera_config)

        # Single detector instance for batch processing
        self.detector = YOLOv11Detector(
            vehicle_model_path="yolo11n.pt",
            use_tensorrt=True,
            fp16=False,
            int8=True,
            input_size=416,
            batch_size=2  # Batch size = number of cameras
        )

        # Async OCR for parallel processing
        self.ocr = AsyncOCRService(PaddleOCRService(), num_workers=2)

        # Tracking per camera
        self.rear_tracker = ByteTracker()
        self.front_tracker = ByteTracker()

    def process_frame_pair(self):
        """Process frames from both cameras in parallel"""
        # Capture frames from both cameras
        rear_frame = self.rear_camera.get_frame()
        front_frame = self.front_camera.get_frame()

        if rear_frame is None or front_frame is None:
            return None

        # Batch detection (both cameras processed together)
        detections = self.detector.detect_vehicles_batch(
            [rear_frame, front_frame],
            confidence_threshold=0.6
        )

        rear_vehicles, front_vehicles = detections[0], detections[1]

        # Track vehicles in each camera
        rear_tracked = self.rear_tracker.update(rear_vehicles)
        front_tracked = self.front_tracker.update(front_vehicles)

        # Detect plates on rear camera (primary ALPR)
        rear_plates = self.detector.detect_plates(
            rear_frame,
            vehicle_bboxes=[v.bbox for v in rear_vehicles],
            confidence_threshold=0.65
        )

        # Queue OCR processing (async)
        for vehicle_idx, plate_bboxes in rear_plates.items():
            for plate_bbox in plate_bboxes:
                plate_img = self._extract_plate(rear_frame, plate_bbox)
                metadata = {
                    'camera': 'rear',
                    'vehicle_id': rear_tracked[vehicle_idx].track_id,
                    'timestamp': time.time()
                }
                self.ocr.process_plate_async(
                    plate_img,
                    metadata,
                    self._handle_plate_result
                )

        # Optionally: Extract vehicle attributes from front camera
        # (make, model, color detection can go here)

        return {
            'rear': {'vehicles': rear_tracked, 'plates': rear_plates},
            'front': {'vehicles': front_tracked}
        }

    def _extract_plate(self, frame, bbox):
        """Extract plate region from frame"""
        x1, y1, x2, y2 = map(int, [bbox.x1, bbox.y1, bbox.x2, bbox.y2])
        return frame[y1:y2, x1:x2]

    def _handle_plate_result(self, ocr_result, metadata):
        """Callback for OCR results"""
        logger.info(
            f"Plate detected: {ocr_result['text']} "
            f"(confidence: {ocr_result['confidence']:.2f})"
        )
        # Store to database, trigger events, etc.
```

---

## 12. Jetson Power Mode (MANDATORY FOR PRODUCTION)

**Expected gain**: 15-25% performance
**Enterprise impact**: ✅ **REQUIRED** - Must run in max performance mode

### Jetson Power Modes

Jetson has multiple power profiles balancing performance vs power consumption:

| Mode | Description | Max Power | Use Case |
|------|-------------|-----------|----------|
| Mode 0 | MAXN - Maximum performance | 25W | Production ALPR |
| Mode 1 | 15W mode | 15W | Power-constrained |
| Mode 2 | 10W mode | 10W | Battery operation |

**Enterprise requirement**: Always use **Mode 0 (MAXN)** for parking gate deployment.

### Setup Commands

```bash
# Check current power mode
sudo nvpmodel -q

# Set to MAXN mode (maximum performance)
sudo nvpmodel -m 0

# Lock clocks to maximum (disable dynamic frequency scaling)
sudo jetson_clocks

# Verify clocks are maxed
sudo jetson_clocks --show

# Make settings persistent across reboots
sudo systemctl enable nvpmodel
sudo systemctl start nvpmodel
```

### Monitoring Temperature

Max performance generates more heat. Monitor thermal state:

```bash
# Real-time stats (every 500ms)
tegrastats --interval 500

# Look for:
# - GPU utilization (should be 60-90% during processing)
# - Temperature (should stay below 80°C)
# - Power draw (should be near 25W under load)
```

**Enterprise guideline**: Install active cooling (fan) if temperature exceeds 75°C during sustained operation.

### Expected Performance Impact

| Configuration | FPS | Notes |
|---------------|-----|-------|
| Default power mode | 45 FPS | Variable clocks |
| + MAXN mode | 55 FPS | +22% improvement |
| + jetson_clocks | 60 FPS | +33% improvement |

---

## Complete Enterprise Optimization Stack

### Recommended Configuration for Parking Gates

**Hardware**:
- Jetson Orin NX 16GB (pilot/single-lane)
- Jetson Orin or AGX Orin (production/multi-lane)
- Active cooling fan
- Dual cameras: Rear (plate) + Front (vehicle)

**Software configuration** (`pilot.py`):
```python
self.detector = YOLOv11Detector(
    vehicle_model_path=detector_model,
    plate_model_path=plate_model,
    use_tensorrt=True,
    fp16=False,
    int8=True,           # ✅ INT8 quantization
    batch_size=2,        # ✅ Dual camera batching
    input_size=416       # ✅ Optimized for close-range
)

# Async OCR for parallel processing
self.ocr = AsyncOCRService(base_ocr, num_workers=2)

# Higher confidence for parking gates
vehicle_conf = 0.6     # ✅ Fewer false positives
plate_conf = 0.65      # ✅ Only clear plates
```

**System setup**:
```bash
# Max performance mode
sudo nvpmodel -m 0
sudo jetson_clocks

# Calibrate INT8 with parking gate footage
# (See INT8_PRECISION_GUIDE.md)
```

**Runtime command**:
```bash
# Production deployment
python pilot.py \
  --skip-frames 2 \      # Process every 3rd frame
  --no-display \         # Headless mode
  --config config/dual_camera.yaml
```

---

## Performance Benchmarking

### Measure Your FPS

Add comprehensive FPS counter to `pilot.py`:

```python
import time
from collections import deque

class PerformanceMonitor:
    """Monitor FPS and latency for enterprise deployments"""

    def __init__(self, window_size=30):
        self.timestamps = deque(maxlen=window_size)
        self.latencies = deque(maxlen=window_size)

    def update(self, latency_ms=None):
        """Update with new frame"""
        self.timestamps.append(time.time())
        if latency_ms is not None:
            self.latencies.append(latency_ms)

    def get_fps(self):
        """Calculate current FPS"""
        if len(self.timestamps) < 2:
            return 0
        return len(self.timestamps) / (self.timestamps[-1] - self.timestamps[0])

    def get_avg_latency(self):
        """Calculate average latency"""
        if not self.latencies:
            return 0
        return sum(self.latencies) / len(self.latencies)

    def get_stats(self):
        """Get comprehensive stats"""
        return {
            'fps': self.get_fps(),
            'avg_latency_ms': self.get_avg_latency(),
            'min_latency_ms': min(self.latencies) if self.latencies else 0,
            'max_latency_ms': max(self.latencies) if self.latencies else 0,
        }

# In ALPRPilot.__init__:
self.perf_monitor = PerformanceMonitor()

# In main loop:
start_time = time.time()
results = self.process_frame(frame)
latency_ms = (time.time() - start_time) * 1000

self.perf_monitor.update(latency_ms)

# Log stats every 30 frames
if frame_count % 30 == 0:
    stats = self.perf_monitor.get_stats()
    logger.info(
        f"Performance: {stats['fps']:.1f} FPS, "
        f"Latency: {stats['avg_latency_ms']:.1f}ms "
        f"(min: {stats['min_latency_ms']:.1f}, "
        f"max: {stats['max_latency_ms']:.1f})"
    )
```

---

## Expected Results (Enterprise Configuration)

### Single Camera - Parking Gate (Jetson Orin NX)

| Configuration | FPS | Latency | Pipeline |
|--------------|-----|---------|----------|
| Baseline (FP16, 640x640) | 22 | 45ms | Detection + OCR + Tracking |
| + INT8 | 55 | 18ms | Full pipeline |
| + Resolution 416x416 | 70 | 14ms | Full pipeline |
| + Async OCR | 85 | 12ms | Full pipeline |
| + Confidence tuning | 90 | 11ms | Full pipeline |
| + MAXN mode | **100** | **10ms** | **Full pipeline** ✓ |

### Dual Camera - Parking Gate (Jetson Orin)

| Configuration | FPS (per camera) | Total Throughput | Latency |
|--------------|------------------|------------------|---------|
| Sequential processing | 45 | 45 FPS | 22ms |
| + Batch processing | 75 | 150 FPS | 13ms |
| + All optimizations | **100+** | **200+ FPS** | **10ms** |

---

## Optimization Priority for Enterprise

Implement in this order for maximum impact:

1. ✅ **INT8 Quantization** - 3x improvement, highest priority
2. ✅ **Jetson MAXN Mode** - 25% improvement, zero code changes
3. ✅ **Resolution 416x416** - 60% improvement for parking gates
4. ✅ **Async OCR Pipeline** - 2x FPS with OCR enabled
5. ✅ **Multi-Camera Batching** - 2x throughput for dual cameras
6. ✅ **Confidence Tuning** - 10-15% improvement
7. ✅ **GPU Streams** - 10-20% for multi-camera
8. ✅ **Memory Optimization** - Stability for 24/7 operation
9. ✅ **Headless Mode** - Required for production
10. ✅ **Frame Skipping** - Test to find optimal rate

---

## Monitoring and Profiling

### Real-time GPU Monitoring

```bash
# Monitor GPU utilization, memory, temperature
watch -n 0.5 tegrastats

# Log to file for analysis
tegrastats --interval 500 --logfile alpr_performance.log
```

### Profile with NVIDIA Nsight Systems

```bash
# Install profiler
sudo apt-get install nvidia-nsight-systems

# Profile application
nsys profile --trace=cuda,nvtx,osrt -o alpr_profile python pilot.py

# Analyze results
nsys-ui alpr_profile.qdrep
```

### Key Metrics to Monitor

**Performance**:
- FPS: Target 60-100 FPS (full pipeline)
- Latency: Target <20ms per frame
- GPU utilization: Target 70-90%

**Quality**:
- Detection rate: Must be 100% (no missed vehicles)
- OCR accuracy: Target >95%
- False positive rate: Target <5%

**System health**:
- Temperature: Keep below 80°C
- Memory usage: Keep below 12GB (leave headroom)
- Power draw: Should be near 25W under load

---

## Trade-off Matrix (Enterprise Focus)

| Optimization | FPS Gain | OCR/Tracking Impact | Complexity | Enterprise Priority |
|--------------|----------|---------------------|------------|-------------------|
| INT8 | +++++ | None ✓ | Low | **CRITICAL** |
| Resolution 416 | ++++ | Minimal ✓ | Low | **HIGH** |
| Async OCR | ++++ | None ✓ | Medium | **CRITICAL** |
| Multi-camera batch | ++++ | None ✓ | Medium | **HIGH** |
| MAXN mode | +++ | None ✓ | Low | **REQUIRED** |
| GPU streams | ++ | None ✓ | Medium | **MEDIUM** |
| Confidence tuning | ++ | None ✓ | Low | **MEDIUM** |
| Memory optimization | + | None ✓ | Medium | **HIGH** |
| Headless mode | + | None ✓ | Low | **REQUIRED** |

**Legend**: + (small), ++ (medium), +++ (large), ++++ (very large), +++++ (extreme)

---

## Troubleshooting

### FPS Lower Than Expected

1. **Check TensorRT**: Verify `.engine` file exists
   ```bash
   ls -lh *.engine
   ```

2. **Verify INT8 active**: Check logs for "INT8" during export

3. **Check power mode**:
   ```bash
   sudo nvpmodel -q  # Should show mode 0
   ```

4. **Monitor thermal throttling**:
   ```bash
   tegrastats  # Temp should be <80°C
   ```

### OCR Bottleneck

1. **Check async queue**: Verify OCR is not blocking
   ```python
   logger.info(f"OCR queue size: {self.ocr.queue.qsize()}")
   ```

2. **Increase workers**: Add more OCR threads
   ```python
   AsyncOCRService(base_ocr, num_workers=4)  # From 2 to 4
   ```

3. **Optimize OCR engine**: Consider lighter OCR model

### Missed Detections

1. **Lower confidence**: May be too high
   ```python
   confidence_threshold=0.5  # From 0.6
   ```

2. **Check calibration**: INT8 may need better calibration data

3. **Increase resolution**: May need 640x640 instead of 416x416

---

## Migration Path: Orin NX → Orin/AGX

### When to Upgrade

Upgrade from Orin NX to Orin/AGX when:
- Need >100 FPS sustained throughput
- Processing 4+ camera streams
- Adding vehicle attribute detection (make/model/color)
- Require higher resolution (640x640 or 1280x1280)

### Platform Comparison

| Feature | Orin NX | Orin | AGX Orin |
|---------|---------|------|----------|
| GPU cores | 1024 | 1792 | 2048 |
| Max power | 25W | 40W | 60W |
| Memory | 16GB | 32GB | 64GB |
| FPS (416x416) | 80-100 | 150-200 | 200-250 |
| FPS (640x640) | 50-70 | 100-120 | 150-180 |
| Camera streams | 2 | 4-6 | 8+ |
| Price | $ | $$ | $$$ |

### Migration Steps

1. **Develop on Orin NX** with 416x416 resolution
2. **Validate** parking gate use case
3. **Upgrade to Orin/AGX** for production
4. **Increase resolution** to 640x640 or higher
5. **Add features**: Make/model/color detection

**No code changes needed** - same software stack runs on all Jetson platforms!

---

## Additional Resources

- [Jetson Orin Developer Guide](https://developer.nvidia.com/embedded/jetson-orin)
- [TensorRT Best Practices](https://docs.nvidia.com/deeplearning/tensorrt/best-practices/)
- [Ultralytics Performance Optimization](https://docs.ultralytics.com/guides/speed-optimization/)
- [INT8 Calibration Guide](./INT8_PRECISION_GUIDE.md)

---

## Summary

**For enterprise parking gate deployment**, focus on these optimizations:

✅ **Must implement**:
1. INT8 quantization (3x FPS)
2. Jetson MAXN mode (25% FPS)
3. Async OCR pipeline (2x FPS with OCR)
4. Headless mode (production requirement)

✅ **Highly recommended**:
5. Resolution 416x416 (60% FPS for close-range)
6. Multi-camera batching (2x throughput)
7. Confidence tuning (10-15% FPS)
8. Memory optimization (stability)

✅ **Optional (test first)**:
9. Frame skipping (validate detection rate)
10. GPU streams (for multi-camera)

**Expected result**: 60-100 FPS on Jetson Orin NX with **full OCR + Tracking** pipeline ✓

**Remember**: Enterprise ALPR requires 100% vehicle detection and >95% OCR accuracy. Always validate optimizations against these requirements using real parking gate footage.
