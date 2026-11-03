"""
Formatting utilities for bytes, duration, FPS, and timecodes.
"""
from typing import Optional


def format_bytes(size_bytes: Optional[int], fallback: str = "N/A") -> str:
    """Format byte count into human-readable B, KB, MB, GB."""
    if size_bytes is None or size_bytes < 0:
        return fallback
    if size_bytes == 0:
        return fallback if fallback != "N/A" else "0 B"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_seconds(seconds: Optional[float], fallback: str = "N/A") -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return fallback
    secs = int(round(seconds))
    hrs = secs // 3600
    mins = (secs % 3600) // 60
    s = secs % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{s:02d}"
    return f"{mins:02d}:{s:02d}"


def parse_time_str(time_str: str) -> float:
    """Parses HH:MM:SS, MM:SS, or seconds (with decimals) into float seconds."""
    s = str(time_str).strip()
    if not s:
        return 0.0
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 1:
            return float(parts[0])
    except Exception:
        return 0.0
    return 0.0


def format_time_hms(seconds: float, include_subseconds: bool = False) -> str:
    """Formats float seconds into HH:MM:SS or HH:MM:SS.s."""
    if seconds < 0:
        seconds = 0.0
    total_int_secs = int(seconds)
    hrs = total_int_secs // 3600
    mins = (total_int_secs % 3600) // 60
    secs = total_int_secs % 60

    if include_subseconds:
        frac = seconds - total_int_secs
        tenth = int(round(frac * 10))
        if tenth >= 10:
            secs += 1
            tenth = 0
            if secs >= 60:
                mins += 1
                secs = 0
                if mins >= 60:
                    hrs += 1
                    mins = 0
        return f"{hrs:02d}:{mins:02d}:{secs:02d}.{tenth}"
    else:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def parse_fps(fps_str: str) -> float:
    """Parse FPS string (e.g., '30000/1001' or '60') into float."""
    if not fps_str or fps_str == "0/0":
        return 30.0
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/")
            den_val = float(den)
            return round(float(num) / den_val, 2) if den_val != 0 else 30.0
        return round(float(fps_str), 2)
    except Exception:
        return 30.0

