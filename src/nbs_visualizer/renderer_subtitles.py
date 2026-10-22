"""Kimi 字幕绘制 mixin。"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .logger import get_logger

from .stage import GROUP_PALETTE
from ._core import VIDEO_WIDTH
from .ui import Subtitle

logger = get_logger(__name__)


class RendererSubtitlesMixin:
    """Kimi 字幕绘制组件（原 Mixin 重构为组合）。"""

    """Kimi 字幕绘制组件（原 Mixin 重构为组合）。"""

    def __init__(self, host):
        self.host = host

    """Kimi 字幕绘制 mixin。"""

    def _draw_kimi_subtitles(self, pil_img: Image.Image, t: float):
        """MC成就弹窗风格字幕：右上角滑入。"""
        raw_subs = self.host.kimi_script.get("subtitles", [])
        if not raw_subs:
            return

        subtitles = [Subtitle(
            text=s.get("text", ""),
            time=s.get("time", 0),
            duration=s.get("duration", 3.0),
        ) for s in raw_subs]

        current = None
        for sub in subtitles:
            st = sub.time
            dur = sub.duration
            if st <= t < st + dur:
                current = sub
                break

        if not current:
            return

        text = current.text
        st = current.time
        dur = current.duration
        elapsed = t - st

        fade_in = min(1.0, elapsed / 0.5)
        fade_out = min(1.0, (dur - elapsed) / 0.5)
        alpha = min(fade_in, fade_out)

        # 滑入动画：前0.3s从右侧滑入
        slide_in = min(1.0, elapsed / 0.3)
        slide_offset = int((1.0 - slide_in) * 60)

        # FIXED-B4: 问题29 - 淡出阶段向右上飘移(y-30px, x+20px)
        fade_out_progress = 1.0 - fade_out  # 0→1 as we fade out
        fade_offset_x = int(fade_out_progress * 20)
        fade_offset_y = int(-fade_out_progress * 30)

        if alpha <= 0.01:
            return

        # 获取当前聚焦组的颜色
        cam_type, focus = self.host.camera._get_script_camera(t)
        if isinstance(focus, int) and 0 <= focus < len(GROUP_PALETTE):
            accent_color = GROUP_PALETTE[focus]["hl"][:3]
        else:
            accent_color = (91, 192, 222)

        # FIXED-B2: 问题53 - 直接在PIL overlay上绘制，无需BGR↔RGB转换
        draw = ImageDraw.Draw(pil_img, "RGBA")

        text_size = draw.textbbox((0, 0), text, font=self.host.font_subtitle)
        tw = text_size[2] - text_size[0]
        th = text_size[3] - text_size[1]
        text_top = text_size[1]

        padding_x = 20
        padding_y = 12
        # FIXED-B4: 问题29 - 叠加淡出偏移(向右上)
        box_x1 = VIDEO_WIDTH - tw - padding_x * 2 - 40 + slide_offset + fade_offset_x
        box_y1 = 30 + fade_offset_y
        box_x2 = VIDEO_WIDTH - 40 + slide_offset + fade_offset_x
        box_h = th + padding_y * 2
        box_y2 = box_y1 + box_h

        # MC成就弹窗背景：#1A1A1A at 85% opacity
        bg_alpha = int(217 * alpha)  # 85% of 255
        # FIXED-B2: 问题8 - 成就弹窗背景去圆角 rounded_rectangle→rectangle
        draw.rectangle(
            [box_x1, box_y1, box_x2, box_y2],
            fill=(26, 26, 26, bg_alpha),
        )
        # 左侧彩色条：当前聚焦组高亮色
        bar_w = 5
        draw.rectangle(
            [box_x1, box_y1, box_x1 + bar_w, box_y2],
            fill=(*accent_color, int(255 * alpha)),
        )

        # 文字：#E0E0E0 + 1px黑色描边
        text_y = box_y1 + (box_h - th) // 2 - text_top
        text_alpha = int(255 * alpha)
        draw.text(
            (box_x1 + padding_x, text_y),
            text,
            font=self.host.font_subtitle,
            fill=(224, 224, 224, text_alpha),
            stroke_width=1,
            stroke_fill=(0, 0, 0, int(199 * alpha)),
        )
        # FIXED-B2: 问题53 - 移除BGR回写，绘制结果已通过ui_overlay.alpha_composite合入bg
