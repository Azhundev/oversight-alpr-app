"""
Crop Utilities for ALPR
Optimized JPEG crop generation with size/quality limits
"""

import cv2
import numpy as np
from typing import Tuple, Optional
from loguru import logger

from shared.schemas.event import BoundingBox


class CropOptimizer:
    """
    Optimized crop generation for ALPR

    Key optimizations:
    - Limit crops to ~640px long side (reduces I/O)
    - JPEG quality 80-85 (keeps CPU/I/O light)
    - Fast resizing for performance
    """

    def __init__(
        self,
        max_dimension: int = 640,
        jpeg_quality: int = 85,
        use_fast_resize: bool = True
    ):
        """
        Initialize crop optimizer

        Args:
            max_dimension: Maximum dimension (long side) in pixels
            jpeg_quality: JPEG compression quality (80-85 recommended)
            use_fast_resize: Use bilinear (fast) vs bicubic (quality)
        """
        self.max_dimension = max_dimension
        self.jpeg_quality = jpeg_quality
        self.resize_interpolation = (
            cv2.INTER_LINEAR if use_fast_resize else cv2.INTER_CUBIC
        )

    def extract_crop(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
        expand_ratio: float = 0.0
    ) -> Optional[np.ndarray]:
        """
        Extract crop from frame with optional expansion

        Args:
            frame: Full frame image
            bbox: Bounding box to crop
            expand_ratio: Expand bbox by this ratio (e.g., 0.1 = 10% larger)

        Returns:
            Cropped image or None if invalid
        """
        h, w = frame.shape[:2]

        # Extract bbox coordinates
        x1, y1, x2, y2 = bbox.x1, bbox.y1, bbox.x2, bbox.y2

        # Expand bbox if requested
        if expand_ratio > 0:
            bbox_w = x2 - x1
            bbox_h = y2 - y1
            expand_w = bbox_w * expand_ratio
            expand_h = bbox_h * expand_ratio

            x1 -= expand_w / 2
            x2 += expand_w / 2
            y1 -= expand_h / 2
            y2 += expand_h / 2

        # Clip to frame bounds
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(w, int(x2))
        y2 = min(h, int(y2))

        # Validate crop
        if x2 <= x1 or y2 <= y1:
            logger.warning(f"Invalid crop bounds: ({x1},{y1}) to ({x2},{y2})")
            return None

        # Extract crop
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            logger.warning("Empty crop extracted")
            return None

        return crop

    def resize_crop(self, crop: np.ndarray) -> np.ndarray:
        """
        Resize crop if larger than max_dimension

        Args:
            crop: Input crop

        Returns:
            Resized crop (or original if already small enough)
        """
        h, w = crop.shape[:2]
        max_side = max(h, w)

        # Already small enough?
        if max_side <= self.max_dimension:
            return crop

        # Calculate scale factor
        scale = self.max_dimension / max_side

        # Resize
        new_w = int(w * scale)
        new_h = int(h * scale)

        resized = cv2.resize(
            crop,
            (new_w, new_h),
            interpolation=self.resize_interpolation
        )

        logger.debug(
            f"Resized crop from {w}x{h} to {new_w}x{new_h} "
            f"(scale: {scale:.2f})"
        )

        return resized

    def encode_jpeg(
        self,
        crop: np.ndarray,
        resize: bool = True
    ) -> Tuple[bool, bytes]:
        """
        Encode crop as optimized JPEG

        Args:
            crop: Input crop
            resize: Apply resize before encoding

        Returns:
            (success, jpeg_bytes)
        """
        # Resize if enabled
        if resize:
            crop = self.resize_crop(crop)

        # Encode as JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        success, encoded = cv2.imencode('.jpg', crop, encode_param)

        if not success:
            logger.error("Failed to encode JPEG")
            return False, b''

        jpeg_bytes = encoded.tobytes()

        logger.debug(
            f"Encoded JPEG: {len(jpeg_bytes)} bytes "
            f"(quality: {self.jpeg_quality})"
        )

        return True, jpeg_bytes

    def create_optimized_crop(
        self,
        frame: np.ndarray,
        bbox: BoundingBox,
        expand_ratio: float = 0.0,
        return_bytes: bool = False
    ) -> Optional[np.ndarray | bytes]:
        """
        Create optimized crop from frame (one-shot helper)

        Args:
            frame: Full frame image
            bbox: Bounding box to crop
            expand_ratio: Expand bbox by this ratio
            return_bytes: Return JPEG bytes instead of numpy array

        Returns:
            Optimized crop (image or JPEG bytes) or None
        """
        # Extract crop
        crop = self.extract_crop(frame, bbox, expand_ratio)

        if crop is None:
            return None

        # Return as JPEG bytes?
        if return_bytes:
            success, jpeg_bytes = self.encode_jpeg(crop, resize=True)
            return jpeg_bytes if success else None

        # Return as resized numpy array
        return self.resize_crop(crop)


# Global instances for convenience
vehicle_crop_optimizer = CropOptimizer(
    max_dimension=640,
    jpeg_quality=85,
    use_fast_resize=True
)

plate_crop_optimizer = CropOptimizer(
    max_dimension=640,
    jpeg_quality=85,
    use_fast_resize=True
)


def create_vehicle_crop(
    frame: np.ndarray,
    bbox: BoundingBox,
    expand_ratio: float = 0.1,  # 10% expansion for context
    return_bytes: bool = False
) -> Optional[np.ndarray | bytes]:
    """
    Create optimized vehicle crop

    Args:
        frame: Full frame image
        bbox: Vehicle bounding box
        expand_ratio: Expand bbox for context
        return_bytes: Return JPEG bytes

    Returns:
        Optimized crop or None
    """
    return vehicle_crop_optimizer.create_optimized_crop(
        frame, bbox, expand_ratio, return_bytes
    )


def create_plate_crop(
    frame: np.ndarray,
    bbox: BoundingBox,
    expand_ratio: float = 0.05,  # 5% expansion (plates are tight)
    return_bytes: bool = False
) -> Optional[np.ndarray | bytes]:
    """
    Create optimized plate crop

    Args:
        frame: Full frame image
        bbox: Plate bounding box
        expand_ratio: Small expansion
        return_bytes: Return JPEG bytes

    Returns:
        Optimized crop or None
    """
    return plate_crop_optimizer.create_optimized_crop(
        frame, bbox, expand_ratio, return_bytes
    )


# Example usage
if __name__ == "__main__":
    # Create test image
    test_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 128

    # Create test bbox
    test_bbox = BoundingBox(x1=100, y1=100, x2=500, y2=400)

    # Create optimized crop
    crop = create_vehicle_crop(test_frame, test_bbox)
    print(f"Crop shape: {crop.shape if crop is not None else 'None'}")

    # Create JPEG bytes
    jpeg_bytes = create_vehicle_crop(test_frame, test_bbox, return_bytes=True)
    print(f"JPEG size: {len(jpeg_bytes) if jpeg_bytes else 0} bytes")

    # Compare sizes
    full_crop = test_frame[100:400, 100:500]
    _, full_encoded = cv2.imencode('.jpg', full_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"Unoptimized JPEG: {len(full_encoded.tobytes())} bytes")
    print(f"Optimized JPEG: {len(jpeg_bytes) if jpeg_bytes else 0} bytes")

    if jpeg_bytes:
        savings = (1 - len(jpeg_bytes) / len(full_encoded.tobytes())) * 100
        print(f"Size reduction: {savings:.1f}%")
