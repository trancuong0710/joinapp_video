"""
Backward compatibility shim for video_meta.
"""
from src.core.video_meta import (
    AudioTrackInfo,
    VideoInfo,
    probe_video,
)
from src.utils.formatters import (
    format_bytes,
    format_seconds,
    parse_fps,
)
from src.core.ffmpeg_env import ensure_ffmpeg_path

__all__ = [
    "AudioTrackInfo",
    "VideoInfo",
    "probe_video",
    "format_bytes",
    "format_seconds",
    "parse_fps",
    "ensure_ffmpeg_path",
]
