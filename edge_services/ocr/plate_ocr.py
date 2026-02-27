"""
Improved Plate OCR with Ensemble and Florida Plate Patterns
Combines PaddleOCR + EasyOCR with smart post-processing
"""

import cv2
import numpy as np
import re
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from loguru import logger
import time

try:
    from shared.schemas.event import BoundingBox, PlateDetection
    _SHARED_SCHEMAS = True
except ImportError:
    _SHARED_SCHEMAS = False


@dataclass
class OCRResult:
    """OCR result with metadata."""
    text: str
    confidence: float
    raw_text: str
    source: str  # 'paddle', 'easyocr', 'ensemble'


class PlateOCR:
    """
    High-accuracy plate OCR using ensemble methods.

    Features:
    - Multi-engine ensemble (PaddleOCR + EasyOCR)
    - Florida plate pattern validation
    - Smart character correction
    - Multi-pass preprocessing
    """

    # Florida plate patterns (most common)
    # Format: 3 letters + 1 space/separator + 3-4 alphanumeric
    # Examples: ABC 1234, ABC D12, 123 ABC
    FLORIDA_PATTERNS = [
        r'^[A-Z]{3}[A-Z0-9]{4}$',   # ABC1234, ABCD123
        r'^[A-Z]{3}[0-9]{4}$',      # ABC1234 (standard)
        r'^[A-Z]{3}[A-Z][0-9]{2}$', # ABCD12 (specialty)
        r'^[0-9]{3}[A-Z]{3}$',      # 123ABC (older format)
        r'^[A-Z]{2}[0-9]{2}[A-Z]{2}$',  # AB12CD
        r'^[A-Z0-9]{5,8}$',         # Generic fallback
    ]

    # Character substitutions based on position
    LETTER_TO_NUMBER = {'O': '0', 'I': '1', 'L': '1', 'S': '5', 'Z': '2', 'B': '8', 'G': '6'}
    NUMBER_TO_LETTER = {'0': 'O', '1': 'I', '8': 'B', '6': 'G', '5': 'S', '2': 'Z'}

    def __init__(
        self,
        use_gpu: bool = True,
        use_easyocr: bool = True,
        use_paddleocr: bool = True,
        enable_ensemble: bool = True,
    ):
        """
        Initialize PlateOCR.

        Args:
            use_gpu: Use GPU acceleration
            use_easyocr: Enable EasyOCR engine
            use_paddleocr: Enable PaddleOCR engine
            enable_ensemble: Use both engines and vote
        """
        self.use_gpu = use_gpu
        self.use_easyocr = use_easyocr
        self.use_paddleocr = use_paddleocr
        self.enable_ensemble = enable_ensemble

        self.paddle_ocr = None
        self.easy_reader = None

        self._init_engines()

    def _init_engines(self):
        """Initialize OCR engines."""
        if self.use_paddleocr:
            try:
                from paddleocr import PaddleOCR
                self.paddle_ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang='en',
                    use_gpu=self.use_gpu,
                    show_log=False,
                    det_db_thresh=0.3,
                    det_db_box_thresh=0.5,
                    rec_batch_num=6,
                )
                logger.info("PaddleOCR initialized")
            except Exception as e:
                logger.warning(f"PaddleOCR init failed: {e}")
                self.paddle_ocr = None

        if self.use_easyocr:
            try:
                import easyocr
                self.easy_reader = easyocr.Reader(
                    ['en'],
                    gpu=self.use_gpu,
                    verbose=False,
                )
                logger.info("EasyOCR initialized")
            except Exception as e:
                logger.warning(f"EasyOCR init failed: {e}")
                self.easy_reader = None

    def preprocess(self, plate_img: np.ndarray) -> List[np.ndarray]:
        """
        Generate preprocessed variations of plate image.

        Args:
            plate_img: BGR plate crop

        Returns:
            List of preprocessed images
        """
        variations = []

        # Convert to grayscale
        if len(plate_img.shape) == 3:
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_img.copy()

        # Resize if too small
        h, w = gray.shape
        if h < 50:
            scale = 64 / h
            gray = cv2.resize(gray, (int(w * scale), 64), interpolation=cv2.INTER_CUBIC)

        # Add padding (helps OCR)
        gray = cv2.copyMakeBorder(gray, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)

        # Strategy 1: CLAHE + denoise (best for most cases)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
        variations.append(cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR))

        # Strategy 2: Adaptive threshold (good for shadows)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        if np.mean(adaptive) < 127:
            adaptive = cv2.bitwise_not(adaptive)
        variations.append(cv2.cvtColor(adaptive, cv2.COLOR_GRAY2BGR))

        # Strategy 3: Sharpening (for blurry plates)
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)
        variations.append(cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR))

        return variations

    def _paddle_read(self, img: np.ndarray) -> List[Tuple[str, float]]:
        """Read with PaddleOCR."""
        if self.paddle_ocr is None:
            return []

        try:
            result = self.paddle_ocr.ocr(img, cls=True)
            if not result or not result[0]:
                return []

            texts = []
            for line in result[0]:
                if len(line) >= 2:
                    text, conf = line[1]
                    texts.append((text, float(conf)))
            return texts
        except Exception as e:
            logger.debug(f"PaddleOCR error: {e}")
            return []

    def _easy_read(self, img: np.ndarray) -> List[Tuple[str, float]]:
        """Read with EasyOCR."""
        if self.easy_reader is None:
            return []

        try:
            result = self.easy_reader.readtext(img)
            texts = []
            for detection in result:
                if len(detection) >= 2:
                    text = detection[1]
                    conf = detection[2] if len(detection) > 2 else 0.5
                    texts.append((text, float(conf)))
            return texts
        except Exception as e:
            logger.debug(f"EasyOCR error: {e}")
            return []

    def _normalize_text(self, text: str) -> str:
        """Basic text normalization."""
        text = text.upper()
        text = re.sub(r'[^A-Z0-9]', '', text)
        return text

    def _apply_florida_corrections(self, text: str) -> str:
        """
        Apply Florida plate-specific corrections.

        Florida plates are typically:
        - 3 letters + 4 numbers (ABC1234)
        - 3 letters + 1 letter + 2 numbers (ABCD12)
        """
        if len(text) < 5 or len(text) > 8:
            return text

        corrected = list(text)

        # First 3 characters should be letters
        for i in range(min(3, len(corrected))):
            if corrected[i].isdigit():
                corrected[i] = self.NUMBER_TO_LETTER.get(corrected[i], corrected[i])

        # Characters 4-7 are typically numbers (for standard plates)
        if len(corrected) >= 7:
            for i in range(3, 7):
                if corrected[i].isalpha():
                    corrected[i] = self.LETTER_TO_NUMBER.get(corrected[i], corrected[i])

        return ''.join(corrected)

    def _validate_florida_pattern(self, text: str) -> Tuple[bool, float]:
        """
        Check if text matches Florida plate patterns.

        Returns:
            (is_valid, confidence_boost)
        """
        for pattern in self.FLORIDA_PATTERNS:
            if re.match(pattern, text):
                return True, 0.1  # 10% confidence boost for valid pattern
        return False, 0.0

    def _select_best_result(self, results: List[OCRResult]) -> Optional[OCRResult]:
        """Select best result from multiple OCR attempts."""
        if not results:
            return None

        # Group by normalized text
        groups: Dict[str, List[OCRResult]] = {}
        for r in results:
            normalized = self._normalize_text(r.text)
            corrected = self._apply_florida_corrections(normalized)

            if len(corrected) < 4:
                continue

            if corrected not in groups:
                groups[corrected] = []
            groups[corrected].append(r)

        if not groups:
            return None

        # Score each group
        best_text = None
        best_score = -1

        for text, group in groups.items():
            # Base score: number of engines that agree
            vote_score = len(group) * 0.2

            # Average confidence
            avg_conf = sum(r.confidence for r in group) / len(group)

            # Pattern validation
            is_valid, pattern_boost = self._validate_florida_pattern(text)

            # Total score
            score = avg_conf + vote_score + pattern_boost

            if score > best_score:
                best_score = score
                best_text = text

        if best_text is None:
            return None

        # Get best confidence from winning group
        group = groups[best_text]
        best_result = max(group, key=lambda r: r.confidence)

        # Apply corrections and boost
        corrected_text = self._apply_florida_corrections(best_text)
        is_valid, boost = self._validate_florida_pattern(corrected_text)

        final_conf = min(1.0, best_result.confidence + boost + (0.1 if len(group) > 1 else 0))

        return OCRResult(
            text=corrected_text,
            confidence=final_conf,
            raw_text=best_result.raw_text,
            source='ensemble' if len(group) > 1 else best_result.source,
        )

    def read(self, plate_img: np.ndarray) -> Optional[OCRResult]:
        """
        Read plate text with ensemble OCR.

        Args:
            plate_img: BGR plate crop image

        Returns:
            OCRResult or None if no text detected
        """
        if plate_img is None or plate_img.size == 0:
            return None

        start_time = time.time()
        all_results = []

        # Generate preprocessed variations
        variations = self.preprocess(plate_img)

        # Try each engine on each variation
        for var_idx, var_img in enumerate(variations):
            # PaddleOCR
            if self.paddle_ocr:
                for text, conf in self._paddle_read(var_img):
                    all_results.append(OCRResult(
                        text=text,
                        confidence=conf,
                        raw_text=text,
                        source='paddle',
                    ))

            # EasyOCR (only on first variation to save time)
            if self.easy_reader and var_idx == 0:
                for text, conf in self._easy_read(var_img):
                    all_results.append(OCRResult(
                        text=text,
                        confidence=conf,
                        raw_text=text,
                        source='easyocr',
                    ))

        # Select best result
        result = self._select_best_result(all_results)

        if result:
            elapsed = (time.time() - start_time) * 1000
            logger.debug(
                f"PlateOCR: '{result.text}' "
                f"(conf: {result.confidence:.2f}, source: {result.source}, "
                f"time: {elapsed:.0f}ms)"
            )

        return result

    def recognize_plate_multi_pass(self, frame: np.ndarray, bbox) -> Optional["PlateDetection"]:
        """
        Adapter matching the EnhancedOCRService interface.
        Crops the plate region from frame using bbox, runs ensemble OCR,
        and returns a PlateDetection compatible with pilot.py.
        """
        x1, y1, x2, y2 = map(int, [bbox.x1, bbox.y1, bbox.x2, bbox.y2])
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        result = self.read(crop)
        if result is None:
            return None

        if _SHARED_SCHEMAS:
            return PlateDetection(
                text=result.text,
                confidence=result.confidence,
                bbox=bbox,
                raw_text=f"{result.raw_text}[{result.source}]",
            )

        # Fallback: return a simple namespace if shared schemas unavailable
        from types import SimpleNamespace
        return SimpleNamespace(
            text=result.text,
            confidence=result.confidence,
            bbox=bbox,
            raw_text=result.raw_text,
        )

    def recognize_plate_crop(self, crop: np.ndarray) -> Optional[tuple]:
        """
        Adapter matching CRNNOCRService interface for async ThreadPoolExecutor use.
        Returns (text, confidence) or None.
        """
        result = self.read(crop)
        if result is None:
            return None
        return (result.text, result.confidence)

    def warmup(self, iterations: int = 3):
        """Warm up OCR engines."""
        logger.info("Warming up PlateOCR...")

        # Create dummy plate image
        dummy = np.ones((64, 200, 3), dtype=np.uint8) * 255
        cv2.putText(dummy, "ABC1234", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)

        for _ in range(iterations):
            self.read(dummy)

        logger.success("PlateOCR warmup complete")


