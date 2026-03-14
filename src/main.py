"""
Traffic recorder entry point.

Behavior:
- If stream_url exists -> try to record it.
- Else if page_url exists -> report unresolved source cleanly.
- Else -> skip.

This keeps the system deterministic while WV511 media endpoint resolution
is still being built.
"""

import argparse
import json
import os
import threading
from typing import Any, Dict, List

from .camera_recorder import CameraRecorder


def load_cameras(config_path: str) -> List[Dict[str, Any]]:
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    cameras = config.get("cameras", [])
    if not isinstance(cameras, list):
        raise ValueError("Invalid cameras configuration: expected a list")
    return cameras


def record_camera(camera: Dict[str, Any], duration: int, output_dir: str) -> None:
    name = camera.get("name", "unknown")
    stream_url = (camera.get("stream_url") or "").strip()
    page_url = (camera.get("page_url") or "").strip()

    if stream_url:
        recorder = CameraRecorder(name, stream_url, output_dir)
        recorder.record(duration)
        return

    if page_url:
        print(f"[UNRESOLVED] {name}: page_url present but stream_url not yet resolved -> {page_url}")
        return

    print(f"[SKIP] {name}: no stream_url or page_url defined")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record live traffic cameras")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "..", "config", "cameras.json"),
        help="Path to JSON camera configuration file",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=3600,
        help="Recording duration in seconds (default: 3600)",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(__file__), "..", "recordings"),
        help="Directory to store recordings",
    )

    args = parser.parse_args()

    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    cameras = load_cameras(args.config)
    if not cameras:
        print("No cameras defined in configuration.")
        return

    threads: List[threading.Thread] = []
    for camera in cameras:
        t = threading.Thread(
            target=record_camera,
            args=(camera, args.duration, output_dir),
            daemon=True,
            name=camera.get("name", "camera_thread"),
        )
        threads.append(t)

    print(f"Starting recording for {len(threads)} cameras. Duration: {args.duration} seconds.")
    for t in threads:
        t.start()

    for t in threads:
        t.join()

    print("All recordings completed.")


if __name__ == "__main__":
    main()
