"""
PaddleOCR Service
Optimized for NVIDIA Jetson Orin NX with GPU acceleration
Handles license plate text recognition
"""

import cv2
import numpy as np
from paddleocr import PaddleOCR
from loguru import logger
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import yaml
import time
import re

from shared.schemas.event import BoundingBox, PlateDetection


class PaddleOCRService:
    """
    PaddleOCR service for license plate text recognition
    Optimized for Jetson Orin NX with GPU acceleration
    """

    def __init__(
        self,
        config_path: str = "config/ocr.yaml",
        use_gpu: bool = True,
        enable_tensorrt: bool = False,
    ):
        """
        Initialize PaddleOCR service

        Args:
            config_path: Path to OCR configuration file
            use_gpu: Enable GPU acceleration
            enable_tensorrt: Enable TensorRT optimization (requires conversion)
        """
        self.config_path = config_path
        self.use_gpu = use_gpu
        self.enable_tensorrt = enable_tensorrt

        # Load configuration
        logger.info(f"Loading OCR configuration from {config_path}")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        self.config = config['ocr']

        # Extract settings
        paddle_config = self.config['paddle']
        self.preprocess_config = self.config['preprocessing']
        self.postprocess_config = self.config['postprocessing']
        self.performance_config = self.config['performance']

        # Initialize PaddleOCR
        logger.info("Initializing PaddleOCR...")
        try:
            # Use minimal parameters for PaddleOCR 3.3.0
            self.ocr = PaddleOCR(lang='en')
            logger.success("PaddleOCR initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {e}")
            raise

        # Character whitelist for post-processing
        self.whitelist = self.postprocess_config.get('whitelist',
                                                      'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        self.use_whitelist = self.postprocess_config.get('use_whitelist', True)
        self.min_confidence = self.postprocess_config.get('min_confidence', 0.7)
        self.min_text_length = self.postprocess_config.get('min_text_length', 3)
        self.max_text_length = self.postprocess_config.get('max_text_length', 10)

    def preprocess_plate_crop(self, plate_crop: np.ndarray) -> np.ndarray:
        """
        Preprocess license plate crop for better OCR accuracy
        Special handling for Florida plates (orange logo removal)

        Args:
            plate_crop: Cropped plate image (BGR)

        Returns:
            Preprocessed image
        """
        # Handle Florida plate orange logo interference
        # The orange logo in the center is being misread as 'C'
        if len(plate_crop.shape) == 3 and self.preprocess_config.get('remove_color', False):
            # Convert to HSV to isolate orange regions
            hsv = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2HSV)

            # Orange color range (Florida logo)
            lower_orange = np.array([5, 100, 100])
            upper_orange = np.array([25, 255, 255])

            # Create mask for orange regions
            orange_mask = cv2.inRange(hsv, lower_orange, upper_orange)

            # Inpaint orange regions with surrounding colors (removes logo)
            plate_crop = cv2.inpaint(plate_crop, orange_mask, 3, cv2.INPAINT_TELEA)

        # Convert to grayscale
        if len(plate_crop.shape) == 3:
            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_crop

        # Resize if too small
        min_height = self.preprocess_config.get('min_plate_height', 32)
        target_height = self.preprocess_config.get('target_height', 64)

        if gray.shape[0] < min_height:
            # Calculate scale factor
            scale = target_height / gray.shape[0]
            new_width = int(gray.shape[1] * scale)
            gray = cv2.resize(gray, (new_width, target_height),
                             interpolation=cv2.INTER_CUBIC)

        # Denoise
        if self.preprocess_config.get('denoise', True):
            gray = cv2.fastNlMeansDenoising(gray, None, h=10,
                                            templateWindowSize=7,
                                            searchWindowSize=21)

        # Enhance contrast
        if self.preprocess_config.get('enhance_contrast', True):
            # CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        # Sharpen for motion blur (important for blurry video)
        if self.preprocess_config.get('sharpen', False):
            # Unsharp mask for sharpening
            gaussian = cv2.GaussianBlur(gray, (0, 0), 2.0)
            gray = cv2.addWeighted(gray, 1.5, gaussian, -0.5, 0)

        # Convert back to BGR for PaddleOCR
        preprocessed = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        return preprocessed

    def recognize_plate(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
        preprocess: bool = True
    ) -> Optional[PlateDetection]:
        """
        Recognize license plate text from bounding box
        Uses multi-strategy approach: tries both raw and preprocessed

        Args:
            frame: Full frame image (BGR)
            bbox: Plate bounding box
            preprocess: Apply preprocessing (will try both strategies)

        Returns:
            PlateDetection object or None if recognition fails
        """
        start_time = time.time()

        # Extract plate crop
        x1, y1, x2, y2 = map(int, [bbox.x1, bbox.y1, bbox.x2, bbox.y2])

        # Ensure coordinates are within frame bounds
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            logger.warning(f"Invalid bbox coordinates: ({x1},{y1}) to ({x2},{y2})")
            return None

        plate_crop = frame[y1:y2, x1:x2]

        if plate_crop.size == 0:
            logger.warning("Empty plate crop")
            return None

        # Multi-strategy OCR: try multiple approaches and pick best result
        best_result = None
        best_confidence = 0.0

        # Strategy 1: Raw image (no preprocessing)
        result_raw = self._run_ocr_on_crop(plate_crop.copy(), strategy="raw", bbox=bbox)
        if result_raw and result_raw.confidence > best_confidence:
            best_result = result_raw
            best_confidence = result_raw.confidence

        # Strategy 2: With preprocessing (if enabled)
        if preprocess:
            preprocessed = self.preprocess_plate_crop(plate_crop.copy())
            result_preprocessed = self._run_ocr_on_crop(preprocessed, strategy="preprocessed", bbox=bbox)
            if result_preprocessed and result_preprocessed.confidence > best_confidence:
                best_result = result_preprocessed
                best_confidence = result_preprocessed.confidence

        # Strategy 3: Upscaled 2x (for small plates)
        plate_h = y2 - y1
        if plate_h < 80:  # Small plate, try upscaling
            upscaled = cv2.resize(plate_crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            result_upscaled = self._run_ocr_on_crop(upscaled, strategy="upscaled", bbox=bbox)
            if result_upscaled and result_upscaled.confidence > best_confidence:
                best_result = result_upscaled
                best_confidence = result_upscaled.confidence

        if best_result:
            logger.debug(f"Best OCR result: '{best_result.text}' (conf: {best_result.confidence:.2f}, strategy: {best_result.raw_text})")

        return best_result

    def _run_ocr_on_crop(self, plate_crop: np.ndarray, strategy: str = "raw", bbox: BoundingBox = None) -> Optional[PlateDetection]:
        """
        Run OCR on a single plate crop

        Args:
            plate_crop: Plate image
            strategy: Strategy name for logging
            bbox: Original bounding box (for PlateDetection)

        Returns:
            PlateDetection or None
        """
        try:
            result = self.ocr.ocr(plate_crop, cls=False)

            if not result or not result[0]:
                return None

            # Extract text and confidence from results
            # PaddleOCR returns: [[[bbox], (text, confidence)], ...]
            best_text = ""
            best_confidence = 0.0

            for line in result[0]:
                if len(line) >= 2:
                    text, confidence = line[1]
                    if confidence > best_confidence:
                        best_text = text
                        best_confidence = confidence

            if not best_text:
                return None

            # Post-process text
            raw_text = best_text
            normalized_text = self.normalize_plate_text(best_text)

            # Filter by confidence
            if best_confidence < self.min_confidence:
                return None

            # Filter by text length
            if len(normalized_text) < self.min_text_length:
                return None

            if len(normalized_text) > self.max_text_length:
                return None

            # Create PlateDetection with strategy name in raw_text for debugging
            plate_detection = PlateDetection(
                text=normalized_text,
                confidence=float(best_confidence),
                bbox=bbox if bbox else BoundingBox(x1=0, y1=0, x2=0, y2=0),
                raw_text=f"{raw_text}[{strategy}]",
            )

            return plate_detection

        except Exception as e:
            return None

    def recognize_plates_batch(
        self,
        frame: np.ndarray,
        bboxes: List[BoundingBox],
        preprocess: bool = True
    ) -> List[Optional[PlateDetection]]:
        """
        Recognize multiple license plates in batch for better performance

        Args:
            frame: Full frame image (BGR)
            bboxes: List of plate bounding boxes
            preprocess: Apply preprocessing

        Returns:
            List of PlateDetection objects (None for failed recognitions)
        """
        if not bboxes:
            return []

        start_time = time.time()
        results = []

        # Extract all crops first
        plate_crops = []
        valid_indices = []

        for idx, bbox in enumerate(bboxes):
            # Extract plate crop
            x1, y1, x2, y2 = map(int, [bbox.x1, bbox.y1, bbox.x2, bbox.y2])

            # Ensure coordinates are within frame bounds
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 <= x1 or y2 <= y1:
                logger.warning(f"Invalid bbox coordinates: ({x1},{y1}) to ({x2},{y2})")
                continue

            plate_crop = frame[y1:y2, x1:x2]

            if plate_crop.size == 0:
                logger.warning("Empty plate crop")
                continue

            # Preprocess if enabled
            if preprocess:
                plate_crop = self.preprocess_plate_crop(plate_crop)

            plate_crops.append(plate_crop)
            valid_indices.append(idx)

        # No valid crops?
        if not plate_crops:
            return [None] * len(bboxes)

        # Batch inference with PaddleOCR
        try:
            # PaddleOCR can process multiple images at once
            batch_results = []
            for crop in plate_crops:
                result = self.ocr.ocr(crop, cls=True)
                batch_results.append(result)

            # Process batch results
            detections = [None] * len(bboxes)

            for crop_idx, result in enumerate(batch_results):
                bbox_idx = valid_indices[crop_idx]
                bbox = bboxes[bbox_idx]

                if not result or not result[0]:
                    continue

                # Extract best text and confidence
                best_text = ""
                best_confidence = 0.0

                for line in result[0]:
                    if len(line) >= 2:
                        text, confidence = line[1]
                        if confidence > best_confidence:
                            best_text = text
                            best_confidence = confidence

                if not best_text:
                    continue

                # Post-process
                raw_text = best_text
                normalized_text = self.normalize_plate_text(best_text)

                # Filter by confidence and length
                if best_confidence < self.min_confidence:
                    continue
                if len(normalized_text) < self.min_text_length:
                    continue
                if len(normalized_text) > self.max_text_length:
                    continue

                # Create detection
                plate_detection = PlateDetection(
                    text=normalized_text,
                    confidence=float(best_confidence),
                    bbox=bbox,
                    raw_text=raw_text,
                )

                detections[bbox_idx] = plate_detection

            inference_time = (time.time() - start_time) * 1000
            successful = sum(1 for d in detections if d is not None)
            logger.debug(
                f"Batch OCR: {successful}/{len(bboxes)} plates in {inference_time:.1f}ms "
                f"({inference_time/len(bboxes):.1f}ms/plate)"
            )

            return detections

        except Exception as e:
            logger.error(f"Batch OCR failed: {e}")
            # Fallback to sequential processing
            logger.warning("Falling back to sequential OCR")
            results = []
            for bbox in bboxes:
                plate_detection = self.recognize_plate(frame, bbox, preprocess)
                results.append(plate_detection)
            return results

    def normalize_plate_text(self, text: str) -> str:
        """
        Normalize plate text to standard format

        Args:
            text: Raw OCR text

        Returns:
            Normalized plate text (uppercase, alphanumeric only)
        """
        # Convert to uppercase
        text = text.upper()

        # Remove spaces, dashes, and special characters
        text = re.sub(r'[^A-Z0-9]', '', text)

        # Apply whitelist if enabled
        if self.use_whitelist:
            text = ''.join([c for c in text if c in self.whitelist])

        # Common OCR corrections (optional)
        # O/0, I/1, S/5, B/8 confusion
        # Can add logic here if needed

        return text

    def warmup(self, iterations: int = 5):
        """
        Warmup OCR model for consistent inference times

        Args:
            iterations: Number of warmup iterations
        """
        logger.info(f"Warming up PaddleOCR ({iterations} iterations)...")

        # Create dummy plate image
        dummy_plate = np.ones((64, 256, 3), dtype=np.uint8) * 255
        cv2.putText(
            dummy_plate,
            "ABC1234",
            (10, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            (0, 0, 0),
            2
        )

        for i in range(iterations):
            try:
                self.ocr.ocr(dummy_plate, cls=True)
            except Exception as e:
                logger.warning(f"Warmup iteration {i+1} failed: {e}")

        logger.success("PaddleOCR warmup complete")


if __name__ == "__main__":
    # Test OCR service
    import sys

    # Initialize service
    ocr_service = PaddleOCRService(
        config_path="../../config/ocr.yaml",
        use_gpu=True,
        enable_tensorrt=False
    )

    # Warmup
    ocr_service.warmup()

    # Test on image if provided
    if len(sys.argv) > 1:
        test_image_path = sys.argv[1]
        frame = cv2.imread(test_image_path)

        if frame is not None:
            # Assume full frame is a plate for testing
            h, w = frame.shape[:2]
            bbox = BoundingBox(x1=0, y1=0, x2=w, y2=h)

            # Recognize
            result = ocr_service.recognize_plate(frame, bbox)

            if result:
                logger.info(f"Detected plate: {result.text} (confidence: {result.confidence:.2f})")
            else:
                logger.warning("No plate text detected")

            # Display
            cv2.imshow("Plate", frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        else:
            logger.error(f"Failed to load image: {test_image_path}")
    else:
        logger.info("OCR service initialized successfully. Provide an image path to test.")
