#!/usr/bin/env python3
# =============================================================================
# FILE: src/main.py
# PROJECT: traffic_recorder_project
# PURPOSE:
#   Launch all configured camera recorders against the current local
#   CameraRecorder API shape.
# =============================================================================

import argparse
import inspect
import sys
import threading
from pathlib import Path

from src.camera_recorder import CameraRecorder
from src.source_resolver import load_cameras


def build_arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=60, help="Recording duration in seconds")
    return parser


def build_recorder(camera: dict) -> CameraRecorder:
    output_dir = str(Path("recordings").resolve())
    return CameraRecorder(
        name=camera["name"],
        stream_url=camera["stream_url"],
        output_dir=output_dir,
        fps=camera.get("fps"),
    )


def build_runner(recorder: CameraRecorder, duration: int):
    candidate_names = [
        "run",
        "record",
        "start",
        "capture",
        "record_stream",
        "start_recording",
    ]

    selected = None
    for name in candidate_names:
        fn = getattr(recorder, name, None)
        if callable(fn):
            selected = fn
            break

    if selected is None:
        public_callables = []
        for name in dir(recorder):
            if name.startswith("_"):
                continue
            value = getattr(recorder, name, None)
            if callable(value):
                public_callables.append(name)
        raise RuntimeError(
            "No supported recorder worker method found. "
            f"Available public callables: {public_callables}"
        )

    sig = inspect.signature(selected)
    params = set(sig.parameters.keys())

    kwargs = {}
    if "duration" in params:
        kwargs["duration"] = duration
    elif "duration_seconds" in params:
        kwargs["duration_seconds"] = duration
    elif "seconds" in params:
        kwargs["seconds"] = duration

    def runner():
        return selected(**kwargs)

    return runner, selected.__name__, str(sig)


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    cameras = load_cameras()
    print(f"Starting recording for {len(cameras)} cameras. Duration: {args.duration} seconds.")

    threads = []

    for cam in cameras:
        stream_url = (cam.get("stream_url") or "").strip()
        if not stream_url:
            print(f"[UNRESOLVED] {cam['name']}: page_url present but stream_url not yet resolved -> {cam.get('page_url', '')}")
            continue

        recorder = build_recorder(cam)
        runner, method_name, method_sig = build_runner(recorder, args.duration)

        print(f"[MAIN] {cam['name']} -> {method_name}{method_sig}")

        t = threading.Thread(target=runner, daemon=False, name=f"rec-{cam['name']}")
        t.start()
        threads.append(t)

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[MAIN] Stop requested by user. Exiting main thread.")
        raise

    print("All recordings completed.")


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except KeyboardInterrupt:
        print("[MAIN] Exited by user.")
        sys.exit(130)
