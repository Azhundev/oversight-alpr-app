"""
Camera Ingestion Service
Supports RTSP streams, video files, and USB cameras
Optimized for NVIDIA Jetson with hardware decoding
"""

import cv2
import numpy as np
from loguru import logger
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import time
from threading import Thread, Event
from queue import Queue, Full
import yaml


class CameraSource:
    """Single camera/video source handler"""

    def __init__(
        self,
        source_id: str,
        source_uri: str,
        name: str = "Camera",
        location: Optional[str] = None,
        use_hw_decode: bool = True,
        buffer_size: int = 1,
        target_fps: Optional[int] = None,
        target_resolution: Optional[Tuple[int, int]] = None,
        loop_video: bool = True,
    ):
        """
        Initialize camera source

        Args:
            source_id: Unique identifier (e.g., "CAM-001")
            source_uri: URI (RTSP URL, file path, or camera index)
            name: Human-readable name
            location: Physical location description
            use_hw_decode: Use hardware decoder on Jetson (H264/H265)
            buffer_size: Internal frame buffer size (1 = no buffering)
            target_fps: Target frame rate (None = use source FPS)
            target_resolution: Target resolution (width, height)
            loop_video: Loop video files (ignored for RTSP/USB)
        """
        self.source_id = source_id
        self.source_uri = source_uri
        self.name = name
        self.location = location
        self.use_hw_decode = use_hw_decode
        self.buffer_size = buffer_size
        self.target_fps = target_fps
        self.target_resolution = target_resolution
        self.loop_video = loop_video

        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.thread: Optional[Thread] = None
        self.stop_event = Event()
        self.frame_queue: Queue = Queue(maxsize=max(buffer_size, 2))  # Minimum 2 for smoother playback

        # Stats
        self.frame_count = 0
        self.dropped_frames = 0
        self.actual_fps = 0.0
        self.last_fps_update = time.time()
        self.fps_frame_count = 0

        self._initialize()

    def _initialize(self):
        """Initialize video capture"""
        logger.info(f"Initializing camera source: {self.name} ({self.source_id})")

        try:
            # Parse source URI
            if isinstance(self.source_uri, int) or self.source_uri.isdigit():
                # USB camera (e.g., 0, 1, 2)
                source = int(self.source_uri)
                logger.info(f"Opening USB camera: {source}")
            elif self.source_uri.startswith("rtsp://"):
                # RTSP stream
                source = self.source_uri
                logger.info(f"Opening RTSP stream: {source}")
            else:
                # Video file
                source = str(self.source_uri)
                if not Path(source).exists():
                    raise FileNotFoundError(f"Video file not found: {source}")
                logger.info(f"Opening video file: {source}")

            # Create VideoCapture
            if self.use_hw_decode and isinstance(source, str) and source.startswith("rtsp://"):
                # Use GStreamer pipeline for hardware decoding on Jetson
                gst_pipeline = self._build_gstreamer_pipeline(source)
                self.cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
                logger.info("Using GStreamer hardware decoder")
            else:
                self.cap = cv2.VideoCapture(source)

            if not self.cap.isOpened():
                raise RuntimeError(f"Failed to open camera source: {source}")

            # Configure capture
            if self.target_resolution:
                width, height = self.target_resolution
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            if self.target_fps:
                self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)

            # Reduce buffering for RTSP streams (lower latency)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Get actual properties
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)

            logger.success(
                f"Camera initialized: {actual_width}x{actual_height} @ {actual_fps:.1f} FPS"
            )

        except Exception as e:
            logger.error(f"Failed to initialize camera: {e}")
            raise

    def _build_gstreamer_pipeline(self, rtsp_url: str) -> str:
        """
        Build GStreamer pipeline for hardware-accelerated RTSP decoding on Jetson

        Args:
            rtsp_url: RTSP stream URL

        Returns:
            GStreamer pipeline string
        """
        pipeline = (
            f"rtspsrc location={rtsp_url} latency=0 ! "
            "rtph264depay ! "
            "h264parse ! "
            "nvv4l2decoder ! "  # Jetson hardware decoder
            "nvvidconv ! "
            "video/x-raw, format=BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=BGR ! "
            "appsink drop=1"
        )
        return pipeline

    def start(self):
        """Start capture thread"""
        if self.is_running:
            logger.warning(f"Camera {self.source_id} already running")
            return

        self.is_running = True
        self.stop_event.clear()
        self.thread = Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        logger.info(f"Camera {self.source_id} capture thread started")

    def stop(self):
        """Stop capture thread"""
        if not self.is_running:
            return

        logger.info(f"Stopping camera {self.source_id}...")
        self.is_running = False
        self.stop_event.set()

        if self.thread:
            self.thread.join(timeout=5.0)

        if self.cap:
            self.cap.release()

        logger.info(f"Camera {self.source_id} stopped")

    def _capture_loop(self):
        """Background capture loop"""
        logger.info(f"Capture loop started for {self.source_id}")

        while self.is_running and not self.stop_event.is_set():
            try:
                ret, frame = self.cap.read()

                if not ret:
                    # For video files, check if we should loop
                    if not self.source_uri.startswith("rtsp://"):
                        if self.loop_video:
                            logger.debug(f"Looping video: {self.source_id}")
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            continue
                        else:
                            logger.info(f"Video ended: {self.source_id}")
                            break
                    else:
                        # RTSP stream disconnected
                        logger.error(f"RTSP stream disconnected: {self.source_id}")
                        break

                self.frame_count += 1

                # Update FPS calculation
                self._update_fps()

                # Add frame to queue (non-blocking)
                try:
                    self.frame_queue.put_nowait(frame)
                except Full:
                    # Queue full, drop oldest frame
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait(frame)
                        self.dropped_frames += 1
                    except:
                        pass

                # Small delay to prevent CPU spinning and allow processing to catch up
                # For video files at 30fps, ~33ms per frame
                if not self.source_uri.startswith("rtsp://") and self.target_fps:
                    time.sleep(1.0 / self.target_fps * 0.5)  # Half speed to give processing time

            except Exception as e:
                logger.error(f"Error in capture loop for {self.source_id}: {e}")
                time.sleep(0.1)

        logger.info(f"Capture loop ended for {self.source_id}")

    def _update_fps(self):
        """Calculate actual FPS"""
        self.fps_frame_count += 1
        elapsed = time.time() - self.last_fps_update

        if elapsed >= 1.0:  # Update every second
            self.actual_fps = self.fps_frame_count / elapsed
            self.fps_frame_count = 0
            self.last_fps_update = time.time()

    def read(self, get_latest: bool = True) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read next frame from queue

        Args:
            get_latest: If True, skip buffered frames and get the most recent one

        Returns:
            Tuple of (success, frame)
        """
        if not self.is_running:
            return False, None

        try:
            if get_latest:
                # Flush queue and get latest frame to prevent buffering
                frame = None
                while not self.frame_queue.empty():
                    try:
                        frame = self.frame_queue.get_nowait()
                    except:
                        break

                if frame is not None:
                    return True, frame

                # If queue was empty, wait for next frame
                frame = self.frame_queue.get(timeout=0.1)
                return True, frame
            else:
                # Get next frame in order (may be buffered)
                frame = self.frame_queue.get(timeout=0.1)
                return True, frame
        except:
            return False, None

    def get_properties(self) -> Dict[str, Any]:
        """Get camera properties and stats"""
        return {
            "source_id": self.source_id,
            "name": self.name,
            "location": self.location,
            "source_uri": self.source_uri,
            "is_running": self.is_running,
            "frame_count": self.frame_count,
            "dropped_frames": self.dropped_frames,
            "actual_fps": self.actual_fps,
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self.cap else 0,
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self.cap else 0,
        }


class CameraManager:
    """Manages multiple camera sources"""

    def __init__(self, config_path: str = "config/cameras.yaml"):
        """
        Initialize camera manager

        Args:
            config_path: Path to cameras configuration file
        """
        self.config_path = config_path
        self.cameras: Dict[str, CameraSource] = {}
        self._load_config()

    def _load_config(self):
        """Load camera configuration"""
        logger.info(f"Loading camera configuration: {self.config_path}")

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Load RTSP cameras
        for cam_config in config.get('cameras', []):
            if not cam_config.get('enabled', True):
                logger.info(f"Skipping disabled camera: {cam_config['id']}")
                continue

            camera = CameraSource(
                source_id=cam_config['id'],
                source_uri=cam_config['rtsp_url'],
                name=cam_config['name'],
                location=cam_config.get('location'),
                use_hw_decode=True,
                target_resolution=self._parse_resolution(
                    cam_config.get('settings', {}).get('resolution')
                ),
                target_fps=cam_config.get('settings', {}).get('fps'),
            )
            self.cameras[cam_config['id']] = camera
            logger.info(f"Loaded camera: {cam_config['id']} - {cam_config['name']}")

        # Load video file sources
        for video_config in config.get('video_sources', []):
            if not video_config.get('enabled', True):
                logger.info(f"Skipping disabled video source: {video_config['id']}")
                continue

            camera = CameraSource(
                source_id=video_config['id'],
                source_uri=video_config['file_path'],
                name=video_config['name'],
                location="Video File",
                use_hw_decode=False,  # Video files don't need HW decode
                loop_video=video_config.get('loop', True),  # Default to loop
                target_fps=video_config.get('settings', {}).get('fps'),  # Control playback speed
            )
            self.cameras[video_config['id']] = camera
            logger.info(f"Loaded video source: {video_config['id']} - {video_config['name']}")

        logger.success(f"Loaded {len(self.cameras)} camera sources")

    def _parse_resolution(self, resolution_str: Optional[str]) -> Optional[Tuple[int, int]]:
        """Parse resolution string (e.g., '1920x1080') to tuple"""
        if not resolution_str:
            return None
        try:
            width, height = map(int, resolution_str.lower().split('x'))
            return (width, height)
        except:
            return None

    def start_all(self):
        """Start all camera sources"""
        logger.info("Starting all cameras...")
        for camera in self.cameras.values():
            camera.start()
        logger.success(f"Started {len(self.cameras)} cameras")

    def stop_all(self):
        """Stop all camera sources"""
        logger.info("Stopping all cameras...")
        for camera in self.cameras.values():
            camera.stop()
        logger.success("All cameras stopped")

    def get_camera(self, source_id: str) -> Optional[CameraSource]:
        """Get camera by ID"""
        return self.cameras.get(source_id)

    def get_all_cameras(self) -> Dict[str, CameraSource]:
        """Get all cameras"""
        return self.cameras

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all cameras"""
        return {
            camera_id: camera.get_properties()
            for camera_id, camera in self.cameras.items()
        }


if __name__ == "__main__":
    # Test camera manager
    import sys

    logger.info("Camera Ingestion Service Test")

    # Create manager
    manager = CameraManager("../../config/cameras.yaml")

    # Start all cameras
    manager.start_all()

    try:
        # Read frames from all cameras
        while True:
            for camera_id, camera in manager.get_all_cameras().items():
                ret, frame = camera.read()

                if ret and frame is not None:
                    # Display frame
                    props = camera.get_properties()
                    cv2.putText(
                        frame,
                        f"{props['name']} | FPS: {props['actual_fps']:.1f} | Frames: {props['frame_count']}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2
                    )

                    # Resize for display
                    display_frame = cv2.resize(frame, (960, 540))
                    cv2.imshow(f"Camera: {camera_id}", display_frame)

            # Print stats every 5 seconds
            if int(time.time()) % 5 == 0:
                stats = manager.get_stats()
                logger.info(f"Camera stats: {stats}")

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        logger.info("Interrupted by user")

    finally:
        manager.stop_all()
        cv2.destroyAllWindows()
        logger.info("Test complete")
