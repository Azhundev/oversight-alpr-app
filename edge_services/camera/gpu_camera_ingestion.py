"""
GPU-Accelerated Camera Ingestion
Fixes bottlenecks: CPU decode, CPU↔GPU copies, multi-stream support
"""

import cv2
import numpy as np
from loguru import logger
from typing import Optional, Tuple
import threading
import queue
import time


class GPUVideoCapture:
    """
    GPU-accelerated video capture using cv2.cudacodec

    Fixes:
    - CPU decode bottleneck → NVDEC (GPU decoder)
    - Multiple CPU↔GPU copies → Direct GPU frame output
    - Single stream limit → Threaded capture
    """

    def __init__(
        self,
        source: str,
        target_size: Optional[Tuple[int, int]] = None,
        use_gpu_decode: bool = True,
        buffer_size: int = 2
    ):
        """
        Initialize GPU video capture

        Args:
            source: RTSP URL or file path
            target_size: Resize to (width, height) on GPU, None for original
            use_gpu_decode: Use NVDEC GPU decoder (True recommended)
            buffer_size: Frame buffer size for threading
        """
        self.source = source
        self.target_size = target_size
        self.use_gpu_decode = use_gpu_decode
        self.buffer_size = buffer_size

        self.cap = None
        self.running = False
        self.thread = None
        self.frame_queue = queue.Queue(maxsize=buffer_size)

        # GPU resources
        self.gpu_frame = None
        self.stream = cv2.cuda.Stream()

        # Stats
        self.frame_count = 0
        self.decode_time_ms = 0

    def start(self) -> bool:
        """Start video capture"""
        try:
            if self.use_gpu_decode:
                # Try GPU decoder first
                try:
                    logger.info(f"Attempting GPU decode for {self.source}")
                    self.cap = cv2.cudacodec.createVideoReader(self.source)
                    logger.success("GPU decode (NVDEC) enabled")
                except Exception as e:
                    logger.warning(f"GPU decode failed: {e}, falling back to CPU")
                    self.use_gpu_decode = False
                    self.cap = cv2.VideoCapture(self.source)
            else:
                # CPU decoder
                logger.info(f"Using CPU decode for {self.source}")
                self.cap = cv2.VideoCapture(self.source)

            # Verify capture opened
            if self.cap is None:
                logger.error(f"Failed to open video source: {self.source}")
                return False

            # Start background thread for capture
            self.running = True
            self.thread = threading.Thread(target=self._capture_thread, daemon=True)
            self.thread.start()

            logger.success(f"Video capture started: {self.source}")
            return True

        except Exception as e:
            logger.error(f"Failed to start capture: {e}")
            return False

    def _capture_thread(self):
        """Background thread for continuous frame capture"""
        while self.running:
            try:
                start_time = time.time()

                if self.use_gpu_decode:
                    # GPU decode path
                    ret, gpu_frame = self.cap.nextFrame()

                    if not ret or gpu_frame.empty():
                        logger.warning("GPU decode failed to get frame")
                        time.sleep(0.001)
                        continue

                    # Resize on GPU if needed
                    if self.target_size:
                        gpu_frame = cv2.cuda.resize(
                            gpu_frame,
                            self.target_size,
                            stream=self.stream
                        )

                    # Keep on GPU - only download when read() is called
                    frame = gpu_frame

                else:
                    # CPU decode path
                    ret, frame = self.cap.read()

                    if not ret or frame is None:
                        logger.warning("CPU decode failed to get frame")
                        time.sleep(0.001)
                        continue

                    # Resize on CPU if needed (will upload to GPU later)
                    if self.target_size:
                        frame = cv2.resize(frame, self.target_size)

                # Put frame in queue (blocking if full)
                try:
                    self.frame_queue.put((True, frame), timeout=0.1)
                    self.frame_count += 1
                    self.decode_time_ms = (time.time() - start_time) * 1000
                except queue.Full:
                    # Drop frame if queue is full (old frame still being processed)
                    logger.debug("Frame queue full, dropping frame")

            except Exception as e:
                logger.error(f"Capture thread error: {e}")
                time.sleep(0.1)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame

        Returns:
            (success, frame) - frame is numpy array (CPU) or GpuMat (GPU)
        """
        try:
            ret, frame = self.frame_queue.get(timeout=1.0)

            # If GPU frame, download to CPU for compatibility
            # (In production, you'd keep it on GPU)
            if self.use_gpu_decode and hasattr(frame, 'download'):
                frame = frame.download()

            return ret, frame

        except queue.Empty:
            logger.warning("Frame queue timeout")
            return False, None

    def stop(self):
        """Stop video capture"""
        self.running = False

        if self.thread:
            self.thread.join(timeout=2.0)

        if self.cap:
            if self.use_gpu_decode:
                # GPU decoder cleanup
                self.cap = None
            else:
                # CPU decoder cleanup
                self.cap.release()

        logger.info("Video capture stopped")

    def get_stats(self) -> dict:
        """Get capture statistics"""
        return {
            'frame_count': self.frame_count,
            'decode_time_ms': self.decode_time_ms,
            'queue_size': self.frame_queue.qsize(),
            'gpu_decode': self.use_gpu_decode,
        }


class MultiStreamCapture:
    """
    Multi-stream video capture with GPU acceleration

    Fixes: 1-2 stream limitation
    """

    def __init__(
        self,
        sources: dict,
        target_size: Tuple[int, int] = (960, 540),
        use_gpu_decode: bool = True
    ):
        """
        Initialize multi-stream capture

        Args:
            sources: Dict of {camera_id: rtsp_url}
            target_size: Resize all streams to this size (960x540 recommended)
            use_gpu_decode: Use GPU decode for all streams
        """
        self.sources = sources
        self.target_size = target_size
        self.use_gpu_decode = use_gpu_decode

        self.captures = {}

    def start_all(self):
        """Start all video captures"""
        for camera_id, source in self.sources.items():
            logger.info(f"Starting capture for {camera_id}: {source}")

            cap = GPUVideoCapture(
                source=source,
                target_size=self.target_size,
                use_gpu_decode=self.use_gpu_decode,
                buffer_size=2
            )

            if cap.start():
                self.captures[camera_id] = cap
            else:
                logger.error(f"Failed to start {camera_id}")

    def read(self, camera_id: str) -> Tuple[bool, Optional[np.ndarray]]:
        """Read frame from specific camera"""
        if camera_id not in self.captures:
            return False, None

        return self.captures[camera_id].read()

    def read_all(self) -> dict:
        """Read frames from all cameras"""
        frames = {}

        for camera_id, cap in self.captures.items():
            ret, frame = cap.read()
            if ret:
                frames[camera_id] = frame

        return frames

    def stop_all(self):
        """Stop all captures"""
        for camera_id, cap in self.captures.items():
            cap.stop()

    def get_stats(self) -> dict:
        """Get stats for all cameras"""
        return {
            camera_id: cap.get_stats()
            for camera_id, cap in self.captures.items()
        }


# Helper function for backward compatibility
def create_optimized_capture(
    source: str,
    target_size: Tuple[int, int] = (960, 540),
    prefer_gpu: bool = True
) -> GPUVideoCapture:
    """
    Create optimized video capture

    Args:
        source: Video source (RTSP URL or file)
        target_size: Target resolution (960x540 for inference)
        prefer_gpu: Try GPU decode first

    Returns:
        GPUVideoCapture instance
    """
    cap = GPUVideoCapture(
        source=source,
        target_size=target_size,
        use_gpu_decode=prefer_gpu
    )

    if not cap.start():
        raise RuntimeError(f"Failed to start capture for {source}")

    return cap


if __name__ == "__main__":
    # Test GPU decode
    import sys

    if len(sys.argv) < 2:
        print("Usage: python gpu_camera_ingestion.py <video_source>")
        sys.exit(1)

    source = sys.argv[1]

    # Test single stream
    logger.info("Testing single stream GPU decode...")
    cap = create_optimized_capture(source, target_size=(960, 540))

    frame_count = 0
    start_time = time.time()

    try:
        while frame_count < 300:  # Test 10 seconds @ 30fps
            ret, frame = cap.read()

            if not ret:
                logger.warning("Failed to read frame")
                break

            frame_count += 1

            if frame_count % 30 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                stats = cap.get_stats()

                logger.info(
                    f"Frame {frame_count}: {fps:.1f} FPS | "
                    f"Decode: {stats['decode_time_ms']:.1f}ms | "
                    f"GPU: {stats['gpu_decode']}"
                )

    finally:
        cap.stop()

    elapsed = time.time() - start_time
    avg_fps = frame_count / elapsed

    logger.success(f"Test complete: {avg_fps:.1f} FPS average")
