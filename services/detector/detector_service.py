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
        """Load and optimize YOLO model"""
        model = YOLO(model_path)

        # Export to TensorRT if enabled (Jetson optimization)
        if self.use_tensorrt and not model_path.endswith('.engine'):
            try:
                if self.int8:
                    logger.info("Exporting model to TensorRT with INT8 precision...")
                    # Export with INT8 precision for maximum speed
                    engine_path = model.export(
                        format='engine',
                        int8=True,
                        device=self.device,
                        batch=self.batch_size,
                        workspace=2,  # 2GB workspace
                        data='coco.yaml',  # Calibration dataset
                    )
                else:
                    logger.info("Exporting model to TensorRT with FP16 precision...")
                    # Export with FP16 precision for Jetson
                    engine_path = model.export(
                        format='engine',
                        half=self.fp16,
                        device=self.device,
                        batch=self.batch_size,
                        workspace=2,  # 2GB workspace
                    )
                logger.success(f"TensorRT engine created: {engine_path}")
                model = YOLO(engine_path)
            except Exception as e:
                logger.warning(f"TensorRT export failed: {e}. Using PyTorch model.")

        # Move PyTorch model to device (TensorRT engines don't support .to())
        if not str(model_path).endswith('.engine'):
            try:
                model.to(self.device)
            except:
                pass  # TensorRT models don't support .to()

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
        plates = {}

        if vehicle_bboxes:
            # Search for plates within each vehicle bbox
            for idx, vehicle_bbox in enumerate(vehicle_bboxes):
                # Extract vehicle ROI
                x1, y1, x2, y2 = map(int, [vehicle_bbox.x1, vehicle_bbox.y1,
                                            vehicle_bbox.x2, vehicle_bbox.y2])
                vehicle_roi = frame[y1:y2, x1:x2]

                if vehicle_roi.size == 0:
                    continue

                # Run plate detection on ROI
                results = self.plate_model.predict(
                    vehicle_roi,
                    conf=confidence_threshold,
                    iou=nms_threshold,
                    verbose=False,
                    device=self.device,
                    half=self.fp16
                )

                plate_bboxes = []
                for result in results:
                    for box in result.boxes:
                        # Convert bbox to global coordinates
                        px1, py1, px2, py2 = box.xyxy[0].cpu().numpy()
                        global_bbox = BoundingBox(
                            x1=x1 + px1,
                            y1=y1 + py1,
                            x2=x1 + px2,
                            y2=y1 + py2
                        )
                        plate_bboxes.append(global_bbox)

                if plate_bboxes:
                    plates[idx] = plate_bboxes
        else:
            # Search entire frame
            results = self.plate_model.predict(
                frame,
                conf=confidence_threshold,
                iou=nms_threshold,
                verbose=False,
                device=self.device,
                half=self.fp16
            )

            plate_bboxes = []
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    plate_bboxes.append(
                        BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
                    )

            if plate_bboxes:
                plates[0] = plate_bboxes

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
        """
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # Bilateral filter to reduce noise while preserving edges
        gray = cv2.bilateralFilter(gray, 11, 17, 17)

        # Edge detection
        edged = cv2.Canny(gray, 30, 200)

        # Find contours
        contours, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []

        for contour in contours:
            # Approximate contour
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.018 * peri, True)

            # Get bounding rect
            x, y, w, h = cv2.boundingRect(approx)

            # Filter by aspect ratio (plates are typically 2:1 to 5.5:1)
            aspect_ratio = w / float(h) if h > 0 else 0
            area = w * h
            roi_area = roi.shape[0] * roi.shape[1]

            # Filter by size and aspect ratio (stricter criteria)
            if (2.5 <= aspect_ratio <= 5.0 and  # Narrower aspect ratio range
                w >= 80 and h >= 25 and  # Larger minimum size
                area >= 2000 and  # Minimum area requirement
                area <= roi_area * 0.15 and  # Max 15% of vehicle area
                w <= roi.shape[1] * 0.8 and h <= roi.shape[0] * 0.4):

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
