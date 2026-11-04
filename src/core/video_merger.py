"""
Video merger engine with zero-copy stream concatenation and GPU hardware acceleration.
"""
import os
import subprocess
import threading
import time
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from src.core.ffmpeg_env import ensure_ffmpeg_path, detect_hardware_encoder, get_windows_startupinfo
from src.core.video_meta import VideoInfo
from src.utils.formatters import format_seconds

ensure_ffmpeg_path()


@dataclass
class MergeConfig:
    mode: str = "fast"  # "fast" (Stream Copy) or "encode" (Re-encode)
    encoder: str = "auto"  # "auto", "gpu", "cpu"
    resolution_mode: str = "Tự động (Theo video lớn nhất)"
    fps_mode: str = "Tự động (Theo video cao nhất)"
    speed_preset: str = "ultrafast"  # ultrafast, veryfast, fast, medium
    crf: int = 22
    audio_bitrate: str = "192k"


class VideoMerger:
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._is_cancelled: bool = False
        self._is_running: bool = False
        self._lock = threading.Lock()
        self._temp_parts_dir: Optional[str] = None
        self.gpu_encoder, self.gpu_label = detect_hardware_encoder()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def cancel(self):
        with self._lock:
            self._is_cancelled = True
            if self._process and self._process.poll() is None:
                try:
                    self._process.terminate()
                    time.sleep(0.3)
                    if self._process.poll() is None:
                        self._process.kill()
                except Exception:
                    pass

    def merge_async(
        self,
        videos: List[VideoInfo],
        output_path: str,
        config: MergeConfig,
        on_progress: Optional[Callable[[float, float, float, str, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        thread = threading.Thread(
            target=self._run_merge,
            args=(videos, output_path, config, on_progress, on_log, on_complete, on_error),
            daemon=True
        )
        thread.start()
        return thread

    def _determine_target_resolution(self, videos: List[VideoInfo], mode: str) -> Tuple[int, int]:
        if mode == "1080p Full HD (1920x1080)":
            return (1920, 1080)
        elif mode == "720p HD (1280x720)":
            return (1280, 720)
        elif mode == "4K Ultra HD (3840x2160)":
            return (3840, 2160)
        elif mode == "Theo video đầu tiên" and videos:
            w = videos[0].width or 1920
            h = videos[0].height or 1080
            return (w - (w % 2), h - (h % 2))
        else:
            max_w = max((v.width for v in videos), default=1920) or 1920
            max_h = max((v.height for v in videos), default=1080) or 1080
            return (max_w - (max_w % 2), max_h - (max_h % 2))

    def _determine_target_fps(self, videos: List[VideoInfo], mode: str) -> float:
        if mode == "60 FPS":
            return 60.0
        elif mode == "30 FPS":
            return 30.0
        elif mode == "24 FPS":
            return 24.0
        else:
            max_fps = max((v.fps for v in videos), default=30.0) or 30.0
            return min(60.0, max(24.0, max_fps))

    def _run_merge(
        self,
        videos: List[VideoInfo],
        output_path: str,
        config: MergeConfig,
        on_progress,
        on_log,
        on_complete,
        on_error,
    ):
        self._is_running = True
        self._is_cancelled = False

        try:
            if not videos:
                raise ValueError("Danh sách video trống.")

            if not output_path.lower().endswith(".mp4"):
                output_path += ".mp4"

            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            if config.mode == "fast":
                self._run_fast_stream_copy(
                    videos, output_path, config, on_progress, on_log, on_complete, on_error
                )
            else:
                self._run_reencode(
                    videos, output_path, config, on_progress, on_log, on_complete, on_error
                )

        except Exception as e:
            if not self._is_cancelled:
                if on_error:
                    on_error(str(e))
                if on_log:
                    on_log(f"❌ Lỗi: {e}")
        finally:
            self._is_running = False
            self._process = None
            if self._temp_parts_dir and os.path.exists(self._temp_parts_dir):
                try:
                    shutil.rmtree(self._temp_parts_dir, ignore_errors=True)
                except Exception:
                    pass
                self._temp_parts_dir = None

    def _determine_target_timescale(self, videos: List[VideoInfo]) -> int:
        """
        Determines the optimal unified video track timescale for zero-copy concatenation.
        Prevents container timescale mismatch bugs where video plays at 2x speed or desyncs.
        """
        valid_timescales = [v.timescale for v in videos if v.timescale > 0]
        if valid_timescales and all(ts == valid_timescales[0] for ts in valid_timescales):
            return valid_timescales[0]

        max_fps = max((v.fps for v in videos), default=25.0)
        if 24.0 <= max_fps <= 26.0:
            return 25000
        elif 29.0 <= max_fps <= 31.0:
            return 30000
        elif 59.0 <= max_fps <= 61.0:
            return 60000
        return 90000

    def _can_direct_concat(self, videos: List[VideoInfo]) -> bool:
        """Check if all videos are already 100% compatible for instant zero-temp-file concat."""
        if len(videos) < 2:
            return False
        if not all(v.file_path.lower().endswith(".mp4") for v in videos):
            return False
        v0 = videos[0]
        for v in videos[1:]:
            if v.codec != v0.codec or v.width != v0.width or v.height != v0.height:
                return False
            # If timescale differs, direct concat without timescale normalization will corrupt packet timestamps!
            if v0.timescale > 0 and v.timescale > 0 and v.timescale != v0.timescale:
                return False
            # If FPS difference exceeds threshold, direct concat is not safe
            if abs(v.fps - v0.fps) > 0.05:
                return False
        if not all(v.has_audio and v.selected_audio_idx == 0 for v in videos):
            return False
        a0 = v0.audio_tracks[0]
        if a0.codec.lower() != "aac" or a0.channels != 2:
            return False
        for v in videos[1:]:
            a = v.audio_tracks[0]
            if a.codec.lower() != "aac" or a.channels != 2 or a.sample_rate != a0.sample_rate:
                return False
        return True

    def _run_fast_stream_copy(
        self,
        videos: List[VideoInfo],
        output_path: str,
        config: MergeConfig,
        on_progress,
        on_log,
        on_complete,
        on_error,
    ):
        total_duration = sum(v.duration for v in videos)
        startupinfo = get_windows_startupinfo()

        # OPTIMIZATION 1: Zero-Intermediate Direct Concat
        if self._can_direct_concat(videos):
            if on_log:
                on_log("⚡ TỐI ƯU CỰC ĐẠI (Zero-Copy): Tất cả video đã đồng nhất chuẩn MP4, H.264 & AAC Stereo!")
                on_log(f"🎬 Nối trực tiếp {len(videos)} video không cần tạo file tạm (Ghi đĩa 1 lần duy nhất)...")
            if on_progress:
                on_progress(30.0, 0, total_duration, "Nối trực tiếp...", "")

            self._temp_parts_dir = tempfile.mkdtemp(prefix="join_direct_")
            list_file = os.path.join(self._temp_parts_dir, "concat_list.txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for v in videos:
                    p_safe = os.path.abspath(v.file_path).replace("\\", "/")
                    f.write(f"file '{p_safe}'\n")

            concat_cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c", "copy",
                "-movflags", "+faststart",
                output_path
            ]

            with self._lock:
                if self._is_cancelled:
                    return
                self._process = subprocess.Popen(
                    concat_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    startupinfo=startupinfo
                )

            _, concat_err = self._process.communicate()
            if self._process.returncode == 0 and os.path.exists(output_path):
                if on_progress:
                    on_progress(100.0, total_duration, total_duration, "Hoàn tất", "")
                if on_log:
                    on_log(f"✅ HOÀN TẤT TỨC THÌ (Zero-Copy)! File đã được lưu tại:\n{output_path}")
                if on_complete:
                    on_complete(output_path)
                return

        # OPTIMIZATION 2: Parallel Multi-Threaded Audio & Video Timescale Normalization
        self._temp_parts_dir = tempfile.mkdtemp(prefix="join_parts_")
        total_steps = len(videos) + 1
        target_timescale = self._determine_target_timescale(videos)

        if on_log:
            on_log(f"⚡ BẮT ĐẦU CHẾ ĐỘ NỐI SIÊU TỐC (Stream Copy + Chuẩn hóa nhịp thời gian {target_timescale}Hz đa luồng)!")
            on_log(f"🎬 Số lượng video: {len(videos)} | Tổng thời lượng: {format_seconds(total_duration)}")
            cpu_cores = os.cpu_count() or 4
            on_log(f"🔥 Xử lý song song đồng thời trên {min(8, cpu_cores)} luồng CPU...")

        part_files = [os.path.join(self._temp_parts_dir, f"part_{idx:03d}.mp4") for idx in range(len(videos))]

        def process_one_video(idx_and_v):
            if self._is_cancelled:
                return idx_and_v[0], False, "Cancelled"
            idx, v = idx_and_v
            part_path = part_files[idx]

            cmd = ["ffmpeg", "-y", "-i", v.file_path]
            has_audio = (
                v.selected_audio_idx >= 0
                and v.selected_audio_idx < len(v.audio_tracks)
            )

            if has_audio:
                track = v.audio_tracks[v.selected_audio_idx]
                cmd.extend([
                    "-map", "0:v:0",
                    "-map", f"0:a:{track.audio_index}",
                    "-c:v", "copy",
                    "-video_track_timescale", str(target_timescale),
                    "-c:a", "aac",
                    "-b:a", config.audio_bitrate,
                    "-ac", "2",
                    "-ar", "48000"
                ])
            else:
                cmd.extend([
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-map", "0:v:0",
                    "-map", "1:a",
                    "-c:v", "copy",
                    "-video_track_timescale", str(target_timescale),
                    "-c:a", "aac",
                    "-b:a", config.audio_bitrate,
                    "-ac", "2",
                    "-ar", "48000",
                    "-shortest"
                ])

            cmd.append(part_path)

            subp = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo
            )
            _, err_out = subp.communicate()
            return idx, (subp.returncode == 0), err_out

        max_workers = min(8, os.cpu_count() or 4)
        completed_count = 0
        failed = False

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(process_one_video, (i, v)): i for i, v in enumerate(videos)
            }
            for future in as_completed(future_to_idx):
                if self._is_cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return
                idx, success, err_msg = future.result()
                if not success:
                    failed = True
                    if on_log:
                        on_log(f"⚠️ Cảnh báo lỗi trích xuất part {idx}: {err_msg[-150:] if err_msg else ''}")
                    break
                completed_count += 1
                pct = (completed_count / total_steps) * 85.0
                if on_progress:
                    on_progress(pct, 0, total_duration, f"Đa luồng ({completed_count}/{len(videos)})", "1000+")
                if on_log:
                    on_log(f"  ✓ Đã chuẩn hóa xong [{completed_count}/{len(videos)}]: {videos[idx].filename}")

        if failed:
            if on_log:
                on_log("🔄 Tự động chuyển sang chế độ Mã Hóa Chuẩn Hóa GPU để hoàn tất...")
            self._run_reencode(videos, output_path, config, on_progress, on_log, on_complete, on_error)
            return

        if self._is_cancelled:
            return

        if on_log:
            on_log("🚀 Đang ghép nối tất cả các đoạn thành file MP4 hoàn chỉnh...")
        if on_progress:
            on_progress(90.0, 0, total_duration, "Đang ghép file...", "")

        list_file = os.path.join(self._temp_parts_dir, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for p in part_files:
                p_safe = os.path.abspath(p).replace("\\", "/")
                f.write(f"file '{p_safe}'\n")

        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path
        ]

        with self._lock:
            if self._is_cancelled:
                return
            self._process = subprocess.Popen(
                concat_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo
            )

        _, concat_err = self._process.communicate()
        returncode = self._process.returncode

        if self._is_cancelled:
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            if on_log:
                on_log("⛔ Đã hủy tiến trình.")
            return

        if returncode == 0 and os.path.exists(output_path):
            if on_progress:
                on_progress(100.0, total_duration, total_duration, "Hoàn tất", "")
            if on_log:
                on_log(f"✅ HOÀN TẤT SIÊU TỐC! File kết quả đã sẵn sàng:\n{output_path}")
            if on_complete:
                on_complete(output_path)
        else:
            if on_log:
                on_log(f"⚠️ Ghép trực tiếp gặp sự cố không tương thích stream: {concat_err[-200:] if concat_err else ''}")
                on_log("🔄 Chuyển sang chế độ Mã Hóa GPU để hoàn tất video...")
            self._run_reencode(videos, output_path, config, on_progress, on_log, on_complete, on_error)

    def _run_reencode(
        self,
        videos: List[VideoInfo],
        output_path: str,
        config: MergeConfig,
        on_progress,
        on_log,
        on_complete,
        on_error,
    ):
        """
        Re-encodes with GPU Hardware Acceleration (AMD AMF / MediaFoundation / NVENC)
        or multi-threaded CPU libx264 with ultrafast preset.
        """
        target_w, target_h = self._determine_target_resolution(videos, config.resolution_mode)
        target_fps = self._determine_target_fps(videos, config.fps_mode)
        total_duration = sum(v.duration for v in videos)
        if total_duration <= 0:
            total_duration = 1.0

        chosen_encoder = "libx264"
        if config.encoder in ("auto", "gpu"):
            chosen_encoder = self.gpu_encoder
        elif config.encoder != "cpu":
            chosen_encoder = config.encoder

        is_gpu = chosen_encoder in ("h264_amf", "h264_nvenc", "h264_qsv", "h264_mf")

        if on_log:
            enc_desc = f"GPU ({chosen_encoder})" if is_gpu else "CPU Đa luồng (libx264 ultrafast)"
            on_log(f"🚀 BẮT ĐẦU CHẾ ĐỘ MÃ HÓA CHUẨN HÓA ({enc_desc})")
            on_log(f"📐 Độ phân giải: {target_w}x{target_h} | FPS: {target_fps}")
            on_log(f"⏱️ Tổng thời lượng: {format_seconds(total_duration)}")

        cmd = ["ffmpeg", "-y", "-progress", "pipe:1"]

        for v in videos:
            cmd.extend(["-i", v.file_path])

        filter_parts = []
        concat_inputs = []

        for i, v in enumerate(videos):
            v_label = f"v{i}"
            filter_parts.append(
                f"[{i}:v:0]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,fps={target_fps},format=yuv420p[{v_label}]"
            )

            a_label = f"a{i}"
            has_audio_selected = (
                v.selected_audio_idx >= 0
                and v.selected_audio_idx < len(v.audio_tracks)
            )

            if has_audio_selected:
                track = v.audio_tracks[v.selected_audio_idx]
                filter_parts.append(
                    f"[{i}:a:{track.audio_index}]aformat=sample_rates=48000:channel_layouts=stereo[{a_label}]"
                )
            else:
                dur = max(0.5, v.duration)
                filter_parts.append(
                    f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={dur}[{a_label}]"
                )

            concat_inputs.append(f"[{v_label}][{a_label}]")

        concat_str = "".join(concat_inputs) + f"concat=n={len(videos)}:v=1:a=1[outv][outa]"
        filter_parts.append(concat_str)

        cmd.extend([
            "-filter_complex", ";\n".join(filter_parts),
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", chosen_encoder
        ])

        if chosen_encoder == "libx264":
            preset = config.speed_preset if config.speed_preset in ("ultrafast", "veryfast") else "ultrafast"
            cmd.extend(["-preset", preset, "-threads", "0", "-crf", str(config.crf)])
        elif chosen_encoder == "h264_amf":
            cmd.extend(["-quality", "speed", "-rc", "cbr"])
        elif chosen_encoder == "h264_nvenc":
            cmd.extend(["-preset", "p1", "-tune", "ull"])
        elif chosen_encoder == "h264_mf":
            cmd.extend(["-rate_control", "cbr"])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", config.audio_bitrate,
            "-movflags", "+faststart",
            output_path
        ])

        startupinfo = get_windows_startupinfo()

        with self._lock:
            if self._is_cancelled:
                return
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo
            )

        def read_stderr():
            for line in self._process.stderr:
                line_clean = line.strip()
                if line_clean and on_log:
                    on_log(line_clean)

        err_thread = threading.Thread(target=read_stderr, daemon=True)
        err_thread.start()

        current_speed = ""
        current_fps = ""

        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            if line.startswith("speed="):
                current_speed = line.split("=", 1)[1].strip()
            elif line.startswith("fps="):
                current_fps = line.split("=", 1)[1].strip()
            elif line.startswith("out_time_us="):
                try:
                    out_us = int(line.split("=", 1)[1].strip())
                    current_sec = out_us / 1_000_000.0
                    pct = min(100.0, max(0.0, (current_sec / total_duration) * 100.0))
                    if on_progress:
                        on_progress(pct, current_sec, total_duration, current_speed, current_fps)
                except ValueError:
                    pass
            elif line == "progress=end":
                if on_progress:
                    on_progress(100.0, total_duration, total_duration, current_speed, current_fps)

        self._process.wait()
        err_thread.join(timeout=2.0)
        returncode = self._process.returncode

        if self._is_cancelled:
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            if on_log:
                on_log("⛔ Đã hủy tiến trình.")
            return

        if returncode == 0 and os.path.exists(output_path):
            if on_progress:
                on_progress(100.0, total_duration, total_duration, current_speed, current_fps)
            if on_log:
                on_log(f"✅ Hoàn thành xuất sắc! File đã được lưu tại:\n{output_path}")
            if on_complete:
                on_complete(output_path)
        else:
            err_msg = f"FFmpeg trả về mã lỗi {returncode}."
            if on_error:
                on_error(err_msg)

