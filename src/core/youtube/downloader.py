"""
YouTube video metadata extraction and stream downloader using yt-dlp.
"""
import os
import shutil
from typing import Callable, List, Optional, Dict, Any
import yt_dlp

from src.core.ffmpeg_env import ensure_ffmpeg_path
from src.core.youtube.models import (
    YouTubeFormatItem,
    YouTubeSubtitleItem,
    YouTubeVideoInfo,
    DownloadCancelledException,
    YtDlpNullLogger,
)
from src.utils.formatters import format_bytes, format_seconds
from src.utils.file_helpers import clean_error_message, find_default_cookie_file


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

    # Extract Subtitles (Only English and Vietnamese)
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

