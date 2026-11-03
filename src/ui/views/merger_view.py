"""
Video Merger View (Ghép Nối Video MP4 Chuyên Nghiệp).
"""
import os
import shutil
import tempfile
import threading
from tkinter import filedialog, messagebox
import customtkinter as ctk
from typing import Callable, List, Optional, Dict

from src.config.constants import SUPPORTED_VIDEO_EXTENSIONS
from src.core.video_meta import VideoInfo, probe_video
from src.core.video_merger import VideoMerger, MergeConfig
from src.ui.components.video_card import VideoCard


class MergerView(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        on_request_cut: Optional[Callable[[str], None]] = None,
        on_request_youtube: Optional[Callable[[], None]] = None,
        **kwargs
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_request_cut = on_request_cut
        self.on_request_youtube = on_request_youtube

        self.video_list: List[VideoInfo] = []
        self.temp_dir = tempfile.mkdtemp(prefix="joinapp_merger_")
        self.merger = VideoMerger()
        self.is_merging = False
        self.output_file_path = ""
        self._thumb_cache: Dict[str, ctk.CTkImage] = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_toolbar()
        self._build_video_list_area()
        self._build_output_and_options_section()
        self._build_progress_and_bottom_bar()

    # ================= UI BUILDERS =================

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 8))
        toolbar.grid_columnconfigure(7, weight=1)

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
            command=lambda: self._move_video(0, -1) if self.video_list else None
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
            command=lambda: self._move_video(len(self.video_list) - 1, 1) if self.video_list else None
        )
        self.btn_move_down.grid(row=0, column=4, padx=(0, 8))

        if self.on_request_cut:
            self.btn_open_cutter_shortcut = ctk.CTkButton(
                toolbar,
                text="✂️ Cắt Video",
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=("#d35400", "#b94600"),
                hover_color=("#a03d00", "#873400"),
                width=115,
                height=34,
                command=lambda: self.on_request_cut("")
            )
            self.btn_open_cutter_shortcut.grid(row=0, column=5, padx=(0, 8))

        if self.on_request_youtube:
            self.btn_open_yt_shortcut = ctk.CTkButton(
                toolbar,
                text="📥 Tải YouTube",
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=("#8e44ad", "#6c3483"),
                hover_color=("#732d91", "#5b2c6f"),
                width=120,
                height=34,
                command=self.on_request_youtube
            )
            self.btn_open_yt_shortcut.grid(row=0, column=6, padx=(0, 12))

        self.lbl_summary = ctk.CTkLabel(
            toolbar,
            text="Chưa chọn video nào. Hãy kéo thả file vào đây hoặc bấm '➕ Thêm Video'.",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray70"),
            anchor="e"
        )
        self.lbl_summary.grid(row=0, column=7, sticky="e", padx=(10, 0))

    def _build_video_list_area(self):
        list_container = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#1e2129"))
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

    def _build_output_and_options_section(self):
        opts_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray88", "#232731"))
        opts_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        opts_frame.grid_columnconfigure(1, weight=1)

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

        self.settings_row = ctk.CTkFrame(opts_frame, fg_color="transparent")
        self.settings_row.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))

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

    def _build_progress_and_bottom_bar(self):
        bottom_container = ctk.CTkFrame(self, fg_color="transparent")
        bottom_container.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 14))
        bottom_container.grid_columnconfigure(0, weight=1)

        self.prog_bar = ctk.CTkProgressBar(bottom_container, height=12, corner_radius=6)
        self.prog_bar.set(0.0)
        self.prog_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

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

        self.log_textbox = ctk.CTkTextbox(
            bottom_container,
            height=100,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=("white", "#14161b")
        )

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

    # ================= LOGIC & ACTIONS =================

    def _on_add_files_clicked(self):
        files = filedialog.askopenfilenames(
            title="Chọn các video để ghép",
            filetypes=[
                ("Tất cả video được hỗ trợ", "*.mp4 *.mkv *.avi *.mov *.flv *.webm *.ts *.m4v *.wmv *.3gp"),
                ("Video MP4", "*.mp4"),
                ("Tất cả định dạng", "*.*")
            ]
        )
        if files:
            self.add_files_by_paths(list(files))

    def _on_add_folder_clicked(self):
        folder = filedialog.askdirectory(title="Chọn thư mục chứa video")
        if not folder:
            return
        found_files = []
        for root_dir, _, filenames in os.walk(folder):
            for fn in filenames:
                if any(fn.lower().endswith(ext) for ext in SUPPORTED_VIDEO_EXTENSIONS):
                    found_files.append(os.path.join(root_dir, fn))
        if found_files:
            self.add_files_by_paths(found_files)
        else:
            messagebox.showinfo("Thông báo", "Không tìm thấy file video nào trong thư mục đã chọn.")

    def add_files_by_paths(self, file_paths: List[str]):
        valid_paths = [
            p for p in file_paths
            if os.path.isfile(p) and any(p.lower().endswith(ext) for ext in SUPPORTED_VIDEO_EXTENSIONS)
        ]
        if not valid_paths:
            return

        self.lbl_status.configure(text=f"Đang phân tích thông số {len(valid_paths)} video...")

        def probe_worker():
            results = []
            for p in valid_paths:
                try:
                    info = probe_video(p, temp_thumb_dir=self.temp_dir)
                    results.append(info)
                except Exception as e:
                    self.after(0, lambda err=e: self._append_log(f"Lỗi phân tích file {p}: {err}"))
            self.after(0, lambda: self._on_probed_done(results))

        threading.Thread(target=probe_worker, daemon=True).start()

    def _on_probed_done(self, new_infos: List[VideoInfo]):
        self.video_list.extend(new_infos)
        self._refresh_video_list_ui()
        self.lbl_status.configure(text=f"Đã thêm {len(new_infos)} video thành công.")

        # Suggest output path if empty
        if not self.entry_output.get().strip() and self.video_list:
            first_dir = os.path.dirname(self.video_list[0].file_path)
            suggested = os.path.join(first_dir, "Ghep_Noi_Tong_Hop.mp4")
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, suggested)

    def _on_clear_all_clicked(self):
        if not self.video_list:
            return
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn xóa tất cả video khỏi danh sách?"):
            self.video_list.clear()
            self._refresh_video_list_ui()
            self.lbl_status.configure(text="Đã xóa toàn bộ video.")

    def _move_video(self, index: int, direction: int):
        target = index + direction
        if 0 <= target < len(self.video_list):
            self.video_list[index], self.video_list[target] = self.video_list[target], self.video_list[index]
            self._refresh_video_list_ui()

    def _remove_video(self, index: int):
        if 0 <= index < len(self.video_list):
            del self.video_list[index]
            self._refresh_video_list_ui()

    def _on_audio_track_changed(self, video_idx: int, selected_str: str):
        if not (0 <= video_idx < len(self.video_list)):
            return
        video = self.video_list[video_idx]
        if "Tắt âm thanh" in selected_str:
            video.selected_audio_idx = -1
        else:
            for i, t in enumerate(video.audio_tracks):
                if t.display_label == selected_str:
                    video.selected_audio_idx = i
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

            text_ph1 = ctk.CTkLabel(self.empty_placeholder, text="Kéo & Thả các file video vào đây", font=ctk.CTkFont(size=16, weight="bold"))
            text_ph1.pack(pady=(0, 4))

            text_ph2 = ctk.CTkLabel(
                self.empty_placeholder,
                text="Hỗ trợ MP4, MKV, AVI, MOV, WEBM, FLV, TS và nhiều định dạng khác.\nSau khi thêm, bạn có thể xem chi tiết thời lượng, độ phân giải và chọn Audio Track để nối.",
                font=ctk.CTkFont(size=13),
                text_color=("gray40", "gray65"),
                justify="center"
            )
            text_ph2.pack()
            self.lbl_summary.configure(text="Chưa chọn video nào. Hãy kéo thả file vào đây hoặc bấm '➕ Thêm Video'.")
            return

        total_sec = sum(v.duration for v in self.video_list)
        from src.utils.formatters import format_seconds
        self.lbl_summary.configure(
            text=f"Đã chọn {len(self.video_list)} video  •  Tổng thời lượng: {format_seconds(total_sec)}"
        )

        for idx, video in enumerate(self.video_list):
            card = VideoCard(
                parent=self.scroll_list,
                index=idx,
                video=video,
                total_count=len(self.video_list),
                thumb_cache=self._thumb_cache,
                on_move=self._move_video,
                on_audio_track_changed=self._on_audio_track_changed,
                on_mute_toggle=lambda i, is_muted: setattr(self.video_list[i], 'selected_audio_idx', -1 if is_muted else 0),
                on_cut=self._on_cut_video_card_clicked,
                on_remove=self._remove_video
            )
            card.grid(row=idx, column=0, sticky="ew", padx=4, pady=4)

    def _on_cut_video_card_clicked(self, file_path: str):
        if self.on_request_cut:
            self.on_request_cut(file_path)

    def _on_browse_output_clicked(self):
        init_file = "Video_Noi_Tong_Hop.mp4"
        init_dir = os.path.dirname(self.video_list[0].file_path) if self.video_list else os.getcwd()
        f = filedialog.asksaveasfilename(
            title="Chọn nơi lưu file MP4 kết quả",
            initialdir=init_dir,
            initialfile=init_file,
            defaultextension=".mp4",
            filetypes=[("Video MP4 chuẩn", "*.mp4")]
        )
        if f:
            if not f.lower().endswith(".mp4"):
                f += ".mp4"
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, f)

    def _on_start_merge_clicked(self):
        if not self.video_list:
            messagebox.showwarning("Chưa có video", "Vui lòng thêm ít nhất 2 video vào danh sách để nối.")
            return

        out_path = self.entry_output.get().strip()
        if not out_path:
            self._on_browse_output_clicked()
            out_path = self.entry_output.get().strip()
            if not out_path:
                return

        if not out_path.lower().endswith(".mp4"):
            out_path += ".mp4"
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, out_path)

        self.output_file_path = out_path

        mode_val = "fast" if "Siêu Tốc" in self.seg_mode.get() else "encode"
        enc_val = "auto"
        if mode_val == "encode":
            enc_str = self.cbo_encoder.get()
            if "CPU" in enc_str:
                enc_val = "cpu"
            else:
                enc_val = "gpu"

        speed_choice = "ultrafast"
        if "Veryfast" in self.cbo_speed.get():
            speed_choice = "veryfast"
        elif "Fast" in self.cbo_speed.get():
            speed_choice = "fast"

        cfg = MergeConfig(
            mode=mode_val,
            encoder=enc_val,
            resolution_mode=self.cbo_res.get(),
            fps_mode=self.cbo_fps.get(),
            speed_preset=speed_choice
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
        self.lbl_status.configure(text="Đang bắt đầu ghép nối...")
        self.log_textbox.delete("1.0", "end")

        self.merger.merge_async(
            videos=self.video_list,
            output_path=out_path,
            config=cfg,
            on_progress=lambda pct, cur, tot, spd, fps: self.after(0, lambda: self._update_progress_ui(pct, cur, tot, spd, fps)),
            on_log=lambda l: self.after(0, lambda: self._append_log(l)),
            on_complete=lambda path: self.after(0, lambda: self._finish_merge_success(path)),
            on_error=lambda err: self.after(0, lambda: self._finish_merge_error(err))
        )

    def _on_cancel_merge_clicked(self):
        if self.is_merging:
            if messagebox.askyesno("Hủy", "Bạn có chắc chắn muốn hủy bỏ tiến trình ghép video?"):
                self.lbl_status.configure(text="Đang hủy bỏ...")
                self.merger.cancel()

    def _update_progress_ui(self, pct: float, cur_sec: float, total_sec: float, speed: str, fps: str):
        self.prog_bar.set(pct / 100.0)
        from src.utils.formatters import format_seconds
        if cur_sec > 0 and total_sec > 0:
            self.lbl_time_detail.configure(
                text=f"{format_seconds(cur_sec)} / {format_seconds(total_sec)} | Tốc độ: {speed} | {fps} FPS"
            )
        self.lbl_status.configure(text=f"Đang xử lý: {pct:.1f}%")

    def _append_log(self, line: str):
        self.log_textbox.insert("end", line + "\n")
        self.log_textbox.see("end")

    def _finish_merge_success(self, output_path: str):
        self.is_merging = False
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.btn_play_result.configure(state="normal")
        self.btn_open_folder.configure(state="normal")
        self.btn_add_files.configure(state="normal")
        self.btn_add_folder.configure(state="normal")
        self.btn_clear_all.configure(state="normal")

        self.prog_bar.set(1.0)
        self.lbl_status.configure(text="🎉 Ghép video thành công rực rỡ!")
        self.output_file_path = output_path
        messagebox.showinfo(
            "Ghép Video Hoàn Tất",
            f"Đã nối thành công {len(self.video_list)} video thành 1 file MP4 duy nhất!\n\nNơi lưu:\n{output_path}"
        )

    def _finish_merge_error(self, err_msg: str):
        self.is_merging = False
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.btn_add_files.configure(state="normal")
        self.btn_add_folder.configure(state="normal")
        self.btn_clear_all.configure(state="normal")

        self.lbl_status.configure(text="❌ Quá trình ghép gặp lỗi.")
        messagebox.showerror("Lỗi ghép video", f"Đã có lỗi xảy ra:\n{err_msg}")

    def _on_play_result_clicked(self):
        if self.output_file_path and os.path.exists(self.output_file_path):
            try:
                os.startfile(self.output_file_path)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể mở file: {e}")

    def _on_open_folder_clicked(self):
        if self.output_file_path and os.path.exists(self.output_file_path):
            try:
                subprocess_dir = os.path.dirname(os.path.abspath(self.output_file_path))
                os.startfile(subprocess_dir)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể mở thư mục: {e}")

    def cleanup(self):
        if self.merger and self.merger.is_running:
            self.merger.cancel()
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception:
                pass