# Convenience function for simple usage
_ocr_instance = None

def get_plate_ocr(use_gpu: bool = True) -> PlateOCR:
    """Get or create PlateOCR instance."""
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = PlateOCR(use_gpu=use_gpu)
    return _ocr_instance


def read_plate(plate_img: np.ndarray, use_gpu: bool = True) -> Optional[str]:
    """
    Simple function to read plate text.

    Args:
        plate_img: BGR plate crop
        use_gpu: Use GPU acceleration

    Returns:
        Plate text or None
    """
    ocr = get_plate_ocr(use_gpu)
    result = ocr.read(plate_img)
    return result.text if result else None


if __name__ == "__main__":
    import sys

    # Test
    ocr = PlateOCR(use_gpu=True)
    ocr.warmup()

    if len(sys.argv) > 1:
        img = cv2.imread(sys.argv[1])
        if img is not None:
            result = ocr.read(img)
            if result:
                print(f"Result: {result.text} (conf: {result.confidence:.2f}, source: {result.source})")
            else:
                print("No text detected")
        else:
            print(f"Failed to load: {sys.argv[1]}")
    else:
        # Test with dummy
        dummy = np.ones((64, 200, 3), dtype=np.uint8) * 255
        cv2.putText(dummy, "ABC1234", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
        result = ocr.read(dummy)
        print(f"Dummy test: {result}")
