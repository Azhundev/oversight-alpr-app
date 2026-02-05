"""
Detector Service Package

This package provides YOLO-based object detection for the ALPR pipeline.

Main Components:
- YOLOv11Detector: Dual-model detector for vehicles and license plates
  - Vehicle detection: YOLOv11 trained on COCO vehicle classes (car, truck, bus, motorcycle)
  - Plate detection: YOLOv11 custom model trained specifically for license plate localization

Features:
- TensorRT optimization for Jetson hardware acceleration (2-3x speedup with FP16)
- GPU inference with CUDA backend
- Automatic warmup iterations for consistent inference times
- Configurable confidence thresholds and NMS parameters

Usage:
    from services.detector import YOLOv11Detector

    detector = YOLOv11Detector(
        vehicle_model_path="models/yolov11n.pt",
        plate_model_path="models/yolov11n-plate.pt",
        use_tensorrt=True,
        fp16=True
    )

    vehicle_detections, plate_detections = detector.detect(frame)
"""
