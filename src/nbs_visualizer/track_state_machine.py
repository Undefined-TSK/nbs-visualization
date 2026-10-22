"""逐轨状态机：管理单个轨道的 playing/resting 状态、alpha、阴影/边框/角标 lerp 过渡、活动度平滑。"""
from __future__ import annotations

import bisect
import math
from typing import List, Optional, Tuple, Dict

from .logger import get_logger

from .utils import clamp, lerp, ease_out_cubic, ease_press, ease_out_back, ease_in_out_cubic
from .stage_constants import (
    RESTING_THRESHOLD, STATE_TRANSITION_DURATION, CARD_BORDER_INACTIVE,
    OUTRO_WAIT_DURATION, OUTRO_FADEOUT_DURATION,
    BLOCK_PRESSED_SCALE, BLOCK_PRESS_DURATION, BLOCK_RELEASE_DURATION,
    DENSE_RECOVERY, DENSE_CYCLE, DENSE_MASK_PRESSED, DENSE_GAUSSIAN_SIGMA,
    DENSE_HOLD_PAD, DENSE_OSC_SIGMA, MASK_LAG, MASK_PRESS_SCALE,
    MASK_SMOOTH_TIME, TEX_SMOOTH_TIME, DEFORM_VEL_GAIN, DEFORM_MAX,
    MASK_DEFORM_VEL_GAIN,
    CARD_SHADOW_COLOR,
)
from .track_data import TrackData
from .anim_system import SmoothAnim

logger = get_logger(__name__)


def _smooth01(p: float) -> float:
    """smoothstep：把 p∈[0,1] 映射到 0→1 的 S 曲线（用于振荡淡入淡出）。"""
    p = clamp(p, 0.0, 1.0)
    return p * p * (3.0 - 2.0 * p)


