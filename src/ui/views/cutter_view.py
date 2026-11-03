"""
Video Cutter View (Cắt & Rút Gọn Video Siêu Tốc Xuất MP4).
"""
import os
import queue
import threading
from datetime import datetime
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
from typing import Callable, Optional

from src.core.video_meta import VideoInfo, probe_video
from src.core.video_cutter import VideoCutter, VideoFrameExtractor
from src.utils.formatters import parse_time_str, format_time_hms


class CutterView(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        on_request_add_to_merger: Optional[Callable[[str], None]] = None,
        temp_dir: Optional[str] = None,
        **kwargs
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_request_add_to_merger = on_request_add_to_merger
        self.temp_dir = temp_dir

        self.cutter = VideoCutter()
        self.cut_extractor = VideoFrameExtractor()
        self.is_cutting = False
        self.cut_input_video: Optional[VideoInfo] = None
        self.cut_output_file_path = ""
        self.cut_start_sec: float = 0.0
        self.cut_end_sec: float = 0.0
        self.cut_selected_audio_idx: int = 0
        self.cut_current_preview_img: Optional[ctk.CTkImage] = None

        # Preview worker thread and queue
        self._preview_req_queue = queue.Queue()
        self._preview_stop_event = threading.Event()
        self._preview_thread = threading.Thread(target=self._preview_worker, daemon=True)
        self._preview_thread.start()

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_top_file_selector()
        self._build_workspace()

    def _preview_worker(self):
        """Background worker extracting video frames on slider scrub."""
        while not self._preview_stop_event.is_set():
            try:
                req = self._preview_req_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if req is None:
                break
            sec, label_info = req

            # Drain quickly to most recent scrub position
            while not self._preview_req_queue.empty():
                try:
                    sec, label_info = self._preview_req_queue.get_nowait()
                except queue.Empty:
                    break

            img = self.cut_extractor.get_frame(sec, target_w=640, target_h=360)
            if img:
                self.after(0, lambda im=img, s=sec, l=label_info: self._on_preview_frame_ready(im, s, l))

    def _on_preview_frame_ready(self, img: Image.Image, sec: float, label_info: str):
        self.cut_current_preview_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        self.cut_lbl_screen.configure(image=self.cut_current_preview_img, text="")
        has_sub = (sec % 1 != 0)
        self.cut_lbl_screen_timestamp.configure(
            text=f"{label_info}: {format_time_hms(sec, has_sub)}"
        )

    # ================= UI BUILDERS =================

    def _build_top_file_selector(self):
        top_card = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray88", "#232731"))
        top_card.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 8))
        top_card.grid_columnconfigure(1, weight=1)

        lbl_cut_title = ctk.CTkLabel(
            top_card,
            text="✂️ CẮT & RÚT GỌN VIDEO (XUẤT ĐỊNH DẠNG MP4 CHUẨN)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1f6aa5", "#38bdf8")
        )
        lbl_cut_title.grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(10, 4))

        lbl_file = ctk.CTkLabel(
            top_card,
            text="File video nguồn:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_file.grid(row=1, column=0, padx=(16, 8), pady=(0, 8), sticky="w")

        self.cut_entry_file = ctk.CTkEntry(
            top_card,
            placeholder_text="Chọn video cần cắt hoặc kéo thả file video vào đây (Hỗ trợ MP4, MKV, AVI, MOV, WEBM...)",
            height=36,
            font=ctk.CTkFont(size=13)
        )
        self.cut_entry_file.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 8))

        self.cut_btn_browse_input = ctk.CTkButton(
            top_card,
            text="📁 Chọn Video...",
            width=130,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._on_cut_browse_input_clicked
        )
        self.cut_btn_browse_input.grid(row=1, column=2, padx=(0, 8), pady=(0, 8))

        self.cut_btn_clear = ctk.CTkButton(
            top_card,
            text="🧹 Xóa",
            width=70,
            height=36,
            fg_color=("gray75", "#2b2f38"),
            hover_color=("#c0392b", "#962d22"),
            text_color=("black", "white"),
            command=self._on_cut_clear_clicked
        )
        self.cut_btn_clear.grid(row=1, column=3, padx=(0, 16), pady=(0, 8))

    def _build_workspace(self):
        work_frame = ctk.CTkFrame(self, fg_color="transparent")
        work_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        work_frame.grid_rowconfigure(0, weight=1)
        work_frame.grid_columnconfigure(0, weight=6)
        work_frame.grid_columnconfigure(1, weight=5)

        # LEFT COLUMN: PREVIEW SCREEN
        preview_container = ctk.CTkFrame(work_frame, corner_radius=10, fg_color=("gray90", "#181a20"))
        preview_container.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        preview_container.grid_rowconfigure(1, weight=1)
        preview_container.grid_columnconfigure(0, weight=1)

        top_preview_bar = ctk.CTkFrame(preview_container, fg_color="transparent")
        top_preview_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 6))
        top_preview_bar.grid_columnconfigure(0, weight=1)

        lbl_screen_title = ctk.CTkLabel(
            top_preview_bar,
            text="🎬 KHUNG HÌNH XEM TRƯỚC (LIVE PREVIEW):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_screen_title.grid(row=0, column=0, sticky="w")

        self.cut_lbl_screen_timestamp = ctk.CTkLabel(
            top_preview_bar,
            text="📍 Chưa nạp video",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#1f6aa5", "#1f6aa5"),
            text_color="white",
            corner_radius=6,
            padx=10,
            pady=3
        )
        self.cut_lbl_screen_timestamp.grid(row=0, column=1, sticky="e")

        self.cut_screen_frame = ctk.CTkFrame(
            preview_container,
            corner_radius=8,
            fg_color="#090a0f",
            border_width=1,
            border_color=("gray75", "#282c37"),
            height=340
        )
        self.cut_screen_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.cut_screen_frame.pack_propagate(False)

        self.cut_lbl_screen = ctk.CTkLabel(
            self.cut_screen_frame,
            text="🎞️ Chưa chọn video nào\n\nHãy bấm '📁 Chọn Video...' ở trên hoặc kéo thả file video vào đây.\nKhung hình sẽ tự động hiển thị trực tiếp theo thanh kéo!",
            font=ctk.CTkFont(size=14),
            text_color=("gray40", "gray65"),
            justify="center"
        )
        self.cut_lbl_screen.pack(expand=True, fill="both")

        screen_btn_bar = ctk.CTkFrame(preview_container, fg_color="transparent")
        screen_btn_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))
        screen_btn_bar.grid_columnconfigure(3, weight=1)

        self.cut_btn_view_start = ctk.CTkButton(
            screen_btn_bar,
            text="📍 Xem Mốc Bắt Đầu",
            width=150,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#1f6aa5", "#144870"),
            command=self._preview_start_marker
        )
        self.cut_btn_view_start.grid(row=0, column=0, padx=(0, 6))

        self.cut_btn_view_end = ctk.CTkButton(
            screen_btn_bar,
            text="📍 Xem Mốc Kết Thúc",
            width=150,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            command=self._preview_end_marker
        )
        self.cut_btn_view_end.grid(row=0, column=1, padx=(0, 6))

        self.cut_btn_preview_orig = ctk.CTkButton(
            screen_btn_bar,
            text="▶️ Phát Video Gốc",
            width=140,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            command=self._on_cut_preview_original_clicked
        )
        self.cut_btn_preview_orig.grid(row=0, column=2, padx=(0, 6))

        meta_chips_frame = ctk.CTkFrame(preview_container, fg_color=("gray95", "#12141a"), corner_radius=6)
        meta_chips_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))

        self.cut_lbl_meta_summary = ctk.CTkLabel(
            meta_chips_frame,
            text="Chưa có thông tin video",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70")
        )
        self.cut_lbl_meta_summary.pack(padx=12, pady=6)

        # RIGHT COLUMN: CONTROLS
        controls_scroll = ctk.CTkScrollableFrame(work_frame, corner_radius=10, fg_color=("gray90", "#1e2129"))
        controls_scroll.grid(row=0, column=1, sticky="nsew", padx=(0, 0), pady=0)
        controls_scroll.grid_columnconfigure(0, weight=1)

        # Time range card
        time_card = ctk.CTkFrame(controls_scroll, corner_radius=8, fg_color=("gray88", "#232731"))
        time_card.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 8))
        time_card.grid_columnconfigure(0, weight=1)

        lbl_range_title = ctk.CTkLabel(
            time_card,
            text="⏱️ THIẾT LẬP THỜI ĐIỂM CẮT VIDEO:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_range_title.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        start_row_top = ctk.CTkFrame(time_card, fg_color="transparent")
        start_row_top.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 2))
        start_row_top.grid_columnconfigure(0, weight=1)

        lbl_s_title = ctk.CTkLabel(start_row_top, text="Bắt đầu (Start):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_s_title.grid(row=0, column=0, sticky="w")

        self.cut_entry_start = ctk.CTkEntry(start_row_top, width=105, height=30, font=ctk.CTkFont(size=13, weight="bold"))
        self.cut_entry_start.insert(0, "00:00:00.0")
        self.cut_entry_start.grid(row=0, column=1, padx=(0, 6))
        self.cut_entry_start.bind("<FocusOut>", self._on_cut_entry_start_changed)
        self.cut_entry_start.bind("<Return>", self._on_cut_entry_start_changed)

        btn_s_reset = ctk.CTkButton(start_row_top, text="00:00:00", width=65, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._set_cut_start(0.0))
        btn_s_reset.grid(row=0, column=2, padx=(0, 3))

        btn_s_m5 = ctk.CTkButton(start_row_top, text="-5s", width=38, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._adjust_cut_start(-5.0))
        btn_s_m5.grid(row=0, column=3, padx=(0, 2))

        btn_s_m1 = ctk.CTkButton(start_row_top, text="-1s", width=38, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._adjust_cut_start(-1.0))
        btn_s_m1.grid(row=0, column=4, padx=(0, 2))

        btn_s_p1 = ctk.CTkButton(start_row_top, text="+1s", width=38, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._adjust_cut_start(1.0))
        btn_s_p1.grid(row=0, column=5, padx=(0, 2))

        btn_s_p5 = ctk.CTkButton(start_row_top, text="+5s", width=38, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._adjust_cut_start(5.0))
        btn_s_p5.grid(row=0, column=6)

        self.cut_slider_start = ctk.CTkSlider(
            time_card,
            from_=0.0,
            to=100.0,
            number_of_steps=1000,
            command=self._on_cut_slider_start_moved,
            height=16
        )
        self.cut_slider_start.set(0.0)
        self.cut_slider_start.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))

        end_row_top = ctk.CTkFrame(time_card, fg_color="transparent")
        end_row_top.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 2))
        end_row_top.grid_columnconfigure(0, weight=1)

        lbl_e_title = ctk.CTkLabel(end_row_top, text="Kết thúc (End):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_e_title.grid(row=0, column=0, sticky="w")

        self.cut_entry_end = ctk.CTkEntry(end_row_top, width=105, height=30, font=ctk.CTkFont(size=13, weight="bold"))
        self.cut_entry_end.insert(0, "00:00:00.0")
        self.cut_entry_end.grid(row=0, column=1, padx=(0, 6))
        self.cut_entry_end.bind("<FocusOut>", self._on_cut_entry_end_changed)
        self.cut_entry_end.bind("<Return>", self._on_cut_entry_end_changed)

        btn_e_end = ctk.CTkButton(end_row_top, text="Cuối Video", width=65, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=self._set_cut_end_to_max)
        btn_e_end.grid(row=0, column=2, padx=(0, 3))

        btn_e_m5 = ctk.CTkButton(end_row_top, text="-5s", width=38, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._adjust_cut_end(-5.0))
        btn_e_m5.grid(row=0, column=3, padx=(0, 2))

        btn_e_m1 = ctk.CTkButton(end_row_top, text="-1s", width=38, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._adjust_cut_end(-1.0))
        btn_e_m1.grid(row=0, column=4, padx=(0, 2))

        btn_e_p1 = ctk.CTkButton(end_row_top, text="+1s", width=38, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._adjust_cut_end(1.0))
        btn_e_p1.grid(row=0, column=5, padx=(0, 2))

        btn_e_p5 = ctk.CTkButton(end_row_top, text="+5s", width=38, height=26, fg_color=("gray80", "#2d3340"), text_color=("black", "white"), command=lambda: self._adjust_cut_end(5.0))
        btn_e_p5.grid(row=0, column=6)

        self.cut_slider_end = ctk.CTkSlider(
            time_card,
            from_=0.0,
            to=100.0,
            number_of_steps=1000,
            command=self._on_cut_slider_end_moved,
            height=16
        )
        self.cut_slider_end.set(100.0)
        self.cut_slider_end.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 8))

        summary_banner = ctk.CTkFrame(time_card, fg_color=("gray95", "#181a20"), corner_radius=6)
        summary_banner.grid(row=5, column=0, sticky="ew", padx=12, pady=(2, 10))

        self.cut_lbl_duration_summary = ctk.CTkLabel(
            summary_banner,
            text="📊 Đoạn cắt dài: 00:00:00 • Từ 00:00:00 đến 00:00:00",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#1f6aa5", "#38bdf8")
        )
        self.cut_lbl_duration_summary.pack(padx=10, pady=6)

        # Audio & mode card
        settings_card = ctk.CTkFrame(controls_scroll, corner_radius=8, fg_color=("gray88", "#232731"))
        settings_card.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        settings_card.grid_columnconfigure(1, weight=1)

        lbl_audio_title = ctk.CTkLabel(settings_card, text="Âm thanh:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_audio_title.grid(row=0, column=0, sticky="w", padx=(12, 6), pady=(10, 4))

        self.cut_audio_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        self.cut_audio_row.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(10, 4))

        lbl_cut_out = ctk.CTkLabel(settings_card, text="Lưu file MP4:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_cut_out.grid(row=1, column=0, sticky="w", padx=(12, 6), pady=(4, 6))

        self.cut_entry_output = ctk.CTkEntry(
            settings_card,
            placeholder_text="Chọn nơi lưu file sau khi cắt (luôn là .mp4)...",
            height=32,
            font=ctk.CTkFont(size=12)
        )
        self.cut_entry_output.grid(row=1, column=1, sticky="ew", padx=(0, 6), pady=(4, 6))

        self.cut_btn_browse_out = ctk.CTkButton(
            settings_card,
            text="📁 Nơi Lưu...",
            width=90,
            height=32,
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=self._on_cut_browse_output_clicked
        )
        self.cut_btn_browse_out.grid(row=1, column=2, padx=(0, 12), pady=(4, 6))

        lbl_cut_mode = ctk.CTkLabel(settings_card, text="Chế độ cắt:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_cut_mode.grid(row=2, column=0, sticky="w", padx=(12, 6), pady=(4, 4))

        self.cut_seg_mode = ctk.CTkSegmentedButton(
            settings_card,
            values=[
                "⚡ Cắt Siêu Tốc (Stream Copy)",
                "🎯 Mã Hóa Chuẩn Hóa"
            ],
            command=self._on_cut_mode_changed,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.cut_seg_mode.set("⚡ Cắt Siêu Tốc (Stream Copy)")
        self.cut_seg_mode.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(4, 4))

        self.cut_lbl_mode_hint = ctk.CTkLabel(
            settings_card,
            text="✨ Cắt cực nhanh 1 - 2s, giữ nguyên 100% độ sắc nét gốc không nén lại.",
            font=ctk.CTkFont(size=11),
            text_color=("#27ae60", "#2ecc71")
        )
        self.cut_lbl_mode_hint.grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))

        # Action & Progress Card
        action_card = ctk.CTkFrame(controls_scroll, corner_radius=8, fg_color=("gray88", "#232731"))
        action_card.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 8))
        action_card.grid_columnconfigure(0, weight=1)

        self.cut_progress_bar = ctk.CTkProgressBar(action_card, height=10, corner_radius=5)
        self.cut_progress_bar.set(0.0)
        self.cut_progress_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        self.cut_lbl_status = ctk.CTkLabel(
            action_card,
            text="Sẵn sàng cắt video.",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.cut_lbl_status.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))

        primary_btn_row = ctk.CTkFrame(action_card, fg_color="transparent")
        primary_btn_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 6))
        primary_btn_row.grid_columnconfigure(0, weight=1)

        self.cut_btn_start = ctk.CTkButton(
            primary_btn_row,
            text="✂️ BẮT ĐẦU CẮT VIDEO",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2980b9",
            hover_color="#1f618d",
            height=38,
            command=self._on_start_cut_clicked
        )
        self.cut_btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.cut_btn_cancel = ctk.CTkButton(
            primary_btn_row,
            text="⏹ Hủy",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#c0392b",
            hover_color="#922b21",
            height=38,
            width=80,
            state="disabled",
            command=self._on_cancel_cut_clicked
        )
        self.cut_btn_cancel.grid(row=0, column=1)

        secondary_btn_row = ctk.CTkFrame(action_card, fg_color="transparent")
        secondary_btn_row.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))

        self.cut_btn_play_result = ctk.CTkButton(
            secondary_btn_row,
            text="▶ Xem Kết Quả",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#27ae60",
            hover_color="#1e8449",
            height=32,
            width=115,
            state="disabled",
            command=self._on_cut_play_result_clicked
        )
        self.cut_btn_play_result.pack(side="left", padx=(0, 4))

        self.cut_btn_open_folder = ctk.CTkButton(
            secondary_btn_row,
            text="📂 Thư Mục",
            font=ctk.CTkFont(size=12),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            height=32,
            width=90,
            state="disabled",
            command=self._on_cut_open_folder_clicked
        )
        self.cut_btn_open_folder.pack(side="left", padx=(0, 4))

        self.cut_btn_add_to_joiner = ctk.CTkButton(
            secondary_btn_row,
            text="➕ Đưa Vào Ghép Video",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#8e44ad",
            hover_color="#732d91",
            height=32,
            state="disabled",
            command=self._on_cut_add_to_joiner_clicked
        )
        self.cut_btn_add_to_joiner.pack(side="left", fill="x", expand=True)

    # ================= LOGIC & ACTIONS =================

    def load_video(self, file_path: str):
        file_path = os.path.normpath(file_path.strip())
        if not os.path.isfile(file_path):
            messagebox.showwarning("Thông báo", f"Tập tin không tồn tại: {file_path}")
            return

        self.cut_entry_file.delete(0, "end")
        self.cut_entry_file.insert(0, file_path)
        self.cut_lbl_status.configure(text=f"Đang đọc thông tin video: {os.path.basename(file_path)}...")

        def probe_worker():
            try:
                info = probe_video(file_path, self.temp_dir)
                self.after(0, lambda: self._on_cut_probe_done(info))
            except Exception as e:
                self.after(0, lambda err=e: self._on_cut_probe_error(str(err)))

        threading.Thread(target=probe_worker, daemon=True).start()

    def _preview_start_marker(self):
        self.cut_btn_view_start.configure(fg_color=("#1f6aa5", "#144870"))
        self.cut_btn_view_end.configure(fg_color=("gray75", "#2b2f38"))
        self._preview_req_queue.put((self.cut_start_sec, "📍 Mốc Bắt Đầu"))

    def _preview_end_marker(self):
        self.cut_btn_view_end.configure(fg_color=("#1f6aa5", "#144870"))
        self.cut_btn_view_start.configure(fg_color=("gray75", "#2b2f38"))
        self._preview_req_queue.put((self.cut_end_sec, "📍 Mốc Kết Thúc"))

    def _on_cut_probe_done(self, info: VideoInfo):
        self.cut_input_video = info
        self.cut_start_sec = 0.0
        self.cut_end_sec = max(0.5, info.duration)
        self.cut_selected_audio_idx = 0

        self.cut_extractor.set_video(info.file_path)
        self._preview_start_marker()

        self.cut_lbl_meta_summary.configure(
            text=f"📁 {info.filename}  •  ⏱️ {info.duration_str}  •  📐 {info.resolution_str} ({info.fps} fps)  •  📦 {info.filesize_str}  •  🎞️ {info.codec.upper()}"
        )

        for w in self.cut_audio_row.winfo_children():
            w.destroy()

        if info.has_multiple_audio:
            opts = [t.display_label for t in info.audio_tracks]
            opts.append("🔇 Tắt âm thanh (Mute)")

            def on_audio_select(val):
                if val.startswith("🔇"):
                    self.cut_selected_audio_idx = -1
                else:
                    for idx, t in enumerate(info.audio_tracks):
                        if t.display_label == val:
                            self.cut_selected_audio_idx = idx
                            break

            cbo = ctk.CTkOptionMenu(
                self.cut_audio_row,
                values=opts,
                font=ctk.CTkFont(size=11),
                height=26,
                width=260,
                command=on_audio_select
            )
            cbo.set(info.audio_tracks[0].display_label)
            cbo.pack(side="left")
        elif len(info.audio_tracks) == 1:
            lbl_a = ctk.CTkLabel(
                self.cut_audio_row,
                text=f"{info.audio_tracks[0].display_label}",
                font=ctk.CTkFont(size=11),
                fg_color=("gray85", "#14161b"),
                corner_radius=4
            )
            lbl_a.pack(side="left", padx=(0, 6))

            mute_var = ctk.BooleanVar(value=False)
            chk = ctk.CTkCheckBox(
                self.cut_audio_row,
                text="Tắt tiếng",
                font=ctk.CTkFont(size=11),
                variable=mute_var,
                command=lambda: setattr(self, 'cut_selected_audio_idx', -1 if mute_var.get() else 0),
                width=20
            )
            chk.pack(side="left")
        else:
            self.cut_selected_audio_idx = -1
            lbl_a = ctk.CTkLabel(
                self.cut_audio_row,
                text="🔇 Video không có tiếng",
                font=ctk.CTkFont(size=11),
                fg_color=("gray85", "#14161b"),
                corner_radius=4
            )
            lbl_a.pack(side="left")

        duration = max(0.5, info.duration)
        self.cut_slider_start.configure(from_=0.0, to=duration)
        self.cut_slider_start.set(0.0)

        self.cut_slider_end.configure(from_=0.0, to=duration)
        self.cut_slider_end.set(duration)

        self.cut_entry_start.delete(0, "end")
        self.cut_entry_start.insert(0, "00:00:00.0")

        self.cut_entry_end.delete(0, "end")
        self.cut_entry_end.insert(0, format_time_hms(duration, True))

        orig_dir = os.path.dirname(info.file_path)
        base_no_ext = os.path.splitext(info.filename)[0]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested_out = os.path.join(orig_dir, f"{base_no_ext}_cut_{ts}.mp4")
        self.cut_entry_output.delete(0, "end")
        self.cut_entry_output.insert(0, suggested_out)
        self.cut_output_file_path = suggested_out

        self._update_cut_summary()
        self.cut_lbl_status.configure(text=f"Đã nạp video: {info.filename}")

    def _on_cut_probe_error(self, err_msg: str):
        self.cut_lbl_status.configure(text="❌ Lỗi khi đọc file video.")
        messagebox.showerror("Lỗi đọc video", f"Không thể phân tích video này:\n{err_msg}")

    def _update_cut_summary(self):
        duration = max(0.0, self.cut_end_sec - self.cut_start_sec)
        has_sub = (self.cut_start_sec % 1 != 0) or (self.cut_end_sec % 1 != 0) or (duration % 1 != 0)
        s_str = format_time_hms(self.cut_start_sec, has_sub)
        e_str = format_time_hms(self.cut_end_sec, has_sub)
        dur_str = format_time_hms(duration, has_sub)

        self.cut_lbl_duration_summary.configure(
            text=f"📊 Đoạn cắt dài: {dur_str}  (Từ {s_str}  đến  {e_str})"
        )

    def _on_cut_slider_start_moved(self, val: float):
        if val >= self.cut_end_sec:
            val = max(0.0, self.cut_end_sec - 0.2)
            self.cut_slider_start.set(val)
        self.cut_start_sec = val
        self.cut_entry_start.delete(0, "end")
        self.cut_entry_start.insert(0, format_time_hms(val, True))
        self._update_cut_summary()
        self.cut_btn_view_start.configure(fg_color=("#1f6aa5", "#144870"))
        self.cut_btn_view_end.configure(fg_color=("gray75", "#2b2f38"))
        self._preview_req_queue.put((val, "📍 Mốc Bắt Đầu"))

    def _on_cut_slider_end_moved(self, val: float):
        max_dur = self.cut_input_video.duration if self.cut_input_video else 100.0
        if val <= self.cut_start_sec:
            val = min(max_dur, self.cut_start_sec + 0.2)
            self.cut_slider_end.set(val)
        self.cut_end_sec = val
        self.cut_entry_end.delete(0, "end")
        self.cut_entry_end.insert(0, format_time_hms(val, True))
        self._update_cut_summary()
        self.cut_btn_view_end.configure(fg_color=("#1f6aa5", "#144870"))
        self.cut_btn_view_start.configure(fg_color=("gray75", "#2b2f38"))
        self._preview_req_queue.put((val, "📍 Mốc Kết Thúc"))

    def _on_cut_entry_start_changed(self, event=None):
        val = parse_time_str(self.cut_entry_start.get())
        max_limit = self.cut_end_sec - 0.2 if self.cut_end_sec > 0.2 else 0.0
        val = max(0.0, min(max_limit, val))
        self.cut_start_sec = val
        self.cut_slider_start.set(val)
        self.cut_entry_start.delete(0, "end")
        self.cut_entry_start.insert(0, format_time_hms(val, True))
        self._update_cut_summary()
        self._preview_start_marker()

    def _on_cut_entry_end_changed(self, event=None):
        val = parse_time_str(self.cut_entry_end.get())
        max_dur = self.cut_input_video.duration if self.cut_input_video else 3600.0
        val = max(self.cut_start_sec + 0.2, min(max_dur, val))
        self.cut_end_sec = val
        self.cut_slider_end.set(val)
        self.cut_entry_end.delete(0, "end")
        self.cut_entry_end.insert(0, format_time_hms(val, True))
        self._update_cut_summary()
        self._preview_end_marker()

    def _set_cut_start(self, val: float):
        self.cut_start_sec = val
        self.cut_slider_start.set(val)
        self.cut_entry_start.delete(0, "end")
        self.cut_entry_start.insert(0, format_time_hms(val, True))
        self._update_cut_summary()
        self._preview_start_marker()

    def _set_cut_end_to_max(self):
        if self.cut_input_video:
            max_d = self.cut_input_video.duration
            self.cut_end_sec = max_d
            self.cut_slider_end.set(max_d)
            self.cut_entry_end.delete(0, "end")
            self.cut_entry_end.insert(0, format_time_hms(max_d, True))
            self._update_cut_summary()
            self._preview_end_marker()

    def _adjust_cut_start(self, delta: float):
        new_val = max(0.0, min(self.cut_end_sec - 0.2, self.cut_start_sec + delta))
        self._set_cut_start(new_val)

    def _adjust_cut_end(self, delta: float):
        max_d = self.cut_input_video.duration if self.cut_input_video else 3600.0
        new_val = min(max_d, max(self.cut_start_sec + 0.2, self.cut_end_sec + delta))
        self.cut_end_sec = new_val
        self.cut_slider_end.set(new_val)
        self.cut_entry_end.delete(0, "end")
        self.cut_entry_end.insert(0, format_time_hms(new_val, True))
        self._update_cut_summary()
        self._preview_end_marker()

    def _on_cut_mode_changed(self, mode_str: str):
        if "Siêu Tốc" in mode_str:
            self.cut_lbl_mode_hint.configure(
                text="✨ Cắt cực nhanh 1 - 2s, giữ nguyên 100% độ sắc nét gốc không nén lại.",
                text_color=("#27ae60", "#2ecc71")
            )
        else:
            self.cut_lbl_mode_hint.configure(
                text="🎯 Cắt chuẩn xác từng khung hình millisecond (Mã hóa chuẩn H.264 + AAC MP4).",
                text_color=("#38bdf8", "#1f6aa5")
            )

    def _on_cut_browse_input_clicked(self):
        filetypes = [
            ("Tập tin Video", "*.mp4 *.mkv *.mov *.avi *.flv *.webm *.ts *.m4v *.wmv *.m2ts"),
            ("Tất cả tập tin", "*.*")
        ]
        chosen = filedialog.askopenfilename(title="Chọn video cần cắt", filetypes=filetypes)
        if chosen:
            self.load_video(chosen)

    def _on_cut_browse_output_clicked(self):
        initial_dir = ""
        initial_file = "video_cat.mp4"
        current_out = self.cut_entry_output.get().strip()
        if current_out:
            initial_dir = os.path.dirname(current_out)
            initial_file = os.path.basename(current_out)
        elif self.cut_input_video:
            initial_dir = os.path.dirname(self.cut_input_video.file_path)

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
            self.cut_output_file_path = path
            self.cut_entry_output.delete(0, "end")
            self.cut_entry_output.insert(0, path)

    def _on_cut_clear_clicked(self):
        self.cut_input_video = None
        self.cut_extractor.close()
        self.cut_entry_file.delete(0, "end")
        self.cut_entry_output.delete(0, "end")
        self.cut_lbl_screen.configure(image=None, text="🎞️ Chưa chọn video nào\n\nHãy bấm '📁 Chọn Video...' ở trên hoặc kéo thả file video vào đây.\nKhung hình sẽ tự động hiển thị trực tiếp theo thanh kéo!")
        self.cut_lbl_screen_timestamp.configure(text="📍 Chưa nạp video")
        self.cut_lbl_meta_summary.configure(text="Chưa có thông tin video")
        self.cut_slider_start.set(0.0)
        self.cut_slider_end.set(100.0)
        self.cut_entry_start.delete(0, "end")
        self.cut_entry_start.insert(0, "00:00:00.0")
        self.cut_entry_end.delete(0, "end")
        self.cut_entry_end.insert(0, "00:00:00.0")
        self.cut_lbl_duration_summary.configure(text="📊 Độ dài đoạn cắt: 00:00:00 • Từ 00:00:00 đến 00:00:00")
        self.cut_lbl_status.configure(text="Sẵn sàng cắt video.")
        self.cut_progress_bar.set(0.0)
        for w in self.cut_audio_row.winfo_children():
            w.destroy()

    def _on_cut_preview_original_clicked(self):
        if self.cut_input_video and os.path.exists(self.cut_input_video.file_path):
            try:
                os.startfile(os.path.abspath(self.cut_input_video.file_path))
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể mở video gốc: {e}")

    def _on_start_cut_clicked(self):
        if not self.cut_input_video:
            messagebox.showwarning("Thông báo", "Vui lòng chọn video cần cắt.")
            return

        out_path = self.cut_entry_output.get().strip()
        if not out_path:
            messagebox.showwarning("Thông báo", "Vui lòng chọn nơi lưu file MP4 kết quả.")
            return

        if not out_path.lower().endswith(".mp4"):
            out_path += ".mp4"
            self.cut_entry_output.delete(0, "end")
            self.cut_entry_output.insert(0, out_path)

        if self.cut_end_sec <= self.cut_start_sec:
            messagebox.showwarning("Thông báo", "Thời điểm kết thúc phải lớn hơn thời điểm bắt đầu.")
            return

        self.cut_output_file_path = out_path
        self.is_cutting = True

        self.cut_btn_start.configure(state="disabled")
        self.cut_btn_cancel.configure(state="normal")
        self.cut_btn_play_result.configure(state="disabled")
        self.cut_btn_open_folder.configure(state="disabled")
        self.cut_btn_add_to_joiner.configure(state="disabled")

        self.cut_progress_bar.set(0.0)
        self.cut_lbl_status.configure(text="Đang bắt đầu tiến trình cắt video...")

        is_fast = "Siêu Tốc" in self.cut_seg_mode.get()
        mode_val = "fast" if is_fast else "encode"

        self.cutter.cut_video_async(
            input_path=self.cut_input_video.file_path,
            output_path=self.cut_output_file_path,
            start_sec=self.cut_start_sec,
            end_sec=self.cut_end_sec,
            mode=mode_val,
            selected_audio_idx=self.cut_selected_audio_idx,
            on_progress=lambda pct, msg: self.after(0, lambda: self._on_cut_progress(pct, msg)),
            on_complete=lambda path: self.after(0, lambda: self._on_cut_complete(path)),
            on_error=lambda err: self.after(0, lambda: self._on_cut_error(err))
        )

    def _on_cancel_cut_clicked(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn hủy quá trình cắt video?"):
            self.cutter.cancel()
            self.cut_lbl_status.configure(text="Đang hủy tiến trình cắt...")

    def _on_cut_progress(self, pct: float, msg: str):
        self.cut_progress_bar.set(pct / 100.0)
        self.cut_lbl_status.configure(text=msg)

    def _on_cut_complete(self, output_path: str):
        self.is_cutting = False
        self.cut_progress_bar.set(1.0)
        self.cut_lbl_status.configure(text="🎉 Cắt video thành công 100%! Đã xuất file MP4 hoàn chỉnh.")

        self.cut_btn_start.configure(state="normal")
        self.cut_btn_cancel.configure(state="disabled")
        self.cut_btn_play_result.configure(state="normal")
        self.cut_btn_open_folder.configure(state="normal")
        self.cut_btn_add_to_joiner.configure(state="normal")

        ans = messagebox.askyesno(
            "Cắt Video Thành Công!",
            f"Đã xuất file video MP4 sau khi cắt thành công:\n{output_path}\n\nBạn có muốn phát xem ngay bây giờ không?"
        )
        if ans:
            self._on_cut_play_result_clicked()

    def _on_cut_error(self, err_msg: str):
        self.is_cutting = False
        self.cut_btn_start.configure(state="normal")
        self.cut_btn_cancel.configure(state="disabled")
        self.cut_lbl_status.configure(text="❌ Quá trình cắt video gặp sự cố.")
        messagebox.showerror("Lỗi cắt video", f"Đã có lỗi xảy ra khi cắt:\n{err_msg}")

    def _on_cut_play_result_clicked(self):
        if self.cut_output_file_path and os.path.exists(self.cut_output_file_path):
            try:
                os.startfile(os.path.abspath(self.cut_output_file_path))
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể mở video kết quả: {e}")

    def _on_cut_open_folder_clicked(self):
        if self.cut_output_file_path and os.path.exists(self.cut_output_file_path):
            try:
                d = os.path.dirname(os.path.abspath(self.cut_output_file_path))
                os.startfile(d)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể mở thư mục: {e}")

    def _on_cut_add_to_joiner_clicked(self):
        if self.cut_output_file_path and os.path.isfile(self.cut_output_file_path):
            if self.on_request_add_to_merger:
                self.on_request_add_to_merger(self.cut_output_file_path)

    def cleanup(self):
        self._preview_stop_event.set()
        self._preview_req_queue.put(None)
        if self.cut_extractor:
            self.cut_extractor.close()
        if self.cutter and self.cutter.current_process:
            self.cutter.cancel()

