"""
ByteTrack Multi-Object Tracking Service
Optimized for ALPR vehicle tracking on Jetson Orin NX

Based on: ByteTrack: Multi-Object Tracking by Associating Every Detection Box
Paper: https://arxiv.org/abs/2110.06864
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from loguru import logger
import yaml
from pathlib import Path

# Kalman filter for motion prediction
from filterpy.kalman import KalmanFilter
# Linear assignment problem solver
from lap import lapjv
# Fast IoU calculation
from cython_bbox import bbox_overlaps as bbox_ious


@dataclass
class TrackState:
    """Track state enumeration"""
    NEW = 0      # New track (tentative)
    TRACKED = 1  # Confirmed track
    LOST = 2     # Lost track (being buffered)
    REMOVED = 3  # Removed track


@dataclass
class Detection:
    """Detection result for tracking"""
    bbox: np.ndarray  # [x1, y1, x2, y2]
    confidence: float
    class_id: int = 0
    features: Optional[np.ndarray] = None  # For ReID


class KalmanBoxTracker:
    """
    Kalman filter for tracking bounding boxes in image space.

    State vector: [x_center, y_center, area, aspect_ratio, dx, dy, da, dr]
    Observation: [x_center, y_center, area, aspect_ratio]
    """

    def __init__(self, bbox: np.ndarray):
        """
        Initialize Kalman filter with bounding box

        Args:
            bbox: [x1, y1, x2, y2]
        """
        self.kf = KalmanFilter(dim_x=8, dim_z=4)

        # State transition matrix (constant velocity model)
        self.kf.F = np.array([
            [1, 0, 0, 0, 1, 0, 0, 0],  # x = x + dx
            [0, 1, 0, 0, 0, 1, 0, 0],  # y = y + dy
            [0, 0, 1, 0, 0, 0, 1, 0],  # a = a + da
            [0, 0, 0, 1, 0, 0, 0, 1],  # r = r + dr
            [0, 0, 0, 0, 1, 0, 0, 0],  # dx = dx
            [0, 0, 0, 0, 0, 1, 0, 0],  # dy = dy
            [0, 0, 0, 0, 0, 0, 1, 0],  # da = da
            [0, 0, 0, 0, 0, 0, 0, 1],  # dr = dr
        ])

        # Measurement matrix (observe position and size)
        self.kf.H = np.array([
            [1, 0, 0, 0, 0, 0, 0, 0],  # measure x
            [0, 1, 0, 0, 0, 0, 0, 0],  # measure y
            [0, 0, 1, 0, 0, 0, 0, 0],  # measure a
            [0, 0, 0, 1, 0, 0, 0, 0],  # measure r
        ])

        # Measurement noise covariance
        self.kf.R[2:, 2:] *= 10.0  # Higher uncertainty for area and aspect ratio

        # Process noise covariance
        self.kf.P[4:, 4:] *= 1000.0  # High uncertainty for velocities
        self.kf.P *= 10.0

        # Process noise
        self.kf.Q[-1, -1] *= 0.01
        self.kf.Q[4:, 4:] *= 0.01

        # Initialize state with bbox
        self.kf.x[:4] = self._bbox_to_z(bbox)

        self.time_since_update = 0
        self.hits = 0
        self.hit_streak = 0
        self.age = 0

    def _bbox_to_z(self, bbox: np.ndarray) -> np.ndarray:
        """
        Convert bounding box to measurement format

        Args:
            bbox: [x1, y1, x2, y2]

        Returns:
            z: [x_center, y_center, area, aspect_ratio]
        """
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = bbox[0] + w / 2.0
        y = bbox[1] + h / 2.0
        area = w * h
        aspect_ratio = w / float(h) if h > 0 else 1.0
        return np.array([x, y, area, aspect_ratio]).reshape((4, 1))

    def _z_to_bbox(self, z: np.ndarray) -> np.ndarray:
        """
        Convert measurement format to bounding box

        Args:
            z: [x_center, y_center, area, aspect_ratio]

        Returns:
            bbox: [x1, y1, x2, y2]
        """
        w = np.sqrt(z[2] * z[3])
        h = z[2] / w if w > 0 else 0
        x1 = z[0] - w / 2.0
        y1 = z[1] - h / 2.0
        x2 = z[0] + w / 2.0
        y2 = z[1] + h / 2.0
        return np.array([x1, y1, x2, y2]).reshape((1, 4))

    def predict(self) -> np.ndarray:
        """
        Predict next state using Kalman filter

        Returns:
            Predicted bbox [x1, y1, x2, y2]
        """
        # Ensure area and aspect ratio stay positive
        if self.kf.x[2] + self.kf.x[6] <= 0:
            self.kf.x[6] = 0

        self.kf.predict()
        self.age += 1

        if self.time_since_update > 0:
            self.hit_streak = 0

        self.time_since_update += 1

        return self._z_to_bbox(self.kf.x[:4])[0]

    def update(self, bbox: np.ndarray):
        """
        Update state with new detection

        Args:
            bbox: [x1, y1, x2, y2]
        """
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1
        self.kf.update(self._bbox_to_z(bbox))

    def get_state(self) -> np.ndarray:
        """
        Get current bounding box estimate

        Returns:
            bbox: [x1, y1, x2, y2]
        """
        return self._z_to_bbox(self.kf.x[:4])[0]


class Track:
    """Single object track"""

    def __init__(self, detection: Detection, track_id: int):
        """
        Initialize track with detection

        Args:
            detection: Detection object
            track_id: Unique track identifier
        """
        self.track_id = track_id
        self.kalman_filter = KalmanBoxTracker(detection.bbox)

        self.state = TrackState.NEW
        self.is_activated = False

        self.confidence = detection.confidence
        self.class_id = detection.class_id
        self.features = detection.features

        self.frame_id = 0
        self.start_frame = 0
        self.tracklet_len = 0

    def predict(self):
        """Predict next position"""
        bbox = self.kalman_filter.predict()
        return bbox

    def update(self, detection: Detection, frame_id: int):
        """
        Update track with new detection

        Args:
            detection: Detection object
            frame_id: Current frame number
        """
        self.frame_id = frame_id
        self.tracklet_len += 1

        self.kalman_filter.update(detection.bbox)
        self.confidence = detection.confidence

        self.state = TrackState.TRACKED
        self.is_activated = True

    def activate(self, frame_id: int):
        """Activate new track"""
        self.track_id = self.track_id
        self.tracklet_len = 0
        self.state = TrackState.TRACKED
        self.is_activated = True
        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, detection: Detection, frame_id: int):
        """Re-activate lost track"""
        self.kalman_filter.update(detection.bbox)
        self.tracklet_len = 0
        self.state = TrackState.TRACKED
        self.is_activated = True
        self.frame_id = frame_id
        self.confidence = detection.confidence

    def mark_lost(self):
        """Mark track as lost"""
        self.state = TrackState.LOST

    def mark_removed(self):
        """Mark track as removed"""
        self.state = TrackState.REMOVED

    @property
    def tlbr(self) -> np.ndarray:
        """Get current bbox [x1, y1, x2, y2]"""
        return self.kalman_filter.get_state()


class ByteTrackService:
    """
    ByteTrack multi-object tracker for ALPR

    Key features:
    - Associates both high and low confidence detections
    - Kalman filter for motion prediction
    - Track buffering for temporary occlusions
    - Configurable via YAML
    """

    def __init__(self, config_path: str = "config/tracking.yaml"):
        """
        Initialize ByteTrack tracker

        Args:
            config_path: Path to tracking configuration file
        """
        self.config_path = config_path

        # Load configuration
        logger.info(f"Loading tracking configuration from {config_path}")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        self.config = config['tracking']['bytetrack']

        # ByteTrack parameters
        self.track_thresh = self.config['track_thresh']  # High confidence threshold (0.5)
        self.track_buffer = self.config['track_buffer']  # Keep lost tracks (30 frames)
        self.match_thresh = self.config['match_thresh']  # IoU matching threshold (0.8)
        self.min_box_area = self.config['min_box_area']  # Minimum bbox area (100 px²)

        # Track management
        self.tracked_tracks: List[Track] = []
        self.lost_tracks: List[Track] = []
        self.removed_tracks: List[Track] = []

        self.frame_id = 0
        self.next_track_id = 0

        logger.success(
            f"ByteTrack initialized: track_thresh={self.track_thresh}, "
            f"buffer={self.track_buffer}, match_thresh={self.match_thresh}"
        )

    def update(self, detections: List[Detection]) -> List[Track]:
        """
        Update tracker with new detections

        Args:
            detections: List of Detection objects for current frame

        Returns:
            List of active Track objects
        """
        self.frame_id += 1

        # Separate high and low confidence detections
        high_detections = [d for d in detections if d.confidence >= self.track_thresh]
        low_detections = [d for d in detections if d.confidence < self.track_thresh]

        # Filter by minimum box area
        high_detections = self._filter_small_boxes(high_detections)
        low_detections = self._filter_small_boxes(low_detections)

        # Predict current positions of tracks
        for track in self.tracked_tracks:
            track.predict()

        # === First association: high confidence detections ===
        matches_high, unmatched_track_indices, unmatched_det_indices = self._associate_detections_to_tracks(
            high_detections, self.tracked_tracks
        )

        # === Second association: remaining tracks with low confidence detections ===
        # Get the actual unmatched tracks (not indices)
        unmatched_tracks = [self.tracked_tracks[i] for i in unmatched_track_indices if i < len(self.tracked_tracks)]
        matches_low, unmatched_tracks_second_indices, unmatched_detections_low = self._associate_detections_to_tracks(
            low_detections, unmatched_tracks
        )

        # Mark tracks that remain unmatched as lost
        for i in unmatched_tracks_second_indices:
            if i < len(unmatched_tracks):
                track = unmatched_tracks[i]
                if track.state != TrackState.LOST:
                    track.mark_lost()
                    self.lost_tracks.append(track)

        # === Third association: lost tracks with remaining high confidence detections ===
        # Filter valid indices only
        remaining_high_detections = [high_detections[i] for i in unmatched_det_indices if i < len(high_detections)]
        matches_lost, unmatched_lost_indices, unmatched_high_indices = self._associate_detections_to_tracks(
            remaining_high_detections, self.lost_tracks, threshold=0.5
        )

        # Re-activate matched lost tracks
        for i_track, i_det in matches_lost:
            if i_track < len(self.lost_tracks) and i_det < len(remaining_high_detections):
                track = self.lost_tracks[i_track]
                det = remaining_high_detections[i_det]
                track.re_activate(det, self.frame_id)
                self.tracked_tracks.append(track)

        # Create new tracks for unmatched high confidence detections
        for i in unmatched_high_indices:
            if i < len(remaining_high_detections):
                det = remaining_high_detections[i]
                if det.confidence >= self.track_thresh:
                    new_track = Track(det, self._next_id())
                    new_track.activate(self.frame_id)
                    self.tracked_tracks.append(new_track)

        # Update lost tracks buffer
        self.lost_tracks = [
            t for t in self.lost_tracks
            if self.frame_id - t.frame_id <= self.track_buffer
        ]

        # Move old lost tracks to removed
        for track in self.lost_tracks:
            if self.frame_id - track.frame_id > self.track_buffer:
                track.mark_removed()
                self.removed_tracks.append(track)

        # Return only active tracked tracks
        output_tracks = [t for t in self.tracked_tracks if t.is_activated]

        return output_tracks

    def _associate_detections_to_tracks(
        self,
        detections: List[Detection],
        tracks: List[Track],
        threshold: Optional[float] = None
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        Associate detections to tracks using IoU and linear assignment

        Args:
            detections: List of detections
            tracks: List of tracks
            threshold: IoU threshold (uses self.match_thresh if None)

        Returns:
            Tuple of (matches, unmatched_track_indices, unmatched_detection_indices)
            matches: List of (track_idx, detection_idx) tuples
        """
        if threshold is None:
            threshold = self.match_thresh

        if len(detections) == 0 or len(tracks) == 0:
            return [], list(range(len(tracks))), list(range(len(detections)))

        # Compute IoU matrix
        detection_boxes = np.array([d.bbox for d in detections])
        track_boxes = np.array([t.tlbr for t in tracks])

        iou_matrix = self._compute_iou_matrix(detection_boxes, track_boxes)

        # Convert IoU to cost (1 - IoU)
        cost_matrix = 1 - iou_matrix

        # Solve linear assignment problem
        matches, unmatched_tracks, unmatched_detections = self._linear_assignment(
            cost_matrix, threshold=1 - threshold
        )

        # Update matched tracks
        for i_track, i_det in matches:
            if i_track < len(tracks) and i_det < len(detections):
                tracks[i_track].update(detections[i_det], self.frame_id)
            else:
                logger.warning(
                    f"Invalid match indices: track={i_track}/{len(tracks)}, "
                    f"det={i_det}/{len(detections)}"
                )

        return matches, unmatched_tracks, unmatched_detections

    def _compute_iou_matrix(
        self,
        detections: np.ndarray,
        tracks: np.ndarray
    ) -> np.ndarray:
        """
        Compute IoU matrix between detections and tracks

        Args:
            detections: Array of detection bboxes (N, 4)
            tracks: Array of track bboxes (M, 4)

        Returns:
            IoU matrix (N, M)
        """
        # Use fast cython implementation
        ious = bbox_ious(
            np.ascontiguousarray(detections, dtype=np.float64),
            np.ascontiguousarray(tracks, dtype=np.float64)
        )
        return ious

    def _linear_assignment(
        self,
        cost_matrix: np.ndarray,
        threshold: float
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        Solve linear assignment problem with threshold

        Args:
            cost_matrix: Cost matrix (N, M)
            threshold: Maximum cost threshold

        Returns:
            Tuple of (matches, unmatched_rows, unmatched_cols)
        """
        if cost_matrix.size == 0:
            return [], list(range(cost_matrix.shape[0])), list(range(cost_matrix.shape[1]))

        # Solve using lap (Jonker-Volgenant algorithm)
        # lapjv returns: (cost, row_to_col, col_to_row) when return_cost=True
        # row_to_col[i] = j means row i is assigned to column j
        _, row_to_col, col_to_row = lapjv(cost_matrix, extend_cost=True, cost_limit=threshold, return_cost=True)

        matches = []
        unmatched_rows = []
        unmatched_cols = list(range(cost_matrix.shape[1]))

        for i, j in enumerate(row_to_col):
            if j >= 0 and j < cost_matrix.shape[1] and cost_matrix[i, j] <= threshold:
                matches.append((i, j))
                if j in unmatched_cols:
                    unmatched_cols.remove(j)
            else:
                unmatched_rows.append(i)

        return matches, unmatched_rows, unmatched_cols

    def _filter_small_boxes(self, detections: List[Detection]) -> List[Detection]:
        """
        Filter out detections with small bounding boxes

        Args:
            detections: List of detections

        Returns:
            Filtered list of detections
        """
        filtered = []
        for det in detections:
            w = det.bbox[2] - det.bbox[0]
            h = det.bbox[3] - det.bbox[1]
            area = w * h
            if area >= self.min_box_area:
                filtered.append(det)
        return filtered

    def _next_id(self) -> int:
        """Generate next track ID"""
        track_id = self.next_track_id
        self.next_track_id += 1
        return track_id

    def reset(self):
        """Reset tracker state"""
        self.tracked_tracks = []
        self.lost_tracks = []
        self.removed_tracks = []
        self.frame_id = 0
        self.next_track_id = 0
        logger.info("ByteTrack tracker reset")
