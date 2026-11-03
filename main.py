import sys
import os

# Ensure working directory is application directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Ensure FFmpeg and FFprobe are properly registered in PATH
try:
    from src.core.ffmpeg_env import ensure_ffmpeg_path
    ensure_ffmpeg_path()
except Exception:
    pass

from src.ui.main_window import run_app

if __name__ == "__main__":
    run_app()
