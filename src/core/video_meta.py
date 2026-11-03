"""
Video metadata extraction and audio track parsing using ffprobe.
"""
import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from src.core.ffmpeg_env import ensure_ffmpeg_path, get_windows_startupinfo
from src.utils.formatters import format_bytes, format_seconds, parse_fps

ensure_ffmpeg_path()


@dataclass
class AudioTrackInfo:
    stream_index: int       # Stream index in container (e.g. 1, 2)
    audio_index: int        # 0-based audio stream index (e.g. 0, 1)
    codec: str              # e.g. 'aac', 'ac3', 'mp3'
    channels: int           # e.g. 2
    channel_layout: str     # e.g. 'stereo', '5.1'
    sample_rate: int        # e.g. 44100, 48000
    bitrate: Optional[int]  # in bps
    language: str           # e.g. 'vie', 'eng', 'und'
    title: str              # e.g. 'Tiếng Việt', 'Director Commentary'
    is_default: bool        # default track flag
    display_label: str = "" # User-facing label for combobox

    def __post_init__(self):
        lang_str = self.language.upper() if self.language and self.language != "und" else ""
        title_str = self.title if self.title else ""
        
        info_parts = []
        if title_str:
            info_parts.append(title_str)
        if lang_str:
            info_parts.append(f"[{lang_str}]")
        
        details = [self.codec.upper()]
        if self.channel_layout:
            details.append(self.channel_layout)
        elif self.channels:
            details.append(f"{self.channels}ch")
        if self.sample_rate:
            details.append(f"{self.sample_rate // 1000}kHz")
            
        desc = " ".join(info_parts)
        if desc:
            self.display_label = f"Track {self.audio_index + 1}: {desc} ({', '.join(details)})"
        else:
            self.display_label = f"Track {self.audio_index + 1}: ({', '.join(details)})"
            
        if self.is_default:
            self.display_label += " [Mặc định]"


@dataclass
class VideoInfo:
    file_path: str
    filename: str
    filesize: int
    filesize_str: str
    duration: float
    duration_str: str
    width: int
    height: int
    resolution_str: str
    fps: float
    codec: str
    audio_tracks: List[AudioTrackInfo] = field(default_factory=list)
    selected_audio_idx: int = 0  # index in audio_tracks; -1 means Mute (no audio)
    thumbnail_path: Optional[str] = None

    @property
    def has_audio(self) -> bool:
        return len(self.audio_tracks) > 0

    @property
    def has_multiple_audio(self) -> bool:
        return len(self.audio_tracks) > 1


def probe_video(file_path: str, temp_thumb_dir: Optional[str] = None) -> VideoInfo:
    """Uses ffprobe to extract complete video and audio stream information."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Tập tin không tồn tại: {file_path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]

    try:
        startupinfo = get_windows_startupinfo()
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
            check=True
        )
        data = json.loads(proc.stdout)
    except Exception as e:
        raise RuntimeError(f"Lỗi khi đọc file bằng ffprobe: {e}")

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    filesize = int(fmt.get("size", os.path.getsize(file_path)))
    duration = float(fmt.get("duration", 0.0))

    video_stream = None
    audio_streams = []

    for s in streams:
        codec_type = s.get("codec_type")
        if codec_type == "video" and video_stream is None:
            video_stream = s
        elif codec_type == "audio":
            audio_streams.append(s)

    width = 0
    height = 0
    fps = 30.0
    vcodec = "unknown"

    if video_stream:
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        fps = parse_fps(video_stream.get("r_frame_rate", video_stream.get("avg_frame_rate", "30/1")))
        vcodec = video_stream.get("codec_name", "unknown")
        if duration <= 0:
            try:
                duration = float(video_stream.get("duration", 0.0))
            except Exception:
                pass

    parsed_audio_tracks = []
    for a_idx, s in enumerate(audio_streams):
        stream_idx = int(s.get("index", a_idx))
        codec = s.get("codec_name", "aac")
        channels = int(s.get("channels", 2))
        ch_layout = s.get("channel_layout", "stereo")
        sample_rate = int(s.get("sample_rate", 44100))
        bitrate = int(s.get("bit_rate")) if s.get("bit_rate") else None
        
        tags = s.get("tags", {})
        language = tags.get("language", tags.get("LANGUAGE", ""))
        title = tags.get("title", tags.get("TITLE", tags.get("handler_name", "")))
        if title.lower() in ("soundhandler", "audiohandler", "handler_name"):
            title = ""

        disposition = s.get("disposition", {})
        is_default = bool(disposition.get("default", 0))

        track = AudioTrackInfo(
            stream_index=stream_idx,
            audio_index=a_idx,
            codec=codec,
            channels=channels,
            channel_layout=ch_layout,
            sample_rate=sample_rate,
            bitrate=bitrate,
            language=language,
            title=title,
            is_default=is_default
        )
        parsed_audio_tracks.append(track)

    selected_idx = 0 if parsed_audio_tracks else -1
    for i, t in enumerate(parsed_audio_tracks):
        if t.is_default:
            selected_idx = i
            break

    thumb_path = None
    if temp_thumb_dir and os.path.exists(temp_thumb_dir) and video_stream:
        try:
            import hashlib
            hash_name = hashlib.md5(file_path.encode('utf-8', errors='ignore')).hexdigest()
            out_thumb = os.path.join(temp_thumb_dir, f"thumb_{hash_name}.jpg")
            
            seek_pos = min(1.0, duration * 0.15) if duration > 0 else 0.5
            
            thumb_cmd = [
                "ffmpeg", "-y",
                "-ss", str(seek_pos),
                "-i", file_path,
                "-vframes", "1",
                "-vf", "scale=160:90:force_original_aspect_ratio=decrease,pad=160:90:(ow-iw)/2:(oh-ih)/2:black",
                "-update", "1",
                out_thumb
            ]
            subprocess.run(
                thumb_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                timeout=5
            )
            if os.path.exists(out_thumb) and os.path.getsize(out_thumb) > 0:
                thumb_path = out_thumb
        except Exception:
            thumb_path = None

    return VideoInfo(
        file_path=file_path,
        filename=os.path.basename(file_path),
        filesize=filesize,
        filesize_str=format_bytes(filesize),
        duration=duration,
        duration_str=format_seconds(duration),
        width=width,
        height=height,
        resolution_str=f"{width}x{height}" if width and height else "Không xác định",
        fps=fps,
        codec=vcodec,
        audio_tracks=parsed_audio_tracks,
        selected_audio_idx=selected_idx,
        thumbnail_path=thumb_path
    )

