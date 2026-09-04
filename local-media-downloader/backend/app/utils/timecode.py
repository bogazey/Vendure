"""Parse and validate HH:MM:SS / MM:SS timecodes for clip ranges."""
from __future__ import annotations

import re

_PATTERN = re.compile(r"^(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)$")


def parse_timecode(value: str) -> float:
    """Return the timecode as seconds. Raises ValueError if malformed."""
    match = _PATTERN.match(value.strip())
    if not match:
        raise ValueError(
            f"Invalid timecode '{value}'. Expected HH:MM:SS or MM:SS."
        )
    hours_str, minutes_str, seconds_str = match.groups()
    hours = int(hours_str) if hours_str else 0
    minutes = int(minutes_str)
    seconds = int(seconds_str)
    return hours * 3600 + minutes * 60 + seconds


def validate_clip_range(start: str, end: str) -> tuple[float, float]:
    start_s = parse_timecode(start)
    end_s = parse_timecode(end)
    if end_s <= start_s:
        raise ValueError("Clip end time must be after start time.")
    return start_s, end_s
