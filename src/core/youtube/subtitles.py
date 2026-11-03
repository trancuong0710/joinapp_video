"""
YouTube subtitle download, parsing, and Google Translate integration.
"""
import os
import re
import shutil
import json
import tempfile
import urllib.parse
import urllib.request
from typing import Callable, List, Optional, Dict, Any
import yt_dlp

from src.core.ffmpeg_env import ensure_ffmpeg_path
from src.core.youtube.models import YtDlpNullLogger
from src.utils.file_helpers import clean_error_message, find_default_cookie_file


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

