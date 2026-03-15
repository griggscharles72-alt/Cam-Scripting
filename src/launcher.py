#!/usr/bin/env python3
# =============================================================================
# FILE: src/launcher.py
# PROJECT: traffic_recorder_project
# PURPOSE:
#   Operational launcher for the WV511 recorder.
# =============================================================================

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_MAIN_MODULE = "src.main"

PRESET_SECONDS = {
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 1 * 60 * 60,
    "2h": 2 * 60 * 60,
    "5h": 5 * 60 * 60,
    "10h": 10 * 60 * 60,
}

STOP_REQUESTED = False


def _handle_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print("\n[LAUNCHER] Stop requested. Finishing current wait/launch cycle...", flush=True)


signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)


@dataclass
class LaunchConfig:
    mode: str
    duration_seconds: int
    preset: str | None = None
    interval_hours: float | None = None
    daily_time: str | None = None


def repo_python() -> str:
    return sys.executable


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return env


def run_recorder(duration_seconds: int) -> int:
    cmd = [repo_python(), "-m", SRC_MAIN_MODULE, "--duration", str(duration_seconds)]

    print("=" * 80)
    print("[LAUNCHER] Starting recorder")
    print(f"[LAUNCHER] cwd={ROOT}")
    print(f"[LAUNCHER] duration_seconds={duration_seconds}")
    print(f"[LAUNCHER] command={' '.join(cmd)}")
    print("=" * 80, flush=True)

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=build_env(),
        check=False,
    )

    print(f"[LAUNCHER] Recorder exit code: {proc.returncode}", flush=True)
    return proc.returncode


def parse_daily_time(hhmm: str) -> tuple[int, int]:
    parts = hhmm.strip().split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23):
        raise argparse.ArgumentTypeError("hour out of range")
    if not (0 <= minute <= 59):
        raise argparse.ArgumentTypeError("minute out of range")
    return hour, minute


def next_daily_run(hhmm: str) -> datetime:
    hour, minute = parse_daily_time(hhmm)
    now = datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def sleep_until(target_dt: datetime) -> None:
    while not STOP_REQUESTED:
        now = datetime.now()
        remaining = (target_dt - now).total_seconds()
        if remaining <= 0:
            return

        shown = int(remaining)
        hrs = shown // 3600
        mins = (shown % 3600) // 60
        secs = shown % 60

        print(
            f"[LAUNCHER] Next launch in {hrs:02d}:{mins:02d}:{secs:02d} "
            f"(target {target_dt.strftime('%Y-%m-%d %H:%M:%S')})",
            end="\r",
            flush=True,
        )
        time.sleep(min(1, max(0.1, remaining)))

    print("\n[LAUNCHER] Wait interrupted by stop request.", flush=True)


def sleep_seconds(seconds: float) -> None:
    end = time.time() + seconds
    while not STOP_REQUESTED:
        remaining = end - time.time()
        if remaining <= 0:
            return

        shown = int(remaining)
        hrs = shown // 3600
        mins = (shown % 3600) // 60
        secs = shown % 60

        print(
            f"[LAUNCHER] Interval wait {hrs:02d}:{mins:02d}:{secs:02d} remaining",
            end="\r",
            flush=True,
        )
        time.sleep(min(1, max(0.1, remaining)))

    print("\n[LAUNCHER] Interval wait interrupted by stop request.", flush=True)


def duration_from_args(args: argparse.Namespace) -> tuple[int, str]:
    if args.preset:
        return PRESET_SECONDS[args.preset], f"preset:{args.preset}"

    if args.hours is not None:
        if args.hours <= 0:
            raise SystemExit("--hours must be > 0")
        return int(args.hours * 3600), f"hours:{args.hours}"

    if args.minutes is not None:
        if args.minutes <= 0:
            raise SystemExit("--minutes must be > 0")
        return int(args.minutes * 60), f"minutes:{args.minutes}"

    return PRESET_SECONDS["1h"], "preset:1h"


def print_config(cfg: LaunchConfig) -> None:
    print("\n" + "=" * 80)
    print("TRAFFIC RECORDER LAUNCHER CONFIG")
    print("=" * 80)
    print(f"mode             : {cfg.mode}")
    print(f"duration_seconds : {cfg.duration_seconds}")
    print(f"duration_minutes : {round(cfg.duration_seconds / 60, 2)}")
    print(f"duration_hours   : {round(cfg.duration_seconds / 3600, 2)}")
    print(f"preset           : {cfg.preset}")
    print(f"interval_hours   : {cfg.interval_hours}")
    print(f"daily_time       : {cfg.daily_time}")
    print(f"repo_root        : {ROOT}")
    print("=" * 80 + "\n", flush=True)


def mode_once(cfg: LaunchConfig) -> int:
    return run_recorder(cfg.duration_seconds)


def mode_interval(cfg: LaunchConfig) -> int:
    if cfg.interval_hours is None or cfg.interval_hours <= 0:
        raise SystemExit("interval mode requires --interval-hours > 0")

    exit_code = 0
    cycle = 0

    while not STOP_REQUESTED:
        cycle += 1
        print(f"\n[LAUNCHER] Interval cycle #{cycle} starting", flush=True)
        exit_code = run_recorder(cfg.duration_seconds)

        if STOP_REQUESTED:
            break

        print(
            f"[LAUNCHER] Interval cycle #{cycle} complete. "
            f"Waiting {cfg.interval_hours} hour(s) for next run.",
            flush=True,
        )
        sleep_seconds(cfg.interval_hours * 3600)

    return exit_code


def mode_daily(cfg: LaunchConfig) -> int:
    if not cfg.daily_time:
        raise SystemExit("daily mode requires --daily-time HH:MM")

    exit_code = 0
    cycle = 0

    while not STOP_REQUESTED:
        cycle += 1
        target = next_daily_run(cfg.daily_time)
        print(f"[LAUNCHER] Daily cycle #{cycle} scheduled for {target}", flush=True)
        sleep_until(target)

        if STOP_REQUESTED:
            break

        print(f"\n[LAUNCHER] Daily cycle #{cycle} launching now", flush=True)
        exit_code = run_recorder(cfg.duration_seconds)

    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launcher for traffic_recorder_project")
    parser.add_argument("--mode", choices=["once", "interval", "daily"], default="once")
    parser.add_argument("--preset", choices=sorted(PRESET_SECONDS.keys(), key=lambda x: PRESET_SECONDS[x]))
    parser.add_argument("--minutes", type=float)
    parser.add_argument("--hours", type=float)
    parser.add_argument("--interval-hours", type=float)
    parser.add_argument("--daily-time", type=str)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    duration_seconds, duration_source = duration_from_args(args)

    cfg = LaunchConfig(
        mode=args.mode,
        duration_seconds=duration_seconds,
        preset=args.preset or duration_source,
        interval_hours=args.interval_hours,
        daily_time=args.daily_time,
    )

    print_config(cfg)

    if cfg.mode == "once":
        return mode_once(cfg)
    if cfg.mode == "interval":
        return mode_interval(cfg)
    if cfg.mode == "daily":
        return mode_daily(cfg)

    raise SystemExit(f"Unsupported mode: {cfg.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
