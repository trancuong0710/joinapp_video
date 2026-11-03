"""
Main Application Window for Video Toolkit Pro.
Coordinates top-level navigation, theme, Drag & Drop, and delegates to feature views.
"""
import os
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

from src.config.constants import APP_NAME, APP_SUBTITLE
from src.core.ffmpeg_env import ensure_ffmpeg_path, detect_hardware_encoder
from src.ui.views.merger_view import MergerView
from src.ui.views.cutter_view import CutterView
from src.ui.views.youtube_view import YouTubeView


class DragDropCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    """CustomTkinter window supporting native Drag and Drop."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class MainWindow(DragDropCTk):
    def __init__(self):
        super().__init__()

        # Ensure ffmpeg & ffprobe are ready
        try:
            ensure_ffmpeg_path()
        except Exception:
            pass

        # Window configuration
        self.title(f"{APP_NAME} - {APP_SUBTITLE}")
        self.geometry("1180x880")
        self.minsize(1020, 720)

        # Theme & Styling
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Detect GPU
        self.gpu_encoder, self.gpu_label = detect_hardware_encoder()

        # Active View State: "joiner", "cutter", or "youtube"
        self.current_view: str = "joiner"

        # Build UI layout
        self._init_ui()

        # Setup Drag and Drop
        self._setup_dnd()

        # Hotkeys
        self.bind("<Control-Key-1>", lambda e: self.switch_view("joiner"))
        self.bind("<Control-Key-2>", lambda e: self.switch_view("cutter"))
        self.bind("<Control-Key-3>", lambda e: self.switch_view("youtube"))
        self.bind("<Control-Key-d>", lambda e: self.switch_view("youtube"))
        self.bind("<Control-Key-x>", lambda e: self.switch_view("cutter"))

        # Window close protocol
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
        if not files:
            return

        if self.current_view == "cutter":
            self.cutter_view.load_video(files[0])
        else:
            if self.current_view != "joiner":
                self.switch_view("joiner")
            self.merger_view.add_files_by_paths(list(files))

    def _init_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Header Frame (Row 0)
        self._build_header()

        # 2. Content Container (Row 1)
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        # 3. Instantiate Feature Views
        self.merger_view = MergerView(
            parent=self.content_container,
            on_request_cut=self.on_request_cut_video,
            on_request_youtube=lambda: self.switch_view("youtube")
        )

        self.cutter_view = CutterView(
            parent=self.content_container,
            on_request_add_to_merger=self.on_request_add_to_merger,
            temp_dir=self.merger_view.temp_dir
        )

        self.youtube_view = YouTubeView(
            parent=self.content_container,
            on_request_cut=self.on_request_cut_video,
            on_request_add_to_merger=self.on_request_add_to_merger
        )

        # 4. Native Menu Bar (after views exist)
        self._build_menu_bar()

        # Show Joiner view by default
        self.switch_view("joiner")

    def _build_menu_bar(self):
        menubar = tk.Menu(self)

        # Menu Trình đơn
        menu_app = tk.Menu(menubar, tearoff=0)
        menu_app.add_command(label="🎬 Ghép Video MP4", command=lambda: self.switch_view("joiner"), accelerator="Ctrl+1")
        menu_app.add_command(label="✂️ Cắt Video MP4", command=lambda: self.switch_view("cutter"), accelerator="Ctrl+2")
        menu_app.add_command(label="📥 Tải Video YouTube", command=lambda: self.switch_view("youtube"), accelerator="Ctrl+3")
        menu_app.add_separator()
        menu_app.add_command(label="🚪 Thoát", command=self._on_close, accelerator="Alt+F4")
        menubar.add_cascade(label="Trình đơn", menu=menu_app)

        # Menu Công cụ
        menu_tools = tk.Menu(menubar, tearoff=0)
        menu_tools.add_command(label="✂️ Mở Trình Cắt Video...", command=lambda: self.switch_view("cutter"), accelerator="Ctrl+X")
        menu_tools.add_command(label="📥 Tải Video YouTube...", command=lambda: self.switch_view("youtube"), accelerator="Ctrl+D")
        menu_tools.add_separator()
        menu_tools.add_command(label="➕ Thêm Video Ghép...", command=lambda: self.merger_view._on_add_files_clicked())
        menu_tools.add_command(label="📂 Thêm Thư Mục...", command=lambda: self.merger_view._on_add_folder_clicked())
        menu_tools.add_command(label="🧹 Xóa danh sách video ghép", command=lambda: self.merger_view._on_clear_all_clicked())
        menubar.add_cascade(label="Công cụ", menu=menu_tools)

        # Menu Trợ giúp
        menu_help = tk.Menu(menubar, tearoff=0)
        menu_help.add_command(label="ℹ️ Giới thiệu Video Toolkit", command=self._show_about_dialog)
        menubar.add_cascade(label="Trợ giúp", menu=menu_help)

        self.config(menu=menubar)

    def _show_about_dialog(self):
        messagebox.showinfo(
            "Giới thiệu Video Toolkit Pro",
            "Video Toolkit Pro (Phiên bản Đa Năng)\n\n"
            "Tính năng chính:\n"
            "1. 🎬 Ghép Video MP4 Chuyên Nghiệp: Hỗ trợ đa định dạng, chọn track audio từng video, tăng tốc GPU NVENC/AMF/QSV.\n"
            "2. ✂️ Cắt Video Siêu Tốc: Kéo thanh trượt xem trực tiếp khung hình, luôn xuất ra file chuẩn MP4 tương thích 100% mọi thiết bị.\n"
            "3. 📥 Tải Video YouTube: Nhập link, hiển thị đầy đủ định dạng (Full HD, 4K, MP3/M4A, phụ đề .SRT và dịch sang Tiếng Việt)."
        )

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray85", "#181a20"))
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(1, weight=1)

        logo_label = ctk.CTkLabel(header_frame, text="🎬", font=ctk.CTkFont(size=30))
        logo_label.grid(row=0, column=0, rowspan=2, padx=(18, 10), pady=10)

        title_label = ctk.CTkLabel(header_frame, text="VIDEO TOOLKIT PRO", font=ctk.CTkFont(size=17, weight="bold"))
        title_label.grid(row=0, column=1, sticky="w", pady=(8, 0))

        sub_text = f"Ghép Video • Cắt Video MP4 • Tải Video YouTube • Tăng tốc: {self.gpu_label}"
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text=sub_text,
            font=ctk.CTkFont(size=11),
            text_color=("#1f6aa5", "#38bdf8"),
            justify="left"
        )
        subtitle_label.grid(row=1, column=1, sticky="w", pady=(0, 8))

        self.nav_segmented = ctk.CTkSegmentedButton(
            header_frame,
            values=["🎬 Ghép Video", "✂️ Cắt Video", "📥 Tải YouTube"],
            command=self._on_nav_segmented_clicked,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=34,
            width=380
        )
        self.nav_segmented.set("🎬 Ghép Video")
        self.nav_segmented.grid(row=0, column=2, rowspan=2, padx=16, pady=10)

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
        if "Cắt" in value:
            self.switch_view("cutter")
        elif "YouTube" in value:
            self.switch_view("youtube")
        else:
            self.switch_view("joiner")

    def switch_view(self, view_name: str):
        self.current_view = view_name
        self.merger_view.grid_forget()
        self.cutter_view.grid_forget()
        self.youtube_view.grid_forget()

        if view_name == "joiner":
            self.merger_view.grid(row=0, column=0, sticky="nsew")
            self.nav_segmented.set("🎬 Ghép Video")
        elif view_name == "cutter":
            self.cutter_view.grid(row=0, column=0, sticky="nsew")
            self.nav_segmented.set("✂️ Cắt Video")
        elif view_name == "youtube":
            self.youtube_view.grid(row=0, column=0, sticky="nsew")
            self.nav_segmented.set("📥 Tải YouTube")

    def on_request_cut_video(self, file_path: str):
        self.switch_view("cutter")
        if file_path:
            self.cutter_view.load_video(file_path)

    def on_request_add_to_merger(self, file_path: str):
        self.switch_view("joiner")
        if file_path:
            self.merger_view.add_files_by_paths([file_path])

    def _on_close(self):
        try:
            self.merger_view.cleanup()
            self.cutter_view.cleanup()
            self.youtube_view.cleanup()
        except Exception:
            pass
        self.destroy()


def run_app():
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    run_app()
