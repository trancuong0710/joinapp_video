"""
Build script to compile Video Toolkit Pro into a Windows executable using PyInstaller.
Run via:
    python build_exe.py
"""
import os
import sys
import subprocess
import shutil


def build():
    print("==================================================")
    print("🚀 Đang chuẩn bị đóng gói Video Toolkit Pro (.exe)...")
    print("==================================================")

    # Check PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("⚠️ Chưa cài đặt PyInstaller. Đang tiến hành cài đặt...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name=VideoToolkitPro",
        "--collect-all=customtkinter",
        "--collect-all=tkinterdnd2",
        "--collect-all=imageio_ffmpeg",
        "--collect-all=yt_dlp",
        "--add-data=README.md;.",
        "main.py"
    ]

    print("\n📦 Đang chạy lệnh PyInstaller:")
    print(" ".join(cmd))
    print()

    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("\n==================================================")
        print("✅ ĐÓNG GÓI THÀNH CÔNG!")
        print("📁 File chạy nằm trong thư mục: dist\\VideoToolkitPro\\VideoToolkitPro.exe")
        print("==================================================")
    else:
        print("\n❌ Quá trình đóng gói thất bại. Mã lỗi:", res.returncode)


if __name__ == "__main__":
    build()

