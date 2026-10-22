"""粒子效果：附魔光效、回收粒子、睡眠粒子、准星。"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple, Dict
from PIL import Image, ImageDraw

from .utils import ease_out_cubic
from .resources import TextureCache
from .particles import CollectionParticle, SleepParticle


class EnchantGlint:
    """MC 附魔光效：密集音符时在贴图周围绘制光晕边框+边缘闪烁。
    不覆盖贴图本身，只在外围添加视觉效果。"""
    def __init__(self, textures: TextureCache):
        self.textures = textures
        self._glint_img = None
        self._active: Dict[int, float] = {}  # track_id → 开始时间

    def _get_glint(self):
        if self._glint_img is not None:
            return self._glint_img
        img = self.textures.get_mc_particle("glint.png")
        if img is None:
            img = Image.new("RGBA", (16, 16), (200, 200, 255, 80))
        self._glint_img = img
        return self._glint_img

    def activate(self, track_id: int, t: float):
        self._active[track_id] = t

    def deactivate(self, track_id: int):
        self._active.pop(track_id, None)

    def is_active(self, track_id: int) -> bool:
        return track_id in self._active

    def draw(self, img: Image.Image, track_id: int, cx: int, cy: int,
             bs: int, t: float, highlight_color: Tuple[int, int, int]):
        """在贴图周围绘制附魔光效：光晕边框 + 边缘闪烁粒子。
        不覆盖贴图像素，只在贴图外围添加视觉效果。"""
        if bs < 60:
            return

        r, g, b = highlight_color
        breathe = 0.5 + 0.5 * math.sin(t * 1.5)
        glow_alpha = int((150 + 80 * breathe) * 0.65)

        half = bs // 2
        x1 = cx - half
        y1 = cy - half
        x2 = cx + half
        y2 = cy + half

        pad = 6
        ov_w = bs + pad * 2
        ov_h = bs + pad * 2
        ox = x1 - pad
        oy = y1 - pad
        overlay = Image.new("RGBA", (ov_w, ov_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)

        lx1, ly1 = pad, pad
        lx2, ly2 = pad + bs, pad + bs

        d.rectangle([lx1 - 2, ly1 - 2, lx2 + 2, ly2 + 2],
                     outline=(r, g, b, glow_alpha), width=2)
        inner_alpha = int(glow_alpha * 0.4)
        d.rectangle([lx1, ly1, lx2, ly2],
                     outline=(r, g, b, inner_alpha), width=1)

        glint = self._get_glint()
        spark_size = 6
        spark_img = glint.resize((spark_size, spark_size), Image.NEAREST)
        num_sparks = 8
        for i in range(num_sparks):
            phase = (t * 0.8 + i * 0.4) % 1.0
            if phase < 0.15 or phase > 0.85:
                continue
            edge = i % 4
            edge_t = ((t * 0.5 + i * 0.3) % 1.0)
            pos_x, pos_y = 0, 0
            if edge == 0:
                pos_x = lx1 + int(edge_t * bs)
                pos_y = ly1
            elif edge == 1:
                pos_x = lx2
                pos_y = ly1 + int(edge_t * bs)
            elif edge == 2:
                pos_x = lx1 + int(edge_t * bs)
                pos_y = ly2
            else:
                pos_x = lx1
                pos_y = ly1 + int(edge_t * bs)

            fade = math.sin(phase * math.pi)
            spark_alpha = int(180 * fade)
            if spark_alpha > 0:
                tinted = Image.new("RGBA", (spark_size, spark_size), (r, g, b, 0))
                tinted.paste(spark_img, (0, 0), spark_img)
                blended = Image.blend(spark_img, tinted, 0.7)
                s_mask = blended.split()[3].point(
                    lambda x: max(0, min(255, round(x * fade * 0.7)))
                )
                result = Image.new("RGBA", (spark_size, spark_size), (0, 0, 0, 0))
                result.paste(blended, (0, 0), s_mask)
                overlay.alpha_composite(result,
                    (pos_x - spark_size // 2, pos_y - spark_size // 2))

        img.alpha_composite(overlay, (ox, oy))


class CollectionParticles:
    """MC 回收粒子：playing→resting 时从卡片边缘吸入中心。"""
    def __init__(self, textures: TextureCache):
        self.textures = textures
        self.particles: List[CollectionParticle] = []
        self._generic_img = None

    def _get_img(self):
        if self._generic_img is not None:
            return self._generic_img
        img = self.textures.get_mc_particle("generic_0.png")
        if img is not None and (img.width != 8 or img.height != 8):
            img = img.resize((8, 8), Image.NEAREST)
        if img is None:
            img = Image.new("RGBA", (8, 8), (180, 180, 180, 150))
        self._generic_img = img
        return self._generic_img

    def emit(self, cx: float, cy: float, card_half: float):
        """在卡片四角生成吸入粒子。"""
        for _ in range(4):
            edge = random.choice(["top", "bottom", "left", "right"])
            if edge == "top":
                sx, sy = cx + random.uniform(-card_half, card_half), cy - card_half
            elif edge == "bottom":
                sx, sy = cx + random.uniform(-card_half, card_half), cy + card_half
            elif edge == "left":
                sx, sy = cx - card_half, cy + random.uniform(-card_half, card_half)
            else:
                sx, sy = cx + card_half, cy + random.uniform(-card_half, card_half)
            self.particles.append(CollectionParticle(
                sx=sx, sy=sy,
                x=sx, y=sy, cx=cx, cy=cy,
                life=0.0, max_life=0.6,
            ))

    def update(self, dt: float):
        alive = []
        for p in self.particles:
            p.life += dt
            if p.life >= p.max_life:
                continue
            progress = p.life / p.max_life
            ease = ease_out_cubic(progress)
            p.x = p.sx + (p.cx - p.sx) * ease
            p.y = p.sy + (p.cy - p.sy) * ease
            alive.append(p)
        self.particles = alive

    def draw(self, img: Image.Image):
        sprite = self._get_img()
        small = sprite.resize((8, 8), Image.Resampling.NEAREST)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        for p in self.particles:
            life_ratio = p.life / p.max_life
            alpha = int(180 * (1 - life_ratio))
            if alpha <= 0:
                continue
            mask = small.split()[3].point(lambda x: max(0, min(255, round(x * (1 - life_ratio)))))
            overlay.paste(small, (int(p.x) - 4, int(p.y) - 4), mask)
        img.alpha_composite(overlay)


class _SleepParticleSystem:
    EMIT_INTERVAL = 0.8

    def __init__(self, textures: TextureCache):
        self.textures = textures
        self.particles: List[SleepParticle] = []
        self._img = None
        self._emit_timer = 0.0

    def _get_img(self):
        if self._img is not None:
            return self._img
        img = self.textures.get_mc_particle("particle_0.png")
        if img is None:
            img = Image.new("RGBA", (8, 8), (200, 200, 200, 76))
        self._img = img
        return self._img

    def emit(self, cx: float, cy: float, card_half: float):
        """从卡片顶部发射1-2个粒子。"""
        count = random.randint(1, 2)
        for _ in range(count):
            sx = cx + random.uniform(-card_half * 0.6, card_half * 0.6)
            sy = cy - card_half - 2
            self.particles.append(SleepParticle(
                x=sx, y=sy,
                vx=random.uniform(-2, 2),
                vy=random.uniform(-10, -5),
                life=0.0,
                max_life=random.uniform(3.0, 4.5),
                size=random.randint(5, 8),
            ))

    def update(self, dt: float):
        self._emit_timer += dt
        alive = []
        for p in self.particles:
            p.life += dt
            if p.life >= p.max_life:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

    def draw(self, img: Image.Image):
        sprite = self._get_img()
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        for p in self.particles:
            life_ratio = p.life / p.max_life
            alpha_mult = (1 - life_ratio) * 0.5
            size = p.size
            small = sprite.resize((size, size), Image.Resampling.NEAREST)
            mask = small.split()[3].point(lambda x: max(0, min(255, round(x * alpha_mult))))
            overlay.paste(small, (int(p.x) - size // 2, int(p.y) - size // 2), mask)
        img.alpha_composite(overlay)


class Crosshair:
    """Camera focus 指示器：聚焦时在画面中心显示。"""
    def __init__(self, textures: TextureCache):
        self.textures = textures
        self._alpha = 0.0
        self._target_alpha = 0.0
        self._crosshair_img = None

    def _get_crosshair(self):
        if self._crosshair_img is not None:
            return self._crosshair_img
        img = self.textures.get_mc_gui("crosshair.png")
        if img is None:
            img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            cx, cy = 12, 12
            size = 6
            gap = 3
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                d.line([
                    (cx + dx * gap, cy + dy * gap),
                    (cx + dx * (gap + size), cy + dy * (gap + size))
                ], fill=(255, 255, 255, 255), width=2)
        self._crosshair_img = img
        return self._crosshair_img

    def set_visible(self, visible: bool):
        self._target_alpha = 0.3 if visible else 0.0

    def update(self, dt: float):
        self._alpha += (self._target_alpha - self._alpha) * dt * 5

    def draw(self, img: Image.Image):
        if self._alpha < 0.01:
            return
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        cx, cy = VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2
        crosshair = self._get_crosshair()
        if crosshair:
            r, g, b, a = crosshair.split()
            a = a.point(lambda x: max(0, min(255, round(x * self._alpha))))
            tinted = Image.merge("RGBA", (r, g, b, a))
            img.alpha_composite(tinted, (cx - crosshair.width // 2, cy - crosshair.height // 2))
