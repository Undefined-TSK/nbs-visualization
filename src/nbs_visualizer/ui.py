"""UI系统：弹幕绘制、文字描边、虚线框、标签徽章、卡片渲染。"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple, TYPE_CHECKING
from PIL import Image, ImageDraw, ImageFont

from .resources import load_font, TextureCache
from .utils import clamp


@dataclass
class Danmaku:
    """弹幕数据（替代字典 d["x"] 式访问）。"""
    text: str
    x: float
    y: float
    speed: float
    alpha: float
    start_time: float
    age: float


@dataclass
class Subtitle:
    """字幕数据。"""
    text: str
    time: float
    duration: float
    group_idx: int = -1


class DanmakuSystem:
    """
    MC聊天框风格弹幕系统：文字从右往左飘过。
    - 时间线驱动，每条弹幕有出现时间
    - MC聊天框背景：#000000(40%)，圆角3px
    - 出现时0.1s scale(0.9→1.0)弹跳动画
    """

    FONT_SIZE = 26
    SPEED = 160  # 像素/秒
    ROW_GAP = 40  # 行间距
    TOP_MARGIN = 80  # 顶部留白
    MAX_ROWS = 6
    POPUP_DURATION = 0.1  # 弹出动画时长

    def __init__(self, danmaku_list: Optional[List[Dict]] = None):
        self.danmaku_list = danmaku_list or []
        self._font = None
        self._active: List[Danmaku] = []
        self._last_emitted = {}  # text -> last emit time

    def _get_font(self):
        if self._font is None:
            self._font = load_font(self.FONT_SIZE)
        return self._font

    def update(self, t: float, dt: float):
        from ._core import VIDEO_WIDTH
        for d in self.danmaku_list:
            dtime = d["time"]
            if dtime <= t < dtime + 0.05:
                already = any(a.start_time == dtime and a.text == d["text"]
                              for a in self._active)
                if already:
                    continue

                text_key = d["text"]
                last_time = self._last_emitted.get(text_key, -999)
                if t - last_time < 10.0:
                    continue
                self._last_emitted[text_key] = t

                row = d.get("row", self._pick_row())
                y = self.TOP_MARGIN + row * self.ROW_GAP

                self._active.append(Danmaku(
                    text=d["text"],
                    x=VIDEO_WIDTH + 10,
                    y=y,
                    speed=self.SPEED + d.get("speed_offset", 0),
                    alpha=1.0,
                    start_time=dtime,
                    age=0.0,
                ))

        new_active = []
        for d in self._active:
            d.x -= d.speed * dt
            d.age += dt
            if d.x < 50:
                d.alpha = max(0, d.x / 50)
            if d.x > -200:
                new_active.append(d)
        self._active = new_active

    def _pick_row(self) -> int:
        from ._core import VIDEO_WIDTH
        used_rows = set()
        for d in self._active:
            if d.x > VIDEO_WIDTH * 0.7:
                row = int((d.y - self.TOP_MARGIN) / self.ROW_GAP)
                used_rows.add(row)
        for r in range(self.MAX_ROWS):
            if r not in used_rows:
                return r
        return 0

    def draw(self, img: Image.Image):
        if not self._active:
            return

        font = self._get_font()
        draw = ImageDraw.Draw(img, "RGBA")

        for d in self._active:
            alpha = d.alpha
            if alpha <= 0:
                continue

            text = d.text
            x = int(d.x)
            y = int(d.y)

            age = d.age
            if age < self.POPUP_DURATION:
                scale = 0.9 + 0.1 * (age / self.POPUP_DURATION)
            else:
                scale = 1.0

            a = int(255 * alpha)

            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            text_top = bbox[1]

            sw = int(tw * scale)
            sh = int(th * scale)
            ox = (tw - sw) // 2
            oy = (th - sh) // 2

            pad_x, pad_y = 10, 6
            bg_x1 = x + ox - pad_x
            bg_y1 = y + oy - pad_y
            bg_x2 = x + ox + sw + pad_x
            bg_y2 = y + oy + sh + pad_y
            draw.rectangle(
                [bg_x1, bg_y1, bg_x2, bg_y2],
                fill=(0, 0, 0, int(102 * alpha)),
            )

            stroke_a = min(255, a + 40)
            draw.text(
                (x + ox, y + oy - text_top),
                text, font=font,
                fill=(255, 255, 255, a),
                stroke_width=1,
                stroke_fill=(0, 0, 0, stroke_a),
            )


# ============== Re-export（兼容现有导入） ==============
from .card_renderer import CardRenderer  # noqa: E402
