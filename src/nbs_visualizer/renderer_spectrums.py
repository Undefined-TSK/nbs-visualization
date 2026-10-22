"""频谱绘制 mixin。"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .logger import get_logger

from .spectrum import _spectrum_bar_pos
from .stage import SPECTRUM_BAR_MAX_RATIO
from .stage_constants import SPECTRUM_RENDER_GAP_RATIO
from ._core import (
    SPECTRUM_BARS_PER_EDGE, SPECTRUM_BAR_WIDTH, SPECTRUM_BAR_MIN_HEIGHT,
    SPECTRUM_ACTIVE_BOOST,
)

logger = get_logger(__name__)


class RendererSpectrumsMixin:
    """频谱绘制组件（原 Mixin 重构为组合）。"""

    """频谱绘制组件（原 Mixin 重构为组合）。"""

    def __init__(self, host):
        self.host = host

    """频谱绘制 mixin。"""

    def _draw_all_spectrums(self, img: Image.Image, t: float,
                            spec_decay: float = 1.0):
        bs = self.host.stage.block_size
        bpe = SPECTRUM_BARS_PER_EDGE
        spec_gap = max(3, int(bs * SPECTRUM_RENDER_GAP_RATIO))
        bar_w = SPECTRUM_BAR_WIDTH
        max_h = max(6, int(bs * SPECTRUM_BAR_MAX_RATIO))
        # 频谱条不可超出卡片边界：half + spec_gap + max_h <= card_half - margin
        # （用户反馈：峰值时会超出卡片，这里硬性限制其最大伸出长度）
        half = bs / 2
        card_half = self.host.stage.card_size / 2.0
        max_allowed = card_half - half - spec_gap - 4.0
        if max_allowed < 6:
            max_allowed = 6
        max_h = min(max_h, int(max_allowed))

        for track in self.host.tracks:
            if not self.host.stage.is_visible(track.layer_id):
                continue
            alpha = self.host.stage.get_alpha(track.layer_id, t)
            if alpha <= 0.01:
                continue

            cx, cy = self.host.stage.get_position(track.layer_id, t)
            spectrum = self.host._spectrum.get_spectrum_at(track, t)

            if spec_decay < 1.0:
                spectrum = [v * spec_decay for v in spectrum]

            if self.host.stage.get_tsm(track.layer_id).is_active_at(t):
                spectrum = [min(1.0, v * SPECTRUM_ACTIVE_BOOST) for v in spectrum]

            # FIXED-B3: 问题31 - Solo卡片频谱光效加倍
            is_solo = self.host._solo_active_id is not None and track.layer_id == self.host._solo_active_id
            if is_solo and self.host._solo_alpha > 0.01:
                solo_boost = 1.0 + self.host._solo_alpha
                spectrum = [min(1.0, v * solo_boost) for v in spectrum]

            half = bs / 2
            palette = self.host.stage.get_color(track.layer_id)
            hl = palette["hl"]
            bar_color = hl
            glow_color = (hl[0], hl[1], hl[2], max(1, hl[3] // 4))

            # FIXED-B2: 问题52 - spec_overlay从全屏改为局部尺寸
            ov_side = int(bs + 2 * (spec_gap + max_h + 4))
            lcx, lcy = ov_side / 2, ov_side / 2
            spec_overlay = Image.new("RGBA", (ov_side, ov_side), (0, 0, 0, 0))
            d = ImageDraw.Draw(spec_overlay)

            for i, val in enumerate(spectrum):
                if spec_decay < 1.0:
                    raw_h = val * max_h
                    h = int(raw_h)
                    if h <= 0:
                        continue
                    # FIXED-B4: 问题41 - 频谱柱亚像素量化：顶部像素按frac比例透明
                    top_frac = raw_h - h  # 0~1 小数部分
                else:
                    raw_h = val * max_h
                    h = max(SPECTRUM_BAR_MIN_HEIGHT, int(raw_h))
                    top_frac = raw_h - int(raw_h) if raw_h >= SPECTRUM_BAR_MIN_HEIGHT else 0
                bx, by, dx, dy = _spectrum_bar_pos(i, lcx, lcy, half, spec_gap, bpe)

                if dy != 0:
                    x1 = int(round(bx - bar_w / 2))
                    x2 = int(round(bx + bar_w / 2))
                    if dy < 0:
                        y1, y2 = int(round(by - h)), int(round(by))
                        top_y = y1 - 1  # 顶部额外像素位置
                    else:
                        y1, y2 = int(round(by)), int(round(by + h))
                        top_y = y2  # 顶部额外像素位置
                else:
                    y1 = int(round(by - bar_w / 2))
                    y2 = int(round(by + bar_w / 2))
                    if dx > 0:
                        x1, x2 = int(round(bx)), int(round(bx + h))
                        top_x = x2  # 顶部额外像素位置
                    else:
                        x1, x2 = int(round(bx - h)), int(round(bx))
                        top_x = x1 - 1  # 顶部额外像素位置

                d.rectangle([x1-2, y1-1, x2+1, y2+1], fill=glow_color)
                d.rectangle([x1, y1, x2-1, y2-1], fill=bar_color)

                # FIXED-B4: 问题41 - 顶部亚像素：按小数比例绘制额外的1像素
                if top_frac > 0.01:
                    top_alpha = int(255 * top_frac)
                    if dy != 0:
                        # 纵向柱：顶部加1像素高的横条
                        top_glow = (*glow_color[:3], max(1, int(glow_color[3] * top_frac)))
                        top_bar = (*bar_color[:3], max(1, int(bar_color[3] * top_frac)))
                        d.rectangle([x1-2, top_y, x2+1, top_y + 1], fill=top_glow)
                        d.rectangle([x1, top_y, x2-1, top_y], fill=top_bar)
                    else:
                        # 横向柱：右侧/左侧加1像素宽的竖条
                        top_glow = (*glow_color[:3], max(1, int(glow_color[3] * top_frac)))
                        top_bar = (*bar_color[:3], max(1, int(bar_color[3] * top_frac)))
                        d.rectangle([top_x, y1-1, top_x + 1, y2+1], fill=top_glow)
                        d.rectangle([top_x, y1, top_x, y2-1], fill=top_bar)

            if alpha < 1.0:
                r, g, b, a = spec_overlay.split()
                a = a.point(lambda x: max(0, min(255, round(x * alpha))))
                spec_overlay = Image.merge("RGBA", (r, g, b, a))

            img.alpha_composite(spec_overlay, (int(cx - ov_side / 2), int(cy - ov_side / 2)))
