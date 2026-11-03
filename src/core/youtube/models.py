"""
Data models and exceptions for YouTube downloader and subtitles.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from src.utils.formatters import format_bytes


class YtDlpNullLogger:
    """Silences yt-dlp internal console logs."""
    def debug(self, msg):
        pass
    def info(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass


@dataclass
class YouTubeFormatItem:
    format_id: str
    format_selector: str          # For yt-dlp download
    label: str                    # E.g. "1080p Full HD"
    ext: str                      # "mp4", "m4a", "webm", etc.
    resolution: str               # "1920x1080", "1280x720", "Audio"
    category: str                 # "video_audio", "audio_only", "video_only", "direct"
    fps: Optional[float] = None
    filesize: Optional[int] = None
    filesize_str: str = ""
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    direct_url: Optional[str] = None
    is_recommended: bool = False
    note: str = ""

    def __post_init__(self):
        if not self.filesize_str:
            self.filesize_str = format_bytes(self.filesize, fallback="Tự động tính")


@dataclass
class YouTubeSubtitleItem:
    lang: str                     # "en" or "vi"
    label: str                    # "Tiếng Anh (English)" or "Tiếng Việt (Vietnamese)"
    is_auto: bool                 # False = chính thức, True = tự động tạo
    source_code: str              # "en", "en-US", "vi", etc.
    ext: str = "srt"              # Luôn là srt
    note: str = ""                # "Phụ đề chính thức" or "Phụ đề tự động tạo (Auto-generated)"


@dataclass
class YouTubeVideoInfo:
    url: str
    video_id: str
    title: str
    channel: str
    duration: float
    duration_str: str
    thumbnail_url: Optional[str] = None
    view_count: Optional[int] = None
    view_count_str: str = ""
    upload_date: Optional[str] = None
    formats: List[YouTubeFormatItem] = field(default_factory=list)
    subtitles: List[YouTubeSubtitleItem] = field(default_factory=list)

    @property
    def has_en_sub(self) -> bool:
        return any(s.lang == 'en' for s in self.subtitles)

    @property
    def has_vi_sub(self) -> bool:
        return any(s.lang == 'vi' for s in self.subtitles)

    @property
    def only_en_sub(self) -> bool:
        return self.has_en_sub and not self.has_vi_sub


class DownloadCancelledException(Exception):
    pass

