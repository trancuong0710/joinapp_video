"""
YouTube download format card component.
"""
import customtkinter as ctk
from typing import Callable
from src.core.youtube.models import YouTubeFormatItem


class FormatCard(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        item: YouTubeFormatItem,
        on_download: Callable[[YouTubeFormatItem], None],
        on_copy_link: Callable[[str], None],
        **kwargs
    ):
        super().__init__(
            parent,
            corner_radius=8,
            fg_color=("#edf2f7", "#232731") if not item.is_recommended else ("#e8f4fd", "#1a3044"),
            border_width=1 if item.is_recommended else 0,
            border_color=("#38bdf8", "#1f6aa5"),
            **kwargs
        )
        self.grid_columnconfigure(1, weight=1)

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
            self,
            text=f" {badge_text} ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=badge_color,
            text_color="white",
            corner_radius=4,
            width=75,
            height=28
        )
        badge.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)

        lbl_name = ctk.CTkLabel(
            self,
            text=item.label,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        lbl_name.grid(row=0, column=1, sticky="w", pady=(8, 2))

        sub_info = f"Định dạng: {item.ext.upper()} • Dung lượng: {item.filesize_str}"
        if item.note:
            sub_info += f" • {item.note}"

        lbl_desc = ctk.CTkLabel(
            self,
            text=sub_info,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            anchor="w"
        )
        lbl_desc.grid(row=1, column=1, sticky="w", pady=(0, 8))

        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
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
                command=lambda: on_copy_link(item.direct_url)
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
            command=lambda: on_download(item)
        )
        btn_dl.pack(side="left")

