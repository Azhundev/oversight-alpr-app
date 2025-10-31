# YOLOv11 Custom Plate Detector Training Summary

## Training Details
- **Date**: October 23, 2025
- **Model**: YOLOv11n (nano)
- **Task**: License plate detection
- **Platform**: NVIDIA Jetson Orin NX

## Dataset
- **Total Images**: 94 (after cleaning)
  - Training: 75 images
  - Validation: 19 images
- **Source**: Extracted from video footage (IMG_6930, IMG_6941, etc.)
- **Dataset Path**: `datasets/plate_training_round2/`
- **Annotations Reviewed**: Yes (using advanced annotation review tool)

## Training Configuration
```
Epochs: 100
Image Size: 416x416
Batch Size: 4
Workers: 2
Optimizer: AdamW (lr=0.002, momentum=0.9)
Model: yolo11n.pt (pretrained)
Device: CUDA (Jetson Orin)
Precision: FP16 (AMP enabled)
Training Time: 0.152 hours (~9 minutes)
```

## Results
### Final Validation Metrics (Best Model)
- **Precision**: 91.8%
- **Recall**: 92.2%
- **mAP@50**: 93.5%
- **mAP@50-95**: 66.5%

### Model Files
- **Best Weights**: `runs/detect/train2/weights/best.pt`
- **Last Weights**: `runs/detect/train2/weights/last.pt`
- **Deployed Model**: `models/yolo11n-plate-custom.pt`

## Deployment
The trained model has been integrated into the OVR-ALPR system:
- **Location**: `models/yolo11n-plate-custom.pt`
- **Usage**: `python3 pilot.py --plate-model models/yolo11n-plate-custom.pt`

## Performance Notes
- Model achieves excellent precision/recall on Florida license plates
- Training converged well without overfitting
- Model size: 5.2MB (optimized for Jetson deployment)
- Inference speed: ~30-50ms per image on Jetson Orin NX

## Next Steps
1. ✅ Model trained and validated
2. ✅ Model deployed to production directory
3. ✅ System tested with new model
4. 🔲 Optional: Export to TensorRT for faster inference
5. 🔲 Optional: Collect more training data for improved accuracy
