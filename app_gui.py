import os
import sys
import time
import shutil
import queue
import tempfile
import threading
from datetime import datetime
from typing import List, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
from PIL import Image

from video_meta import VideoInfo, probe_video, format_seconds, format_bytes
from video_merger import VideoMerger, MergeConfig

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

        # Window configuration
        self.title("Nối Video MP4 Chuyên Nghiệp - Video Joiner Pro")
        self.geometry("1100x820")
        self.minsize(920, 680)

        # Theme & Styling
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # State
        self.video_list: List[VideoInfo] = []
        self.selected_index: int = -1
        self.temp_dir = tempfile.mkdtemp(prefix="joinapp_")
        self.merger = VideoMerger()
        self.is_merging = False
        self.output_file_path = ""
        self._thumb_cache = {}
        self._event_queue = queue.Queue()

        # Build UI
        self._init_ui()

        # Setup Drag and Drop
        self._setup_dnd()

        # Start queue polling
        self._poll_event_queue()

        # Handle window close cleanup
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _poll_event_queue(self):
        try:
            while True:
                event_type, data = self._event_queue.get_nowait()
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
        # Parse dropped files (handles space in path enclosed in curly braces)
        files = self.tk.splitlist(raw_data)
        self._add_files_by_paths(list(files))

    def _init_ui(self):
        # Grid layout: 1 column, multiple rows
        self.grid_rowconfigure(2, weight=1)  # Video list expands
        self.grid_columnconfigure(0, weight=1)

        # 1. Header Frame
        self._build_header()

        # 2. Action Toolbar Frame
        self._build_toolbar()

        # 3. Central Video List Area (Scrollable)
        self._build_video_list_area()

        # 4. Output & Options Section
        self._build_output_and_options_section()

        # 5. Progress & Bottom Action Bar
        self._build_progress_and_bottom_bar()

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray85", "#181a20"))
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(1, weight=1)

        # App Logo / Title
        logo_label = ctk.CTkLabel(
            header_frame,
            text="🎬",
            font=ctk.CTkFont(size=32)
        )
        logo_label.grid(row=0, column=0, rowspan=2, padx=(20, 10), pady=12)

        title_label = ctk.CTkLabel(
            header_frame,
            text="NỐI VIDEO CHUYÊN NGHIỆP (MP4 JOINER)",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.grid(row=0, column=1, sticky="w", pady=(10, 0))

        sub_text = (
            f"Ghép nhiều video đa định dạng thành file MP4 • Hỗ trợ chọn Audio Track theo từng file\n"
            f"⚡ Tăng tốc phần cứng: {self.merger.gpu_label}"
        )
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text=sub_text,
            font=ctk.CTkFont(size=11),
            text_color=("#1f6aa5", "#38bdf8"),
            justify="left"
        )
        subtitle_label.grid(row=1, column=1, sticky="w", pady=(0, 10))

        # Appearance mode toggle switch
        self.theme_switch = ctk.CTkSwitch(
            header_frame,
            text="Giao diện Tối",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light"
        )
        self.theme_switch.select()
        self.theme_switch.grid(row=0, column=2, rowspan=2, padx=20, pady=12)

    def _toggle_theme(self):
        mode = "Dark" if self.theme_switch.get() == "Dark" else "Light"
        ctk.set_appearance_mode(mode)
        self.theme_switch.configure(text=f"Giao diện {'Tối' if mode == 'Dark' else 'Sáng'}")

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(12, 8))
        toolbar.grid_columnconfigure(5, weight=1)

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
        self.btn_move_down.grid(row=0, column=4, padx=(0, 12))

        # Video summary status label
        self.lbl_summary = ctk.CTkLabel(
            toolbar,
            text="Chưa chọn video nào. Hãy kéo thả file vào đây hoặc bấm '➕ Thêm Video'.",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray70"),
            anchor="e"
        )
        self.lbl_summary.grid(row=0, column=5, sticky="e", padx=(10, 0))

    def _build_video_list_area(self):
        # Outer frame for border and drop hint
        list_container = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#1e2129"))
        list_container.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 8))
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

    def _build_output_and_options_section(self):
        opts_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray88", "#232731"))
        opts_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))
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

        # 1. Fast mode banner inside settings_row
        self.frame_fast_info = ctk.CTkFrame(self.settings_row, fg_color=("gray95", "#181a20"), corner_radius=6)
        lbl_fast_hint = ctk.CTkLabel(
            self.frame_fast_info,
            text="✨ Tốc độ cực nhanh (100x - 300x): Bỏ qua bước nén lại video, giữ nguyên 100% độ sắc nét gốc. Quá trình nối chỉ mất vài giây!",
            font=ctk.CTkFont(size=12),
            text_color=("#27ae60", "#2ecc71")
        )
        lbl_fast_hint.pack(side="left", padx=12, pady=6)

        # 2. Re-encode options frame
        self.frame_reencode_opts = ctk.CTkFrame(self.settings_row, fg_color="transparent")

        # Encoder selection
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

        # Resolution option
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

        # Speed preset option
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

        # FPS option
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

        # Initial display
        self._on_mode_changed(self.seg_mode.get())

    def _on_mode_changed(self, mode_str: str):
        if "Siêu Tốc" in mode_str:
            self.frame_reencode_opts.pack_forget()
            self.frame_fast_info.pack(fill="x", expand=True)
        else:
            self.frame_fast_info.pack_forget()
            self.frame_reencode_opts.pack(fill="x", expand=True)

    def _build_progress_and_bottom_bar(self):
        bottom_container = ctk.CTkFrame(self, fg_color="transparent")
        bottom_container.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 14))
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

        # Collapsible FFmpeg Log box (hidden by default)
        self.log_textbox = ctk.CTkTextbox(
            bottom_container,
            height=100,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=("white", "#14161b")
        )
        # Hidden initially

        # Buttons row
        buttons_row = ctk.CTkFrame(bottom_container, fg_color="transparent")
        buttons_row.grid(row=3, column=0, sticky="ew", pady=(4, 0))

        # Main Start button
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

        # Cancel button
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

        # Play merged output button
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

        # Open containing folder button
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
        # Filter valid video files
        valid_paths = []
        for p in file_paths:
            p = os.path.normpath(p.strip())
            if os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    valid_paths.append(p)

        if not valid_paths:
            return

        # Show status
        self.lbl_status.configure(text=f"Đang đọc thông tin {len(valid_paths)} video...")
        self.update_idletasks()

        # Run probe in background thread so UI doesn't freeze
        def probe_worker():
            new_infos = []
            for path in valid_paths:
                try:
                    info = probe_video(path, self.temp_dir)
                    new_infos.append(info)
                except Exception as e:
                    print(f"Lỗi đọc file {path}: {e}")

            # Send results to thread-safe event queue
            self._event_queue.put(("probe_done", new_infos))

        threading.Thread(target=probe_worker, daemon=True).start()

    def _on_probed_done(self, new_infos: List[VideoInfo]):
        for info in new_infos:
            self.video_list.append(info)

        # Auto-suggest output path if not set
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
        # Move first video or helper
        pass

    def _on_move_down_selected(self):
        pass

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
        # Clear existing widgets inside scroll_list
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

        # Summary text
        total_sec = sum(v.duration for v in self.video_list)
        total_size = sum(v.filesize for v in self.video_list)
        self.lbl_summary.configure(
            text=f"📊 {len(self.video_list)} video | Tổng thời lượng: {format_seconds(total_sec)} | Tổng dung lượng: {format_bytes(total_size)}"
        )

        # Render each video card
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

        # File title
        title_row = ctk.CTkFrame(main_col, fg_color="transparent")
        title_row.pack(fill="x", pady=(0, 3))

        lbl_fname = ctk.CTkLabel(
            title_row,
            text=video.filename,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        lbl_fname.pack(side="left")

        # Badges row: duration, resolution, size, fps, codec
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
            # Highlight badge for multiple audio tracks
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
            # Single audio track
            track_label = ctk.CTkLabel(
                audio_frame,
                text=f"🎵 Âm thanh: {track.display_label}",
                font=ctk.CTkFont(size=11),
                fg_color=("gray90", "#181a20"),
                corner_radius=4
            )
            track_label.pack(side="left", padx=(0, 6))

            # Option to mute if desired
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
            # 0 audio tracks
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

        # Gather config
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

        # Lock UI controls
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

        # Start merge
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

        # Restore buttons
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.btn_play_result.configure(state="normal")
        self.btn_open_folder.configure(state="normal")
        self.btn_add_files.configure(state="normal")
        self.btn_add_folder.configure(state="normal")
        self.btn_clear_all.configure(state="normal")

        # Ask to play or view
        answer = messagebox.askyesno(
            "Hoàn tất nối video!",
            f"Video đã được ghép nối thành công vào định dạng MP4:\n\n{output_path}\n\nBạn có muốn mở xem ngay không?"
        )
        if answer:
            self._on_play_result_clicked()

    def _on_merge_error(self, err_msg: str):
        self.after(0, lambda: self._finish_merge_error(err_msg))

    def _finish_merge_error(self, err_msg: str):
        self.is_merging = False
        self.lbl_status.configure(text=f"❌ Xảy ra lỗi khi nối video!")
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
                # Select file in explorer
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

        # Clean temporary thumbnails
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
