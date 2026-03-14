"""Utility functions for the traffic recorder project."""

import datetime
from typing import Tuple


def parse_hms(duration_str: str) -> int:
    """Parse a duration string in the form HH:MM:SS into seconds.

    Args:
        duration_str: A string of the form ``HH:MM:SS`` or ``MM:SS``.

    Returns:
        The total duration in seconds.

    Raises:
        ValueError: If the format is invalid.
    """
    parts = duration_str.strip().split(":")
    if not 2 <= len(parts) <= 3:
        raise ValueError("Duration must be MM:SS or HH:MM:SS")
    parts = [int(p) for p in parts]
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    else:
        hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def timestamp_str() -> str:
    """Return current timestamp as a compact string (YYYYMMDD_HHMMSS)."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")