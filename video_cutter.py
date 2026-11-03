"""
Backward compatibility shim for video_cutter.
"""
from src.core.video_cutter import VideoCutter, VideoFrameExtractor
from src.utils.formatters import parse_time_str, format_time_hms
from src.core.ffmpeg_env import ensure_ffmpeg_path

__all__ = [
    "VideoCutter",
    "VideoFrameExtractor",
    "parse_time_str",
    "format_time_hms",
    "ensure_ffmpeg_path",
]
