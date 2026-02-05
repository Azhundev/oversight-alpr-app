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
            if self.use_hw_decode and isinstance(source, str):
                # Use GStreamer for RTSP streams or video files
                if source.startswith("rtsp://") or Path(source).exists():
                    # Detect codec for video files
                    codec = self._detect_codec(source)
                    logger.info(f"Using codec: {codec}")

                    gst_pipeline = self._build_gstreamer_pipeline(source, codec)
                    logger.info(f"GStreamer pipeline: {gst_pipeline}")
                    self.cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)

                    if self.cap.isOpened():
                        logger.success(f"✅ Hardware decoder initialized successfully ({codec.upper()})")
                    else:
                        logger.error("❌ Hardware decoder failed, falling back to CPU")
                        self.cap = cv2.VideoCapture(source)
                else:
                    self.cap = cv2.VideoCapture(source)
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

    def _detect_codec(self, source: str) -> str:
        """
        Auto-detect video codec (H.264 or H.265)

        Args:
            source: RTSP URL or file path

        Returns:
            Codec type: "h264" or "h265"
        """
        if source.startswith("rtsp://"):
            # For RTSP, default to h264 (can be configured per camera)
            return "h264"
        else:
            # Probe video file for codec
            import subprocess
            try:
                result = subprocess.run(
                    ["gst-discoverer-1.0", source],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                output = result.stdout.lower()
                if "h.265" in output or "h265" in output or "hevc" in output:
                    logger.info(f"Detected H.265/HEVC codec in {source}")
                    return "h265"
                else:
                    logger.info(f"Detected H.264 codec in {source}")
                    return "h264"
            except Exception as e:
                logger.warning(f"Failed to detect codec, defaulting to h264: {e}")
                return "h264"

    def _build_gstreamer_pipeline(self, source: str, codec: str = "h264") -> str:
        """
        Build GStreamer pipeline for hardware-accelerated decoding on Jetson
        Supports both RTSP streams and video files with H.264/H.265 codecs

        Args:
            source: RTSP URL or video file path
            codec: Video codec ("h264" or "h265")

        Returns:
            GStreamer pipeline string
        """
        # Codec-specific parsing and depay elements
        parser = "h264parse" if codec == "h264" else "h265parse"

        if source.startswith("rtsp://"):
            # RTSP stream with hardware decode and optimizations
            depay = f"rtp{codec}depay" if codec in ["h264", "h265"] else "rtph264depay"
            pipeline = (
                f"rtspsrc location={source} "
                "latency=0 "  # Low latency
                "buffer-mode=0 "  # Auto buffer mode
                "protocols=tcp ! "  # TCP for stability
                f"{depay} ! "
                f"{parser} ! "
                "nvv4l2decoder "
                "enable-max-performance=1 "  # Max performance mode
                "drop-frame-interval=0 ! "  # Don't drop frames
                "nvvidconv ! "
                "video/x-raw, format=BGRx ! "
                "videoconvert ! "
                "video/x-raw, format=BGR ! "
                "appsink "
                "max-buffers=1 "  # Minimal buffering for low latency
                "drop=true "  # Drop old frames if processing is slow
                "sync=false"  # Don't sync to clock for realtime
            )
        else:
            # Video file with hardware decode
            # Use direct pipeline instead of uridecodebin to avoid seeking/looping issues

            # Ensure absolute path
            from pathlib import Path
            abs_source = str(Path(source).resolve())

            # Detect container format from file extension
            ext = Path(source).suffix.lower()
            if ext == '.avi':
                demux = 'avidemux'
            elif ext in ['.mp4', '.mov', '.m4v']:
                demux = 'qtdemux'
            elif ext in ['.mkv', '.webm']:
                demux = 'matroskademux'
            else:
                demux = 'qtdemux'  # Default to qtdemux

            pipeline = (
                f"filesrc location={abs_source} ! "  # Direct file source
                f"{demux} ! "  # Container demuxer
                f"{parser} ! "  # H.264/H.265 parser
                "nvv4l2decoder "  # Hardware decoder
                "enable-max-performance=1 ! "  # Max performance
                "nvvidconv ! "  # Convert from NVMM to regular memory
                "video/x-raw,format=BGRx ! "  # Intermediate format
                "videoconvert ! "  # Final conversion
                "video/x-raw,format=BGR ! "  # BGR for OpenCV
                "appsink max-buffers=1 drop=true sync=false"  # Sink
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
        """
        Background capture loop - runs in separate thread
        Continuously reads frames and adds them to queue for processing
        """
        logger.info(f"Capture loop started for {self.source_id}")

        while self.is_running and not self.stop_event.is_set():
            try:
                # Read next frame from capture device/file
                ret, frame = self.cap.read()

                if not ret:
                    # Handle end-of-stream based on source type
                    if not self.source_uri.startswith("rtsp://"):
                        # Video file reached end
                        if self.loop_video:
                            # Reset to beginning for continuous playback
                            logger.debug(f"Looping video: {self.source_id}")
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            continue
                        else:
                            # Stop playback when video ends
                            logger.info(f"Video ended: {self.source_id}")
                            break
                    else:
                        # RTSP stream disconnected or failed
                        logger.error(f"RTSP stream disconnected: {self.source_id}")
                        break

                # Increment frame counter for statistics
                self.frame_count += 1

                # Update actual FPS calculation
                self._update_fps()

                # Add frame to queue (non-blocking to prevent thread from blocking)
                try:
                    self.frame_queue.put_nowait(frame)
                except Full:
                    # Queue is full - drop oldest frame and add new one
                    # This implements a sliding window to reduce latency
                    try:
                        self.frame_queue.get_nowait()  # Remove oldest
                        self.frame_queue.put_nowait(frame)  # Add newest
                        self.dropped_frames += 1
                    except:
                        pass

                # Rate limiting for video files to match playback speed
                # Prevents reading entire video into memory instantly
                # For video files at 30fps, ~33ms per frame
                if not self.source_uri.startswith("rtsp://") and self.target_fps:
                    # Use half speed (50% of frame time) to allow processing to keep up
                    time.sleep(1.0 / self.target_fps * 0.5)

            except Exception as e:
                logger.error(f"Error in capture loop for {self.source_id}: {e}")
                time.sleep(0.1)  # Brief pause before retry

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
                       This reduces latency for real-time processing by discarding old frames

        Returns:
            Tuple of (success, frame)
        """
        if not self.is_running:
            return False, None

        try:
            if get_latest:
                # Flush queue and get latest frame to minimize latency
                # Important for real-time ALPR - we want the freshest frame, not buffered ones
                frame = None
                while not self.frame_queue.empty():
                    try:
                        # Discard all queued frames except the last one
                        frame = self.frame_queue.get_nowait()
                    except:
                        break

                if frame is not None:
                    return True, frame

                # If queue was empty, wait briefly for next frame
                frame = self.frame_queue.get(timeout=0.1)
                return True, frame
            else:
                # Get next frame in order (preserves temporal sequence)
                # Used when frame order matters (e.g., video recording)
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
                use_hw_decode=False,  # Disable hardware decode for video files (seeking issues with GStreamer)
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
