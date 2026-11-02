import os
import subprocess
import threading
import time
import shutil
from typing import Callable, Optional
from video_merger import detect_hardware_encoder
from youtube_downloader import ensure_ffmpeg_path

ensure_ffmpeg_path()


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
        rounded_total = int(round(seconds))
        r_hrs = rounded_total // 3600
        r_mins = (rounded_total % 3600) // 60
        r_secs = rounded_total % 60
        return f"{r_hrs:02d}:{r_mins:02d}:{r_secs:02d}"


class VideoCutter:
    def __init__(self):
        self.current_process: Optional[subprocess.Popen] = None
        self._is_cancelled = False
        self.gpu_encoder, self.gpu_label = detect_hardware_encoder()

    def cancel(self):
        self._is_cancelled = True
        if self.current_process:
            try:
                self.current_process.terminate()
            except Exception:
                pass
            try:
                self.current_process.kill()
            except Exception:
                pass

    def cut_video_async(
        self,
        input_path: str,
        output_path: str,
        start_sec: float,
        end_sec: float,
        mode: str = "fast",  # "fast" (Stream Copy) or "encode" (Re-encode)
        selected_audio_idx: int = 0,  # -1 for mute
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """Asynchronously cuts video and outputs an MP4 file."""
        thread = threading.Thread(
            target=self._run_cut,
            args=(input_path, output_path, start_sec, end_sec, mode, selected_audio_idx, on_progress, on_complete, on_error),
            daemon=True
        )
        thread.start()

    def _run_cut(
        self,
        input_path: str,
        output_path: str,
        start_sec: float,
        end_sec: float,
        mode: str,
        selected_audio_idx: int,
        on_progress: Optional[Callable[[float, str], None]],
        on_complete: Optional[Callable[[str], None]],
        on_error: Optional[Callable[[str], None]]
    ):
        self._is_cancelled = False
        self.current_process = None

        ensure_ffmpeg_path()

        if not os.path.isfile(input_path):
            if on_error:
                on_error(f"Tập tin nguồn không tồn tại: {input_path}")
            return

        # Ensure output always has .mp4 extension
        if not output_path.lower().endswith(".mp4"):
            output_path += ".mp4"

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        if end_sec <= start_sec:
            if on_error:
                on_error("Thời điểm kết thúc phải lớn hơn thời điểm bắt đầu!")
            return

        cut_duration = end_sec - start_sec

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        use_stream_copy = (mode == "fast")

        audio_args = []
        if selected_audio_idx == -1:
            audio_args = ["-an"]
        else:
            audio_args = ["-map", f"0:a:{selected_audio_idx}?"]

        def build_cmd(stream_copy: bool) -> list:
            cmd = ["ffmpeg", "-y"]
            
            # Precise seek
            cmd += ["-ss", str(round(start_sec, 3))]
            cmd += ["-to", str(round(end_sec, 3))]
            cmd += ["-i", input_path]
            
            cmd += ["-map", "0:v:0"]
            cmd += audio_args

            if stream_copy:
                cmd += [
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    "-movflags", "+faststart"
                ]
            else:
                enc = self.gpu_encoder if self.gpu_encoder != "libx264" else "libx264"
                cmd += ["-c:v", enc]
                if enc == "libx264":
                    cmd += ["-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
                else:
                    cmd += ["-pix_fmt", "yuv420p"]

                if selected_audio_idx != -1:
                    cmd += ["-c:a", "aac", "-b:a", "192k"]

                cmd += ["-movflags", "+faststart"]

            cmd += ["-progress", "pipe:1"]
            cmd.append(output_path)
            return cmd

        tried_fallback = False
        while True:
            cmd = build_cmd(use_stream_copy)
            stderr_lines = []

            try:
                self.current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    startupinfo=startupinfo
                )

                # Background thread to consume stderr to prevent buffer pipe deadlocks
                def read_stderr():
                    try:
                        for l in self.current_process.stderr:
                            stderr_lines.append(l)
                    except Exception:
                        pass

                t_err = threading.Thread(target=read_stderr, daemon=True)
                t_err.start()

                # Process stdout progress lines
                while True:
                    line = self.current_process.stdout.readline()
                    if not line:
                        if self.current_process.poll() is not None:
                            break
                        time.sleep(0.02)
                        continue

                    line = line.strip()
                    if line.startswith("out_time_ms="):
                        try:
                            val_str = line.split("=")[1]
                            out_us = int(val_str)
                            cur_sec = out_us / 1_000_000.0
                            pct = min(99.0, max(0.0, (cur_sec / cut_duration) * 100.0))
                            if on_progress:
                                on_progress(pct, f"Đang cắt video: {pct:.1f}% ({format_time_hms(cur_sec, True)} / {format_time_hms(cut_duration, True)})")
                        except Exception:
                            pass
                    elif line.startswith("progress=end"):
                        break

                self.current_process.wait()
                retcode = self.current_process.returncode

                if self._is_cancelled:
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                        except Exception:
                            pass
                    if on_error:
                        on_error("Tiến trình cắt video đã bị hủy bỏ.")
                    return

                if retcode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                    if on_progress:
                        on_progress(100.0, "Cắt video hoàn tất 100%!")
                    if on_complete:
                        on_complete(output_path)
                    return
                else:
                    if use_stream_copy and not tried_fallback:
                        use_stream_copy = False
                        tried_fallback = True
                        if on_progress:
                            on_progress(5.0, "Tự động chuyển sang chế độ mã hóa chuẩn hóa MP4...")
                        continue

                    full_err = "".join(stderr_lines[-30:])
                    if on_error:
                        on_error(f"Lỗi FFmpeg (Exit code {retcode}):\n{full_err}")
                    return

            except Exception as e:
                if self._is_cancelled:
                    return
                if use_stream_copy and not tried_fallback:
                    use_stream_copy = False
                    tried_fallback = True
                    continue
                if on_error:
                    on_error(f"Lỗi khi thực thi tiến trình cắt: {e}")
                return
