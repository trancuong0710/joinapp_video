"""
YouTube subtitle card component with one-click Vietnamese translation.
"""
import customtkinter as ctk
from typing import Callable
from src.core.youtube.models import YouTubeSubtitleItem


class SubtitleCard(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        item: YouTubeSubtitleItem,
        only_en: bool,
        on_download: Callable[[YouTubeSubtitleItem], None],
        on_translate: Callable[[YouTubeSubtitleItem], None],
        **kwargs
    ):
        super().__init__(
            parent,
            corner_radius=8,
            fg_color=("#edf2f7", "#232731"),
            border_width=1,
            border_color=("#27ae60", "#27ae60") if item.lang == "vi" else ("#2980b9", "#2980b9"),
            **kwargs
        )
        self.grid_columnconfigure(0, weight=1)

        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        top_row.grid_columnconfigure(1, weight=1)

        is_vi = (item.lang == "vi")
        badge_text = "🇻🇳 SUB VIỆT" if is_vi else "🔤 SUB ANH"
        badge_color = ("#27ae60", "#27ae60") if is_vi else ("#2980b9", "#2980b9")
        badge = ctk.CTkLabel(
            top_row,
            text=f" {badge_text} ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=badge_color,
            text_color="white",
            corner_radius=4,
            width=90,
            height=28
        )
        badge.grid(row=0, column=0, padx=(0, 10), sticky="w")

        info_box = ctk.CTkFrame(top_row, fg_color="transparent")
        info_box.grid(row=0, column=1, sticky="w")

        lbl_name = ctk.CTkLabel(
            info_box,
            text=f"Phụ đề {item.label}  •  Định dạng: .SRT",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        lbl_name.pack(anchor="w")

        lbl_desc = ctk.CTkLabel(
            info_box,
            text=f"{item.note}  •  Chuẩn SubRip (.srt) dùng được cho mọi video",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray70"),
            anchor="w"
        )
        lbl_desc.pack(anchor="w")

        btn_dl = ctk.CTkButton(
            top_row,
            text="⬇️ Tải File .SRT",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=125,
            height=30,
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=lambda: on_download(item)
        )
        btn_dl.grid(row=0, column=2, padx=(8, 0), sticky="e")

        if item.lang == "en":
            trans_box = ctk.CTkFrame(self, fg_color=("#e6edf5", "#1c2431"), corner_radius=6)
            trans_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 8))
            trans_box.grid_columnconfigure(0, weight=1)

            hint_text = (
                "⚠️ Video chỉ có phụ đề Tiếng Anh gốc. Bấm nút bên để dịch tự động sang Tiếng Việt và xuất file .srt:"
                if only_en else
                "💡 Bấm nút bên để tự động dịch phụ đề Tiếng Anh này sang Tiếng Việt và xuất file .srt:"
            )

            lbl_hint = ctk.CTkLabel(
                trans_box,
                text=hint_text,
                font=ctk.CTkFont(size=11),
                text_color=("#c0392b", "#f39c12") if only_en else ("gray40", "gray75"),
                anchor="w",
                justify="left"
            )
            lbl_hint.grid(row=0, column=0, sticky="w", padx=10, pady=6)

            btn_trans = ctk.CTkButton(
                trans_box,
                text="🌐 Dịch sang Tiếng Việt (.srt)",
                font=ctk.CTkFont(size=12, weight="bold"),
                width=210,
                height=30,
                fg_color="#8e44ad",
                hover_color="#732d91",
                command=lambda: on_translate(item)
            )
            btn_trans.grid(row=0, column=1, padx=(6, 10), pady=6, sticky="e")

