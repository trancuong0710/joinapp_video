"""
Backward compatibility shim for video_merger.
"""
from src.core.video_merger import VideoMerger, MergeConfig
from src.core.ffmpeg_env import detect_hardware_encoder, ensure_ffmpeg_path

__all__ = [
    "VideoMerger",
    "MergeConfig",
    "detect_hardware_encoder",
    "ensure_ffmpeg_path",
]
