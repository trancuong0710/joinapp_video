import os
import sys
import time
import shutil
import queue
import tempfile
import threading
import io
import webbrowser
from datetime import datetime
from typing import List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES
from PIL import Image
import requests

from video_meta import VideoInfo, probe_video, format_seconds, format_bytes
from video_merger import VideoMerger, MergeConfig
from youtube_downloader import (
    extract_youtube_info,
    download_youtube_video,
    YouTubeVideoInfo,
    YouTubeFormatItem,
    sanitize_filename,
    DownloadCancelledException,
    ensure_ffmpeg_path,
    format_bytes as yt_format_bytes
)

# Supported video extensions
SUPPORTED_EXTENSIONS = (
    ".mp4", ".mkv", ".mov", ".avi", ".flv", ".webm",
    ".ts", ".m4v", ".wmv", ".m2ts", ".vob", ".3gp"
)


class DragDropCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class VideoJoinerApp(DragDropCTk):
    def __init__(self):
        super().__init__()

        # Ensure ffmpeg & ffprobe are ready
        try:
            ensure_ffmpeg_path()
        except Exception:
            pass

        # Window configuration
        self.title("Video Toolkit Pro - Nối Video & Tải YouTube")
        self.geometry("1140x840")
        self.minsize(960, 700)

        # Theme & Styling
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Joiner State
        self.video_list: List[VideoInfo] = []
        self.selected_index: int = -1
        self.temp_dir = tempfile.mkdtemp(prefix="joinapp_")
        self.merger = VideoMerger()
        self.is_merging = False
        self.output_file_path = ""
        self._thumb_cache = {}

        # YouTube State
        self.current_view: str = "joiner"  # "joiner" or "youtube"
        self.yt_current_info: Optional[YouTubeVideoInfo] = None
        self.yt_is_fetching: bool = False
        self.yt_is_downloading: bool = False
        self.yt_cancel_event: Optional[threading.Event] = None
        self.yt_downloaded_file: Optional[str] = None
        self.yt_thumb_image: Optional[ctk.CTkImage] = None
        self.yt_active_filter: str = "Tất cả"

        # Thread-safe event queue
        self._event_queue = queue.Queue()

        # Build UI
        self._init_ui()

        # Setup Drag and Drop
        self._setup_dnd()

        # Start queue polling
        self._poll_event_queue()

        # Keybindings
        self.bind("<Control-Key-1>", lambda e: self._switch_view("joiner"))
        self.bind("<Control-Key-2>", lambda e: self._switch_view("youtube"))
        self.bind("<Control-Key-d>", lambda e: self._switch_view("youtube"))

        # Handle window close cleanup
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _poll_event_queue(self):
        try:
            while True:
                event_type, data = self._event_queue.get_nowait()
                # Joiner events
                if event_type == "probe_done":
                    self._on_probed_done(data)
                elif event_type == "progress":
                    pct, cur_sec, total_sec, speed, fps = data
                    self._update_progress_ui(pct, cur_sec, total_sec, speed, fps)
                elif event_type == "log":
                    self._append_log(data)
                elif event_type == "complete":
                    self._finish_merge_success(data)
                elif event_type == "error":
                    self._finish_merge_error(data)
                # YouTube events
                elif event_type == "yt_info_done":
                    self._on_yt_info_done(data)
                elif event_type == "yt_info_error":
                    self._on_yt_info_error(data)
                elif event_type == "yt_progress":
                    self._on_yt_download_progress(data)
                elif event_type == "yt_complete":
                    self._on_yt_download_complete(data)
                elif event_type == "yt_cancelled":
                    self._on_yt_download_cancelled()
                elif event_type == "yt_error":
                    self._on_yt_download_error(data)
        except queue.Empty:
            pass
        finally:
            self.after(50, self._poll_event_queue)

    def _setup_dnd(self):
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_files_dropped)
        except Exception as e:
            print(f"Không thể kích hoạt Drag & Drop: {e}")

    def _on_files_dropped(self, event):
        raw_data = event.data
        if not raw_data:
            return
        files = self.tk.splitlist(raw_data)
        if self.current_view != "joiner":
            self._switch_view("joiner")
        self._add_files_by_paths(list(files))

    def _init_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Native Menu Bar
        self._build_menu_bar()

        # 2. Header Frame (Row 0)
        self._build_header()

        # 3. Content Container (Row 1)
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        # 3A. Video Joiner View
        self.joiner_view = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.joiner_view.grid_rowconfigure(1, weight=1)  # Video list expands
        self.joiner_view.grid_columnconfigure(0, weight=1)

        self._build_toolbar(self.joiner_view)
        self._build_video_list_area(self.joiner_view)
        self._build_output_and_options_section(self.joiner_view)
        self._build_progress_and_bottom_bar(self.joiner_view)

        # 3B. YouTube Downloader View
        self.youtube_view = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.youtube_view.grid_rowconfigure(2, weight=1)  # Formats scroll list expands
        self.youtube_view.grid_columnconfigure(0, weight=1)

        self._build_youtube_view(self.youtube_view)

        # Show Joiner by default
        self._switch_view("joiner")

    def _build_menu_bar(self):
        menubar = tk.Menu(self)

        # Menu Trình đơn
        menu_app = tk.Menu(menubar, tearoff=0)
        menu_app.add_command(label="🎬 Ghép Video MP4", command=lambda: self._switch_view("joiner"), accelerator="Ctrl+1")
        menu_app.add_command(label="📥 Tải Video YouTube", command=lambda: self._switch_view("youtube"), accelerator="Ctrl+2")
        menu_app.add_separator()
        menu_app.add_command(label="🚪 Thoát", command=self._on_close, accelerator="Alt+F4")
        menubar.add_cascade(label="Trình đơn", menu=menu_app)

        # Menu Công cụ
        menu_tools = tk.Menu(menubar, tearoff=0)
        menu_tools.add_command(label="📥 Tải Video YouTube...", command=lambda: self._switch_view("youtube"), accelerator="Ctrl+D")
        menu_tools.add_command(label="➕ Thêm Video...", command=self._on_add_files_clicked)
        menu_tools.add_command(label="📂 Thêm Thư Mục...", command=self._on_add_folder_clicked)
        menu_tools.add_command(label="🧹 Xóa danh sách video", command=self._on_clear_all_clicked)
        menubar.add_cascade(label="Công cụ", menu=menu_tools)

        # Menu Trợ giúp
        menu_help = tk.Menu(menubar, tearoff=0)
        menu_help.add_command(label="ℹ️ Giới thiệu Video Toolkit", command=self._show_about_dialog)
        menubar.add_cascade(label="Trợ giúp", menu=menu_help)

        self.config(menu=menubar)

    def _show_about_dialog(self):
        messagebox.showinfo(
            "Giới thiệu Video Toolkit Pro",
            "Video Toolkit Pro (Phiên bản Nâng cấp)\n\n"
            "Tính năng chính:\n"
            "1. Ghép Video MP4 Chuyên Nghiệp: Hỗ trợ đa định dạng, chọn track audio từng video, tăng tốc GPU NVENC/AMF/QSV.\n"
            "2. Tải Video YouTube: Nhập link, xem danh sách đầy đủ định dạng (Full HD, 4K, MP3/M4A), tải về máy với 1 cú click."
        )

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray85", "#181a20"))
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(1, weight=1)

        # App Logo / Title
        logo_label = ctk.CTkLabel(
            header_frame,
            text="🎬",
            font=ctk.CTkFont(size=30)
        )
        logo_label.grid(row=0, column=0, rowspan=2, padx=(18, 10), pady=10)

        title_label = ctk.CTkLabel(
            header_frame,
            text="VIDEO TOOLKIT PRO",
            font=ctk.CTkFont(size=17, weight="bold")
        )
        title_label.grid(row=0, column=1, sticky="w", pady=(8, 0))

        sub_text = (
            f"Ghép Video MP4 Đa Định Dạng • Tải Video & Nhạc YouTube • {self.merger.gpu_label}"
        )
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text=sub_text,
            font=ctk.CTkFont(size=11),
            text_color=("#1f6aa5", "#38bdf8"),
            justify="left"
        )
        subtitle_label.grid(row=1, column=1, sticky="w", pady=(0, 8))

        # View Switcher Segmented Button
        self.nav_segmented = ctk.CTkSegmentedButton(
            header_frame,
            values=["🎬 Ghép Video", "📥 Tải YouTube"],
            command=self._on_nav_segmented_clicked,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=34,
            width=260
        )
        self.nav_segmented.set("🎬 Ghép Video")
        self.nav_segmented.grid(row=0, column=2, rowspan=2, padx=16, pady=10)

        # Appearance mode toggle switch
        self.theme_switch = ctk.CTkSwitch(
            header_frame,
            text="Giao diện Tối",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light"
        )
        self.theme_switch.select()
        self.theme_switch.grid(row=0, column=3, rowspan=2, padx=(0, 18), pady=10)

    def _toggle_theme(self):
        mode = "Dark" if self.theme_switch.get() == "Dark" else "Light"
        ctk.set_appearance_mode(mode)
        self.theme_switch.configure(text=f"Giao diện {'Tối' if mode == 'Dark' else 'Sáng'}")

    def _on_nav_segmented_clicked(self, value: str):
        if "YouTube" in value:
            self._switch_view("youtube")
        else:
            self._switch_view("joiner")

    def _switch_view(self, view_name: str):
        self.current_view = view_name
        if view_name == "joiner":
            self.youtube_view.grid_forget()
            self.joiner_view.grid(row=0, column=0, sticky="nsew")
            self.nav_segmented.set("🎬 Ghép Video")
        else:
            self.joiner_view.grid_forget()
            self.youtube_view.grid(row=0, column=0, sticky="nsew")
            self.nav_segmented.set("📥 Tải YouTube")

    # ================= 1. VIDEO JOINER VIEW =================

    def _build_toolbar(self, parent):
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 8))
        toolbar.grid_columnconfigure(6, weight=1)

        self.btn_add_files = ctk.CTkButton(
            toolbar,
            text="➕ Thêm Video...",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1f6aa5",
            hover_color="#144870",
            width=130,
            height=34,
            command=self._on_add_files_clicked
        )
        self.btn_add_files.grid(row=0, column=0, padx=(0, 8))

        self.btn_add_folder = ctk.CTkButton(
            toolbar,
            text="📂 Thêm Thư Mục...",
            font=ctk.CTkFont(size=13),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            width=140,
            height=34,
            command=self._on_add_folder_clicked
        )
        self.btn_add_folder.grid(row=0, column=1, padx=(0, 8))

        self.btn_clear_all = ctk.CTkButton(
            toolbar,
            text="🧹 Xóa Tất Cả",
            font=ctk.CTkFont(size=13),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("#c0392b", "#962d22"),
            text_color=("black", "white"),
            width=110,
            height=34,
            command=self._on_clear_all_clicked
        )
        self.btn_clear_all.grid(row=0, column=2, padx=(0, 8))

        # Reorder buttons
        self.btn_move_up = ctk.CTkButton(
            toolbar,
            text="▲ Lên",
            width=65,
            height=34,
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            command=self._on_move_up_selected
        )
        self.btn_move_up.grid(row=0, column=3, padx=(0, 4))

        self.btn_move_down = ctk.CTkButton(
            toolbar,
            text="▼ Xuống",
            width=65,
            height=34,
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            command=self._on_move_down_selected
        )
        self.btn_move_down.grid(row=0, column=4, padx=(0, 8))

        # Direct shortcut button to YouTube Downloader
        self.btn_open_yt_shortcut = ctk.CTkButton(
            toolbar,
            text="📥 Tải YouTube",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#8e44ad", "#6c3483"),
            hover_color=("#732d91", "#5b2c6f"),
            width=125,
            height=34,
            command=lambda: self._switch_view("youtube")
        )
        self.btn_open_yt_shortcut.grid(row=0, column=5, padx=(0, 12))

        # Summary label
        self.lbl_summary = ctk.CTkLabel(
            toolbar,
            text="Chưa chọn video nào. Hãy kéo thả file vào đây hoặc bấm '➕ Thêm Video'.",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray70"),
            anchor="e"
        )
        self.lbl_summary.grid(row=0, column=6, sticky="e", padx=(10, 0))

    def _build_video_list_area(self, parent):
        list_container = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray90", "#1e2129"))
        list_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        self.scroll_list = ctk.CTkScrollableFrame(
            list_container,
            fg_color="transparent",
            corner_radius=8
        )
        self.scroll_list.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.scroll_list.grid_columnconfigure(0, weight=1)

        # Empty state placeholder
        self.empty_placeholder = ctk.CTkFrame(self.scroll_list, fg_color="transparent")
        self.empty_placeholder.grid(row=0, column=0, pady=80, sticky="nsew")
        self.empty_placeholder.grid_columnconfigure(0, weight=1)

        icon_ph = ctk.CTkLabel(
            self.empty_placeholder,
            text="🎞️",
            font=ctk.CTkFont(size=56)
        )
        icon_ph.pack(pady=(0, 10))

        text_ph1 = ctk.CTkLabel(
            self.empty_placeholder,
            text="Kéo & Thả các file video vào đây",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        text_ph1.pack(pady=(0, 4))

        text_ph2 = ctk.CTkLabel(
            self.empty_placeholder,
            text="Hỗ trợ MP4, MKV, AVI, MOV, WEBM, FLV, TS và nhiều định dạng khác.\nSau khi thêm, bạn có thể xem chi tiết thời lượng, độ phân giải và chọn Audio Track để nối.",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray65"),
            justify="center"
        )
        text_ph2.pack()

    def _build_output_and_options_section(self, parent):
        opts_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray88", "#232731"))
        opts_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        opts_frame.grid_columnconfigure(1, weight=1)

        # Output save path row
        lbl_out = ctk.CTkLabel(
            opts_frame,
            text="💾 Nơi lưu file MP4 kết quả:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_out.grid(row=0, column=0, sticky="w", padx=(14, 8), pady=(12, 6))

        self.entry_output = ctk.CTkEntry(
            opts_frame,
            placeholder_text="Chọn nơi lưu file kết quả (luôn là định dạng .mp4)...",
            height=34,
            font=ctk.CTkFont(size=12)
        )
        self.entry_output.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(12, 6))

        self.btn_browse_output = ctk.CTkButton(
            opts_frame,
            text="📁 Chọn Nơi Lưu...",
            width=130,
            height=34,
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=self._on_browse_output_clicked
        )
        self.btn_browse_output.grid(row=0, column=2, padx=(0, 14), pady=(12, 6))

        # Mode selection row
        mode_row = ctk.CTkFrame(opts_frame, fg_color="transparent")
        mode_row.grid(row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(2, 6))

        lbl_mode = ctk.CTkLabel(
            mode_row,
            text="⚡ Chế độ ghép:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_mode.pack(side="left", padx=(0, 10))

        self.seg_mode = ctk.CTkSegmentedButton(
            mode_row,
            values=[
                "⚡ Ghép Siêu Tốc (Stream Copy - Khuyên dùng)",
                "🚀 Mã Hóa Chuẩn Hóa (GPU / CPU Re-encode)"
            ],
            command=self._on_mode_changed,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.seg_mode.set("⚡ Ghép Siêu Tốc (Stream Copy - Khuyên dùng)")
        self.seg_mode.pack(side="left", padx=(0, 12))

        self.chk_show_log = ctk.CTkCheckBox(
            mode_row,
            text="Xem log chi tiết",
            font=ctk.CTkFont(size=12),
            command=self._on_toggle_log
        )
        self.chk_show_log.pack(side="right")

        # Dynamic options container
        self.settings_row = ctk.CTkFrame(opts_frame, fg_color="transparent")
        self.settings_row.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))

        # Fast mode banner
        self.frame_fast_info = ctk.CTkFrame(self.settings_row, fg_color=("gray95", "#181a20"), corner_radius=6)
        lbl_fast_hint = ctk.CTkLabel(
            self.frame_fast_info,
            text="✨ Tốc độ cực nhanh (100x - 300x): Bỏ qua bước nén lại video, giữ nguyên 100% độ sắc nét gốc. Quá trình nối chỉ mất vài giây!",
            font=ctk.CTkFont(size=12),
            text_color=("#27ae60", "#2ecc71")
        )
        lbl_fast_hint.pack(side="left", padx=12, pady=6)

        # Re-encode options frame
        self.frame_reencode_opts = ctk.CTkFrame(self.settings_row, fg_color="transparent")

        lbl_enc = ctk.CTkLabel(self.frame_reencode_opts, text="Bộ mã hóa:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_enc.pack(side="left", padx=(0, 4))
        self.cbo_encoder = ctk.CTkOptionMenu(
            self.frame_reencode_opts,
            values=[f"GPU ({self.merger.gpu_encoder})", "CPU (libx264 Đa luồng)"],
            width=180,
            height=28
        )
        self.cbo_encoder.set(f"GPU ({self.merger.gpu_encoder})")
        self.cbo_encoder.pack(side="left", padx=(0, 12))

        lbl_res = ctk.CTkLabel(self.frame_reencode_opts, text="Độ phân giải:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_res.pack(side="left", padx=(0, 4))
        self.cbo_res = ctk.CTkOptionMenu(
            self.frame_reencode_opts,
            values=[
                "Tự động (Theo video lớn nhất)",
                "Theo video đầu tiên",
                "1080p Full HD (1920x1080)",
                "720p HD (1280x720)",
                "4K Ultra HD (3840x2160)"
            ],
            width=180,
            height=28
        )
        self.cbo_res.set("Tự động (Theo video lớn nhất)")
        self.cbo_res.pack(side="left", padx=(0, 12))

        lbl_speed = ctk.CTkLabel(self.frame_reencode_opts, text="Tốc độ:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_speed.pack(side="left", padx=(0, 4))
        self.cbo_speed = ctk.CTkOptionMenu(
            self.frame_reencode_opts,
            values=[
                "Siêu tốc (Ultrafast)",
                "Rất nhanh (Veryfast)",
                "Cân bằng (Fast)"
            ],
            width=150,
            height=28
        )
        self.cbo_speed.set("Siêu tốc (Ultrafast)")
        self.cbo_speed.pack(side="left", padx=(0, 12))

        lbl_fps = ctk.CTkLabel(self.frame_reencode_opts, text="FPS:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_fps.pack(side="left", padx=(0, 4))
        self.cbo_fps = ctk.CTkOptionMenu(
            self.frame_reencode_opts,
            values=["Tự động (Theo video cao nhất)", "30 FPS", "60 FPS"],
            width=140,
            height=28
        )
        self.cbo_fps.set("Tự động (Theo video cao nhất)")
        self.cbo_fps.pack(side="left")

        self._on_mode_changed(self.seg_mode.get())

    def _on_mode_changed(self, mode_str: str):
        if "Siêu Tốc" in mode_str:
            self.frame_reencode_opts.pack_forget()
            self.frame_fast_info.pack(fill="x", expand=True)
        else:
            self.frame_fast_info.pack_forget()
            self.frame_reencode_opts.pack(fill="x", expand=True)

    def _build_progress_and_bottom_bar(self, parent):
        bottom_container = ctk.CTkFrame(parent, fg_color="transparent")
        bottom_container.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 14))
        bottom_container.grid_columnconfigure(0, weight=1)

        # Real-time progress bar
        self.prog_bar = ctk.CTkProgressBar(bottom_container, height=12, corner_radius=6)
        self.prog_bar.set(0.0)
        self.prog_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # Status text row
        status_row = ctk.CTkFrame(bottom_container, fg_color="transparent")
        status_row.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        status_row.grid_columnconfigure(0, weight=1)

        self.lbl_status = ctk.CTkLabel(
            status_row,
            text="Sẵn sàng nối video.",
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        self.lbl_status.grid(row=0, column=0, sticky="w")

        self.lbl_time_detail = ctk.CTkLabel(
            status_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
            anchor="e"
        )
        self.lbl_time_detail.grid(row=0, column=1, sticky="e")

        # Collapsible FFmpeg Log box
        self.log_textbox = ctk.CTkTextbox(
            bottom_container,
            height=100,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=("white", "#14161b")
        )

        # Buttons row
        buttons_row = ctk.CTkFrame(bottom_container, fg_color="transparent")
        buttons_row.grid(row=3, column=0, sticky="ew", pady=(4, 0))

        self.btn_start = ctk.CTkButton(
            buttons_row,
            text="🚀 BẮT ĐẦU NỐI VIDEO",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2980b9",
            hover_color="#1f618d",
            height=42,
            width=220,
            command=self._on_start_merge_clicked
        )
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_cancel = ctk.CTkButton(
            buttons_row,
            text="⏹ Hủy Bỏ",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#c0392b",
            hover_color="#922b21",
            height=42,
            width=110,
            state="disabled",
            command=self._on_cancel_merge_clicked
        )
        self.btn_cancel.pack(side="left", padx=(0, 10))

        self.btn_play_result = ctk.CTkButton(
            buttons_row,
            text="▶ Xem File Kết Quả",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#27ae60",
            hover_color="#1e8449",
            height=42,
            width=160,
            state="disabled",
            command=self._on_play_result_clicked
        )
        self.btn_play_result.pack(side="right")

        self.btn_open_folder = ctk.CTkButton(
            buttons_row,
            text="📂 Mở Thư Mục Chứa File",
            font=ctk.CTkFont(size=13),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            height=42,
            width=170,
            state="disabled",
            command=self._on_open_folder_clicked
        )
        self.btn_open_folder.pack(side="right", padx=(0, 8))

    def _on_toggle_log(self):
        if self.chk_show_log.get():
            self.log_textbox.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        else:
            self.log_textbox.grid_forget()

    # ================= 2. YOUTUBE DOWNLOADER VIEW =================

    def _build_youtube_view(self, parent):
        parent.grid_rowconfigure(2, weight=1)  # Formats scroll frame expands
        parent.grid_columnconfigure(0, weight=1)

        # Row 0: Input Card
        input_card = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray88", "#232731"))
        input_card.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 8))
        input_card.grid_columnconfigure(1, weight=1)

        lbl_yt_title = ctk.CTkLabel(
            input_card,
            text="📥 TẢI VIDEO & ÂM THANH YOUTUBE TỐC ĐỘ CAO",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1f6aa5", "#38bdf8")
        )
        lbl_yt_title.grid(row=0, column=0, columnspan=5, sticky="w", padx=16, pady=(10, 4))

        lbl_url = ctk.CTkLabel(
            input_card,
            text="Link YouTube:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_url.grid(row=1, column=0, padx=(16, 8), pady=(0, 8), sticky="w")

        self.yt_entry_url = ctk.CTkEntry(
            input_card,
            placeholder_text="Dán đường link YouTube vào đây (VD: https://www.youtube.com/watch?v=... hoặc https://youtu.be/...)",
            height=36,
            font=ctk.CTkFont(size=13)
        )
        self.yt_entry_url.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 8))
        self.yt_entry_url.bind("<Return>", lambda e: self._on_yt_fetch_clicked())

        self.yt_btn_paste = ctk.CTkButton(
            input_card,
            text="📋 Dán Link",
            width=100,
            height=36,
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            command=self._on_yt_paste_clicked
        )
        self.yt_btn_paste.grid(row=1, column=2, padx=(0, 8), pady=(0, 8))

        self.yt_btn_fetch = ctk.CTkButton(
            input_card,
            text="🔍 Lấy Link Tải",
            width=130,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._on_yt_fetch_clicked
        )
        self.yt_btn_fetch.grid(row=1, column=3, padx=(0, 8), pady=(0, 8))

        self.yt_btn_clear = ctk.CTkButton(
            input_card,
            text="🧹 Xóa",
            width=70,
            height=36,
            fg_color=("gray75", "#2b2f38"),
            hover_color=("#c0392b", "#962d22"),
            text_color=("black", "white"),
            command=self._on_yt_clear_clicked
        )
        self.yt_btn_clear.grid(row=1, column=4, padx=(0, 16), pady=(0, 8))

        self.yt_lbl_input_status = ctk.CTkLabel(
            input_card,
            text="Sẵn sàng: Nhập link YouTube và nhấn '🔍 Lấy Link Tải' để hiển thị các định dạng video & âm thanh.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
            anchor="w"
        )
        self.yt_lbl_input_status.grid(row=2, column=0, columnspan=5, sticky="w", padx=16, pady=(0, 10))

        # Row 1: Video Preview Card (Initially hidden)
        self.yt_preview_card = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray90", "#1e2129"))
        self.yt_preview_card.grid_columnconfigure(1, weight=1)

        self.yt_lbl_thumb = ctk.CTkLabel(
            self.yt_preview_card,
            text="🎬",
            font=ctk.CTkFont(size=36),
            width=180,
            height=100,
            corner_radius=6,
            fg_color=("gray80", "#13151b")
        )
        self.yt_lbl_thumb.grid(row=0, column=0, rowspan=3, padx=12, pady=10)

        self.yt_lbl_title = ctk.CTkLabel(
            self.yt_preview_card,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=620
        )
        self.yt_lbl_title.grid(row=0, column=1, sticky="w", padx=(6, 12), pady=(10, 2))

        self.yt_lbl_meta = ctk.CTkLabel(
            self.yt_preview_card,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=("#1f6aa5", "#38bdf8"),
            anchor="w"
        )
        self.yt_lbl_meta.grid(row=1, column=1, sticky="w", padx=(6, 12), pady=(0, 4))

        meta_actions = ctk.CTkFrame(self.yt_preview_card, fg_color="transparent")
        meta_actions.grid(row=2, column=1, sticky="w", padx=(6, 12), pady=(0, 10))

        self.yt_btn_open_browser = ctk.CTkButton(
            meta_actions,
            text="🌐 Mở trên YouTube",
            width=140,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            command=self._on_yt_open_browser_clicked
        )
        self.yt_btn_open_browser.pack(side="left", padx=(0, 8))

        # Row 2: Formats Outer Container
        formats_outer = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray90", "#1e2129"))
        formats_outer.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 8))
        formats_outer.grid_rowconfigure(1, weight=1)
        formats_outer.grid_columnconfigure(0, weight=1)

        # Formats Filter Bar
        filter_bar = ctk.CTkFrame(formats_outer, fg_color="transparent")
        filter_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        filter_bar.grid_columnconfigure(0, weight=1)

        lbl_fmts = ctk.CTkLabel(
            filter_bar,
            text="⚡ CÁC LINK TẢI VỀ (Click vào một link để tải về máy):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_fmts.grid(row=0, column=0, sticky="w")

        self.yt_filter_seg = ctk.CTkSegmentedButton(
            filter_bar,
            values=["Tất cả", "Video MP4", "Chỉ Âm thanh", "Luồng trực tiếp"],
            command=self._on_yt_filter_changed,
            height=28,
            font=ctk.CTkFont(size=12)
        )
        self.yt_filter_seg.set("Tất cả")
        self.yt_filter_seg.grid(row=0, column=1, sticky="e")

        # Scrollable Formats List
        self.yt_formats_scroll = ctk.CTkScrollableFrame(
            formats_outer,
            fg_color="transparent",
            corner_radius=8
        )
        self.yt_formats_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.yt_formats_scroll.grid_columnconfigure(0, weight=1)

        self._show_yt_formats_placeholder("Chưa có link tải nào. Hãy dán link YouTube ở trên và nhấn '🔍 Lấy Link Tải'.")

        # Row 3: Download Progress & Action Card (Initially hidden)
        self.yt_dl_card = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray88", "#232731"))
        self.yt_dl_card.grid_columnconfigure(0, weight=1)

        self.yt_lbl_dl_title = ctk.CTkLabel(
            self.yt_dl_card,
            text="Tiến trình tải về",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        self.yt_lbl_dl_title.grid(row=0, column=0, sticky="w", padx=16, pady=(10, 4))

        self.yt_progress_bar = ctk.CTkProgressBar(self.yt_dl_card, height=12, corner_radius=6)
        self.yt_progress_bar.set(0.0)
        self.yt_progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

        dl_status_row = ctk.CTkFrame(self.yt_dl_card, fg_color="transparent")
        dl_status_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        dl_status_row.grid_columnconfigure(0, weight=1)

        self.yt_lbl_dl_details = ctk.CTkLabel(
            dl_status_row,
            text="Đang kết nối...",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
            anchor="w"
        )
        self.yt_lbl_dl_details.grid(row=0, column=0, sticky="w")

        self.yt_actions_box = ctk.CTkFrame(dl_status_row, fg_color="transparent")
        self.yt_actions_box.grid(row=0, column=1, sticky="e")

        self.yt_btn_cancel_dl = ctk.CTkButton(
            self.yt_actions_box,
            text="⏹ Dừng Tải",
            width=90,
            height=30,
            fg_color=("#c0392b", "#962d22"),
            hover_color=("#962d22", "#78241c"),
            command=self._on_yt_cancel_download_clicked
        )
        self.yt_btn_cancel_dl.pack(side="left", padx=(0, 6))

        self.yt_btn_open_file = ctk.CTkButton(
            self.yt_actions_box,
            text="▶️ Xem Video",
            width=105,
            height=30,
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._on_yt_open_file_clicked
        )

        self.yt_btn_open_folder = ctk.CTkButton(
            self.yt_actions_box,
            text="📂 Mở Thư Mục",
            width=110,
            height=30,
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            command=self._on_yt_open_folder_clicked
        )

        self.yt_btn_add_to_joiner = ctk.CTkButton(
            self.yt_actions_box,
            text="➕ Thêm Vào Ghép Video",
            width=165,
            height=30,
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=self._on_yt_add_to_joiner_clicked
        )

    def _show_yt_formats_placeholder(self, message: str):
        for w in self.yt_formats_scroll.winfo_children():
            w.destroy()

        ph = ctk.CTkFrame(self.yt_formats_scroll, fg_color="transparent")
        ph.grid(row=0, column=0, pady=70, sticky="nsew")
        ph.grid_columnconfigure(0, weight=1)

        icon_ph = ctk.CTkLabel(ph, text="📥", font=ctk.CTkFont(size=50))
        icon_ph.pack(pady=(0, 8))

        lbl_text = ctk.CTkLabel(
            ph,
            text=message,
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray65"),
            justify="center"
        )
        lbl_text.pack()

    # ================= YouTube Event Handlers =================

    def _on_yt_paste_clicked(self):
        try:
            clip = self.clipboard_get().strip()
            if clip:
                self.yt_entry_url.delete(0, "end")
                self.yt_entry_url.insert(0, clip)
                self._on_yt_fetch_clicked()
        except Exception:
            messagebox.showwarning("Thông báo", "Không tìm thấy nội dung trong Clipboard.")

    def _on_yt_clear_clicked(self):
        self.yt_entry_url.delete(0, "end")
        self.yt_current_info = None
        self.yt_preview_card.grid_forget()
        self.yt_lbl_input_status.configure(
            text="Đã xóa link. Nhập link YouTube và nhấn '🔍 Lấy Link Tải'.",
            text_color=("gray40", "gray70")
        )
        self._show_yt_formats_placeholder("Chưa có link tải nào. Hãy dán link YouTube ở trên và nhấn '🔍 Lấy Link Tải'.")

    def _on_yt_fetch_clicked(self):
        if self.yt_is_fetching:
            return

        url = self.yt_entry_url.get().strip()
        if not url:
            messagebox.showwarning("Thông báo", "Vui lòng nhập hoặc dán đường link YouTube.")
            return

        self.yt_is_fetching = True
        self.yt_btn_fetch.configure(state="disabled", text="⏳ Đang lấy...")
        self.yt_btn_paste.configure(state="disabled")
        self.yt_lbl_input_status.configure(
            text="⏳ Đang phân tích video từ YouTube, vui lòng đợi trong giây lát...",
            text_color=("#1f6aa5", "#38bdf8")
        )

        for w in self.yt_formats_scroll.winfo_children():
            w.destroy()

        self._show_yt_formats_placeholder("⏳ Đang tải danh sách link download từ YouTube...")

        def fetch_worker():
            try:
                info = extract_youtube_info(url)
                self._event_queue.put(("yt_info_done", info))
            except Exception as e:
                self._event_queue.put(("yt_info_error", str(e)))

        threading.Thread(target=fetch_worker, daemon=True).start()

    def _on_yt_info_done(self, info: YouTubeVideoInfo):
        self.yt_is_fetching = False
        self.yt_btn_fetch.configure(state="normal", text="🔍 Lấy Link Tải")
        self.yt_btn_paste.configure(state="normal")
        self.yt_current_info = info

        self.yt_lbl_input_status.configure(
            text=f"✅ Đã tìm thấy {len(info.formats)} link tải cho video: {info.title[:60]}...",
            text_color=("#27ae60", "#2ecc71")
        )

        # Show preview card
        self.yt_lbl_title.configure(text=info.title)
        meta_str = f"📺 Kênh: {info.channel}   •   ⏱ Thời lượng: {info.duration_str}"
        if info.view_count_str:
            meta_str += f"   •   👁 {info.view_count_str}"
        self.yt_lbl_meta.configure(text=meta_str)
        self.yt_lbl_thumb.configure(image=None, text="🎬")

        # Load thumbnail asynchronously
        if info.thumbnail_url:
            def load_thumb():
                try:
                    resp = requests.get(info.thumbnail_url, timeout=5)
                    if resp.status_code == 200:
                        pil_img = Image.open(io.BytesIO(resp.content))
                        pil_img.thumbnail((200, 112))
                        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
                        self.after(0, lambda: self.yt_lbl_thumb.configure(image=ctk_img, text=""))
                except Exception:
                    pass
            threading.Thread(target=load_thumb, daemon=True).start()

        self.yt_preview_card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))

        # Render formats
        self._render_yt_formats()

    def _on_yt_info_error(self, err_msg: str):
        self.yt_is_fetching = False
        self.yt_btn_fetch.configure(state="normal", text="🔍 Lấy Link Tải")
        self.yt_btn_paste.configure(state="normal")
        self.yt_lbl_input_status.configure(
            text="❌ Không thể lấy thông tin video. Kiểm tra lại đường link hoặc kết nối mạng.",
            text_color=("#c0392b", "#e74c3c")
        )
        self._show_yt_formats_placeholder("Không thể lấy dữ liệu video từ link đã nhập.")
        messagebox.showerror("Lỗi YouTube", f"Không thể lấy thông tin video từ YouTube:\n\n{err_msg}")

    def _on_yt_filter_changed(self, value: str):
        self.yt_active_filter = value
        if self.yt_current_info:
            self._render_yt_formats()

    def _render_yt_formats(self):
        for w in self.yt_formats_scroll.winfo_children():
            w.destroy()

        if not self.yt_current_info or not self.yt_current_info.formats:
            self._show_yt_formats_placeholder("Không tìm thấy link tải nào cho video này.")
            return

        filter_val = self.yt_active_filter
        filtered_list = []
        for f in self.yt_current_info.formats:
            if filter_val == "Tất cả":
                filtered_list.append(f)
            elif filter_val == "Video MP4":
                if f.category in ["video_audio", "video_only"] and f.ext.lower() == "mp4":
                    filtered_list.append(f)
                elif f.category == "video_audio":
                    filtered_list.append(f)
            elif filter_val == "Chỉ Âm thanh":
                if f.category == "audio_only":
                    filtered_list.append(f)
            elif filter_val == "Luồng trực tiếp":
                if f.direct_url:
                    filtered_list.append(f)

        if not filtered_list:
            self._show_yt_formats_placeholder(f"Không có định dạng nào thuộc nhóm '{filter_val}'.")
            return

        for idx, item in enumerate(filtered_list):
            self._create_yt_format_card(idx, item)

    def _create_yt_format_card(self, idx: int, item: YouTubeFormatItem):
        card = ctk.CTkFrame(
            self.yt_formats_scroll,
            corner_radius=8,
            fg_color=("#edf2f7", "#232731") if not item.is_recommended else ("#e8f4fd", "#1a3044"),
            border_width=1 if item.is_recommended else 0,
            border_color=("#38bdf8", "#1f6aa5")
        )
        card.grid(row=idx, column=0, sticky="ew", padx=6, pady=4)
        card.grid_columnconfigure(1, weight=1)

        # 1. Badge (Left)
        badge_color = ("#1f6aa5", "#1f6aa5")
        badge_text = item.resolution
        if item.category == "audio_only":
            badge_color = ("#d35400", "#d35400")
            badge_text = "🎵 AUDIO"
        elif "2160" in item.resolution or "1440" in item.resolution:
            badge_color = ("#8e44ad", "#8e44ad")
        elif "1080" in item.resolution:
            badge_color = ("#27ae60", "#27ae60")

        badge = ctk.CTkLabel(
            card,
            text=f" {badge_text} ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=badge_color,
            text_color="white",
            corner_radius=4,
            width=75,
            height=28
        )
        badge.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)

        # 2. Main title & description
        lbl_name = ctk.CTkLabel(
            card,
            text=item.label,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        lbl_name.grid(row=0, column=1, sticky="w", pady=(8, 2))

        sub_info = f"Định dạng: {item.ext.upper()} • Dung lượng: {item.filesize_str}"
        if item.note:
            sub_info += f" • {item.note}"

        lbl_desc = ctk.CTkLabel(
            card,
            text=sub_info,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            anchor="w"
        )
        lbl_desc.grid(row=1, column=1, sticky="w", pady=(0, 8))

        # 3. Actions column (Right)
        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.grid(row=0, column=2, rowspan=2, padx=(10, 12), pady=8, sticky="e")

        if item.direct_url:
            btn_copy = ctk.CTkButton(
                actions_frame,
                text="🔗 Copy Link",
                width=90,
                height=32,
                font=ctk.CTkFont(size=11),
                fg_color=("gray80", "#2d3340"),
                hover_color=("gray70", "#3a4253"),
                text_color=("black", "white"),
                command=lambda u=item.direct_url: self._copy_direct_url_to_clipboard(u)
            )
            btn_copy.pack(side="left", padx=(0, 8))

        btn_dl = ctk.CTkButton(
            actions_frame,
            text="⬇️ Tải Về Máy",
            width=115,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=lambda it=item: self._start_yt_download(it)
        )
        btn_dl.pack(side="left")

    def _copy_direct_url_to_clipboard(self, url: str):
        self.clipboard_clear()
        self.clipboard_append(url)
        messagebox.showinfo(
            "Đã sao chép link",
            "Đã copy đường link download trực tiếp vào bộ nhớ tạm (Clipboard)!\nBạn có thể dán vào IDM hoặc trình duyệt web để tải trực tiếp."
        )

    def _on_yt_open_browser_clicked(self):
        if self.yt_current_info and self.yt_current_info.url:
            webbrowser.open(self.yt_current_info.url)

    def _start_yt_download(self, item: YouTubeFormatItem):
        if self.yt_is_downloading:
            messagebox.showwarning("Thông báo", "Một tiến trình tải video khác đang chạy. Vui lòng đợi hoàn tất hoặc dừng tải.")
            return

        if not self.yt_current_info:
            return

        clean_title = sanitize_filename(self.yt_current_info.title)
        if not clean_title:
            clean_title = "youtube_download"
        default_file = f"{clean_title}_{item.resolution}.{item.ext}"

        # Choose destination
        default_dir = os.path.expanduser("~/Downloads")
        if not os.path.isdir(default_dir):
            default_dir = os.getcwd()

        filetypes = [
            (f"{item.ext.upper()} (*.{item.ext})", f"*.{item.ext}"),
            ("Tất cả tập tin", "*.*")
        ]

        save_path = filedialog.asksaveasfilename(
            title=f"Chọn nơi lưu file ({item.label})",
            initialdir=default_dir,
            initialfile=default_file,
            defaultextension=f".{item.ext}",
            filetypes=filetypes
        )
        if not save_path:
            return

        self.yt_is_downloading = True
        self.yt_cancel_event = threading.Event()
        self.yt_downloaded_file = None

        # Display download card
        self.yt_dl_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.yt_lbl_dl_title.configure(
            text=f"Đang tải: {os.path.basename(save_path)} ({item.resolution})",
            text_color=("black", "white")
        )
        self.yt_progress_bar.set(0.0)
        self.yt_lbl_dl_details.configure(text="Đang kết nối tới máy chủ YouTube...")
        self.yt_btn_cancel_dl.configure(state="normal")

        # Hide completion action buttons initially
        self.yt_btn_open_file.pack_forget()
        self.yt_btn_open_folder.pack_forget()
        self.yt_btn_add_to_joiner.pack_forget()

        def dl_worker():
            try:
                final_file = download_youtube_video(
                    url=self.yt_current_info.url,
                    format_selector=item.format_selector,
                    output_filepath=save_path,
                    progress_callback=lambda p: self._event_queue.put(("yt_progress", p)),
                    cancel_event=self.yt_cancel_event
                )
                self._event_queue.put(("yt_complete", final_file))
            except DownloadCancelledException:
                self._event_queue.put(("yt_cancelled", None))
            except Exception as e:
                self._event_queue.put(("yt_error", str(e)))

        threading.Thread(target=dl_worker, daemon=True).start()

    def _on_yt_download_progress(self, p: dict):
        if not self.yt_is_downloading:
            return

        status = p.get('status')
        if status == 'downloading':
            pct = p.get('percent', 0.0)
            self.yt_progress_bar.set(pct / 100.0)
            
            dl_b = yt_format_bytes(p.get('downloaded_bytes'))
            tot_b = yt_format_bytes(p.get('total_bytes'))
            spd = p.get('speed_str', '')
            eta = p.get('eta_str', '')
            
            self.yt_lbl_dl_details.configure(
                text=f"{pct:.1f}% • Đã tải: {dl_b} / {tot_b} • Tốc độ: {spd} • Còn lại: {eta}"
            )
        elif status == 'processing':
            self.yt_progress_bar.set(0.99)
            self.yt_lbl_dl_details.configure(text=p.get('message', 'Đang xử lý xuất file...'))

    def _on_yt_download_complete(self, final_path: str):
        self.yt_is_downloading = False
        self.yt_downloaded_file = final_path
        self.yt_progress_bar.set(1.0)

        fname = os.path.basename(final_path)
        self.yt_lbl_dl_title.configure(
            text=f"🎉 TẢI THÀNH CÔNG: {fname}",
            text_color=("#27ae60", "#2ecc71")
        )
        self.yt_lbl_dl_details.configure(text=f"Đã lưu tại: {final_path}")
        self.yt_btn_cancel_dl.configure(state="disabled")

        # Show completion action buttons
        self.yt_btn_open_file.pack(side="left", padx=(0, 6))
        self.yt_btn_open_folder.pack(side="left", padx=(0, 6))
        self.yt_btn_add_to_joiner.pack(side="left", padx=(0, 6))

        # Ask to play video
        ans = messagebox.askyesno(
            "Tải YouTube Thành Công!",
            f"Đã tải video/âm thanh thành công:\n\n{final_path}\n\nBạn có muốn mở xem ngay không?"
        )
        if ans:
            self._on_yt_open_file_clicked()

    def _on_yt_download_cancelled(self):
        self.yt_is_downloading = False
        self.yt_lbl_dl_title.configure(text="⏹ Đã hủy tiến trình tải về.", text_color=("#c0392b", "#e74c3c"))
        self.yt_lbl_dl_details.configure(text="File tạm đã được dọn dẹp.")
        self.yt_btn_cancel_dl.configure(state="disabled")

    def _on_yt_download_error(self, err_msg: str):
        self.yt_is_downloading = False
        self.yt_lbl_dl_title.configure(text="❌ Lỗi khi tải video!", text_color=("#c0392b", "#e74c3c"))
        self.yt_lbl_dl_details.configure(text=err_msg[:80] + "...")
        self.yt_btn_cancel_dl.configure(state="disabled")
        messagebox.showerror("Lỗi tải YouTube", f"Không thể tải video:\n\n{err_msg}")

    def _on_yt_cancel_download_clicked(self):
        if self.yt_cancel_event and not self.yt_cancel_event.is_set():
            if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn hủy quá trình tải YouTube không?"):
                self.yt_cancel_event.set()
                self.yt_lbl_dl_details.configure(text="Đang dừng và hủy tiến trình...")

    def _on_yt_open_file_clicked(self):
        if self.yt_downloaded_file and os.path.exists(self.yt_downloaded_file):
            try:
                os.startfile(os.path.abspath(self.yt_downloaded_file))
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể mở file: {e}")
        else:
            messagebox.showwarning("Thông báo", "File video không tồn tại.")

    def _on_yt_open_folder_clicked(self):
        if self.yt_downloaded_file:
            abs_p = os.path.abspath(self.yt_downloaded_file)
            if os.path.exists(abs_p):
                import subprocess
                subprocess.run(f'explorer /select,"{abs_p}"', shell=True)
            else:
                fdir = os.path.dirname(abs_p)
                if os.path.isdir(fdir):
                    os.startfile(fdir)

    def _on_yt_add_to_joiner_clicked(self):
        if not self.yt_downloaded_file or not os.path.exists(self.yt_downloaded_file):
            messagebox.showwarning("Thông báo", "File video không tồn tại.")
            return

        # Switch to joiner view
        self._switch_view("joiner")
        # Add to joiner
        self._add_files_by_paths([self.yt_downloaded_file])
        messagebox.showinfo(
            "Thành công",
            f"Đã thêm video vừa tải vào danh sách ghép video:\n{os.path.basename(self.yt_downloaded_file)}"
        )

    # ================= Video Item Management =================

    def _on_add_files_clicked(self):
        filetypes = [
            ("Tập tin Video", "*.mp4 *.mkv *.mov *.avi *.flv *.webm *.ts *.m4v *.wmv *.m2ts"),
            ("Tất cả tập tin", "*.*")
        ]
        files = filedialog.askopenfilenames(
            title="Chọn các video cần nối",
            filetypes=filetypes
        )
        if files:
            self._add_files_by_paths(list(files))

    def _on_add_folder_clicked(self):
        folder = filedialog.askdirectory(title="Chọn thư mục chứa video")
        if not folder:
            return
        video_paths = []
        for root, _, filenames in os.walk(folder):
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    video_paths.append(os.path.join(root, fn))
        if video_paths:
            self._add_files_by_paths(video_paths)
        else:
            messagebox.showinfo("Thông báo", "Không tìm thấy file video nào trong thư mục đã chọn.")

    def _add_files_by_paths(self, file_paths: List[str]):
        valid_paths = []
        for p in file_paths:
            p = os.path.normpath(p.strip())
            if os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    valid_paths.append(p)

        if not valid_paths:
            return

        self.lbl_status.configure(text=f"Đang đọc thông tin {len(valid_paths)} video...")
        self.update_idletasks()

        def probe_worker():
            new_infos = []
            for path in valid_paths:
                try:
                    info = probe_video(path, self.temp_dir)
                    new_infos.append(info)
                except Exception as e:
                    print(f"Lỗi đọc file {path}: {e}")

            self._event_queue.put(("probe_done", new_infos))

        threading.Thread(target=probe_worker, daemon=True).start()

    def _on_probed_done(self, new_infos: List[VideoInfo]):
        for info in new_infos:
            self.video_list.append(info)

        if not self.output_file_path and self.video_list:
            first_dir = os.path.dirname(self.video_list[0].file_path)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            suggested = os.path.join(first_dir, f"video_da_noi_{ts}.mp4")
            self.output_file_path = suggested
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, suggested)

        self._refresh_video_list_ui()
        self.lbl_status.configure(text=f"Đã nạp {len(self.video_list)} video vào danh sách.")

    def _on_clear_all_clicked(self):
        if not self.video_list:
            return
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn xóa toàn bộ danh sách video không?"):
            self.video_list.clear()
            self._refresh_video_list_ui()
            self.lbl_status.configure(text="Đã xóa toàn bộ video khỏi danh sách.")

    def _on_move_up_selected(self):
        if self.video_list and len(self.video_list) > 1:
            self._move_video(len(self.video_list) - 1, -1)

    def _on_move_down_selected(self):
        if self.video_list and len(self.video_list) > 1:
            self._move_video(0, 1)

    def _move_video(self, index: int, direction: int):
        target_idx = index + direction
        if 0 <= target_idx < len(self.video_list):
            self.video_list[index], self.video_list[target_idx] = (
                self.video_list[target_idx],
                self.video_list[index],
            )
            self._refresh_video_list_ui()

    def _remove_video(self, index: int):
        if 0 <= index < len(self.video_list):
            del self.video_list[index]
            self._refresh_video_list_ui()

    def _on_audio_track_changed(self, video_idx: int, selected_str: str):
        if video_idx >= len(self.video_list):
            return
        video = self.video_list[video_idx]
        if selected_str.startswith("🔇"):
            video.selected_audio_idx = -1
        else:
            for idx, track in enumerate(video.audio_tracks):
                if track.display_label == selected_str:
                    video.selected_audio_idx = idx
                    break

    def _refresh_video_list_ui(self):
        for widget in self.scroll_list.winfo_children():
            widget.destroy()

        if not self.video_list:
            self.empty_placeholder = ctk.CTkFrame(self.scroll_list, fg_color="transparent")
            self.empty_placeholder.grid(row=0, column=0, pady=80, sticky="nsew")
            self.empty_placeholder.grid_columnconfigure(0, weight=1)

            icon_ph = ctk.CTkLabel(self.empty_placeholder, text="🎞️", font=ctk.CTkFont(size=56))
            icon_ph.pack(pady=(0, 10))

            text_ph1 = ctk.CTkLabel(
                self.empty_placeholder,
                text="Kéo & Thả các file video vào đây",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            text_ph1.pack(pady=(0, 4))

            text_ph2 = ctk.CTkLabel(
                self.empty_placeholder,
                text="Hỗ trợ MP4, MKV, AVI, MOV, WEBM, FLV, TS và nhiều định dạng khác.\nSau khi thêm, bạn có thể xem chi tiết thời lượng, độ phân giải và chọn Audio Track để nối.",
                font=ctk.CTkFont(size=13),
                text_color=("gray40", "gray65"),
                justify="center"
            )
            text_ph2.pack()

            self.lbl_summary.configure(text="Chưa chọn video nào.")
            self.btn_start.configure(state="disabled")
            return

        self.btn_start.configure(state="normal")

        total_sec = sum(v.duration for v in self.video_list)
        total_size = sum(v.filesize for v in self.video_list)
        self.lbl_summary.configure(
            text=f"📊 {len(self.video_list)} video | Tổng: {format_seconds(total_sec)} | {format_bytes(total_size)}"
        )

        for i, video in enumerate(self.video_list):
            card = self._create_video_card(i, video)
            card.grid(row=i, column=0, sticky="ew", padx=6, pady=4)

    def _create_video_card(self, index: int, video: VideoInfo) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self.scroll_list,
            corner_radius=8,
            fg_color=("white", "#232731"),
            border_width=1,
            border_color=("gray80", "#323744")
        )
        card.grid_columnconfigure(2, weight=1)

        # 1. Index & Reorder Column (Left)
        left_col = ctk.CTkFrame(card, fg_color="transparent", width=45)
        left_col.grid(row=0, column=0, rowspan=2, padx=(10, 6), pady=8, sticky="ns")

        idx_badge = ctk.CTkLabel(
            left_col,
            text=f"#{index + 1}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#3498db"
        )
        idx_badge.pack(pady=(4, 2))

        btn_up = ctk.CTkButton(
            left_col,
            text="▲",
            width=28,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color=("gray85", "#2b2f38"),
            hover_color=("gray75", "#3a3f4b"),
            text_color=("black", "white"),
            command=lambda idx=index: self._move_video(idx, -1)
        )
        if index == 0:
            btn_up.configure(state="disabled")
        btn_up.pack(pady=2)

        btn_down = ctk.CTkButton(
            left_col,
            text="▼",
            width=28,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color=("gray85", "#2b2f38"),
            hover_color=("gray75", "#3a3f4b"),
            text_color=("black", "white"),
            command=lambda idx=index: self._move_video(idx, 1)
        )
        if index == len(self.video_list) - 1:
            btn_down.configure(state="disabled")
        btn_down.pack(pady=2)

        # 2. Thumbnail Column
        thumb_frame = ctk.CTkFrame(card, fg_color=("gray90", "#181a20"), width=120, height=68, corner_radius=6)
        thumb_frame.grid(row=0, column=1, rowspan=2, padx=(4, 12), pady=8)
        thumb_frame.pack_propagate(False)

        ctk_img = None
        if video.thumbnail_path and os.path.exists(video.thumbnail_path):
            try:
                if video.thumbnail_path not in self._thumb_cache:
                    pil_img = Image.open(video.thumbnail_path)
                    self._thumb_cache[video.thumbnail_path] = ctk.CTkImage(
                        light_image=pil_img,
                        dark_image=pil_img,
                        size=(120, 68)
                    )
                ctk_img = self._thumb_cache[video.thumbnail_path]
            except Exception:
                ctk_img = None

        if ctk_img:
            lbl_img = ctk.CTkLabel(thumb_frame, text="", image=ctk_img)
            lbl_img.pack(expand=True, fill="both")
        else:
            lbl_no_img = ctk.CTkLabel(thumb_frame, text="🎬", font=ctk.CTkFont(size=28))
            lbl_no_img.pack(expand=True, fill="both")

        # 3. Main Info Column
        main_col = ctk.CTkFrame(card, fg_color="transparent")
        main_col.grid(row=0, column=2, sticky="nsew", padx=(0, 10), pady=(8, 4))
        main_col.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(main_col, fg_color="transparent")
        title_row.pack(fill="x", pady=(0, 3))

        lbl_fname = ctk.CTkLabel(
            title_row,
            text=video.filename,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        lbl_fname.pack(side="left")

        badges_row = ctk.CTkFrame(main_col, fg_color="transparent")
        badges_row.pack(fill="x", pady=(0, 6))

        badges_info = [
            f"⏱️ {video.duration_str}",
            f"📐 {video.resolution_str} ({video.fps} fps)",
            f"📦 {video.filesize_str}",
            f"🎞️ {video.codec.upper()}"
        ]

        for b_text in badges_info:
            b_label = ctk.CTkLabel(
                badges_row,
                text=f" {b_text} ",
                font=ctk.CTkFont(size=11),
                fg_color=("gray90", "#181a20"),
                corner_radius=4
            )
            b_label.pack(side="left", padx=(0, 6))

        # Audio Track Selection Area
        audio_frame = ctk.CTkFrame(main_col, fg_color="transparent")
        audio_frame.pack(fill="x", pady=(2, 4))

        if video.has_multiple_audio:
            badge_multi = ctk.CTkLabel(
                audio_frame,
                text=" 🔥 Đa Audio Track: ",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#e67e22",
                text_color="white",
                corner_radius=4
            )
            badge_multi.pack(side="left", padx=(0, 6))

            audio_options = [t.display_label for t in video.audio_tracks]
            audio_options.append("🔇 Tắt âm thanh (Mute)")

            current_val = (
                video.audio_tracks[video.selected_audio_idx].display_label
                if 0 <= video.selected_audio_idx < len(video.audio_tracks)
                else "🔇 Tắt âm thanh (Mute)"
            )

            cbo_audio = ctk.CTkOptionMenu(
                audio_frame,
                values=audio_options,
                font=ctk.CTkFont(size=12),
                height=26,
                width=340,
                command=lambda val, idx=index: self._on_audio_track_changed(idx, val)
            )
            cbo_audio.set(current_val)
            cbo_audio.pack(side="left")

        elif len(video.audio_tracks) == 1:
            track = video.audio_tracks[0]
            track_label = ctk.CTkLabel(
                audio_frame,
                text=f"🎵 Âm thanh: {track.display_label}",
                font=ctk.CTkFont(size=11),
                fg_color=("gray90", "#181a20"),
                corner_radius=4
            )
            track_label.pack(side="left", padx=(0, 6))

            mute_var = ctk.BooleanVar(value=(video.selected_audio_idx == -1))
            def on_mute_toggle(idx=index, var=mute_var):
                self.video_list[idx].selected_audio_idx = -1 if var.get() else 0

            chk_mute = ctk.CTkCheckBox(
                audio_frame,
                text="Tắt tiếng",
                font=ctk.CTkFont(size=11),
                variable=mute_var,
                checkbox_width=18,
                checkbox_height=18,
                command=on_mute_toggle
            )
            chk_mute.pack(side="left", padx=(6, 0))

        else:
            no_audio_label = ctk.CTkLabel(
                audio_frame,
                text="🔇 Không có âm thanh (Sẽ tự động chèn khoảng lặng khi nối)",
                font=ctk.CTkFont(size=11),
                fg_color=("gray90", "#2c1d1d"),
                text_color=("#c0392b", "#e74c3c"),
                corner_radius=4
            )
            no_audio_label.pack(side="left")

        # 4. Delete Action Column (Right)
        right_col = ctk.CTkFrame(card, fg_color="transparent")
        right_col.grid(row=0, column=3, rowspan=2, padx=(0, 10), pady=8, sticky="ns")

        btn_del = ctk.CTkButton(
            right_col,
            text="❌",
            width=32,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            hover_color=("#f2dede", "#5c1d1d"),
            text_color=("#c0392b", "#e74c3c"),
            command=lambda idx=index: self._remove_video(idx)
        )
        btn_del.pack(expand=True)

        return card

    # ================= Destination and Export =================

    def _on_browse_output_clicked(self):
        initial_dir = ""
        initial_file = "video_da_noi.mp4"
        if self.output_file_path:
            initial_dir = os.path.dirname(self.output_file_path)
            initial_file = os.path.basename(self.output_file_path)
        elif self.video_list:
            initial_dir = os.path.dirname(self.video_list[0].file_path)

        path = filedialog.asksaveasfilename(
            title="Chọn nơi lưu file MP4 kết quả",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=".mp4",
            filetypes=[("Video MP4 (*.mp4)", "*.mp4")]
        )
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self.output_file_path = path
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, path)

    def _on_start_merge_clicked(self):
        if not self.video_list:
            messagebox.showwarning("Thông báo", "Vui lòng chọn ít nhất 1 video để nối.")
            return

        out_path = self.entry_output.get().strip()
        if not out_path:
            messagebox.showwarning("Thông báo", "Vui lòng chọn nơi lưu file kết quả.")
            return

        if not out_path.lower().endswith(".mp4"):
            out_path += ".mp4"
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, out_path)

        self.output_file_path = out_path

        is_fast_mode = "Siêu Tốc" in self.seg_mode.get()
        chosen_encoder = "auto"
        if not is_fast_mode:
            chosen_encoder = self.merger.gpu_encoder if "GPU" in self.cbo_encoder.get() else "libx264"

        speed_map = {
            "Siêu tốc (Ultrafast)": "ultrafast",
            "Rất nhanh (Veryfast)": "veryfast",
            "Cân bằng (Fast)": "fast",
        }
        cfg = MergeConfig(
            mode="fast" if is_fast_mode else "encode",
            encoder=chosen_encoder,
            resolution_mode=self.cbo_res.get(),
            fps_mode=self.cbo_fps.get(),
            speed_preset=speed_map.get(self.cbo_speed.get(), "ultrafast")
        )

        self.is_merging = True
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.btn_play_result.configure(state="disabled")
        self.btn_open_folder.configure(state="disabled")
        self.btn_add_files.configure(state="disabled")
        self.btn_add_folder.configure(state="disabled")
        self.btn_clear_all.configure(state="disabled")

        self.prog_bar.set(0.0)
        self.lbl_status.configure(text="Đang chuẩn bị tiến trình nối video...")
        self.lbl_time_detail.configure(text="")
        self.log_textbox.delete("1.0", "end")

        self.merger.merge_async(
            videos=self.video_list,
            output_path=self.output_file_path,
            config=cfg,
            on_progress=lambda *args: self._event_queue.put(("progress", args)),
            on_log=lambda line: self._event_queue.put(("log", line)),
            on_complete=lambda path: self._event_queue.put(("complete", path)),
            on_error=lambda err: self._event_queue.put(("error", err))
        )

    def _on_cancel_merge_clicked(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn hủy quá trình nối video?"):
            self.merger.cancel()
            self.lbl_status.configure(text="Đang hủy tiến trình...")

    def _update_progress_ui(self, pct: float, cur_sec: float, total_sec: float, speed: str, fps: str):
        self.prog_bar.set(pct / 100.0)
        speed_str = f" • Tốc độ: {speed}" if speed else ""
        fps_str = f" • FPS: {fps}" if fps else ""
        self.lbl_status.configure(text=f"Đang xử lý: {pct:.1f}%{speed_str}{fps_str}")
        self.lbl_time_detail.configure(
            text=f"Thời gian: {format_seconds(cur_sec)} / {format_seconds(total_sec)}"
        )

    def _append_log(self, line: str):
        self.log_textbox.insert("end", line + "\n")
        self.log_textbox.see("end")

    def _finish_merge_success(self, output_path: str):
        self.is_merging = False
        self.prog_bar.set(1.0)
        self.lbl_status.configure(text="🎉 Đã nối video thành công 100%!")
        self.lbl_time_detail.configure(text="")

        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.btn_play_result.configure(state="normal")
        self.btn_open_folder.configure(state="normal")
        self.btn_add_files.configure(state="normal")
        self.btn_add_folder.configure(state="normal")
        self.btn_clear_all.configure(state="normal")

        answer = messagebox.askyesno(
            "Hoàn tất nối video!",
            f"Video đã được ghép nối thành công vào định dạng MP4:\n\n{output_path}\n\nBạn có muốn mở xem ngay không?"
        )
        if answer:
            self._on_play_result_clicked()

    def _finish_merge_error(self, err_msg: str):
        self.is_merging = False
        self.lbl_status.configure(text="❌ Xảy ra lỗi khi nối video!")
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.btn_add_files.configure(state="normal")
        self.btn_add_folder.configure(state="normal")
        self.btn_clear_all.configure(state="normal")
        messagebox.showerror("Lỗi ghép video", f"Không thể hoàn thành ghép video:\n{err_msg}")

    def _on_play_result_clicked(self):
        if self.output_file_path and os.path.exists(self.output_file_path):
            try:
                os.startfile(os.path.abspath(self.output_file_path))
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể mở video: {e}")
        else:
            messagebox.showwarning("Thông báo", "File kết quả chưa được tạo.")

    def _on_open_folder_clicked(self):
        if self.output_file_path:
            abs_path = os.path.abspath(self.output_file_path)
            if os.path.exists(abs_path):
                import subprocess
                subprocess.run(f'explorer /select,"{abs_path}"', shell=True)
            else:
                folder = os.path.dirname(abs_path)
                if os.path.exists(folder):
                    os.startfile(folder)
                else:
                    messagebox.showwarning("Thông báo", "Thư mục không tồn tại.")

    def _on_close(self):
        if self.is_merging:
            if not messagebox.askyesno("Đang nối video", "Tiến trình nối video đang chạy. Bạn có chắc muốn thoát?"):
                return
            self.merger.cancel()

        if self.yt_is_downloading:
            if not messagebox.askyesno("Đang tải YouTube", "Tiến trình tải video YouTube đang chạy. Bạn có chắc muốn thoát?"):
                return
            if self.yt_cancel_event:
                self.yt_cancel_event.set()

        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

        self.destroy()


def run_app():
    app = VideoJoinerApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
