"""
Video card component for the merger list.
"""
import os
import customtkinter as ctk
from PIL import Image
from typing import Callable, Dict, Optional
from src.core.video_meta import VideoInfo


class VideoCard(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        index: int,
        video: VideoInfo,
        total_count: int,
        thumb_cache: Dict[str, ctk.CTkImage],
        on_move: Callable[[int, int], None],
        on_audio_track_changed: Callable[[int, str], None],
        on_mute_toggle: Callable[[int, bool], None],
        on_cut: Callable[[str], None],
        on_remove: Callable[[int], None],
        **kwargs
    ):
        super().__init__(
            parent,
            corner_radius=8,
            fg_color=("white", "#232731"),
            border_width=1,
            border_color=("gray80", "#323744"),
            **kwargs
        )
        self.grid_columnconfigure(2, weight=1)

        # 1. Index & Reorder Column (Left)
        left_col = ctk.CTkFrame(self, fg_color="transparent", width=45)
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
            command=lambda: on_move(index, -1)
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
            command=lambda: on_move(index, 1)
        )
        if index == total_count - 1:
            btn_down.configure(state="disabled")
        btn_down.pack(pady=2)

        # 2. Thumbnail Column
        thumb_frame = ctk.CTkFrame(self, fg_color=("gray90", "#181a20"), width=120, height=68, corner_radius=6)
        thumb_frame.grid(row=0, column=1, rowspan=2, padx=(4, 12), pady=8)
        thumb_frame.pack_propagate(False)

        ctk_img = None
        if video.thumbnail_path and os.path.exists(video.thumbnail_path):
            try:
                if video.thumbnail_path not in thumb_cache:
                    pil_img = Image.open(video.thumbnail_path)
                    thumb_cache[video.thumbnail_path] = ctk.CTkImage(
                        light_image=pil_img,
                        dark_image=pil_img,
                        size=(120, 68)
                    )
                ctk_img = thumb_cache[video.thumbnail_path]
            except Exception:
                ctk_img = None

        if ctk_img:
            lbl_img = ctk.CTkLabel(thumb_frame, text="", image=ctk_img)
            lbl_img.pack(expand=True, fill="both")
        else:
            lbl_no_img = ctk.CTkLabel(thumb_frame, text="🎬", font=ctk.CTkFont(size=28))
            lbl_no_img.pack(expand=True, fill="both")

        # 3. Main Info Column
        main_col = ctk.CTkFrame(self, fg_color="transparent")
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
                command=lambda val: on_audio_track_changed(index, val)
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
            chk_mute = ctk.CTkCheckBox(
                audio_frame,
                text="Tắt tiếng",
                font=ctk.CTkFont(size=11),
                variable=mute_var,
                checkbox_width=18,
                checkbox_height=18,
                command=lambda: on_mute_toggle(index, mute_var.get())
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

        # 4. Action Column (Right: Cut & Delete)
        right_col = ctk.CTkFrame(self, fg_color="transparent")
        right_col.grid(row=0, column=3, rowspan=2, padx=(0, 10), pady=8, sticky="ns")

        btn_cut = ctk.CTkButton(
            right_col,
            text="✂️ Cắt",
            width=55,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#d35400", "#b94600"),
            hover_color=("#a03d00", "#873400"),
            command=lambda: on_cut(video.file_path)
        )
        btn_cut.pack(side="left", padx=(0, 6))

        btn_del = ctk.CTkButton(
            right_col,
            text="❌",
            width=32,
            height=30,
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            hover_color=("#f2dede", "#5c1d1d"),
            text_color=("#c0392b", "#e74c3c"),
            command=lambda: on_remove(index)
        )
        btn_del.pack(side="left")

