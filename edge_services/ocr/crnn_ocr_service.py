"""
Thread-safe OCR service using the CRNN ONNX model trained on Florida plates.

Uses onnxruntime.InferenceSession which is explicitly thread-safe, enabling
async ThreadPoolExecutor use in pilot.py without the silent-failure issue
that affects PaddleOCR's C++ backend.
"""

import re
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from loguru import logger

try:
    from shared.schemas.event import BoundingBox, PlateDetection
    _SHARED_SCHEMAS = True
except ImportError:
    _SHARED_SCHEMAS = False

# ── Character set (must match train_crnn.py) ──────────────────────────────────

CHARS     = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
BLANK_IDX = 0
idx_to_char = {i + 1: c for i, c in enumerate(CHARS)}

IMG_H = 32
IMG_W = 128

# Florida plate patterns for confidence boost
_FL_PATTERNS = [
    re.compile(r'^[A-Z]{3}[0-9]{4}$'),        # ABC1234 standard
    re.compile(r'^[A-Z]{3}[A-Z][0-9]{2}$'),   # ABCD12 specialty
    re.compile(r'^[0-9]{3}[A-Z]{3}$'),        # 123ABC older
    re.compile(r'^[A-Z]{2}[0-9]{2}[A-Z]{2}$'), # AB12CD
    re.compile(r'^[A-Z0-9]{5,8}$'),           # generic fallback
]


def _florida_boost(text: str) -> float:
    for p in _FL_PATTERNS:
        if p.match(text):
            return 0.10
    return 0.0


class CRNNOCRService:
    """
    Thread-safe OCR for Florida license plates.

    Drop-in replacement for PaddleOCRService in pilot.py. The underlying
    onnxruntime.InferenceSession is safe to call from multiple threads
    simultaneously, enabling async ThreadPoolExecutor OCR.
    """

    def __init__(
        self,
        model_path: str = "models/crnn_florida/florida_plate_ocr.onnx",
        use_gpu: bool = True,
        min_confidence: float = 0.30,
        min_text_length: int = 4,
        max_text_length: int = 10,
    ):
        import onnxruntime as ort

        self.min_confidence  = min_confidence
        self.min_text_length = min_text_length
        self.max_text_length = max_text_length

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if use_gpu else
            ["CPUExecutionProvider"]
        )

        self.sess = ort.InferenceSession(str(model_path), providers=providers)
        active = self.sess.get_providers()
        logger.info(f"CRNNOCRService loaded: {Path(model_path).name} | providers={active}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _preprocess(self, plate_crop: np.ndarray) -> np.ndarray:
        """BGR crop → (1, 1, IMG_H, IMG_W) float32 array."""
        if len(plate_crop.shape) == 3:
            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_crop

        # Upscale tiny crops before shrinking to model input size
        h, w = gray.shape
        if h < IMG_H:
            scale = IMG_H / h
            gray = cv2.resize(gray, (int(w * scale), IMG_H), interpolation=cv2.INTER_CUBIC)

        resized = cv2.resize(gray, (IMG_W, IMG_H), interpolation=cv2.INTER_CUBIC)
        img = resized.astype(np.float32) / 255.0
        return img[np.newaxis, np.newaxis, :]   # (1, 1, H, W)

    def _ctc_decode(self, log_probs: np.ndarray):
        """
        Greedy CTC decode.

        log_probs: (T, 1, C) as returned by onnxruntime — log-softmax over classes.
        Returns (text, confidence).
        """
        probs = np.exp(log_probs[:, 0, :])   # (T, C) softmax probabilities
        preds = np.argmax(probs, axis=1)      # (T,) greedy argmax

        chars      = []
        char_probs = []
        prev       = BLANK_IDX

        for t, p in enumerate(preds):
            if p != prev and p != BLANK_IDX:
                chars.append(idx_to_char.get(int(p), "?"))
                char_probs.append(float(probs[t, p]))
            prev = p

        text = "".join(chars)
        conf = float(np.mean(char_probs)) if char_probs else 0.0
        return text, conf

    # ── Public interface ──────────────────────────────────────────────────────

    def recognize_plate_crop(self, crop: np.ndarray) -> Optional["PlateDetection"]:
        """
        Run OCR on an already-cropped plate image.

        This is what gets submitted to the ThreadPoolExecutor — the crop
        is extracted and .copy()'d on the main thread before submission
        so the frame buffer advancing is safe.
        """
        if crop is None or crop.size == 0:
            return None

        inp       = self._preprocess(crop)
        log_probs = self.sess.run(None, {"input": inp})[0]   # (T, 1, C)
        text, conf = self._ctc_decode(log_probs)

        # Strip non-plate characters and validate length
        text = re.sub(r"[^A-Z0-9]", "", text.upper())

        if len(text) < self.min_text_length or len(text) > self.max_text_length:
            return None

        # Boost confidence for known Florida patterns
        conf = min(1.0, conf + _florida_boost(text))

        if conf < self.min_confidence:
            return None

        return text, conf   # caller wraps into PlateDetection with bbox

    def recognize_plate(
        self,
        frame: np.ndarray,
        bbox: "BoundingBox",
        preprocess: bool = True,
    ) -> Optional["PlateDetection"]:
        """
        Synchronous interface — matches PaddleOCRService signature.
        Used as a fallback / test path; the async path calls recognize_plate_crop().
        """
        x1, y1, x2, y2 = map(int, [bbox.x1, bbox.y1, bbox.x2, bbox.y2])
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        crop   = frame[y1:y2, x1:x2]
        result = self.recognize_plate_crop(crop)

        if result is None:
            return None

        text, conf = result

        if _SHARED_SCHEMAS:
            return PlateDetection(text=text, confidence=conf, bbox=bbox, raw_text=text)

        from types import SimpleNamespace
        return SimpleNamespace(text=text, confidence=conf, bbox=bbox, raw_text=text)

    def warmup(self, iterations: int = 3):
        """Pre-run the ONNX session to avoid cold-start latency."""
        logger.info("Warming up CRNNOCRService...")
        dummy = np.zeros((1, 1, IMG_H, IMG_W), dtype=np.float32)
        for _ in range(iterations):
            self.sess.run(None, {"input": dummy})
        logger.success("CRNNOCRService warmup complete")
