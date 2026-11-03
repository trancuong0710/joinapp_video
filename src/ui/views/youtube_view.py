"""
YouTube Downloader View (Tải Video, Âm Thanh & Phụ Đề Từ YouTube).
"""
import io
import os
import threading
import webbrowser
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
import requests
from typing import Callable, Optional

from src.core.youtube import (
    YouTubeFormatItem,
    YouTubeSubtitleItem,
    YouTubeVideoInfo,
    DownloadCancelledException,
    extract_youtube_info,
    download_youtube_video,
    download_youtube_subtitle,
    download_and_convert_en_to_vi_subtitle,
)
from src.ui.components.format_card import FormatCard
from src.ui.components.subtitle_card import SubtitleCard
from src.utils.formatters import format_bytes
from src.utils.file_helpers import sanitize_filename, find_default_cookie_file


class YouTubeView(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        on_request_cut: Optional[Callable[[str], None]] = None,
        on_request_add_to_merger: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_request_cut = on_request_cut
        self.on_request_add_to_merger = on_request_add_to_merger

        self.yt_current_info: Optional[YouTubeVideoInfo] = None
        self.yt_is_fetching: bool = False
        self.yt_is_downloading: bool = False
        self.yt_cancel_event: Optional[threading.Event] = None
        self.yt_downloaded_file: Optional[str] = None
        self.yt_active_filter: str = "Tất cả"
        self.yt_cookie_file: str = find_default_cookie_file() or ""

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_input_card()
        self._build_preview_card()
        self._build_formats_container()
        self._build_download_card()

    # ================= UI BUILDERS =================

    def _build_input_card(self):
        input_card = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray88", "#232731"))
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
            text="Sẵn sàng: Nhập link YouTube và nhấn '🔍 Lấy Link Tải' để hiển thị các định dạng video, âm thanh & phụ đề.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
            anchor="w"
        )
        self.yt_lbl_input_status.grid(row=2, column=0, columnspan=5, sticky="w", padx=16, pady=(0, 6))

        # Cookie bar
        cookie_frame = ctk.CTkFrame(input_card, fg_color=("gray95", "#1c1f26"), corner_radius=6)
        cookie_frame.grid(row=3, column=0, columnspan=5, sticky="ew", padx=16, pady=(0, 10))
        cookie_frame.grid_columnconfigure(0, weight=1)

        default_cookie_text = "🍪 Cookie: Chưa nạp (Chế độ khách ẩn danh)"
        if self.yt_cookie_file and os.path.isfile(self.yt_cookie_file):
            default_cookie_text = f"🍪 Cookie: {os.path.basename(self.yt_cookie_file)} (Đã kích hoạt)"

        self.yt_lbl_cookie_status = ctk.CTkLabel(
            cookie_frame,
            text=default_cookie_text,
            font=ctk.CTkFont(size=11),
            text_color=("#27ae60", "#2ecc71") if self.yt_cookie_file else ("gray50", "gray70"),
            anchor="w"
        )
        self.yt_lbl_cookie_status.grid(row=0, column=0, sticky="w", padx=10, pady=4)

        cookie_btn_box = ctk.CTkFrame(cookie_frame, fg_color="transparent")
        cookie_btn_box.grid(row=0, column=1, sticky="e", padx=6, pady=4)

        self.yt_btn_load_cookie = ctk.CTkButton(
            cookie_btn_box,
            text="🍪 Nạp File cookies.txt",
            width=135,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("#1f6aa5", "#2980b9"),
            hover_color=("#144870", "#1f618d"),
            command=self._on_yt_load_cookie_clicked
        )
        self.yt_btn_load_cookie.pack(side="left", padx=2)

        self.yt_btn_clear_cookie = ctk.CTkButton(
            cookie_btn_box,
            text="❌ Bỏ Cookie",
            width=80,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("#c0392b", "#962d22"),
            text_color=("black", "white"),
            command=self._on_yt_clear_cookie_clicked
        )
        if self.yt_cookie_file:
            self.yt_btn_clear_cookie.pack(side="left", padx=2)

        self.yt_btn_cookie_help = ctk.CTkButton(
            cookie_btn_box,
            text="❓ Cách lấy Cookie",
            width=120,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#2b2f38"),
            hover_color=("gray65", "#3a3f4b"),
            text_color=("black", "white"),
            command=self._on_yt_cookie_help_clicked
        )
        self.yt_btn_cookie_help.pack(side="left", padx=2)

    def _build_preview_card(self):
        self.yt_preview_card = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#1e2129"))
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

    def _build_formats_container(self):
        formats_outer = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#1e2129"))
        formats_outer.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 8))
        formats_outer.grid_rowconfigure(1, weight=1)
        formats_outer.grid_columnconfigure(0, weight=1)

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
            values=["Tất cả", "Video MP4", "Chỉ Âm thanh", "Phụ đề (Subtitles)", "Luồng trực tiếp"],
            command=self._on_yt_filter_changed,
            height=28,
            font=ctk.CTkFont(size=12)
        )
        self.yt_filter_seg.set("Tất cả")
        self.yt_filter_seg.grid(row=0, column=1, sticky="e")

        self.yt_formats_scroll = ctk.CTkScrollableFrame(
            formats_outer,
            fg_color="transparent",
            corner_radius=8
        )
        self.yt_formats_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.yt_formats_scroll.grid_columnconfigure(0, weight=1)

        self._show_yt_formats_placeholder("Chưa có link tải nào. Hãy dán link YouTube ở trên và nhấn '🔍 Lấy Link Tải'.")

    def _build_download_card(self):
        self.yt_dl_card = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray88", "#232731"))
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

        self.yt_btn_cut_this_video = ctk.CTkButton(
            self.yt_actions_box,
            text="✂️ Cắt Video Này",
            width=130,
            height=30,
            fg_color=("#d35400", "#b94600"),
            hover_color=("#a03d00", "#873400"),
            command=self._on_yt_cut_this_video_clicked
        )

        self.yt_btn_add_to_joiner = ctk.CTkButton(
            self.yt_actions_box,
            text="➕ Đưa Vào Ghép Video",
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

    # ================= LOGIC & ACTIONS =================

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

    def _on_yt_load_cookie_clicked(self):
        chosen = filedialog.askopenfilename(
            title="Chọn file cookies.txt",
            filetypes=[("Text files (*.txt)", "*.txt"), ("Tất cả tập tin", "*.*")]
        )
        if chosen:
            self.yt_cookie_file = chosen
            self.yt_lbl_cookie_status.configure(
                text=f"🍪 Cookie: {os.path.basename(chosen)} (Đã kích hoạt - sẵn sàng tải)",
                text_color=("#27ae60", "#2ecc71")
            )
            self.yt_btn_clear_cookie.pack(side="left", padx=2, before=self.yt_btn_cookie_help)
            messagebox.showinfo(
                "Đã Nạp Cookie Thành Công",
                f"Đã liên kết file cookie:\n{chosen}\n\nBây giờ bạn có thể lấy link và tải các video YouTube bị yêu cầu xác minh bot một cách dễ dàng!"
            )

    def _on_yt_clear_cookie_clicked(self):
        self.yt_cookie_file = ""
        self.yt_lbl_cookie_status.configure(
            text="🍪 Cookie: Chưa nạp (Chế độ khách ẩn danh)",
            text_color=("gray50", "gray70")
        )
        self.yt_btn_clear_cookie.pack_forget()

    def _on_yt_cookie_help_clicked(self):
        msg = (
            "📌 HƯỚNG DẪN XUẤT FILE COOKIES.TXT VƯỢT BOTGUARD YOUTUBE:\n\n"
            "Khi YouTube hiện lỗi 'Sign in to confirm you're not a bot', bạn làm theo 3 bước sau:\n\n"
            "1. Cài tiện ích mở rộng trên Chrome hoặc Edge:\n"
            "   Tìm tiện ích 'Get cookies.txt LOCALLY' hoặc 'Cookie-Editor' trên Chrome Web Store và cài đặt.\n\n"
            "2. Xuất Cookie từ YouTube:\n"
            "   Mở trang https://www.youtube.com (đã đăng nhập tài khoản của bạn) > Bấm vào biểu tượng tiện ích vừa cài > Chọn 'Export' (hoặc Download) để lưu file cookies.txt.\n\n"
            "3. Nạp vào ứng dụng:\n"
            "   Bấm nút '🍪 Nạp File cookies.txt' bên cạnh và chọn file vừa lưu (hoặc chỉ cần đặt file tên 'cookies.txt' vào cùng thư mục với phần mềm).\n\n"
            "💡 Mẹo khác: Bạn cũng có thể tạm thời tắt VPN / Cloudflare WARP hoặc chuyển sang mạng 4G từ điện thoại để đổi IP mới sạch."
        )
        messagebox.showinfo("Hướng dẫn Cookie YouTube", msg)

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
                info = extract_youtube_info(url, cookiefile=self.yt_cookie_file)
                self.after(0, lambda: self._on_yt_info_done(info))
            except Exception as e:
                self.after(0, lambda err=e: self._on_yt_info_error(str(err)))

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

        self.yt_lbl_title.configure(text=info.title)
        meta_str = f"📺 Kênh: {info.channel}   •   ⏱ Thời lượng: {info.duration_str}"
        if info.view_count_str:
            meta_str += f"   •   👁 {info.view_count_str}"
        if info.subtitles:
            sub_labels = [s.label.split('(')[0].strip() for s in info.subtitles]
            meta_str += f"\n📝 Phụ đề: {', '.join(sub_labels)}"
            if info.only_en_sub:
                meta_str += "  (✨ Hỗ trợ dịch tự động sang Tiếng Việt .srt)"
        self.yt_lbl_meta.configure(text=meta_str)
        self.yt_lbl_thumb.configure(image=None, text="🎬")

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
        self._render_yt_formats()

    def _on_yt_info_error(self, err_msg: str):
        self.yt_is_fetching = False
        self.yt_btn_fetch.configure(state="normal", text="🔍 Lấy Link Tải")
        self.yt_btn_paste.configure(state="normal")
        self.yt_lbl_input_status.configure(
            text="❌ Không thể lấy thông tin video. Kiểm tra lại đường link hoặc nạp cookies.txt.",
            text_color=("#c0392b", "#e74c3c")
        )
        self._show_yt_formats_placeholder("Không thể lấy dữ liệu video từ link đã nhập.")
        messagebox.showerror("Thông báo YouTube", err_msg)

    def _on_yt_filter_changed(self, value: str):
        self.yt_active_filter = value
        if self.yt_current_info:
            self._render_yt_formats()

    def _render_yt_formats(self):
        for w in self.yt_formats_scroll.winfo_children():
            w.destroy()

        if not self.yt_current_info:
            self._show_yt_formats_placeholder("Không tìm thấy thông tin video.")
            return

        filter_val = self.yt_active_filter
        row_counter = 0

        # Subtitle-only filter
        if filter_val == "Phụ đề (Subtitles)":
            if not self.yt_current_info.subtitles:
                self._show_yt_formats_placeholder("Video này không có phụ đề Tiếng Anh hoặc Tiếng Việt.")
                return
            for sub_item in self.yt_current_info.subtitles:
                card = SubtitleCard(
                    parent=self.yt_formats_scroll,
                    item=sub_item,
                    only_en=self.yt_current_info.only_en_sub,
                    on_download=self._start_sub_download,
                    on_translate=self._start_sub_translation
                )
                card.grid(row=row_counter, column=0, sticky="ew", padx=6, pady=4)
                row_counter += 1
            return

        if filter_val == "Tất cả" and self.yt_current_info.subtitles:
            sec_lbl = ctk.CTkLabel(
                self.yt_formats_scroll,
                text="📝 PHỤ ĐỀ VIDEO (SUBTITLES):",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("#1f6aa5", "#38bdf8"),
                anchor="w"
            )
            sec_lbl.grid(row=row_counter, column=0, sticky="w", padx=10, pady=(6, 2))
            row_counter += 1

            for sub_item in self.yt_current_info.subtitles:
                card = SubtitleCard(
                    parent=self.yt_formats_scroll,
                    item=sub_item,
                    only_en=self.yt_current_info.only_en_sub,
                    on_download=self._start_sub_download,
                    on_translate=self._start_sub_translation
                )
                card.grid(row=row_counter, column=0, sticky="ew", padx=6, pady=4)
                row_counter += 1

            fmt_lbl = ctk.CTkLabel(
                self.yt_formats_scroll,
                text="🎬 CÁC ĐỊNH DẠNG VIDEO & ÂM THANH:",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("#1f6aa5", "#38bdf8"),
                anchor="w"
            )
            fmt_lbl.grid(row=row_counter, column=0, sticky="w", padx=10, pady=(10, 2))
            row_counter += 1

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

        if not filtered_list and (filter_val != "Tất cả" or not self.yt_current_info.subtitles):
            self._show_yt_formats_placeholder(f"Không có định dạng nào thuộc nhóm '{filter_val}'.")
            return

        for item in filtered_list:
            card = FormatCard(
                parent=self.yt_formats_scroll,
                item=item,
                on_download=self._start_yt_download,
                on_copy_link=self._copy_direct_url_to_clipboard
            )
            card.grid(row=row_counter, column=0, sticky="ew", padx=6, pady=4)
            row_counter += 1

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

        self.yt_dl_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.yt_lbl_dl_title.configure(
            text=f"Đang tải: {os.path.basename(save_path)} ({item.resolution})",
            text_color=("black", "white")
        )
        self.yt_progress_bar.set(0.0)
        self.yt_lbl_dl_details.configure(text="Đang kết nối tới máy chủ YouTube...")
        self.yt_btn_cancel_dl.configure(state="normal")

        self.yt_btn_open_file.pack_forget()
        self.yt_btn_open_folder.pack_forget()
        self.yt_btn_cut_this_video.pack_forget()
        self.yt_btn_add_to_joiner.pack_forget()

        def dl_worker():
            try:
                final_file = download_youtube_video(
                    url=self.yt_current_info.url,
                    format_selector=item.format_selector,
                    output_filepath=save_path,
                    progress_callback=lambda p: self.after(0, lambda: self._on_yt_download_progress(p)),
                    cancel_event=self.yt_cancel_event,
                    cookiefile=self.yt_cookie_file
                )
                self.after(0, lambda: self._on_yt_download_complete(final_file))
            except DownloadCancelledException:
                self.after(0, self._on_yt_download_cancelled)
            except Exception as e:
                self.after(0, lambda err=e: self._on_yt_download_error(str(err)))

        threading.Thread(target=dl_worker, daemon=True).start()

    def _start_sub_download(self, item: YouTubeSubtitleItem):
        if self.yt_is_downloading:
            messagebox.showwarning("Thông báo", "Một tiến trình tải khác đang chạy. Vui lòng đợi hoàn tất.")
            return

        if not self.yt_current_info:
            return

        clean_title = sanitize_filename(self.yt_current_info.title)
        if not clean_title:
            clean_title = "youtube_subtitle"
        default_file = f"{clean_title}_{item.lang}.srt"

        default_dir = os.path.expanduser("~/Downloads")
        if not os.path.isdir(default_dir):
            default_dir = os.getcwd()

        save_path = filedialog.asksaveasfilename(
            title=f"Chọn nơi lưu phụ đề {item.label}",
            initialdir=default_dir,
            initialfile=default_file,
            defaultextension=".srt",
            filetypes=[("Phụ đề SRT (*.srt)", "*.srt")]
        )
        if not save_path:
            return

        if not save_path.lower().endswith(".srt"):
            save_path += ".srt"

        self.yt_is_downloading = True
        self.yt_downloaded_file = None

        self.yt_dl_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.yt_lbl_dl_title.configure(
            text=f"Đang tải phụ đề: {os.path.basename(save_path)} ({item.label})",
            text_color=("black", "white")
        )
        self.yt_progress_bar.set(0.2)
        self.yt_lbl_dl_details.configure(text="Đang kết nối tới máy chủ YouTube tải file phụ đề...")
        self.yt_btn_cancel_dl.configure(state="disabled")

        self.yt_btn_open_file.pack_forget()
        self.yt_btn_open_folder.pack_forget()
        self.yt_btn_cut_this_video.pack_forget()
        self.yt_btn_add_to_joiner.pack_forget()

        def sub_worker():
            try:
                final_file = download_youtube_subtitle(
                    url=self.yt_current_info.url,
                    lang_code=item.source_code,
                    is_auto=item.is_auto,
                    output_filepath=save_path,
                    cookiefile=self.yt_cookie_file
                )
                self.after(0, lambda: self._on_yt_download_complete(final_file))
            except Exception as e:
                self.after(0, lambda err=e: self._on_yt_download_error(str(err)))

        threading.Thread(target=sub_worker, daemon=True).start()

    def _start_sub_translation(self, item: YouTubeSubtitleItem):
        if self.yt_is_downloading:
            messagebox.showwarning("Thông báo", "Một tiến trình tải khác đang chạy. Vui lòng đợi hoàn tất.")
            return

        if not self.yt_current_info:
            return

        clean_title = sanitize_filename(self.yt_current_info.title)
        if not clean_title:
            clean_title = "youtube_subtitle"
        default_file = f"{clean_title}_TiengViet.srt"

        default_dir = os.path.expanduser("~/Downloads")
        if not os.path.isdir(default_dir):
            default_dir = os.getcwd()

        save_path = filedialog.asksaveasfilename(
            title="Chọn nơi lưu phụ đề Tiếng Việt đã dịch",
            initialdir=default_dir,
            initialfile=default_file,
            defaultextension=".srt",
            filetypes=[("Phụ đề SRT (*.srt)", "*.srt")]
        )
        if not save_path:
            return

        if not save_path.lower().endswith(".srt"):
            save_path += ".srt"

        self.yt_is_downloading = True
        self.yt_downloaded_file = None

        self.yt_dl_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.yt_lbl_dl_title.configure(
            text=f"Đang dịch phụ đề Tiếng Anh sang Tiếng Việt: {os.path.basename(save_path)}",
            text_color=("black", "white")
        )
        self.yt_progress_bar.set(0.05)
        self.yt_lbl_dl_details.configure(text="Đang tải phụ đề Tiếng Anh gốc từ YouTube...")
        self.yt_btn_cancel_dl.configure(state="disabled")

        self.yt_btn_open_file.pack_forget()
        self.yt_btn_open_folder.pack_forget()
        self.yt_btn_cut_this_video.pack_forget()
        self.yt_btn_add_to_joiner.pack_forget()

        def trans_worker():
            try:
                def prog(curr, total, msg):
                    self.after(0, lambda: self._on_sub_trans_progress(curr / total if total else 0.5, msg))

                final_file = download_and_convert_en_to_vi_subtitle(
                    url=self.yt_current_info.url,
                    en_lang_code=item.source_code,
                    is_auto=item.is_auto,
                    output_filepath=save_path,
                    progress_callback=prog,
                    cookiefile=self.yt_cookie_file
                )
                self.after(0, lambda: self._on_yt_download_complete(final_file))
            except Exception as e:
                self.after(0, lambda err=e: self._on_yt_download_error(str(err)))

        threading.Thread(target=trans_worker, daemon=True).start()

    def _on_sub_trans_progress(self, pct: float, msg: str):
        self.yt_progress_bar.set(pct)
        self.yt_lbl_dl_details.configure(text=msg)

    def _on_yt_download_progress(self, p: dict):
        if not self.yt_is_downloading:
            return

        status = p.get('status')
        if status == 'downloading':
            pct = p.get('percent', 0.0)
            self.yt_progress_bar.set(pct / 100.0)
            
            dl_b = format_bytes(p.get('downloaded_bytes'))
            tot_b = format_bytes(p.get('total_bytes'))
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
        is_sub = fname.lower().endswith(".srt")

        success_title = f"🎉 XUẤT PHỤ ĐỀ THÀNH CÔNG: {fname}" if is_sub else f"🎉 TẢI THÀNH CÔNG: {fname}"
        self.yt_lbl_dl_title.configure(
            text=success_title,
            text_color=("#27ae60", "#2ecc71")
        )
        self.yt_lbl_dl_details.configure(text=f"Đã lưu tại: {final_path}")
        self.yt_btn_cancel_dl.configure(state="disabled")

        self.yt_btn_open_file.configure(text="📝 Xem File .SRT" if is_sub else "▶ Mở Xem")
        self.yt_btn_open_file.pack(side="left", padx=(0, 6))
        self.yt_btn_open_folder.pack(side="left", padx=(0, 6))

        if not is_sub:
            self.yt_btn_cut_this_video.pack(side="left", padx=(0, 6))
            self.yt_btn_add_to_joiner.pack(side="left", padx=(0, 6))

        prompt_msg = (
            f"Đã tải và xuất file phụ đề .SRT thành công:\n\n{final_path}\n\nBạn có muốn mở xem nội dung phụ đề ngay không?"
            if is_sub else
            f"Đã tải video/âm thanh thành công:\n\n{final_path}\n\nBạn có muốn mở xem ngay không?"
        )
        ans = messagebox.askyesno("Tải YouTube Thành Công!", prompt_msg)
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

    def _on_yt_cut_this_video_clicked(self):
        if self.yt_downloaded_file and os.path.exists(self.yt_downloaded_file):
            if self.on_request_cut:
                self.on_request_cut(self.yt_downloaded_file)
        else:
            messagebox.showwarning("Thông báo", "File video không tồn tại.")

    def _on_yt_add_to_joiner_clicked(self):
        if not self.yt_downloaded_file or not os.path.exists(self.yt_downloaded_file):
            messagebox.showwarning("Thông báo", "File video không tồn tại.")
            return

        if self.on_request_add_to_merger:
            self.on_request_add_to_merger(self.yt_downloaded_file)
            messagebox.showinfo(
                "Thành công",
                f"Đã thêm video vừa tải vào danh sách ghép video:\n{os.path.basename(self.yt_downloaded_file)}"
            )

    def cleanup(self):
        if self.yt_cancel_event:
            self.yt_cancel_event.set()

