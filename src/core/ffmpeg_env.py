"""
FFmpeg environment initialization and hardware acceleration detection.
"""
import os
import sys
import shutil
import subprocess
import winreg
from typing import Optional, Tuple
from src.config.constants import HARDWARE_ENCODER_CANDIDATES, FALLBACK_CPU_ENCODER


def get_windows_startupinfo() -> Optional[subprocess.STARTUPINFO]:
    """Returns STARTUPINFO with SW_HIDE on Windows to prevent console windows popping up."""
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return startupinfo
    return None


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


# Cache hardware encoder detection result so we don't spawn ffmpeg repeatedly
_CACHED_ENCODER: Optional[Tuple[str, str]] = None


def detect_hardware_encoder() -> Tuple[str, str]:
    """Detect available GPU hardware encoder for maximum speed."""
    global _CACHED_ENCODER
    if _CACHED_ENCODER is not None:
        return _CACHED_ENCODER

    ensure_ffmpeg_path()
    startupinfo = get_windows_startupinfo()

    for enc, label in HARDWARE_ENCODER_CANDIDATES:
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=0.1:size=256x256:rate=30",
                "-c:v", enc,
                "-f", "null", "-"
            ]
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                timeout=4
            )
            if res.returncode == 0:
                _CACHED_ENCODER = (enc, label)
                return _CACHED_ENCODER
        except Exception:
            pass

    _CACHED_ENCODER = FALLBACK_CPU_ENCODER
    return _CACHED_ENCODER

