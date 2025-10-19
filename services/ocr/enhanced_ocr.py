"""
Enhanced OCR Service with Improved Accuracy
Fixes: Low OCR accuracy through better preprocessing and multi-pass recognition
"""

import cv2
import numpy as np
from paddleocr import PaddleOCR
from loguru import logger
from typing import List, Dict, Tuple, Optional
import yaml
import time
import re

from shared.schemas.event import BoundingBox, PlateDetection


class EnhancedOCRService:
    """
    Enhanced PaddleOCR with accuracy improvements

    Improvements:
    1. Multi-scale preprocessing
    2. Multiple preprocessing strategies
    3. Majority voting across strategies
    4. Better contrast/brightness normalization
    5. Morphological operations
    """

    def __init__(
        self,
        config_path: str = "config/ocr.yaml",
        use_gpu: bool = True,
        enable_multi_pass: bool = True,
    ):
        """
        Initialize enhanced OCR service

        Args:
            config_path: Path to OCR configuration
            use_gpu: Enable GPU acceleration
            enable_multi_pass: Run multiple preprocessing strategies (higher accuracy)
        """
        self.config_path = config_path
        self.use_gpu = use_gpu
        self.enable_multi_pass = enable_multi_pass

        # Load configuration
        logger.info(f"Loading OCR configuration from {config_path}")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        self.config = config['ocr']
        paddle_config = self.config['paddle']
        self.preprocess_config = self.config['preprocessing']
        self.postprocess_config = self.config['postprocessing']

        # Initialize PaddleOCR
        logger.info("Initializing Enhanced PaddleOCR...")
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang='en',
            use_gpu=self.use_gpu,
            gpu_mem=paddle_config.get('gpu_mem', 2000),
            show_log=False,
            det_db_thresh=paddle_config.get('det_db_thresh', 0.3),
            det_db_box_thresh=paddle_config.get('det_db_box_thresh', 0.6),
            rec_batch_num=paddle_config.get('rec_batch_num', 6),
        )
        logger.success("Enhanced OCR initialized")

        # OCR settings
        self.whitelist = self.postprocess_config.get('whitelist',
                                                      'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        self.use_whitelist = self.postprocess_config.get('use_whitelist', True)
        self.min_confidence = self.postprocess_config.get('min_confidence', 0.7)
        self.min_text_length = self.postprocess_config.get('min_text_length', 3)
        self.max_text_length = self.postprocess_config.get('max_text_length', 10)

    def preprocess_adaptive(self, plate_crop: np.ndarray) -> List[np.ndarray]:
        """
        Generate multiple preprocessing variations for better accuracy

        Returns:
            List of preprocessed images to try
        """
        variations = []

        # Convert to grayscale
        if len(plate_crop.shape) == 3:
            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_crop.copy()

        # Resize if too small (critical for OCR accuracy!)
        h, w = gray.shape
        min_height = 64  # Increased from 32
        target_height = 80  # Increased from 64

        if h < min_height:
            scale = target_height / h
            new_width = int(w * scale)
            gray = cv2.resize(gray, (new_width, target_height),
                             interpolation=cv2.INTER_CUBIC)  # CUBIC for upscaling

        # Strategy 1: Standard preprocessing (CLAHE + denoise)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced1 = clahe.apply(gray)
        denoised1 = cv2.fastNlMeansDenoising(enhanced1, None, h=10)
        variations.append(cv2.cvtColor(denoised1, cv2.COLOR_GRAY2BGR))

        # Strategy 2: Aggressive contrast (good for faded plates)
        enhanced2 = cv2.equalizeHist(gray)
        denoised2 = cv2.bilateralFilter(enhanced2, 9, 75, 75)
        variations.append(cv2.cvtColor(denoised2, cv2.COLOR_GRAY2BGR))

        # Strategy 3: Adaptive threshold (good for uneven lighting)
        adaptive = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2
        )
        # Invert if more black than white (dark plate on light background)
        if np.mean(adaptive) < 127:
            adaptive = cv2.bitwise_not(adaptive)
        variations.append(cv2.cvtColor(adaptive, cv2.COLOR_GRAY2BGR))

        # Strategy 4: Morphological operations (good for broken characters)
        morph = clahe.apply(gray)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morph = cv2.morphologyEx(morph, cv2.MORPH_CLOSE, kernel)
        variations.append(cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR))

        # Strategy 5: Sharpening (good for blurry plates)
        kernel_sharp = np.array([[-1, -1, -1],
                                 [-1,  9, -1],
                                 [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced1, -1, kernel_sharp)
        variations.append(cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR))

        if not self.enable_multi_pass:
            # Return only best strategy (Strategy 1)
            return [variations[0]]

        return variations

    def recognize_plate_multi_pass(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
    ) -> Optional[PlateDetection]:
        """
        Multi-pass OCR with majority voting for higher accuracy

        Args:
            frame: Full frame image
            bbox: Plate bounding box

        Returns:
            PlateDetection with best result
        """
        start_time = time.time()

        # Extract plate crop
        x1, y1, x2, y2 = map(int, [bbox.x1, bbox.y1, bbox.x2, bbox.y2])

        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        plate_crop = frame[y1:y2, x1:x2]

        if plate_crop.size == 0:
            return None

        # Generate preprocessing variations
        variations = self.preprocess_adaptive(plate_crop)

        # Try OCR on each variation
        results = []

        for idx, preprocessed in enumerate(variations):
            try:
                ocr_result = self.ocr.ocr(preprocessed, cls=True)

                if not ocr_result or not ocr_result[0]:
                    continue

                # Extract best text from this variation
                for line in ocr_result[0]:
                    if len(line) >= 2:
                        text, confidence = line[1]
                        normalized = self.normalize_plate_text(text)

                        # Validate
                        if (confidence >= self.min_confidence and
                            self.min_text_length <= len(normalized) <= self.max_text_length):

                            results.append({
                                'text': normalized,
                                'raw_text': text,
                                'confidence': confidence,
                                'strategy': idx
                            })

            except Exception as e:
                logger.debug(f"OCR strategy {idx} failed: {e}")
                continue

        if not results:
            return None

        # Majority voting or highest confidence
        best_result = self._select_best_result(results)

        if not best_result:
            return None

        # Create PlateDetection
        plate_detection = PlateDetection(
            text=best_result['text'],
            confidence=float(best_result['confidence']),
            bbox=bbox,
            raw_text=best_result['raw_text'],
        )

        inference_time = (time.time() - start_time) * 1000
        logger.debug(
            f"Enhanced OCR: '{best_result['text']}' "
            f"(conf: {best_result['confidence']:.2f}, "
            f"strategy: {best_result['strategy']}, "
            f"time: {inference_time:.1f}ms)"
        )

        return plate_detection

    def _select_best_result(self, results: List[dict]) -> Optional[dict]:
        """
        Select best result using majority voting and confidence

        Args:
            results: List of OCR results from different strategies

        Returns:
            Best result dict
        """
        if not results:
            return None

        # Count text occurrences
        text_votes = {}
        for r in results:
            text = r['text']
            if text not in text_votes:
                text_votes[text] = []
            text_votes[text].append(r)

        # Find text with most votes
        best_text = max(text_votes.keys(), key=lambda t: len(text_votes[t]))

        # Among same text, select highest confidence
        candidates = text_votes[best_text]
        best_result = max(candidates, key=lambda r: r['confidence'])

        # Boost confidence if multiple strategies agree
        vote_count = len(candidates)
        if vote_count > 1:
            boost = min(0.1 * (vote_count - 1), 0.15)  # Max 15% boost
            best_result['confidence'] = min(1.0, best_result['confidence'] + boost)
            logger.debug(f"Majority vote: {best_text} ({vote_count} votes, +{boost:.2f} conf)")

        return best_result

    def normalize_plate_text(self, text: str) -> str:
        """
        Enhanced text normalization with common OCR error corrections

        Args:
            text: Raw OCR text

        Returns:
            Normalized plate text
        """
        # Convert to uppercase
        text = text.upper()

        # Remove spaces, dashes, special characters
        text = re.sub(r'[^A-Z0-9]', '', text)

        # Apply whitelist
        if self.use_whitelist:
            text = ''.join([c for c in text if c in self.whitelist])

        # Common OCR error corrections
        corrections = {
            'O': '0',  # O → 0 (context-dependent)
            'I': '1',  # I → 1 in numeric positions
            'S': '5',  # S → 5 (rare, context-dependent)
            'B': '8',  # B → 8 (context-dependent)
            'Z': '2',  # Z → 2 (rare)
        }

        # Apply smart corrections (heuristic)
        # If text starts with letters, assume front part is letters
        # If text has numbers, back part is likely numbers

        # Simple heuristic: First 2-3 chars are letters, rest are numbers
        if len(text) >= 4:
            # Try to detect letter vs number regions
            corrected = ""
            for i, char in enumerate(text):
                if i < 3:  # First 3 positions: prefer letters
                    corrected += char
                else:  # Later positions: prefer numbers
                    # O → 0, I → 1 in numeric region
                    if char == 'O':
                        corrected += '0'
                    elif char == 'I':
                        corrected += '1'
                    elif char == 'S':
                        corrected += '5'
                    elif char == 'B':
                        corrected += '8'
                    else:
                        corrected += char

            text = corrected

        return text

    def warmup(self, iterations: int = 5):
        """Warmup OCR model"""
        logger.info(f"Warming up Enhanced OCR ({iterations} iterations)...")

        dummy_plate = np.ones((80, 320, 3), dtype=np.uint8) * 255
        cv2.putText(
            dummy_plate,
            "ABC1234",
            (10, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            2.0,
            (0, 0, 0),
            3
        )

        for i in range(iterations):
            try:
                self.ocr.ocr(dummy_plate, cls=True)
            except Exception as e:
                logger.warning(f"Warmup iteration {i+1} failed: {e}")

        logger.success("Enhanced OCR warmup complete")


if __name__ == "__main__":
    import sys

    # Test enhanced OCR
    ocr_service = EnhancedOCRService(
        config_path="../../config/ocr.yaml",
        use_gpu=True,
        enable_multi_pass=True
    )

    ocr_service.warmup()

    if len(sys.argv) > 1:
        test_image_path = sys.argv[1]
        frame = cv2.imread(test_image_path)

        if frame is not None:
            h, w = frame.shape[:2]
            bbox = BoundingBox(x1=0, y1=0, x2=w, y2=h)

            result = ocr_service.recognize_plate_multi_pass(frame, bbox)

            if result:
                logger.info(f"Result: {result.text} (confidence: {result.confidence:.2f})")
            else:
                logger.warning("No text detected")

            cv2.imshow("Plate", frame)
            cv2.waitKey(0)
        else:
            logger.error(f"Failed to load image: {test_image_path}")
