"""
Tracking Utilities
Helper functions for object tracking and visualization
"""

import numpy as np
import cv2
from typing import List, Tuple
from shared.schemas.event import BoundingBox


def calculate_iou(bbox1: BoundingBox, bbox2: BoundingBox) -> float:
    """
    Calculate Intersection over Union between two bounding boxes

    Args:
        bbox1: First bounding box
        bbox2: Second bounding box

    Returns:
        IoU score between 0 and 1
    """
    # Extract coordinates
    x1_1, y1_1, x2_1, y2_1 = bbox1.x1, bbox1.y1, bbox1.x2, bbox1.y2
    x1_2, y1_2, x2_2, y2_2 = bbox2.x1, bbox2.y1, bbox2.x2, bbox2.y2

    # Calculate intersection area
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)

    if x2_i < x1_i or y2_i < y1_i:
        return 0.0

    intersection = (x2_i - x1_i) * (y2_i - y1_i)

    # Calculate union area
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection

    if union == 0:
        return 0.0

    return intersection / union


def bbox_to_numpy(bbox: BoundingBox) -> np.ndarray:
    """
    Convert BoundingBox to numpy array

    Args:
        bbox: BoundingBox object

    Returns:
        numpy array [x1, y1, x2, y2]
    """
    return np.array([bbox.x1, bbox.y1, bbox.x2, bbox.y2])


def numpy_to_bbox(arr: np.ndarray) -> BoundingBox:
    """
    Convert numpy array to BoundingBox

    Args:
        arr: numpy array [x1, y1, x2, y2]

    Returns:
        BoundingBox object
    """
    return BoundingBox(x1=float(arr[0]), y1=float(arr[1]), x2=float(arr[2]), y2=float(arr[3]))


def get_track_color(track_id: int) -> Tuple[int, int, int]:
    """
    Get consistent color for track ID

    Args:
        track_id: Track identifier

    Returns:
        BGR color tuple
    """
    # Generate colors from track ID (consistent across frames)
    np.random.seed(track_id)
    color = tuple(np.random.randint(0, 255, 3).tolist())
    return color


def draw_track_id(
    frame: np.ndarray,
    bbox: BoundingBox,
    track_id: int,
    label: str = "",
    confidence: float = 0.0,
    color: Tuple[int, int, int] = (0, 255, 0)
) -> np.ndarray:
    """
    Draw track ID and label on frame

    Args:
        frame: Image frame
        bbox: Bounding box
        track_id: Track identifier
        label: Optional label text
        confidence: Detection confidence
        color: Box color (BGR)

    Returns:
        Annotated frame
    """
    x1, y1, x2, y2 = int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)

    # Draw bounding box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # Prepare label text
    if label:
        text = f"ID:{track_id} {label} {confidence:.2f}"
    else:
        text = f"ID:{track_id}"

    # Get text size
    (text_width, text_height), baseline = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
    )

    # Draw text background
    cv2.rectangle(
        frame,
        (x1, y1 - text_height - baseline - 5),
        (x1 + text_width, y1),
        color,
        -1
    )

    # Draw text
    cv2.putText(
        frame,
        text,
        (x1, y1 - baseline - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
        cv2.LINE_AA
    )

    return frame


def draw_track_trail(
    frame: np.ndarray,
    track_history: List[Tuple[int, int]],
    color: Tuple[int, int, int] = (0, 255, 255),
    max_points: int = 30
) -> np.ndarray:
    """
    Draw track trail (center points over time)

    Args:
        frame: Image frame
        track_history: List of (x, y) center points
        color: Trail color (BGR)
        max_points: Maximum number of points to draw

    Returns:
        Annotated frame
    """
    if len(track_history) < 2:
        return frame

    # Draw lines connecting points
    points = track_history[-max_points:]
    for i in range(1, len(points)):
        cv2.line(frame, points[i - 1], points[i], color, 2, cv2.LINE_AA)

    return frame


def get_bbox_center(bbox: BoundingBox) -> Tuple[int, int]:
    """
    Get center point of bounding box

    Args:
        bbox: BoundingBox object

    Returns:
        (x, y) center coordinates
    """
    x = int((bbox.x1 + bbox.x2) / 2)
    y = int((bbox.y1 + bbox.y2) / 2)
    return (x, y)


def is_bbox_stable(
    current_bbox: BoundingBox,
    previous_bbox: BoundingBox,
    iou_threshold: float = 0.8
) -> bool:
    """
    Check if bounding box is stable compared to previous frame

    Args:
        current_bbox: Current bounding box
        previous_bbox: Previous bounding box
        iou_threshold: Minimum IoU for stability

    Returns:
        True if bbox is stable
    """
    iou = calculate_iou(current_bbox, previous_bbox)
    return iou >= iou_threshold


def get_bbox_area(bbox: BoundingBox) -> float:
    """
    Calculate bounding box area

    Args:
        bbox: BoundingBox object

    Returns:
        Area in pixels
    """
    width = bbox.x2 - bbox.x1
    height = bbox.y2 - bbox.y1
    return width * height


def clip_bbox_to_frame(bbox: BoundingBox, frame_width: int, frame_height: int) -> BoundingBox:
    """
    Clip bounding box to frame boundaries

    Args:
        bbox: BoundingBox object
        frame_width: Frame width
        frame_height: Frame height

    Returns:
        Clipped BoundingBox
    """
    return BoundingBox(
        x1=max(0, min(bbox.x1, frame_width)),
        y1=max(0, min(bbox.y1, frame_height)),
        x2=max(0, min(bbox.x2, frame_width)),
        y2=max(0, min(bbox.y2, frame_height))
    )
