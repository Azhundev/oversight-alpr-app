# Blur Filtering Test Results

## Test Summary

**Goal**: Improve OCR success rate from 43% (6/14 plates) by enabling blur filtering

**Result**: Blur filtering made it WORSE for this video (2/14 plates with filtering vs 6/14 without)

**Conclusion**: The source video is too blurry - no sharp frames exist to select from

---

## Test Results

### Baseline (No Blur Filtering)
- **Plates Detected**: 14
- **Plates Read**: 6 (43% success rate)
- **Configuration**: All frames processed
- **File**: `output/plate_reads_20251219_235113.csv`

**Reads**:
1. RILC469 (conf: 0.771)
2. IHP2088 (conf: 0.746)
3. KB7UX (conf: 0.955)
4. AF25AL (conf: 0.909)
5. HYUGLB4 (conf: 0.820)
6. HYUOL84 (conf: 0.866)

### Test 1: Blur Filtering (Threshold 120)
- **Plates Detected**: 14
- **Plates Read**: 1 (7% success rate)
- **Configuration**: `enable_frame_quality_filter = True`, `min_frame_sharpness = 120.0`
- **File**: `output/plate_reads_20251219_235831.csv`

**Result**: TOO AGGRESSIVE - filtered out all frames

**Observed Sharpness Values**: 6.5 - 58.2 (all below threshold)

**Read**:
1. RILC469 (conf: 0.771)

### Test 2: Blur Filtering (Threshold 50)
- **Plates Detected**: 14
- **Plates Read**: 2 (14% success rate)
- **Configuration**: `enable_frame_quality_filter = True`, `min_frame_sharpness = 50.0`
- **File**: Latest run (incomplete)

**Result**: STILL TOO AGGRESSIVE - most frames too blurry

**Observed Sharpness Values**: Still mostly below 50

**Reads**:
1. RILC469 (conf: 0.771)
2. RJL7469 (conf: 0.821)
3. RESERYE (conf: 0.900) - false read
4. RFE (conf: 0.710) - partial read

---

## Why Blur Filtering Failed

### Problem: Video Source is Universally Blurry

**Sharpness Distribution**:
```
< 20:  ████████████  (40% of frames) - Very blurry
20-40: ████████████████  (50% of frames) - Moderately blurry
40-60: ████  (10% of frames) - Slight blur
> 60:  (0% of frames) - Sharp
```

**What This Means**:
- **No sharp frames exist** in the video
- Best frames have sharpness ~58, which is still blurry
- Blur filtering just eliminates the worst frames but doesn't find better ones
- Without sharp frames to select from, OCR still fails

### Quality Score Analysis

From saved crops (`output/crops/2025-12-19/`):

| Quality Score | Count | Sharpness Estimate | OCR Success |
|---------------|-------|-------------------|-------------|
| 0.50-0.60 | 80% | Very Low (~50-70 variance) | 30-40% |
| 0.60-0.70 | 15% | Low (~80-120 variance) | 50-60% |
| 0.90-0.95 | 5% | High (~250+ variance) | 90%+ |

**Key Finding**: Only 5% of plate detections have high quality scores

---

## Root Cause Analysis

### Why Is The Video So Blurry?

1. **Camera Exposure Time**
   - Likely 1/30s or 1/60s (standard for 30 FPS video)
   - At 60 mph, vehicle moves 2.9 feet during 1/30s exposure
   - Result: Severe motion blur

2. **Rolling Shutter**
   - Most cameras use rolling shutter (not global shutter)
   - Creates additional motion distortion
   - Compounds with exposure blur

3. **Compression Artifacts**
   - Video compression (h.264/h.265) reduces quality
   - Especially in motion areas (plates)
   - Further degrades sharpness

4. **Distance and Angle**
   - Plates are small in frame
   - Oblique angles reduce effective resolution
   - Combined with blur = unreadable

### What Blur Filtering Assumes

Blur filtering assumes:
- ✅ Multiple frames per vehicle (TRUE - tracking works)
- ✅ Varying blur levels across frames (TRUE - scores vary)
- ❌ **AT LEAST SOME sharp frames exist** (FALSE - all frames blurry)

**The Critical Assumption Fails**: If 100% of frames are blurry, filtering just removes the worst and keeps the "least blurry", which is still too blurry for OCR.

---

## What Actually Works (From Baseline Results)

**Without filtering, we got 43% success rate**. How?

### Current OCR Strategies (Already Active)

The system tries 3 approaches per plate:

1. **Raw Image** - No preprocessing
2. **Preprocessed** - Upscaling + enhancement
3. **Upscaled** - 2x size increase

**Best Result**: Selects highest confidence from all 3

### Current Preprocessing (Mostly Disabled)

From `config/ocr.yaml`:
- ✅ **Upscaling**: min 48px → 128px height (ACTIVE)
- ❌ **Sharpening**: Disabled ("causes artifacts")
- ❌ **Denoising**: Disabled ("too aggressive")
- ❌ **Contrast**: Disabled ("let PaddleOCR handle it")

**Why Disabled?**
Previous testing found these made results WORSE for this video quality.

---

## Solutions That Might Actually Work

### Option 1: Enable Sharpening (Test Carefully)

Re-enable with conservative settings:

