"""
File and system helpers.
"""
import os
import re
from typing import Optional


def sanitize_filename(name: str, max_len: int = 120) -> str:
    """Sanitize string to be safe for filenames on Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:max_len] if len(clean) > max_len else clean


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


def find_default_cookie_file(base_dir: Optional[str] = None) -> Optional[str]:
    """Finds default cookies.txt in app dir or current working dir if available."""
    dirs_to_check = []
    if base_dir:
        dirs_to_check.append(base_dir)
    dirs_to_check.append(os.getcwd())
    
    candidates = []
    for d in dirs_to_check:
        candidates.append(os.path.join(d, "cookies.txt"))
        candidates.append(os.path.join(d, "youtube_cookies.txt"))
        
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 0:
            return os.path.abspath(c)
    return None
