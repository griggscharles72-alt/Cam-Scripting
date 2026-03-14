"""Camera recording utilities.

This module defines the ``CameraRecorder`` class, which encapsulates the logic
required to connect to a live video stream and save the frames to a file.  If
the connection drops, the recorder will attempt to reconnect after a short
delay.  Recorded files are saved with timestamped names in the specified
output directory.

Example usage::

    from camera_recorder import CameraRecorder
    recorder = CameraRecorder("I-64 @ 47 Crosslanes", "http://example.com/stream", "recordings")
    recorder.record(duration_seconds=3600)

The above example will save an hour of footage from the stream into the
``recordings`` directory.

Note:
    The actual streaming URLs must be provided in your configuration.  The
    recorder assumes that OpenCV can open the stream via ``cv2.VideoCapture``.
"""

import os
import time
import datetime
from typing import Optional

import cv2  # type: ignore


class CameraRecorder:
    """A helper class to record video from a streaming camera.

    Args:
        name: Human‑readable identifier for the camera.
        stream_url: URL to open with OpenCV.  Should point to an MJPEG, RTSP
            or HLS stream that OpenCV can decode.
        output_dir: Directory where recorded video files will be stored.
        fps: Optional frames per second for the output file.  If ``None``
            (default), the recorder will attempt to use the source frame rate.
    """

    def __init__(self, name: str, stream_url: str, output_dir: str, fps: Optional[float] = None) -> None:
        self.name = name
        self.stream_url = stream_url
        self.output_dir = output_dir
        self.fps = fps

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

    def _generate_filename(self) -> str:
        """Generate a timestamped filename based on the camera name."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.name.replace(" ", "_").replace("/", "_")
        return f"{safe_name}_{timestamp}.avi"

    def record(self, duration_seconds: int) -> None:
        """Record video for a fixed duration.

        Args:
            duration_seconds: How long to record for, in seconds.

        The method will attempt to keep recording until the specified time has
        elapsed.  If the stream drops or cannot be opened, it will retry after
        a short delay.
        """
        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            # Attempt to open the stream
            cap = cv2.VideoCapture(self.stream_url)
            if not cap.isOpened():
                print(f"[{self.name}] Unable to open stream; retrying in 5 seconds...")
                cap.release()
                time.sleep(5)
                continue

            # Determine frame properties
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            fps = self.fps or (source_fps if source_fps and source_fps > 0 else 25.0)

            filename = self._generate_filename()
            filepath = os.path.join(self.output_dir, filename)
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

            print(f"[{self.name}] Recording started: {filepath}")
            frame_start = time.time()
            while time.time() < end_time:
                ret, frame = cap.read()
                if not ret:
                    # Break to reconnect
                    print(f"[{self.name}] Stream interrupted; attempting reconnect...")
                    break
                writer.write(frame)
                # Sleep to approximate the frame rate
                if fps > 0:
                    time.sleep(max(0, (1.0 / fps) - (time.time() - frame_start)))
                frame_start = time.time()

            writer.release()
            cap.release()
            print(f"[{self.name}] Recording saved: {filepath}")

            if time.time() < end_time:
                # Wait a bit before attempting to reopen the stream
                time.sleep(5)