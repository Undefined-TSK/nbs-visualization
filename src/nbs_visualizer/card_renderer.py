"""卡片渲染器：卡片绘制、标签徽章、组标签。"""
from __future__ import annotations

import math
from typing import Dict, Tuple
from PIL import Image, ImageDraw, ImageFont

from .resources import TextureCache


class CardRenderer:
    """卡片渲染器：将 FrameRenderer 中分散的卡片/标签绘制逻辑内聚为单一类。"""

    def __init__(self, resources: TextureCache, fonts: Dict):
        self.res = resources
        self.fonts = fonts

    def _draw_label_badge(self, draw: ImageDraw.ImageDraw, xy: Tuple[int, int],
                          text: str, font: ImageFont.FreeTypeFont,
                          fill, anchor: str = "ra",
                          badge_color=(0, 0, 0, 140)):
        """带半透明深色徽章的文字标签，确保在任何贴图上都可读。"""
        from ._core import TEXT_STROKE_COLOR
        x, y = xy
        bbox = draw.textbbox((x, y), text, font=font, anchor=anchor)
        pad_x, pad_y = 4, 2
        draw.rectangle(
            [bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y],
            fill=badge_color,
        )
        draw.text((x, y), text, font=font, fill=fill, anchor=anchor,
                  stroke_width=1, stroke_fill=TEXT_STROKE_COLOR)

    def _draw_text_with_stroke(self, draw: ImageDraw.ImageDraw, xy: Tuple[int, int],
                               text: str, font: ImageFont.FreeTypeFont,
                               fill: Tuple[int, int, int, int],
                               stroke_color=None,
                               stroke_width=None,
                               anchor: str = "mm"):
        from ._core import TEXT_STROKE_COLOR, TEXT_STROKE_WIDTH
        if stroke_color is None:
            stroke_color = TEXT_STROKE_COLOR
        if stroke_width is None:
            stroke_width = TEXT_STROKE_WIDTH
        x, y = xy
        sw = stroke_width
        for dx in range(-sw, sw + 1, sw):
            for dy in range(-sw, sw + 1, sw):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font,
                          fill=stroke_color, anchor=anchor)
        draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

    def draw_card(self, img: Image.Image, t: float, tsm,
                  cx: float, cy: float, card_size: int, block_size: int,
                  palette: Dict, alpha: float, is_active: bool):
        """绘制单个卡片（阴影、背景、内阴影、边框、角标、经验条、线框化）。"""
        from .stage import (
            CARD_SHADOW_COLOR, CARD_CORNER_LEN_RATIO, CARD_BORDER_INACTIVE,
            OUTRO_FADEIN_DURATION, OUTRO_WAIT_DURATION,
        )

        is_playing = tsm.state == "playing"
        bs = block_size
        corner_len = max(5, int(bs * CARD_CORNER_LEN_RATIO))

        card_tier = 3 if bs < 80 else (2 if bs < 120 else 1)
        border_w = 2 if card_tier >= 2 else 1

        half = card_size // 2
        x1 = int(cx - half)
        y1 = int(cy - half)
        x2 = int(cx + half)
        y2 = int(cy + half)

        pad = 6
        ov_w = card_size + pad * 2
        ov_h = card_size + pad * 2 + 12
        ox, oy = x1 - pad, y1 - pad
        lx1, ly1 = pad, pad
        lx2, ly2 = pad + card_size, pad + card_size
        card_overlay = Image.new("RGBA", (ov_w, ov_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card_overlay)

        is_wireframe = (tsm.audio_end_time > 0 and
                        t > tsm.audio_end_time + OUTRO_WAIT_DURATION and
                        alpha < 0.3)
        if is_wireframe:
            wf_alpha = int(255 * alpha)
            d.rectangle([lx1, ly1, lx2, ly2],
                        outline=palette["hl"][:3] + (wf_alpha,), width=1)
            img.alpha_composite(card_overlay, (ox, oy))
            return

        shadow_off, shadow_alpha = tsm.get_shadow()
        d.rectangle(
            [lx1 + shadow_off, ly1 + shadow_off + 2,
             lx2 + shadow_off, ly2 + shadow_off + 2],
            fill=(*CARD_SHADOW_COLOR[:3], shadow_alpha),
        )

        d.rectangle([lx1, ly1, lx2, ly2], fill=palette["base"])

        border_color = tsm.get_border_color()
        d.rectangle([lx1, ly1, lx2, ly2], outline=border_color, width=border_w)

        if card_tier >= 2:
            cl = corner_len
            if is_playing and is_active:
                breath = 1.0 + 0.15 * math.sin(t * 2 * math.pi / 0.8)
                cl = int(cl * breath)
            corner_color = tsm.get_corner_color()
            for (cx1, cy1, dx1, dy1, dx2, dy2) in [
                (lx1, ly1, 1, 0, 0, 1),
                (lx2, ly1, -1, 0, 0, 1),
                (lx1, ly2, 1, 0, 0, -1),
                (lx2, ly2, -1, 0, 0, -1),
            ]:
                d.line([(cx1, cy1), (cx1 + dx1 * cl, cy1 + dy1 * cl)],
                       fill=corner_color, width=2)
                d.line([(cx1, cy1), (cx1 + dx2 * cl, cy1 + dy2 * cl)],
                       fill=corner_color, width=2)

        if card_tier == 1:
            bar_y = ly2 + 2
            bar_h = 7
            bar_x1 = lx1 + 4
            bar_x2 = lx2 - 4
            d.rectangle([bar_x1, bar_y, bar_x2, bar_y + bar_h],
                         fill=(0, 0, 0, 76))
            activity = tsm.get_activity()
            fill_w = int(round((bar_x2 - bar_x1) * activity))
            if fill_w > 0:
                d.rectangle([bar_x1, bar_y, bar_x1 + fill_w, bar_y + bar_h],
                             fill=palette["hl"])

        if alpha < 1.0:
            r, g, b, a = card_overlay.split()
            a = a.point(lambda x: max(0, min(255, round(x * alpha))))
            card_overlay = Image.merge("RGBA", (r, g, b, a))

        img.alpha_composite(card_overlay, (ox, oy))

    def draw_card_labels(self, img: Image.Image, t: float, tsm,
                         cx: float, cy: float, block_size: int, alpha: float):
        """绘制卡片上的角色名/乐器名标签。"""
        from ._core import LABEL_COLOR_ROLE, LABEL_COLOR_INST
        track = tsm.track
        bs = block_size
        half = bs // 2
        pad = max(3, int(bs * 0.02))

        label_pad = 8
        ov_size = bs + label_pad * 2
        lox = int(cx - half) - label_pad
        loy = int(cy - half) - label_pad
        label_overlay = Image.new("RGBA", (ov_size, ov_size), (0, 0, 0, 0))
        d = ImageDraw.Draw(label_overlay)

        role_text = track.role_name
        role_x = cx + half - pad - lox
        role_y = cy - half + pad - loy
        self._draw_label_badge(d, (role_x, role_y), role_text,
                               self.fonts["label"], LABEL_COLOR_ROLE, anchor="ra")

        inst_text = track.instrument_name
        inst_x = cx - half + pad - lox
        inst_y = cy + half - pad - loy
        self._draw_label_badge(d, (inst_x, inst_y), inst_text,
                               self.fonts["label"], LABEL_COLOR_INST, anchor="ld")

        if alpha < 1.0:
            r, g, b, a = label_overlay.split()
            a = a.point(lambda x: max(0, min(255, round(x * alpha))))
            label_overlay = Image.merge("RGBA", (r, g, b, a))

        img.alpha_composite(label_overlay, (lox, loy))

    def draw_group_label(self, img: Image.Image, gb: Dict,
                         label_width: int, font: ImageFont.FreeTypeFont):
        """绘制单个组标签（MC 木牌风格）。"""
        from ._core import LABEL_COLOR_ROLE, TEXT_STROKE_COLOR, TEXT_STROKE_WIDTH
        from .stage import GROUP_PALETTE

        d = ImageDraw.Draw(img)
        oak = self.res.get_mc_block("oak_planks.png")
        spruce = self.res.get_mc_block("spruce_planks.png")
        cold_indices = {0, 2, 5, 7}

        palette = GROUP_PALETTE[gb["color_idx"]]
        is_cold = gb["color_idx"] in cold_indices
        is_horizontal = gb.get("is_horizontal_label", False)

        if is_horizontal:
            lx = int(gb["label_x"])
            ly = int(gb["label_y"] - gb["label_h"] / 2)
            lw = int(gb.get("label_w", label_width * 2))
            lh = int(gb["label_h"])

            wood_tex = spruce if (is_cold and spruce) else oak
            wood_alpha = 0.12 if is_cold else 0.22
            if wood_tex:
                label_layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
                ow, oh = wood_tex.width, wood_tex.height
                for ty in range(0, lh, oh):
                    for tx in range(0, lw, ow):
                        label_layer.alpha_composite(wood_tex, (tx, ty))
                r, g, b, a = label_layer.split()
                a = a.point(lambda x: max(0, min(255, round(x * wood_alpha))))
                label_layer = Image.merge("RGBA", (r, g, b, a))
                img.alpha_composite(label_layer, (lx, ly))

            d.rectangle([lx, ly, lx + lw - 1, ly + lh - 1],
                        outline=palette["hl"], width=2)

            text_x = lx + lw // 2
            text_y = ly + lh // 2
            d.text((text_x, text_y), gb["name"], fill=LABEL_COLOR_ROLE, font=font,
                   anchor="mm")
        else:
            lx = int(gb["label_x"])
            ly = int(gb["y_top"])
            lw = label_width
            lh = int(gb["y_bottom"] - gb["y_top"])

            wood_tex = spruce if (is_cold and spruce) else oak
            wood_alpha = 0.10 if is_cold else 0.20
            if wood_tex:
                label_layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
                ow, oh = wood_tex.width, wood_tex.height
                for ty in range(0, lh, oh):
                    for tx in range(0, lw, ow):
                        label_layer.alpha_composite(wood_tex, (tx, ty))
                label_layer = label_layer.resize((lw, lh))
                r, g, b, a = label_layer.split()
                a = a.point(lambda x: max(0, min(255, round(x * wood_alpha))))
                label_layer = Image.merge("RGBA", (r, g, b, a))
                img.alpha_composite(label_layer, (lx, ly))

            d.rectangle(
                [lx, ly + 2, lx + lw, ly + lh - 2],
                outline=palette["hl"],
                width=2,
            )
            text_cx = lx + lw / 2
            text_cy = gb["label_y"]
            self._draw_text_with_stroke(d, (text_cx, text_cy), gb["name"], font,
                                        fill=LABEL_COLOR_ROLE,
                                        stroke_color=TEXT_STROKE_COLOR,
                                        stroke_width=TEXT_STROKE_WIDTH)