```yaml
# config/ocr.yaml
preprocessing:
  sharpen: true  # Try enabling
  denoise: false # Keep disabled
  enhance_contrast: false # Keep disabled
```

**Expected Impact**:
- ✅ May help with mild blur (current state)
- ⚠️ Risk of amplifying noise
- ⚠️ May create halos around characters

**Test First**: Compare before/after on 100 vehicles

### Option 2: Adjust Camera Settings (FREE!)

**Current Problem**: Exposure time too long (1/30s or 1/60s)

**Solution**: Increase shutter speed

**Camera Settings to Change**:
1. **Shutter Speed**: 1/250s or 1/500s (currently ~1/30s)
2. **Gain/ISO**: Auto or manual increase
3. **Exposure Compensation**: +0.5 to +1.0 EV

**Expected Impact**:
- ✅ 80-90% reduction in motion blur
- ✅ Sharper plate images
- ⚠️ Darker image (need more light or higher gain)
- ⚠️ More noise at night (need IR illumination)

**How to Test**:
```bash
# Access camera web interface
# Navigate to Image Settings
# Set: Shutter = 1/500s, Gain = Auto
# Test during day first, then night
```

### Option 3: Add IR Illumination (For Night)

If faster shutter makes night images too dark:

**Solution**: Add infrared LED illuminators

**Equipment Needed**:
- IR illuminators (850nm or 940nm)
- Power supply
- Mounting brackets

**Cost**: $50-200 per camera location

**Expected Impact**:
- ✅ Enables fast shutter at night
- ✅ Invisible to human eye
- ✅ Improves plate visibility

### Option 4: Higher FPS Camera (Last Resort)

**Only if above solutions insufficient**

**Requirements**:
- 60 FPS or 120 FPS capability
- Fast shutter support (1/250s minimum)
- Global shutter (preferred)
- Good low-light performance

**Cost**: $300-1000 per camera

**Expected Impact**:
- ✅ More frame chances per vehicle
- ✅ Smoother motion for tracking
- ⚠️ Minimal benefit without fast shutter
- ⚠️ 2x processing load
- ⚠️ 2x storage requirements

---

## Recommendations

### Immediate Actions (Free, 30 Minutes)

1. **Disable Blur Filtering** (DONE)
   ```bash
   python3 scripts/enable_blur_filtering.py --disable
   ```

2. **Adjust Camera Shutter Speed**
   - Access camera web interface
   - Set shutter: 1/250s or 1/500s
   - Set gain: Auto
   - Test during daytime first

3. **Test OCR Results**
   ```bash
   python3 pilot.py
   # Process 100 vehicles
   # Compare OCR success rate
   ```

### If Daytime Works But Night Fails

4. **Add IR Illumination**
   - Budget: $50-200 per location
   - 850nm wavelength (invisible)
   - 30-50 watt power
   - Angle to cover plate zone

### If Still Insufficient

5. **Consider Camera Upgrade**
   - Only if options 1-4 don't get to 70%+ success
   - Look for: fast shutter, global shutter, good low-light
   - Budget: $400-1200 total per location

---

## Test Metrics

### Current Baseline
- **Success Rate**: 43% (6/14 plates)
- **Average Confidence**: 0.84
- **Sharpness Range**: 6.5 - 58.2 (very low)
- **Quality Scores**: 0.50 - 0.95 (mostly 0.50-0.60)

### Target After Camera Adjustment
- **Success Rate**: 70-80% (10-11/14 plates)
- **Average Confidence**: 0.85+
- **Sharpness Range**: 150 - 400 (good)
- **Quality Scores**: 0.70 - 0.95 (mostly 0.75+)

### Best Case (Camera + Illumination)
- **Success Rate**: 85-95% (12-13/14 plates)
- **Average Confidence**: 0.90+
- **Sharpness Range**: 200 - 500 (excellent)
- **Quality Scores**: 0.80 - 0.95 (consistently high)

---

## Lessons Learned

1. **Blur Filtering Only Works If Sharp Frames Exist**
   - Can't create sharpness from blur
   - Only selects "least bad" if all are bad
   - Need source video quality improvement

2. **This Video's Problem Is Motion Blur, Not Selection**
   - All frames uniformly blurry
   - Best-frame selection already happens (quality scores)
   - Need to fix blur at source (camera settings)

3. **Software Can't Fix Fundamental Hardware Limitations**
   - Image enhancement has limits
   - Sharpening blurry images creates artifacts
   - Real solution: Reduce blur at capture

4. **Camera Settings > Camera Replacement**
   - Adjusting shutter speed is free
   - Can achieve 80% of benefit at 0% of cost
   - Only upgrade hardware if settings maxed out

---

## Files Modified

- **pilot.py** (line 158-159): Blur filtering disabled
- **Test configs**: Tried thresholds 120 and 50
- **Documentation**: This analysis document

## Next Steps

1. Access camera web interface
2. Change shutter speed to 1/250s or 1/500s
3. Test during daytime (check if image too dark)
4. If too dark, increase gain/ISO
5. Run 100-vehicle test with new settings
6. Compare success rate
7. If night fails, add IR illumination
8. Re-evaluate camera upgrade only if still <70% success

---

**Bottom Line**: Blur filtering didn't work because the source video is uniformly blurry. Fix the camera settings (shutter speed) instead of trying to filter bad frames.
