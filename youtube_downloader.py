"""
Backward compatibility shim for youtube_downloader.
"""
from src.core.youtube import (
    YouTubeFormatItem,
    YouTubeSubtitleItem,
    YouTubeVideoInfo,
    DownloadCancelledException,
    YtDlpNullLogger,
    parse_vtt_or_srt_to_cues,
    cues_to_srt,
    translate_texts_to_vietnamese,
    download_youtube_subtitle,
    download_and_convert_en_to_vi_subtitle,
    extract_youtube_info,
    download_youtube_video,
)
from src.core.ffmpeg_env import ensure_ffmpeg_path
from src.utils.formatters import format_bytes, format_seconds
from src.utils.file_helpers import sanitize_filename, clean_error_message, find_default_cookie_file

__all__ = [
    "YouTubeFormatItem",
    "YouTubeSubtitleItem",
    "YouTubeVideoInfo",
    "DownloadCancelledException",
    "YtDlpNullLogger",
    "parse_vtt_or_srt_to_cues",
    "cues_to_srt",
    "translate_texts_to_vietnamese",
    "download_youtube_subtitle",
    "download_and_convert_en_to_vi_subtitle",
    "extract_youtube_info",
    "download_youtube_video",
    "ensure_ffmpeg_path",
    "format_bytes",
    "format_seconds",
    "sanitize_filename",
    "clean_error_message",
    "find_default_cookie_file",
]
