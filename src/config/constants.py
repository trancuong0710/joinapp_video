"""
Application constants and shared configuration.
"""

APP_NAME = "Video Toolkit Pro"
APP_SUBTITLE = "Nối Video • Cắt Video • Tải YouTube Tốc Độ Cao"
APP_VERSION = "2.0.0"

SUPPORTED_VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v", ".wmv", ".3gp"
)

DEFAULT_FPS = 30.0

HARDWARE_ENCODER_CANDIDATES = [
    ("h264_amf", "AMD Radeon (AMF Hardware Accel)"),
    ("h264_nvenc", "NVIDIA GeForce (NVENC Hardware Accel)"),
    ("h264_qsv", "Intel QuickSync (QSV Hardware Accel)"),
    ("h264_mf", "Windows Media Foundation (Hardware Accel)"),
]

FALLBACK_CPU_ENCODER = ("libx264", "CPU (libx264 Đa luồng)")