class TrackStateMachine:
    """管理单个轨道的 playing/resting 状态、alpha、阴影/边框/角标 lerp 过渡、活动度平滑。
    将原 StaticGroupLayout 中的状态管理 + FrameRenderer 中的阴影/边框/角标/活动度状态整合为单一类。
    """
    def __init__(self, track: TrackData, audio_end_time: float = 0.0,
                 threshold: float = RESTING_THRESHOLD,
                 transition_duration: float = STATE_TRANSITION_DURATION):
        self.track = track
        self.audio_end_time = audio_end_time
        self.threshold = threshold
        self.transition_duration = transition_duration

        # 预计算音符时间
        self._note_times: List[float] = sorted(set(n[0] for n in track.notes))

        # 状态机
        has_early = any(nt <= 1.0 for nt in self._note_times)
        self.state = "playing" if has_early else "resting"
        self._trans_start: float = -1.0
        self._trans_from: float = 1.0 if has_early else 0.5

        # 阴影 lerp 状态
        self._shadow_off: int = 1
        self._shadow_alpha: int = 10

        # 边框 lerp 状态
        self._border_color: Tuple[int, int, int, int] = CARD_BORDER_INACTIVE

        # 角标 lerp 状态
        self._corner_color: Tuple[int, int, int, int] = (80, 85, 105, 250)

        # 活动度平滑状态
        self._activity_smoothed: float = 0.0

        # ===== 可打断动画系统（类手机物理动画）=====
        # 临界阻尼弹簧：位置与速度连续 (C1)，目标可随时改变而绝不跳变
        # → 起始/结束无顿挫、动画进行中可被新音符/密集区打断而平滑接续。
        self._tex_scale = SmoothAnim(1.0, smooth_time=TEX_SMOOTH_TIME)
        self._mask_env = SmoothAnim(1.0, smooth_time=MASK_SMOOTH_TIME)
        # 预计算按下窗口 / 密集区边界，支持 O(log n) 查询，避免逐帧线性扫描
        self._pstarts = sorted(ev[0] for ev in track.press_events)
        self._pends = {ev[0]: ev[1] for ev in track.press_events}
        self._dstarts = sorted(s for s, e in track.dense_regions)
        self._dends = {s: e for s, e in track.dense_regions}

    def update_state(self, t: float):
        """更新 playing/resting 状态转换。"""
        times = self._note_times
        if self.state == "playing":
            idx = bisect.bisect_right(times, t)
            last_note = times[idx - 1] if idx > 0 else 0.0
            if t - last_note > self.threshold and t > 0:
                self.state = "resting"
                self._trans_start = t
                self._trans_from = 1.0
        elif self.state == "resting":
            idx = bisect.bisect_left(times, t - 0.05)
            if idx < len(times) and times[idx] <= t + 0.05:
                self.state = "playing"
                self._trans_start = t
                self._trans_from = 0.5

    def get_alpha(self, t: float) -> float:
        """返回透明度: 1.0=完全可见, 0.5=半透明(resting), 0.0=不可见。"""
        target = 1.0 if self.state == "playing" else 0.5

        if self._trans_start >= 0 and (t - self._trans_start) < self.transition_duration:
            p = clamp((t - self._trans_start) / self.transition_duration, 0, 1)
            base = self._trans_from + (target - self._trans_from) * ease_in_out_cubic(p)
        else:
            base = target

        # 尾奏3阶段（HC#18: 衰减3.0s → 淡出2.0s → 缓冲0.5s）
        if self.audio_end_time > 0 and t > self.audio_end_time:
            dt = t - self.audio_end_time
            decay_end = OUTRO_WAIT_DURATION        # 衰减阶段结束: 3.0s
            fadeout_end = decay_end + OUTRO_FADEOUT_DURATION  # 淡出阶段结束: 5.0s

            if dt < decay_end:
                # 衰减阶段 3.0s：从当前alpha → 70%当前alpha（smoothstep）
                p = dt / decay_end
                p = clamp(p, 0, 1)
                p = 3 * p * p - 2 * p * p * p  # smoothstep
                base = lerp(base, base * 0.7, p)
            elif dt < fadeout_end:
                # 淡出阶段 2.0s：从70%当前alpha → 0.0
                decayed = base * 0.7
                p = clamp((dt - decay_end) / OUTRO_FADEOUT_DURATION, 0, 1)
                p = 3 * p * p - 2 * p * p * p  # smoothstep
                base = lerp(decayed, 0.0, p)
            else:
                # 缓冲阶段：完全透明
                base = 0.0

        return base

    def get_outro_effects(self, t: float) -> Tuple[float, float]:
        """返回 (dy, scale) 尾奏漂移和收缩（HC#18: 0→5→12px, 100%→97%→93%）。"""
        if self.audio_end_time <= 0 or t <= self.audio_end_time:
            return 0.0, 1.0

        dt = t - self.audio_end_time
        decay_end = OUTRO_WAIT_DURATION       # 衰减阶段结束: 3.0s
        fadeout_end = decay_end + OUTRO_FADEOUT_DURATION  # 淡出阶段结束: 5.0s

        if dt < decay_end:
            # 衰减阶段 3.0s: 0 → 5px, 100% → 97%
            p = dt / decay_end
            p = clamp(p, 0, 1)
            p = 3 * p * p - 2 * p * p * p  # smoothstep
            return -5 * p, lerp(1.0, 0.97, p)
        elif dt < fadeout_end:
            # 淡出阶段 2.0s: 5 → 12px, 97% → 93%
            p = clamp((dt - decay_end) / OUTRO_FADEOUT_DURATION, 0, 1)
            p = 3 * p * p - 2 * p * p * p
            return -5 - 7 * p, lerp(0.97, 0.93, p)
        else:
            # 缓冲阶段：保持最终值
            return -12.0, 0.93

    def update_visual(self, t: float, dt: float, is_active: bool,
                      is_solo: bool = False, solo_alpha: float = 0.0,
                      palette: Optional[Dict] = None):
        """更新阴影/边框/角标 lerp 过渡和活动度平滑。"""
        is_playing = self.state == "playing"

        # 阴影 lerp (0.2s)
        target_off = 3 if is_playing else 1
        target_alpha = CARD_SHADOW_COLOR[3] if is_playing else 10
        if is_solo and solo_alpha > 0.01:
            sa = solo_alpha
            target_off = int(target_off * (1 - sa) + 8 * sa)
            target_alpha = int(target_alpha * (1 - sa) + 50 * sa)
        shadow_smooth = 1.0 - math.exp(-dt / 0.2)
        self._shadow_off = int(self._shadow_off + (target_off - self._shadow_off) * shadow_smooth)
        self._shadow_alpha = int(self._shadow_alpha + (target_alpha - self._shadow_alpha) * shadow_smooth)

        # 边框 lerp (0.3s)
        if palette is not None:
            if is_playing:
                target_border = palette["hl"] if is_active else (palette["hl"][0], palette["hl"][1], palette["hl"][2], 102)
            else:
                target_border = CARD_BORDER_INACTIVE
            border_smooth = 1.0 - math.exp(-dt / 0.3)
            self._border_color = tuple(
                int(self._border_color[i] + (target_border[i] - self._border_color[i]) * border_smooth)
                for i in range(4)
            )

            # 角标 lerp (0.3s)
            if is_playing and is_active:
                target_corner = palette["hl"][:3] + (250,)
            elif is_playing:
                target_corner = palette["hl"][:3] + (180,)
            else:
                target_corner = (80, 85, 105, 250)
            self._corner_color = tuple(
                int(self._corner_color[i] + (target_corner[i] - self._corner_color[i]) * border_smooth)
                for i in range(4)
            )

        # 活动度平滑 (0.3s)
        raw_activity = self.get_activity_ratio(t)
        smooth_factor = 1.0 - math.exp(-dt / 0.3)
        self._activity_smoothed += (raw_activity - self._activity_smoothed) * smooth_factor

    def get_shadow(self) -> Tuple[int, int]:
        """返回 (offset, alpha)，已 lerp 过渡。"""
        return (self._shadow_off, self._shadow_alpha)

    def get_border_color(self) -> Tuple[int, int, int, int]:
        """返回当前边框颜色，已 lerp 过渡。"""
        return self._border_color

    def get_corner_color(self) -> Tuple[int, int, int, int]:
        """返回当前角标颜色，已 lerp 过渡。"""
        return self._corner_color

    def get_activity(self) -> float:
        """返回指数平滑后的活动度。"""
        return self._activity_smoothed

    # ============== 动画方法（每个卡片独立的时间线） ==============

    # ============== 可打断动画系统（临界阻尼弹簧 + 遮盖延迟 + 密集区高速振荡） ==============
    #
    # 设计要点（对应用户动画规范）：
    # ① 贴图(英雄)缩放由弹簧驱动，目标 = 0.80(按下/密集) / 1.0(静止)。
    # ② 挤压拉伸(squash/stretch)由弹簧"速度"推导 → 只在按下/回弹的过渡瞬间出现，
    #    保持期/等待期速度≈0 → 自动归零恢复正方形（无持续变形，无顿挫）。
    # ③ 遮盖层比贴图"慢半拍"：其目标在贴图的按下/静止状态基础上整体后移 MASK_LAG 秒，
    #    因此遮盖的按下、回弹永远比贴图晚一点点（步骤1/3/4 都有延迟感）。
    # ④ 密集区保持段：贴图静止于 0.80(正方形)；遮盖在该段做"高速高斯振荡"
    #    （直接解析驱动，不经弹簧低通→保留高频），从环 0.90 脉冲到 0.50，清晰可见。

    def _tex_target(self, t: float) -> float:
        """贴图目标缩放（解析、无平滑）：密集区或按下窗口内为按下 0.80，否则 1.0。"""
        for (ds, de) in self.track.dense_regions:
            if ds <= t <= de:
                return BLOCK_PRESSED_SCALE
        for (ps, pe) in self.track.press_events:
            if ps <= t <= pe:
                return BLOCK_PRESSED_SCALE
        return 1.0

    def _mask_env_target(self, t: float) -> float:
        """遮盖层"包络"目标缩放（解析）：比贴图整体后移 MASK_LAG 秒 → 慢半拍。

        - 密集区：遮盖形成环 DENSE_RECOVERY(0.90)，窗口 [ds+LAG, de+LAG]；
        - 非密集区按下：遮盖略大于贴图(MASK_PRESS_SCALE=0.85)以露出细环，窗口 [ps+LAG, pe+LAG]；
        - 其余：1.0（与贴图同大→无环）。
        """
        lag = MASK_LAG
        for (ds, de) in self.track.dense_regions:
            if ds + lag <= t <= de + lag:
                return DENSE_RECOVERY
        for (ps, pe) in self.track.press_events:
            if ps + lag <= t <= pe + lag:
                return MASK_PRESS_SCALE
        return 1.0

    def _mask_oscillation(self, t: float) -> float:
        """密集区"保持段"的高速高斯振荡强度 0..1（直接解析，不经弹簧→保留高频）。

        仅在 [ds+DENSE_HOLD_PAD, de-DENSE_HOLD_PAD] 内非零；周期 DENSE_CYCLE，
        每周期一个高斯凸起；窗口两端平滑 ramp 进出，避免突跳。
        """
        pad = DENSE_HOLD_PAD
        for (ds, de) in self.track.dense_regions:
            hs = ds + pad
            he = de - pad
            if hs <= t <= he:
                cycle = DENSE_CYCLE
                local = t - hs
                frac = (local % cycle) / cycle          # 0..1
                x = frac - 0.5
                pulse = math.exp(-(x * x) / (2.0 * DENSE_OSC_SIGMA * DENSE_OSC_SIGMA))
                # 两端 ramp（各 1 个周期）平滑进出，避免突跳
                ramp = 1.0
                if local < cycle:
                    ramp = min(ramp, _smooth01(local / cycle))
                tail = he - t
                if tail < cycle:
                    ramp = min(ramp, _smooth01(tail / cycle))
                return pulse * ramp
        return 0.0

    def advance_anim(self, t: float, dt: float):
        """推进可打断动画弹簧：目标随时可变，弹簧从当前 value+velocity 平滑重收敛。"""
        self._tex_scale.set_target(self._tex_target(t))
        self._mask_env.set_target(self._mask_env_target(t))
        self._tex_scale.advance(dt)
        self._mask_env.advance(dt)

    def get_texture_scale(self, t: float) -> float:
        """贴图缩放（标量），由弹簧驱动。"""
        return self._tex_scale.value

    # 挤压拉伸（Squash & Stretch）：由弹簧"速度"推导，仅在过渡瞬间出现、保持期归零
    # —— 这保证了"按下/回弹同步进行，之后变形过渡结束恢复正方形"的规范。
    def get_squash(self, t: float):
        """返回贴图 (sx, sy) 形变因子。

        弹簧值下降(按下, vel<0) → 压扁(宽而矮)；弹簧值上升(回弹, vel>0) → 拉伸(窄而高)；
        到达保持/静止(vel≈0) → 无形变(正方形)。全程 C1 连续、无顿挫、可随时打断。
        """
        scale = self._tex_scale.value
        v = self._tex_scale.vel
        # e>0: 压扁(宽矮); e<0: 拉伸(窄高)
        e = clamp(-v * DEFORM_VEL_GAIN, -DEFORM_MAX, DEFORM_MAX)
        return scale * (1.0 + e), scale * (1.0 - e)

    def get_mask_scale(self, t: float) -> float:
        """灰色蒙版缩放：包络(弹簧, 慢半拍) + 密集区保持段高速高斯振荡(直接解析)。"""
        osc = self._mask_oscillation(t)
        return lerp(self._mask_env.value, DENSE_MASK_PRESSED, osc)

    def get_mask_squash(self, t: float):
        """返回遮盖层 (msx, msy) 形变因子——比贴图克制，由遮盖自身弹簧速度推导（慢半拍）。"""
        v = self._mask_env.vel
        e = clamp(-v * MASK_DEFORM_VEL_GAIN, -0.06, 0.06)
        scale = self.get_mask_scale(t)   # 已含振荡
        return scale * (1.0 + e), scale * (1.0 - e)

    def is_active_at(self, t: float) -> bool:
        """判断当前时刻是否处于按下状态。"""
        for (ps, pe) in self.track.press_events:
            if ps <= t <= pe:
                return True
        return False

    def get_activity_ratio(self, t: float, window: float = 2.0) -> float:
        """计算活动度。"""
        starts = self.track.note_starts
        if not starts:
            return 0.0
        lo = t - window
        hi = t
        import bisect as _b
        left = _b.bisect_left(starts, lo)
        right = _b.bisect_right(starts, hi)
        return clamp((right - left) / window, 0.0, 1.0)
