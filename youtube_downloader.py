import os
import re
import sys
import time
import shutil
import logging
import winreg
import urllib.parse
import urllib.request
import json
import tempfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Dict, Any
import yt_dlp


def ensure_ffmpeg_path():
    """Ensure ffmpeg and ffprobe are in PATH from registry or imageio_ffmpeg."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    paths = []
    # Check Windows Registry User & Machine PATH
    if sys.platform.startswith("win"):
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for sub in (r"Environment", r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"):
                try:
                    with winreg.OpenKey(root, sub) as key:
                        val = winreg.QueryValueEx(key, "Path")[0]
                        paths.extend(val.split(";"))
                except Exception:
                    pass

    # Check imageio_ffmpeg
    try:
        import imageio_ffmpeg
        paths.append(os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception:
        pass

    # Add to current os.environ["PATH"]
    existing = os.environ.get("PATH", "").split(os.pathsep)
    new_dirs = [p for p in paths if p and os.path.isdir(p) and p not in existing]
    if new_dirs:
        os.environ["PATH"] = os.pathsep.join(new_dirs) + os.pathsep + os.environ.get("PATH", "")


ensure_ffmpeg_path()


class YtDlpNullLogger:
    def debug(self, msg):
        pass
    def info(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass


def clean_error_message(err: Exception) -> str:
    """Removes ANSI color escape codes and formats known YouTube errors nicely."""
    msg = str(err)
    clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', msg)
    clean = clean.replace('\r', ' ').strip()
    
    if "Sign in to confirm you're not a bot" in clean or "Sign in to confirm you’re not a bot" in clean:
        return (
            "⚠️ YOUTUBE YÊU CẦU XÁC MINH ROBOT (Sign in to confirm you're not a bot):\n\n"
            "YouTube vừa kích hoạt cơ chế bảo vệ chống bot (BotGuard/PO Token) đối với địa chỉ IP mạng của bạn.\n\n"
            "👉 CÁCH KHẮC PHỤC DỄ DÀNG:\n"
            "1. Tắt VPN hoặc Cloudflare WARP (1.1.1.1) nếu đang bật.\n"
            "2. Hoặc nạp Cookie: Xuất file 'cookies.txt' từ YouTube trên trình duyệt và bấm '🍪 Nạp Cookies' trong ứng dụng."
        )
    return clean


def find_default_cookie_file() -> Optional[str]:
    """Finds default cookies.txt in app dir or current working dir if available."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"),
        os.path.join(os.getcwd(), "cookies.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_cookies.txt"),
        os.path.join(os.getcwd(), "youtube_cookies.txt"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 0:
            return os.path.abspath(c)
    return None


def format_bytes(size_bytes: Optional[int]) -> str:
    if not size_bytes or size_bytes <= 0:
        return "Tự động tính"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_seconds(seconds: Optional[float]) -> str:
    if not seconds or seconds <= 0:
        return "00:00"
    secs = int(round(seconds))
    hrs = secs // 3600
    mins = (secs % 3600) // 60
    s = secs % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{s:02d}"
    return f"{mins:02d}:{s:02d}"


def sanitize_filename(name: str) -> str:
    """Sanitize string to be safe for filenames on Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = clean.strip()
    return clean[:120] if len(clean) > 120 else clean


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
            self.filesize_str = format_bytes(self.filesize)


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


def extract_youtube_info(
    url: str,
    cookiefile: Optional[str] = None,
    cookies_from_browser: Optional[str] = None
) -> YouTubeVideoInfo:
    """Extracts YouTube metadata, download formats, and subtitles using yt-dlp."""
    ensure_ffmpeg_path()
    url = url.strip()
    if not url:
        raise ValueError("Đường link YouTube không được để trống!")

    ydl_opts: Dict[str, Any] = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'extract_flat': False,
        'logger': YtDlpNullLogger(),
    }

    if shutil.which("node"):
        ydl_opts['js_runtimes'] = {'node': {}}

    eff_cookie = cookiefile if (cookiefile and os.path.isfile(cookiefile)) else find_default_cookie_file()
    if eff_cookie and os.path.isfile(eff_cookie):
        ydl_opts['cookiefile'] = eff_cookie
    elif cookies_from_browser and cookies_from_browser.lower() not in ("none", "không dùng", ""):
        ydl_opts['cookiesfrombrowser'] = (cookies_from_browser.lower(), None, None, None)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise RuntimeError(clean_error_message(e))

    if not info:
        raise RuntimeError("Không tìm thấy thông tin video.")

    title = info.get('title', 'Video YouTube')
    channel = info.get('uploader') or info.get('channel') or "Không rõ kênh"
    duration = float(info.get('duration') or 0)
    duration_str = format_seconds(duration)
    thumbnail_url = info.get('thumbnail')
    video_id = info.get('id', '')
    
    views = info.get('view_count')
    if views:
        if views >= 1_000_000:
            view_count_str = f"{views / 1_000_000:.1f}M lượt xem"
        elif views >= 1_000:
            view_count_str = f"{views / 1_000:.1f}K lượt xem"
        else:
            view_count_str = f"{views:,} lượt xem"
    else:
        view_count_str = ""

    raw_formats = info.get('formats', [])
    available_heights = set()
    audio_formats = []

    for f in raw_formats:
        h = f.get('height')
        if h and isinstance(h, int):
            available_heights.add(h)
        
        acodec = f.get('acodec')
        vcodec = f.get('vcodec')
        if acodec != 'none' and (vcodec == 'none' or not vcodec):
            audio_formats.append(f)

    format_items: List[YouTubeFormatItem] = []

    # 1. Preset high-quality combined formats (Video + Audio MP4)
    target_resolutions = [
        (2160, "4K Ultra HD (2160p)", "Rõ nét đỉnh cao 4K"),
        (1440, "2K Quad HD (1440p)", "Độ nét cao 2K"),
        (1080, "Full HD (1080p)", "Chuẩn Full HD sắc nét nhất (Khuyên dùng)"),
        (720, "HD (720p)", "Chuẩn HD sắc nét, tải nhanh (Khuyên dùng)"),
        (480, "SD (480p)", "Chuẩn tiêu chuẩn, tiết kiệm dung lượng"),
        (360, "360p", "Dung lượng siêu nhẹ, xem mượt")
    ]

    for height, res_name, note in target_resolutions:
        has_res = any(h >= height for h in available_heights) if height in [1080, 720, 480, 360] else (height in available_heights)
        if has_res:
            matching_v = [f for f in raw_formats if f.get('height') == height]
            size_est = None
            fps_val = None
            direct_u = None
            if matching_v:
                v = matching_v[0]
                v_size = v.get('filesize') or v.get('filesize_approx') or 0
                a_size = 0
                if audio_formats:
                    a_size = audio_formats[-1].get('filesize') or audio_formats[-1].get('filesize_approx') or 0
                if v_size:
                    size_est = v_size + a_size
                fps_val = v.get('fps')
                direct_u = v.get('url')

            selector = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
            
            format_items.append(YouTubeFormatItem(
                format_id=f"preset_{height}p",
                format_selector=selector,
                label=f"🎬 Video MP4 • {res_name}",
                ext="mp4",
                resolution=f"{height}p",
                category="video_audio",
                fps=fps_val,
                filesize=size_est,
                direct_url=direct_u,
                is_recommended=(height in [1080, 720]),
                note=f"{note} • Đầy đủ hình ảnh + âm thanh"
            ))

    # 2. Audio-only options
    best_audio_size = None
    best_audio_url = None
    if audio_formats:
        best_a = audio_formats[-1]
        best_audio_size = best_a.get('filesize') or best_a.get('filesize_approx')
        best_audio_url = best_a.get('url')

    format_items.append(YouTubeFormatItem(
        format_id="audio_best_m4a",
        format_selector="bestaudio[ext=m4a]/bestaudio/best",
        label="🎵 Âm thanh M4A / AAC • Gốc tốt nhất",
        ext="m4a",
        resolution="Audio",
        category="audio_only",
        filesize=best_audio_size,
        direct_url=best_audio_url,
        is_recommended=True,
        note="Tách riêng âm thanh gốc, chất lượng cao, dung lượng nhẹ"
    ))

    # 3. Direct individual streams from formats
    seen_streams = set()
    for f in raw_formats:
        fid = str(f.get('format_id', ''))
        ext = f.get('ext', '')
        url_link = f.get('url')
        if not url_link or ext in ['mhtml', 'json']:
            continue
            
        res = f.get('resolution') or (f"{f.get('height')}p" if f.get('height') else "Audio")
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        size = f.get('filesize') or f.get('filesize_approx')
        fps = f.get('fps')
        abr = f.get('abr')
        
        if vcodec != 'none' and acodec != 'none':
            cat = "video_audio"
            lbl = f"🔗 MP4 Kèm Tiếng {res} ({ext.upper()})"
            stream_note = f"Stream ID {fid} • Video + Âm thanh trực tiếp"
        elif vcodec != 'none':
            cat = "video_only"
            lbl = f"🔗 Video Không Tiếng {res} ({ext.upper()})"
            stream_note = f"Stream ID {fid} • Chỉ hình ảnh • Codec {vcodec[:10]}"
        else:
            cat = "audio_only"
            abr_str = f"{int(abr)}k" if abr else ""
            lbl = f"🔗 Âm thanh {abr_str} ({ext.upper()})"
            stream_note = f"Stream ID {fid} • Chỉ âm thanh • Codec {acodec[:10]}"

        stream_key = (res, ext, cat)
        if stream_key in seen_streams:
            continue
        seen_streams.add(stream_key)

        format_items.append(YouTubeFormatItem(
            format_id=f"stream_{fid}",
            format_selector=fid,
            label=lbl,
            ext=ext,
            resolution=str(res),
            category=cat,
            fps=fps,
            filesize=size,
            video_codec=vcodec,
            audio_codec=acodec,
            direct_url=url_link,
            is_recommended=False,
            note=stream_note
        ))

    # Extract Subtitles (Only English and Vietnamese as required)
    subtitles_dict = info.get('subtitles') or {}
    auto_captions_dict = info.get('automatic_captions') or {}
    sub_items: List[YouTubeSubtitleItem] = []

    def find_sub_match(code_map: dict, prefix: str) -> Optional[str]:
        if prefix in code_map:
            return prefix
        for k in code_map.keys():
            if k.lower() == f"{prefix}-{prefix}".lower() or k.lower() == prefix:
                return k
        for k in code_map.keys():
            if k.lower().startswith(f"{prefix}-"):
                return k
        return None

    # 1. Check Vietnamese Subtitle
    vi_code = find_sub_match(subtitles_dict, "vi")
    if vi_code:
        sub_items.append(YouTubeSubtitleItem(
            lang="vi",
            label="Tiếng Việt (Vietnamese)",
            is_auto=False,
            source_code=vi_code,
            ext="srt",
            note="Phụ đề người đăng tạo (Chính thức)"
        ))
    else:
        vi_auto_code = find_sub_match(auto_captions_dict, "vi")
        if vi_auto_code:
            sub_items.append(YouTubeSubtitleItem(
                lang="vi",
                label="Tiếng Việt (Vietnamese)",
                is_auto=True,
                source_code=vi_auto_code,
                ext="srt",
                note="Phụ đề tự động tạo (Auto-generated)"
            ))

    # 2. Check English Subtitle
    en_code = find_sub_match(subtitles_dict, "en")
    if en_code:
        sub_items.append(YouTubeSubtitleItem(
            lang="en",
            label="Tiếng Anh (English)",
            is_auto=False,
            source_code=en_code,
            ext="srt",
            note="Phụ đề người đăng tạo (Chính thức)"
        ))
    else:
        en_auto_code = find_sub_match(auto_captions_dict, "en")
        if en_auto_code:
            sub_items.append(YouTubeSubtitleItem(
                lang="en",
                label="Tiếng Anh (English)",
                is_auto=True,
                source_code=en_auto_code,
                ext="srt",
                note="Phụ đề tự động tạo (Auto-generated)"
            ))

    return YouTubeVideoInfo(
        url=url,
        video_id=video_id,
        title=title,
        channel=channel,
        duration=duration,
        duration_str=duration_str,
        thumbnail_url=thumbnail_url,
        view_count=views,
        view_count_str=view_count_str,
        upload_date=info.get('upload_date'),
        formats=format_items,
        subtitles=sub_items
    )


def parse_vtt_or_srt_to_cues(raw_text: str) -> List[Dict[str, str]]:
    """
    Parses WebVTT or SRT subtitle text into structured cue objects:
    [{'start': '00:00:01,200', 'end': '00:00:03,360', 'text': '...'}]
    Cleans inline formatting tags and deduplicates repeating lines.
    """
    text = raw_text.replace('\r\n', '\n').replace('\r', '\n')
    time_pat = re.compile(r'((?:\d{2}:)?\d{2}:\d{2}[\.,]\d{3})\s*-->\s*((?:\d{2}:)?\d{2}:\d{2}[\.,]\d{3})')
    blocks = re.split(r'\n\s*\n', text)
    cues = []

    for block in blocks:
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if not lines:
            continue
        time_idx = -1
        m = None
        for i, l in enumerate(lines):
            m = time_pat.search(l)
            if m:
                time_idx = i
                break
        if not m:
            continue

        start_t = m.group(1).replace('.', ',')
        end_t = m.group(2).replace('.', ',')
        if start_t.count(':') == 1:
            start_t = '00:' + start_t
        if end_t.count(':') == 1:
            end_t = '00:' + end_t

        content_lines = lines[time_idx + 1:]
        cleaned_lines = []
        for cl in content_lines:
            cl_clean = re.sub(r'<[^>]+>', '', cl).strip()
            if cl_clean and (not cleaned_lines or cl_clean != cleaned_lines[-1]):
                cleaned_lines.append(cl_clean)

        cue_text = '\n'.join(cleaned_lines).strip()
        if cue_text:
            cues.append({'start': start_t, 'end': end_t, 'text': cue_text})

    return cues


def cues_to_srt(cues: List[Dict[str, str]]) -> str:
    """Formats a list of cues into standard SubRip (.srt) subtitle string."""
    out = []
    for idx, c in enumerate(cues, 1):
        s = c['start']
        e = c['end']
        t = c['text']
        out.append(f"{idx}\n{s} --> {e}\n{t}\n")
    return '\n'.join(out)


def translate_texts_to_vietnamese(
    texts: List[str],
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[str]:
    """
    Translates a list of English cue texts to Vietnamese in efficient batches.
    Falls back gracefully to individual requests if a batch encounters an issue.
    """
    if not texts:
        return []

    chunk_size = 25
    results: List[str] = []
    total = len(texts)

    for i in range(0, total, chunk_size):
        chunk = texts[i:i + chunk_size]
        delimiter = ' ___ '
        combined = delimiter.join(t.replace('\n', ' ') for t in chunk)

        try:
            url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=' + urllib.parse.quote(combined)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                trans_text = ''.join(s[0] for s in data[0] if s[0])
                parts = [p.strip() for p in trans_text.split('___')]
                if len(parts) < len(chunk):
                    parts += [''] * (len(chunk) - len(parts))
                results.extend(parts[:len(chunk)])
        except Exception:
            for item in chunk:
                try:
                    url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=' + urllib.parse.quote(item)
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        results.append(''.join(s[0] for s in data[0] if s[0]).strip())
                except Exception:
                    results.append(item)

        if progress_callback:
            curr = min(total, i + chunk_size)
            progress_callback(curr, total, f"Đang dịch phụ đề: {curr}/{total} câu...")

    return results


def download_youtube_subtitle(
    url: str,
    lang_code: str,
    is_auto: bool,
    output_filepath: str,
    cookiefile: Optional[str] = None
) -> str:
    """
    Downloads YouTube subtitle (official or auto) and converts it to standard .srt format.
    """
    ensure_ffmpeg_path()
    temp_dir = tempfile.mkdtemp(prefix="yt_sub_")
    out_tmpl = os.path.join(temp_dir, "sub.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        'skip_download': True,
        'writesubtitles': not is_auto,
        'writeautomaticsub': is_auto,
        'subtitleslangs': [lang_code],
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True,
        'logger': YtDlpNullLogger(),
    }

    if shutil.which("node"):
        ydl_opts['js_runtimes'] = {'node': {}}

    eff_cookie = cookiefile if (cookiefile and os.path.isfile(cookiefile)) else find_default_cookie_file()
    if eff_cookie and os.path.isfile(eff_cookie):
        ydl_opts['cookiefile'] = eff_cookie

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        sub_file = None
        for f in os.listdir(temp_dir):
            if f.endswith('.vtt') or f.endswith('.srt'):
                sub_file = os.path.join(temp_dir, f)
                break

        if not sub_file or not os.path.isfile(sub_file):
            raise RuntimeError(f"Không thể tải file phụ đề '{lang_code}' từ YouTube.")

        with open(sub_file, 'r', encoding='utf-8', errors='ignore') as fp:
            raw_content = fp.read()

        cues = parse_vtt_or_srt_to_cues(raw_content)
        if not cues:
            raise RuntimeError("Nội dung phụ đề trống hoặc không đúng định dạng.")

        srt_content = cues_to_srt(cues)

        if not output_filepath.lower().endswith(".srt"):
            output_filepath += ".srt"

        os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)
        with open(output_filepath, 'w', encoding='utf-8') as out_fp:
            out_fp.write(srt_content)

        return output_filepath
    except Exception as e:
        raise RuntimeError(clean_error_message(e))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def download_and_convert_en_to_vi_subtitle(
    url: str,
    en_lang_code: str,
    is_auto: bool,
    output_filepath: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cookiefile: Optional[str] = None
) -> str:
    """
    Downloads YouTube English subtitle, translates each cue into Vietnamese,
    and formats the final output as a standard .srt file.
    """
    ensure_ffmpeg_path()
    if progress_callback:
        progress_callback(5, 100, "Đang tải file phụ đề Tiếng Anh gốc từ YouTube...")

    temp_dir = tempfile.mkdtemp(prefix="yt_sub_trans_")
    out_tmpl = os.path.join(temp_dir, "sub.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        'skip_download': True,
        'writesubtitles': not is_auto,
        'writeautomaticsub': is_auto,
        'subtitleslangs': [en_lang_code],
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True,
        'logger': YtDlpNullLogger(),
    }

    if shutil.which("node"):
        ydl_opts['js_runtimes'] = {'node': {}}

    eff_cookie = cookiefile if (cookiefile and os.path.isfile(cookiefile)) else find_default_cookie_file()
    if eff_cookie and os.path.isfile(eff_cookie):
        ydl_opts['cookiefile'] = eff_cookie

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        sub_file = None
        for f in os.listdir(temp_dir):
            if f.endswith('.vtt') or f.endswith('.srt'):
                sub_file = os.path.join(temp_dir, f)
                break

        if not sub_file or not os.path.isfile(sub_file):
            raise RuntimeError("Không thể tải file phụ đề Tiếng Anh từ YouTube.")

        with open(sub_file, 'r', encoding='utf-8', errors='ignore') as fp:
            raw_content = fp.read()

        cues = parse_vtt_or_srt_to_cues(raw_content)
        if not cues:
            raise RuntimeError("Nội dung phụ đề Tiếng Anh trống hoặc không đúng định dạng.")

        if progress_callback:
            progress_callback(15, 100, f"Đã lấy {len(cues)} mốc phụ đề. Bắt đầu dịch sang Tiếng Việt...")

        en_texts = [c['text'] for c in cues]

        def sub_progress(curr, total, msg):
            if progress_callback:
                pct = int(15 + (curr / total) * 75)
                progress_callback(pct, 100, msg)

        vi_texts = translate_texts_to_vietnamese(en_texts, progress_callback=sub_progress)

        vi_cues = []
        for orig_c, vi_t in zip(cues, vi_texts):
            vi_cues.append({
                'start': orig_c['start'],
                'end': orig_c['end'],
                'text': vi_t if vi_t else orig_c['text']
            })

        if progress_callback:
            progress_callback(95, 100, "Đang định dạng chuẩn SRT và ghi file Tiếng Việt...")

        srt_content = cues_to_srt(vi_cues)

        if not output_filepath.lower().endswith(".srt"):
            output_filepath += ".srt"

        os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)
        with open(output_filepath, 'w', encoding='utf-8') as out_fp:
            out_fp.write(srt_content)

        if progress_callback:
            progress_callback(100, 100, "Hoàn tất dịch và xuất file phụ đề Tiếng Việt .SRT thành công!")

        return output_filepath
    except Exception as e:
        raise RuntimeError(clean_error_message(e))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def download_youtube_video(
    url: str,
    format_selector: str,
    output_filepath: str,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[Any] = None,
    cookiefile: Optional[str] = None,
    cookies_from_browser: Optional[str] = None
) -> str:
    """
    Downloads a video/audio using yt-dlp according to format_selector.
    Reports progress to progress_callback.
    Supports cancellation via cancel_event.
    Returns final downloaded file path.
    """
    ensure_ffmpeg_path()

    if cancel_event and cancel_event.is_set():
        raise DownloadCancelledException("Tác vụ đã bị hủy trước khi tải.")

    out_dir = os.path.dirname(output_filepath)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    base_name, target_ext = os.path.splitext(output_filepath)
    if not target_ext:
        target_ext = ".mp4"

    out_tmpl = f"{base_name}.%(ext)s"

    def ytdl_progress_hook(d):
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelledException("Người dùng đã hủy quá trình tải.")

        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percent = (downloaded / total * 100.0) if total > 0 else 0.0

            speed = d.get('speed')
            speed_str = f"{format_bytes(int(speed))}/s" if speed else "-- KB/s"

            eta = d.get('eta')
            eta_str = format_seconds(eta) if eta is not None else "--:--"

            if progress_callback:
                progress_callback({
                    'status': 'downloading',
                    'percent': percent,
                    'downloaded_bytes': downloaded,
                    'total_bytes': total,
                    'speed_str': speed_str,
                    'eta_str': eta_str,
                    'filename': os.path.basename(output_filepath),
                })
        elif status == 'finished':
            if progress_callback:
                progress_callback({
                    'status': 'processing',
                    'percent': 100.0,
                    'message': 'Đang hoàn thiện và xuất file video/audio...'
                })

    ydl_opts: Dict[str, Any] = {
        'format': format_selector,
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [ytdl_progress_hook],
        'noplaylist': True,
        'logger': YtDlpNullLogger(),
    }

    if shutil.which("node"):
        ydl_opts['js_runtimes'] = {'node': {}}

    eff_cookie = cookiefile if (cookiefile and os.path.isfile(cookiefile)) else find_default_cookie_file()
    if eff_cookie and os.path.isfile(eff_cookie):
        ydl_opts['cookiefile'] = eff_cookie
    elif cookies_from_browser and cookies_from_browser.lower() not in ("none", "không dùng", ""):
        ydl_opts['cookiesfrombrowser'] = (cookies_from_browser.lower(), None, None, None)

    if target_ext.lower() == ".mp4":
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadCancelledException:
        for ext_tmp in [target_ext, ".part", ".ytdl", ".temp", ".mp4", ".m4a", ".webm"]:
            for pattern in [f"{base_name}{ext_tmp}", f"{base_name}{ext_tmp}.part"]:
                if os.path.exists(pattern):
                    try:
                        os.remove(pattern)
                    except Exception:
                        pass
        raise
    except Exception as e:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelledException("Người dùng đã hủy quá trình tải.")
        raise RuntimeError(clean_error_message(e))

    # Determine final produced file
    expected_file = f"{base_name}{target_ext}"
    if os.path.isfile(expected_file):
        final_file = expected_file
    else:
        final_file = None
        cand_dir = out_dir if out_dir else "."
        for fname in os.listdir(cand_dir):
            if fname.startswith(os.path.basename(base_name)):
                final_file = os.path.join(cand_dir, fname)
                break
        if not final_file:
            final_file = expected_file

    if progress_callback:
        progress_callback({
            'status': 'complete',
            'percent': 100.0,
            'filepath': final_file
        })

    return final_file
