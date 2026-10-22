"""粒子系统：音符粒子、回收粒子、暴击粒子、睡眠粒子、附魔光效、准星。"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image, ImageDraw

import numpy as np

from .utils import ease_out_cubic
from .resources import TextureCache, load_font


# ============== 粒子相位（显式状态机） ==============

class _ParticlePhase(Enum):
    RISE = 1    # 上升（出生→顶点）
    FALL = 2    # 下落（顶点→消散）
    BURST = 3   # 暴击径向爆发（短生命、无长尾）


# ============== 粒子数据类 ==============

@dataclass
class NoteParticle:
    """音符粒子数据（替代字典 p["x"] 式访问）。phase 显式驱动物理与渲染。"""
    track_id: int
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    phase: Any
    critical: bool = False
    color: Optional[tuple] = None
    trail: List[Tuple[float, float]] = field(default_factory=list)
    size: float = 20.0


@dataclass
class CollectionParticle:
    """回收粒子数据。"""
    sx: float
    sy: float
    x: float
    y: float
    cx: float
    cy: float
    life: float
    max_life: float


@dataclass
class SleepParticle:
    """睡眠粒子数据。"""
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: int = 6


@dataclass
class BgParticle:
    """背景粒子数据（保留定义，供 _core 导出；背景系统现已用 NumPy 数组实现）。"""
    img: Optional[Image.Image]
    x: int
    y: int
    speed: float
    drift: float
    size_factor: float
    alpha: float


# ============== 音符粒子系统 ==============

class NoteParticleSystem:
    """MC 音符粒子：从方块(贴图按下瞬间)顶部生成，抛物线运动；带彗尾与色彩渐变。

    状态管理要点（本次重构）：
    - 每个粒子持有显式 phase 状态机(RISE→FALL / BURST)，由 (life/max_life) 与 phase
      共同驱动物理与渲染，取代旧版'只要活着就画'的隐式逻辑。
    - 每轨活跃计数 O(1) 维护（_count_by_track），取代旧版每次 emit 全表 O(n) 扫描。
    - 发射受「贴图按下状态 + 卡片透明度 + 遮盖(occlusion)」三重约束：
      仅贴图处于'英雄按下'时刻才迸发；被遮盖/暗化(resting 淡出或独奏非聚焦)的轨道不发射，
      体现'贴图与遮盖行为不同'——遮盖是容器，不是英雄时刻。
    - 出生点跟随贴图被按下时的真实盒顶（tx_scale 缩小的盒子），让粒子'粘'在英雄动作上。
    """
    MAX_PER_TRACK = 3          # 每轨最多 3 个普通音符粒子（Spec §9）
    MAX_CRIT_PER_TRACK = 6     # 暴击粒子上限略高（径向爆发，短生命）
    GRAVITY = 80.0
    MIN_LIFETIME = 0.9
    MAX_LIFETIME = 1.3
    TRAIL_LEN = 8

    def __init__(self, textures: TextureCache):
        self.textures = textures
        self.particles: List[NoteParticle] = []
        self._count_by_track: Dict[int, int] = {}
        self._note_img = None
        self._critical_img = None
        self._t = 0.0

    def _get_note_img(self):
        if self._note_img is None:
            img = self.textures.get_mc_particle("note.png")
            self._note_img = img if img is not None else Image.new("RGBA", (8, 8), (255, 255, 100, 200))
        return self._note_img

    def _get_critical_img(self):
        if self._critical_img is None:
            img = self.textures.get_mc_particle("critical_hit.png")
            self._critical_img = img if img is not None else Image.new("RGBA", (8, 8), (255, 100, 50, 220))
        return self._critical_img

    def emit(self, track_id: int, cx: float, cy: float, t: float,
             tsm, highlight, bs: float,
             is_critical: bool = False, card_alpha: float = 1.0,
             occluded: bool = False, intensity: float = 1.0):
        """在方块顶部生成音符粒子。受贴图按下 + 遮盖约束。

        intensity: 音频能量驱动（默认1.0）；越响亮喷发的粒子越多（最多 round(intensity) 颗）。
        """
        # 遮盖/暗化时绝不发射：被遮盖的方块不该迸发粒子
        if occluded or card_alpha < 0.25:
            return
        # 仅贴图处于'按下'英雄时刻才迸发（贴图与遮盖行为不同）
        if not tsm.is_active_at(t):
            return

        cap = self.MAX_CRIT_PER_TRACK if is_critical else self.MAX_PER_TRACK
        if self._count_by_track.get(track_id, 0) >= cap:
            return

        # 出生点：当前贴图(被按下缩小)盒子的顶边，让粒子'粘'在英雄动作上
        tex_scale = tsm.get_texture_scale(t)
        half = bs * tex_scale * 0.5
        spawn_x = cx + random.uniform(-half * 0.3, half * 0.3)
        spawn_y = cy - half - 3

        # 音频能量驱动：越响亮喷发越多（至少 1 颗，向上取整）
        n = max(1, int(round(intensity)))

        if is_critical:
            base_speed = random.uniform(70, 130) * (0.85 + 0.3 * intensity)
            for _ in range(n):
                angle = random.uniform(0, math.pi * 2)
                speed = base_speed * random.uniform(0.7, 1.1)
                self.particles.append(NoteParticle(
                    track_id=track_id, x=spawn_x, y=spawn_y,
                    vx=math.cos(angle) * speed, vy=math.sin(angle) * speed,
                    life=0.0, max_life=0.28, phase=_ParticlePhase.BURST,
                    critical=True, color=highlight, size=14.0,
                ))
                self._count_by_track[track_id] = self._count_by_track.get(track_id, 0) + 1
        else:
            for _ in range(n):
                angle = math.radians(random.uniform(60, 120))
                speed = random.uniform(35, 65)
                dirx = random.choice([-1, 1])
                self.particles.append(NoteParticle(
                    track_id=track_id, x=spawn_x, y=spawn_y,
                    vx=math.cos(angle) * speed * dirx, vy=-math.sin(angle) * speed,
                    life=0.0, max_life=random.uniform(self.MIN_LIFETIME, self.MAX_LIFETIME),
                    phase=_ParticlePhase.RISE, critical=False, color=None, size=20.0,
                ))
                self._count_by_track[track_id] = self._count_by_track.get(track_id, 0) + 1

    def update(self, dt: float):
        """显式相位状态机 + 半隐式欧拉积分（粒子数为数十级，逐粒子循环已足够快且状态清晰）。"""
        if not self.particles:
            return
        self._t += dt
        # 全局风场：让密集音符的粒子像星云一样横向流动
        wind_x = 10.0 * math.sin(self._t * 0.7) + 4.0 * math.sin(self._t * 1.9 + 1.1)

        alive = []
        for p in self.particles:
            p.life += dt
            if p.life >= p.max_life:
                self._count_by_track[p.track_id] = max(
                    0, self._count_by_track.get(p.track_id, 0) - 1)
                continue
            if p.phase == _ParticlePhase.BURST:
                # 径向爆发：无重力，带阻尼扩散
                p.vx *= (1 - 1.6 * dt)
                p.vy *= (1 - 1.6 * dt)
            else:
                p.vy += self.GRAVITY * dt
                if p.phase == _ParticlePhase.RISE and p.vy >= 0:
                    p.phase = _ParticlePhase.FALL
            p.x += (p.vx + wind_x) * dt
            p.y += p.vy * dt
            # 彗尾：仅普通粒子(RISE/FALL)记录；暴击为干净径向闪光，不留尾
            if p.phase != _ParticlePhase.BURST:
                p.trail.append((p.x, p.y))
                if len(p.trail) > self.TRAIL_LEN:
                    p.trail.pop(0)
            alive.append(p)
        self.particles = alive

    def draw(self, img: Image.Image, dim_tracks: Optional[set] = None):
        note_img = self._get_note_img()
        critical_img = self._get_critical_img()
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        for p in self.particles:
            lr = p.life / p.max_life
            if p.phase == _ParticlePhase.BURST:
                alpha = 1.0 - lr
                size = p.size * (1.0 + 0.5 * lr)
            elif p.phase == _ParticlePhase.RISE:
                alpha = min(1.0, lr / 0.15)          # 快速淡入
                size = p.size
            else:  # FALL
                alpha = max(0.0, 1.0 - (lr - 0.15) / 0.85)
                size = p.size
            if alpha <= 0.01:
                continue

            base_img = critical_img if p.critical else note_img
            sprite = base_img.resize((max(2, int(size)), max(2, int(size))),
                                     Image.Resampling.NEAREST)
            if p.color is not None:
                r, g, b = p.color[:3]
                tinted = Image.new("RGBA", sprite.size, (r, g, b, 0))
                tinted.paste(sprite, (0, 0), sprite)
                sprite = Image.blend(sprite, tinted, 0.6)

            # 遮盖(独奏暗化)下的轨道：粒子同步变暗
            dim = 0.3 if (dim_tracks is not None and p.track_id in dim_tracks) else 1.0

            # 彗尾（速度越快尾巴越亮越长）
            speed = math.hypot(p.vx, p.vy)
            tl = len(p.trail)
            for ti, (tx, ty) in enumerate(p.trail):
                frac = (ti + 1) / (tl + 1)
                t_alpha = (alpha * frac * 0.5
                           * min(1.0, max(0.5, speed / 100.0)) * dim)
                if t_alpha <= 0.01:
                    continue
                t_size = max(3, int(size * (0.35 + 0.55 * frac)))
                t_sprite = base_img.resize((t_size, t_size), Image.Resampling.NEAREST)
                t_mask = t_sprite.split()[3].point(
                    lambda xx: max(0, min(255, round(xx * t_alpha))))
                overlay.paste(t_sprite,
                              (int(tx) - t_size // 2, int(ty) - t_size // 2), t_mask)

            # 头部
            mask = sprite.split()[3].point(
                lambda xx: max(0, min(255, round(xx * alpha * dim))))
            overlay.paste(sprite,
                          (int(p.x) - sprite.width // 2, int(p.y) - sprite.height // 2),
                          mask)
        img.alpha_composite(overlay)


# ============== 背景粒子系统（NumPy 向量化 + 风场） ==============

class ParticleSystem:
    """背景粒子：固定数量，NumPy 数组向量化更新；叠加风场形成星云流动感。"""
    def __init__(self, textures: TextureCache):
        self.textures = textures
        from ._core import PARTICLE_COUNT
        self.count = PARTICLE_COUNT
        self.imgs = self.textures.get_particles()
        self._t = 0.0
        self._init_arrays(random_y=True)

    def _init_arrays(self, random_y=False):
        from ._core import (PARTICLE_SPEED_MIN, PARTICLE_SPEED_MAX,
                            PARTICLE_ALPHA_MIN, PARTICLE_ALPHA_MAX,
                            VIDEO_WIDTH, VIDEO_HEIGHT)
        n = self.count
        self.x = np.random.randint(0, VIDEO_WIDTH, size=n).astype(float)
        self.y = (np.random.randint(0, VIDEO_HEIGHT, size=n) if random_y
                  else np.full(n, VIDEO_HEIGHT + 20)).astype(float)
        self.speed = np.random.uniform(PARTICLE_SPEED_MIN, PARTICLE_SPEED_MAX, size=n)
        self.drift = np.random.uniform(-0.3, 0.3, size=n)
        self.sizef = np.random.uniform(0.4, 0.8, size=n)
        self.alpha = np.random.uniform(PARTICLE_ALPHA_MIN, PARTICLE_ALPHA_MAX, size=n)
        if self.imgs:
            self.img_idx = np.random.randint(0, len(self.imgs), size=n)
        else:
            self.img_idx = np.zeros(n, dtype=int)

    def update(self, dt: float):
        from ._core import VIDEO_HEIGHT
        self._t += dt
        # 风场：双频叠加的水平气流，营造缓慢流动/汇聚感
        wind = 12.0 * math.sin(self._t * 0.25) + 6.0 * math.sin(self._t * 0.6 + 1.3)
        self.y -= self.speed * dt * 30.0
        self.x += (self.drift * 30.0 + wind) * dt

        dead = self.y < -30
        if dead.any():
            from ._core import (PARTICLE_SPEED_MIN, PARTICLE_SPEED_MAX,
                                PARTICLE_ALPHA_MIN, PARTICLE_ALPHA_MAX,
                                VIDEO_WIDTH)
            nd = int(dead.sum())
            self.y[dead] = VIDEO_HEIGHT + 20
            self.x[dead] = np.random.randint(0, VIDEO_WIDTH, size=nd)
            self.speed[dead] = np.random.uniform(PARTICLE_SPEED_MIN, PARTICLE_SPEED_MAX, size=nd)
            self.drift[dead] = np.random.uniform(-0.3, 0.3, size=nd)
            self.sizef[dead] = np.random.uniform(0.4, 0.8, size=nd)
            self.alpha[dead] = np.random.uniform(PARTICLE_ALPHA_MIN, PARTICLE_ALPHA_MAX, size=nd)
            if self.imgs:
                self.img_idx[dead] = np.random.randint(0, len(self.imgs), size=nd)

    def draw(self, img: Image.Image):
        if not self.imgs:
            return
        for i in range(self.count):
            ii = int(self.img_idx[i])
            pimg = self.imgs[ii]
            pw = max(1, int(pimg.width * self.sizef[i]))
            ph = max(1, int(pimg.height * self.sizef[i]))
            sprite = pimg.resize((pw, ph), Image.Resampling.NEAREST)
            a = int(255 * self.alpha[i])
            px, py = int(self.x[i]), int(self.y[i])
            if a < 255:
                mask = sprite.split()[3].point(lambda xx: max(0, min(255, round(xx * self.alpha[i]))))
                img.paste(sprite, (px, py), mask)
            else:
                img.paste(sprite, (px, py), sprite)


# ============== Re-export（兼容现有导入） ==============
from .particle_effects import (  # noqa: E402
    EnchantGlint, CollectionParticles, _SleepParticleSystem, Crosshair,
)
