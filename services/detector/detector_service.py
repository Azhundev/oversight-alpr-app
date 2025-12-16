"""
YOLOv11 Detector Service
Optimized for NVIDIA Jetson Orin NX with TensorRT
"""

import cv2
import numpy as np
import torch
from ultralytics import YOLO
from loguru import logger
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import time

from shared.schemas.event import BoundingBox, VehicleDetection


class YOLOv11Detector:
    """
    YOLOv11 detector for vehicles and license plates
    Optimized for Jetson Orin NX with TensorRT acceleration
    """

    def __init__(
        self,
        vehicle_model_path: str = "yolo11n.pt",
        plate_model_path: Optional[str] = None,
        device: str = "cuda:0",
        use_tensorrt: bool = True,
        fp16: bool = True,
        int8: bool = False,
        batch_size: int = 1,
    ):
        """
        Initialize YOLO detector

        Args:
            vehicle_model_path: Path to YOLOv11 vehicle detection model
            plate_model_path: Optional path to custom plate detection model
            device: Device to run on (cuda:0 for Jetson)
            use_tensorrt: Enable TensorRT optimization
            fp16: Use FP16 precision for faster inference
            int8: Use INT8 precision for even faster inference (requires calibration)
            batch_size: Batch size for inference
        """
        self.device = device
        self.use_tensorrt = use_tensorrt
        self.fp16 = fp16
        self.int8 = int8
        self.batch_size = batch_size

        # Vehicle classes from COCO dataset
        self.vehicle_classes = {
            2: 'car',
            3: 'motorcycle',
            5: 'bus',
            7: 'truck'
        }

        # Load vehicle detection model
        logger.info(f"Loading vehicle detection model: {vehicle_model_path}")
        self.vehicle_model = self._load_model(vehicle_model_path)

        # Load optional plate detection model
        self.plate_model = None
        if plate_model_path and Path(plate_model_path).exists():
            logger.info(f"Loading plate detection model: {plate_model_path}")
            self.plate_model = self._load_model(plate_model_path)
        else:
            logger.warning("No custom plate model provided, will use vehicle model for plate detection")

        logger.success("YOLOv11 detector initialized successfully")

    def _load_model(self, model_path: str) -> YOLO:
        """
        Load and optimize YOLO model

        Optimizes model for Jetson using TensorRT:
        - FP16: 2-3x faster than FP32, minimal accuracy loss
        - INT8: 3-4x faster, requires calibration dataset

        TensorRT engines are cached and reused across runs
        """

        # Check if TensorRT engine already exists (avoids re-export)
        if self.use_tensorrt and not model_path.endswith('.engine'):
            # Look for cached .engine file (same name as .pt model)
            engine_path = str(Path(model_path).with_suffix('.engine'))

            if Path(engine_path).exists():
                logger.info(f"Loading existing TensorRT engine: {engine_path}")
                model = YOLO(engine_path)
                return model
            else:
                logger.info(f"No existing TensorRT engine found, will create: {engine_path}")

        # Load PyTorch model (.pt format)
        model = YOLO(model_path)

        # Export to TensorRT if enabled (Jetson-specific optimization)
        # TensorRT significantly improves inference speed on Jetson hardware
        if self.use_tensorrt and not model_path.endswith('.engine'):
            try:
                if self.int8:
                    logger.info("Exporting model to TensorRT with INT8 precision...")
                    # INT8: Maximum speed but requires calibration data
                    # Uses representative dataset to determine quantization parameters
                    engine_path = model.export(
                        format='engine',
                        int8=True,
                        device=self.device,
                        batch=self.batch_size,
                        workspace=4,  # 4GB workspace for INT8 calibration
                        data='calibration.yaml',  # Calibration dataset from training videos
                        dynamic=False,  # Fixed input shapes for INT8 (required)
                        imgsz=640,  # Fixed input size 640x640
                    )
                else:
                    logger.info("Exporting model to TensorRT with FP16 precision...")
                    # FP16: Good balance of speed and accuracy for Jetson
                    # Provides 2-3x speedup with minimal accuracy loss
                    engine_path = model.export(
                        format='engine',
                        half=self.fp16,  # Enable FP16 precision
                        device=self.device,
                        batch=self.batch_size,
                        workspace=2,  # 2GB workspace for FP16 optimization
                    )
                logger.success(f"TensorRT engine created: {engine_path}")
                # Reload the optimized engine
                model = YOLO(engine_path)
            except Exception as e:
                logger.warning(f"TensorRT export failed: {e}. Using PyTorch model.")

        # Move PyTorch model to GPU (TensorRT engines don't support .to())
        if not str(model_path).endswith('.engine'):
            try:
                model.to(self.device)
            except:
                pass  # TensorRT models are already device-specific

        return model

    def detect_vehicles(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.4,
        nms_threshold: float = 0.5
    ) -> List[VehicleDetection]:
        """
        Detect vehicles in frame

        Args:
            frame: Input frame (BGR)
            confidence_threshold: Minimum confidence score
            nms_threshold: NMS IoU threshold

        Returns:
            List of VehicleDetection objects
        """
        start_time = time.time()

        # Run inference
        results = self.vehicle_model.predict(
            frame,
            conf=confidence_threshold,
            iou=nms_threshold,
            classes=list(self.vehicle_classes.keys()),
            verbose=False,
            device=self.device,
            half=self.fp16
        )

        detections = []
        for result in results:
            boxes = result.boxes

            for box in boxes:
                # Extract bbox coordinates
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()

                # Extract class and confidence
                cls_id = int(box.cls[0].cpu().numpy())
                conf = float(box.conf[0].cpu().numpy())

                # Create detection
                detection = VehicleDetection(
                    vehicle_type=self.vehicle_classes.get(cls_id, 'vehicle'),
                    bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    confidence=conf
                )
                detections.append(detection)

        inference_time = (time.time() - start_time) * 1000  # ms
        logger.debug(f"Vehicle detection: {len(detections)} vehicles in {inference_time:.1f}ms")

        return detections

    def detect_plates(
        self,
        frame: np.ndarray,
        vehicle_bboxes: Optional[List[BoundingBox]] = None,
        confidence_threshold: float = 0.6,
        nms_threshold: float = 0.4
    ) -> Dict[int, List[BoundingBox]]:
        """
        Detect license plates in frame

        Args:
            frame: Input frame (BGR)
            vehicle_bboxes: Optional list of vehicle bboxes to search within
            confidence_threshold: Minimum confidence score
            nms_threshold: NMS IoU threshold

        Returns:
            Dict mapping vehicle index to list of plate bboxes
        """
        start_time = time.time()

        # If no custom plate model, use contour-based detection
        if self.plate_model is None:
            return self._detect_plates_contour(frame, vehicle_bboxes)

        # Use custom plate detection model
        # Search entire frame since model was trained on full frames
        results = self.plate_model.predict(
            frame,
            conf=confidence_threshold,
            iou=nms_threshold,
            verbose=False,
            device=self.device,
            half=self.fp16,
            imgsz=416  # Plate model was trained at 416x416
        )

        # Collect all detected plates
        all_plate_bboxes = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                all_plate_bboxes.append(
                    BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
                )

        # Associate detected plates with their respective vehicles
        # Uses spatial matching based on plate center position
        plates = {}
        if vehicle_bboxes and all_plate_bboxes:
            for plate_bbox in all_plate_bboxes:
                # Find which vehicle this plate belongs to
                # Using center-point matching (faster than IoU for this use case)
                best_iou = 0
                best_vehicle_idx = None

                for idx, vehicle_bbox in enumerate(vehicle_bboxes):
                    # Calculate plate center point
                    plate_cx = (plate_bbox.x1 + plate_bbox.x2) / 2
                    plate_cy = (plate_bbox.y1 + plate_bbox.y2) / 2

                    # Check if plate center falls within vehicle bounding box
                    if (vehicle_bbox.x1 <= plate_cx <= vehicle_bbox.x2 and
                        vehicle_bbox.y1 <= plate_cy <= vehicle_bbox.y2):
                        # Plate center is inside vehicle - assign it
                        # (Plates should always be within vehicle bbox)
                        if idx not in plates:
                            plates[idx] = []
                        plates[idx].append(plate_bbox)
                        break
        elif all_plate_bboxes:
            # No vehicles provided - return all plates grouped under index 0
            plates[0] = all_plate_bboxes

        inference_time = (time.time() - start_time) * 1000
        logger.debug(f"Plate detection: {sum(len(p) for p in plates.values())} plates in {inference_time:.1f}ms")

        return plates

    def _detect_plates_contour(
        self,
        frame: np.ndarray,
        vehicle_bboxes: Optional[List[BoundingBox]] = None
    ) -> Dict[int, List[BoundingBox]]:
        """
        Fallback contour-based plate detection
        Used when no custom plate model is available
        """
        plates = {}

        if vehicle_bboxes:
            for idx, vehicle_bbox in enumerate(vehicle_bboxes):
                # Extract vehicle ROI
                x1, y1, x2, y2 = map(int, [vehicle_bbox.x1, vehicle_bbox.y1,
                                            vehicle_bbox.x2, vehicle_bbox.y2])
                vehicle_roi = frame[y1:y2, x1:x2]

                if vehicle_roi.size == 0:
                    continue

                # Find plate candidates
                plate_bboxes = self._find_plate_candidates(vehicle_roi, x1, y1)

                if plate_bboxes:
                    plates[idx] = plate_bboxes

        return plates

    def _find_plate_candidates(
        self,
        roi: np.ndarray,
        offset_x: int = 0,
        offset_y: int = 0
    ) -> List[BoundingBox]:
        """
        Find license plate candidates using contour detection

        Fallback method when no custom YOLO plate detector is available.
        Uses classical computer vision techniques:
        1. Bilateral filtering - reduces noise while preserving edges
        2. Canny edge detection - finds strong edges
        3. Contour detection - identifies rectangular regions
        4. Geometric filtering - validates plate-like shapes
        """
        # Convert to grayscale for processing
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # Bilateral filter: reduces noise while preserving strong edges
        # Critical for clean edge detection on license plates
        gray = cv2.bilateralFilter(gray, 11, 17, 17)

        # Canny edge detection: finds strong gradients (plate borders)
        edged = cv2.Canny(gray, 30, 200)

        # Find contours in edge map
        contours, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []

        for contour in contours:
            # Approximate contour to reduce number of points
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.018 * peri, True)

            # Get bounding rectangle for this contour
            x, y, w, h = cv2.boundingRect(approx)

            # Calculate geometric properties
            aspect_ratio = w / float(h) if h > 0 else 0  # Width to height ratio
            area = w * h
            roi_area = roi.shape[0] * roi.shape[1]

            # Filter candidates using plate characteristics:
            # - Aspect ratio: US plates are typically 2.5:1 to 5:1 (FL ~2.3:1)
            # - Size: minimum dimensions to avoid noise
            # - Area: reasonable proportion of vehicle ROI
            if (2.5 <= aspect_ratio <= 5.0 and  # Plate-like aspect ratio
                w >= 80 and h >= 25 and  # Minimum dimensions (pixels)
                area >= 2000 and  # Minimum area to avoid small artifacts
                area <= roi_area * 0.15 and  # Maximum 15% of vehicle bbox
                w <= roi.shape[1] * 0.8 and h <= roi.shape[0] * 0.4):  # Reasonable relative size

                # Convert ROI coordinates to frame coordinates
                bbox = BoundingBox(
                    x1=offset_x + x,
                    y1=offset_y + y,
                    x2=offset_x + x + w,
                    y2=offset_y + y + h
                )
                candidates.append(bbox)

        return candidates

    def warmup(self, iterations: int = 10):
        """
        Warmup model for consistent inference times
        Important for TensorRT engines
        """
        logger.info(f"Warming up detector ({iterations} iterations)...")
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)

        for i in range(iterations):
            self.detect_vehicles(dummy_frame, confidence_threshold=0.5)

        logger.success("Detector warmup complete")


if __name__ == "__main__":
    # Test detector
    detector = YOLOv11Detector(
        vehicle_model_path="yolo11n.pt",
        use_tensorrt=True,
        fp16=True
    )

    # Warmup
    detector.warmup()

    # Test on video
    cap = cv2.VideoCapture("../../a.mp4")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Detect vehicles
        vehicles = detector.detect_vehicles(frame)

        # Draw detections
        for vehicle in vehicles:
            bbox = vehicle.bbox
            cv2.rectangle(
                frame,
                (int(bbox.x1), int(bbox.y1)),
                (int(bbox.x2), int(bbox.y2)),
                (0, 255, 0),
                2
            )
            cv2.putText(
                frame,
                f"{vehicle.vehicle_type} {vehicle.confidence:.2f}",
                (int(bbox.x1), int(bbox.y1) - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )

        cv2.imshow('Detector Test', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
