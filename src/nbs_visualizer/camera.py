"""摄像机系统：脚本解析、镜头运动、呼吸/摇臂/巡视、节拍驱动的导演级运镜。"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple, Dict, Any

import numpy as np

from .utils import clamp, lerp, ease_out_cubic, ease_in_cubic

class CameraController:
    """
    摄像机控制器：根据 Kimi 镜头脚本驱动镜头运动。
    - 有 Kimi 脚本时：以脚本为主导，并叠加节拍脉冲/震动
    - 无 Kimi 脚本时：退化为"自动导演"模式（前奏推远→节拍崩溃推近→平静环绕）
    增强功能：平移呼吸、摇臂效果、全景巡视、节拍 Crash Zoom、低频 Shake、平静 Orbit。
    """

    ZOOM_WIDE = 1.0
    ZOOM_GROUP = 1.25
    ZOOM_CLOSE = 1.55
    SMOOTH_FACTOR = 0.08
    BREATH_AMP = 0.006

    # 平移呼吸参数（持续漂移是眩晕主因，已压到极轻微）
    PAN_BREATH_AMP_X = 1.5
    PAN_BREATH_PERIOD_X = 14.0
    PAN_BREATH_AMP_Y = 1.0
    PAN_BREATH_PERIOD_Y = 11.0

    # 全景巡视参数 (Lissajous)（已压到极轻微，仅保留极缓慢的镜头流动）
    PATROL_AMP_X = 4.0
    PATROL_PERIOD_X = 18.0
    PATROL_AMP_Y = 2.0
    PATROL_PERIOD_Y = 23.0

    # 摇臂效果参数
    ROCKER_ANTICIPATE_DUR = 0.3
    ROCKER_ANTICIPATE_AMP = 7.0
    ROCKER_PUSH_DUR = 0.8
    ROCKER_SETTLE_DUR = 0.5
    ROCKER_SETTLE_AMP = 2.5

    # ===== 导演级运镜参数 =====
    CRASH_GAIN = 0.35        # 节拍命中时最大额外推近 (+35% zoom)
    SHAKE_AMP = 6.0          # 震动最大位移 (px)，已下调以避免"过度抖动/晃动"
    SHAKE_FREQ = 20.0        # 震动摆动角频率 (rad/s)，稍慢更耐看
    SHAKE_MIN_STRENGTH = 0.35  # 仅中强拍才触发震动，弱音不抖
    INTRO_DUR = 4.0          # 前奏推远持续 (s)
    INTRO_ZOOM = 0.92        # 前奏最远 (略小于1=看见更多)
    ORBIT_AMP = 5.0          # 环绕平移幅度 (px)，已下调避免持续环绕引发的眩晕
    ORBIT_SPEED = 0.20       # 环绕角速度 (rad/s)，稍慢更耐看
    CALM_THRESHOLD = 2       # 0.4s 内命中数低于此值判定为平静段
    BEAT_PAD = 0.05          # 节拍命中判定窗口 (s)

    def __init__(self, tracks: List[TrackData], layout,
                 kimi_script: Optional[Dict] = None,
                 stage: Optional['StaticGroupLayout'] = None):
        self.tracks = tracks
        self.layout = layout
        self.script = kimi_script
        self.stage = stage
        from ._core import CAMERA_ENABLED, VIDEO_WIDTH, VIDEO_HEIGHT
        self.enabled = CAMERA_ENABLED

        self.current_zoom = self.ZOOM_WIDE
        self.current_x = VIDEO_WIDTH / 2
        self.current_y = VIDEO_HEIGHT / 2

        self.target_zoom = self.ZOOM_WIDE
        self.target_x = VIDEO_WIDTH / 2
        self.target_y = VIDEO_HEIGHT / 2

        # 摇臂效果状态
        self._rocker_start_time = -10.0
        self._rocker_active = False
        self._prev_cam_type = "wide"

        # 节拍驱动的导演状态
        self._zoom_pulse = 0.0   # 崩溃推近脉冲 (0~1，逐帧衰减)
        self._shake = 0.0        # 震动强度 (0~1，逐帧衰减)
        self._shake_ang = 0.0    # 本次命定的震动方向（连贯，不逐帧随机）
        self._last_beat = -10.0  # 上次触发节拍时间（防抖重触发）
        self._shake_phase = 0.0   # 震动相位累加器（帧率无关，保证连贯）
        self._last_t = 0.0        # 上一帧时间，用于计算 dt

        # 预计算节拍时间轴（所有音轨的 note_starts，单位秒）
        all_b: List[float] = []
        for tr in self.tracks:
            ns = getattr(tr, "note_starts", None)
            if ns:
                all_b.extend(ns)
        self._beats = np.array(sorted(all_b), dtype=float) if all_b else np.array([])

    def _get_group_center(self, group_idx: int, t: float = 0) -> Tuple[float, float]:
        if self.stage and group_idx < len(self.stage.group_bounds):
            gb = self.stage.group_bounds[group_idx]
            center_x = gb["label_x"] + gb.get("label_w", 0) / 2
            center_y = (gb.get("y_top", 0) + gb.get("y_bottom", 0)) / 2
            return float(center_x), float(center_y)
        xs, ys = [], []
        for tr in self.tracks:
            if tr.group_index != group_idx:
                continue
            if self.stage:
                pos = self.stage.get_position(tr.layer_id, t)
            else:
                pos = self.layout.get_position(tr.layer_id)
            xs.append(float(pos[0]))
            ys.append(float(pos[1]))
        if not xs:
            from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
            return VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2
        return sum(xs) / len(xs), sum(ys) / len(ys)

    def _get_track_center(self, layer_id: int, t: float = 0) -> Tuple[float, float]:
        if self.stage:
            pos = self.stage.get_position(layer_id, t)
            return float(pos[0]), float(pos[1])
        pos = self.layout.get_position(layer_id)
        return float(pos[0]), float(pos[1])

    def _get_script_camera(self, t: float) -> Tuple[str, Any]:
        if not self.script or "cameras" not in self.script:
            return "wide", "all"

        cameras = self.script["cameras"]
        current = cameras[0] if cameras else None
        for cam in cameras:
            if cam.get("time", 0) <= t:
                current = cam
            else:
                break

        if not current:
            return "wide", "all"
        return current.get("type", "wide"), current.get("focus", "all")

    def _beat_info(self, t: float) -> Tuple[bool, float]:
        """检测 t 附近是否有节拍命中，返回 (is_hit, strength∈[0,1])。"""
        if self._beats.size == 0:
            return False, 0.0
        lo = t - self.BEAT_PAD
        hi = t + self.BEAT_PAD
        idx = int(np.searchsorted(self._beats, lo))
        cnt = 0
        while idx < self._beats.size and self._beats[idx] <= hi:
            cnt += 1
            idx += 1
        if cnt == 0:
            return False, 0.0
        # 局部密度（0.15s 窗口）增强强度
        d0 = int(np.searchsorted(self._beats, t - 0.15))
        d1 = int(np.searchsorted(self._beats, t + 0.15))
        density = d1 - d0
        strength = clamp(cnt / 2.0, 0.2, 1.0) * clamp(density / 6.0, 0.4, 1.0)
        return True, strength

    def _density(self, t: float) -> int:
        """返回 t 前 0.4s 内的节拍数（用于判定平静段）。"""
        if self._beats.size == 0:
            return 0
        i0 = int(np.searchsorted(self._beats, t - 0.4))
        i1 = int(np.searchsorted(self._beats, t))
        return i1 - i0

    def _compute_target(self, t: float) -> Tuple[float, float, float]:
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        cam_type, focus = self._get_script_camera(t)

        if cam_type == "close" and isinstance(focus, (int, float)):
            if self.stage and self.stage.get_alpha(int(focus), t) < 0.3:
                cx, cy = VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2
                zoom = self.ZOOM_WIDE
            else:
                cx, cy = self._get_track_center(int(focus), t)
                zoom = self.ZOOM_CLOSE
        elif cam_type == "group" and isinstance(focus, int) and 0 <= focus <= 7:
            cx, cy = self._get_group_center(focus, t)
            zoom = self.ZOOM_GROUP
        else:
            cx, cy = VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2
            zoom = self.ZOOM_WIDE

        return zoom, cx, cy

    def _compute_rocker_offset(self, t: float) -> Tuple[float, float]:
        """摇臂效果：idle→anticipate→push→settle。返回 (dx, dy) 偏移。"""
        elapsed = t - self._rocker_start_time
        if elapsed < 0:
            return 0.0, 0.0

        if elapsed < self.ROCKER_ANTICIPATE_DUR:
            p = elapsed / self.ROCKER_ANTICIPATE_DUR
            # FIXED-B4: 问题38 - 预备阶段用ease_in_cubic(p)替代线性p，蓄力感更强
            amp = self.ROCKER_ANTICIPATE_AMP * ease_in_cubic(p)
            return -amp, -amp * 0.5
        elif elapsed < self.ROCKER_ANTICIPATE_DUR + self.ROCKER_PUSH_DUR:
            p = (elapsed - self.ROCKER_ANTICIPATE_DUR) / self.ROCKER_PUSH_DUR
            ease = 1 - (1 - p) ** 3
            amp = -self.ROCKER_ANTICIPATE_AMP + (self.ROCKER_ANTICIPATE_AMP * 2) * ease
            return amp, amp * 0.5
        elif elapsed < self.ROCKER_ANTICIPATE_DUR + self.ROCKER_PUSH_DUR + self.ROCKER_SETTLE_DUR:
            p = (elapsed - self.ROCKER_ANTICIPATE_DUR - self.ROCKER_PUSH_DUR) / self.ROCKER_SETTLE_DUR
            ease = math.sin(p * math.pi)
            amp = self.ROCKER_SETTLE_AMP * ease
            return amp, amp * 0.5
        else:
            return 0.0, 0.0

    def update(self, t: float, audio_energy: float = 0.0):
        """更新镜头状态（目标计算、呼吸、摇臂、指数平滑 + 导演级节拍运镜）。

        audio_energy: 来自真实音频(0..1)的瞬时能量，响亮处额外推近镜头，
        实现"声音驱动运镜"——不依赖 Kimi 脚本也能随音乐起伏。
        """
        if not self.enabled:
            return

        cam_type, _ = self._get_script_camera(t)

        # 检测镜头类型切换 → 触发摇臂
        if cam_type != self._prev_cam_type:
            if cam_type == "close":
                self._rocker_start_time = t
                self._rocker_active = True
            self._prev_cam_type = cam_type

        target_zoom, target_x, target_y = self._compute_target(t)

        # 缩放呼吸
        breath = math.sin(t * 2 * math.pi / 12.0) * self.BREATH_AMP
        target_zoom += breath

        # 平移呼吸（与缩放呼吸不同周期，产生非周期复合）
        pan_breath_x = math.sin(t * 2 * math.pi / self.PAN_BREATH_PERIOD_X) * self.PAN_BREATH_AMP_X
        pan_breath_y = math.sin(t * 2 * math.pi / self.PAN_BREATH_PERIOD_Y) * self.PAN_BREATH_AMP_Y

        # 全景巡视（Lissajous曲线，仅在wide时叠加）
        if cam_type == "wide":
            patrol_x = math.sin(t * 2 * math.pi / self.PATROL_PERIOD_X) * self.PATROL_AMP_X
            patrol_y = math.sin(t * 2 * math.pi / self.PATROL_PERIOD_Y * 2) * self.PATROL_AMP_Y
        else:
            patrol_x = 0.0
            patrol_y = 0.0

        # 摇臂偏移
        if self._rocker_active:
            r_dx, r_dy = self._compute_rocker_offset(t)
            if r_dx == 0 and r_dy == 0 and (t - self._rocker_start_time) > (
                self.ROCKER_ANTICIPATE_DUR + self.ROCKER_PUSH_DUR + self.ROCKER_SETTLE_DUR
            ):
                self._rocker_active = False
        else:
            r_dx, r_dy = 0.0, 0.0

        # ============ 导演级节拍运镜（附加层）============
        dt = max(0.0, min(0.1, t - self._last_t))
        self._last_t = t

        beats_hit, strength = self._beat_info(t)
        if beats_hit and strength >= self.SHAKE_MIN_STRENGTH and (t - self._last_beat) > 0.12:
            self._last_beat = t
            # 命中即注入脉冲；强拍叠加强度
            self._zoom_pulse = min(1.0, self._zoom_pulse + 0.6 * strength)
            self._shake = min(1.0, self._shake + 0.7 * strength)
            # 连贯关键：仅当上一轮震动已基本消退(<0.15)时才重新选定方向，
            # 否则保持原方向——避免每 0.08s 重随机导致 12 次/秒方向跳变(原"疯抖"根因)。
            if self._shake < 0.15:
                self._shake_ang = random.uniform(0, 2 * math.pi)
        # 脉冲逐帧衰减（约 0.1~0.2s 内消退）
        self._zoom_pulse *= 0.86
        self._shake *= 0.82
        # 实时音频能量驱动：响亮处额外推近（声音驱动运镜，独立于节拍/Kimi）
        if audio_energy > 0.12:
            self._zoom_pulse = min(1.0, self._zoom_pulse + audio_energy * 0.45)
        # 相位累加器：帧率无关，保证 120fps / 60fps 下振荡周期一致
        self._shake_phase += self.SHAKE_FREQ * dt

        # Crash Zoom：脉冲瞬间推近特写
        if self._zoom_pulse > 0.001:
            target_zoom *= (1.0 + self._zoom_pulse * self.CRASH_GAIN)
        # Shake：沿"选定方向"做阻尼正弦摆动（相位连续→连贯，不再逐次乱跳）
        if self._shake > 0.01:
            wob = math.sin(self._shake_phase)
            r = self._shake * self.SHAKE_AMP * wob
            target_x += math.cos(self._shake_ang) * r
            target_y += math.sin(self._shake_ang) * r

        # 无脚本（自动导演）专属：前奏推远 + 平静段环绕 Orbit
        if not self.script or "cameras" not in self.script:
            if t < self.INTRO_DUR:
                intro = lerp(self.INTRO_ZOOM, 1.0, clamp(t / self.INTRO_DUR, 0.0, 1.0))
                target_zoom *= intro
            density = self._density(t)
            if density < self.CALM_THRESHOLD and self._zoom_pulse < 0.05:
                # 环绕 Orbit：绕画面中心做缓慢圆周平移，制造呼吸式镜头流动
                ox = math.cos(t * self.ORBIT_SPEED) * self.ORBIT_AMP
                oy = math.sin(t * self.ORBIT_SPEED) * self.ORBIT_AMP * 0.6
                target_x += ox
                target_y += oy
        # ================================================

        # 叠加呼吸和巡视到目标位置
        target_x += pan_breath_x + patrol_x + r_dx
        target_y += pan_breath_y + patrol_y + r_dy

        # 指数平滑
        self.current_zoom += (target_zoom - self.current_zoom) * self.SMOOTH_FACTOR
        self.current_x += (target_x - self.current_x) * self.SMOOTH_FACTOR
        self.current_y += (target_y - self.current_y) * self.SMOOTH_FACTOR

    def get_transform(self) -> Tuple[float, float, float]:
        """返回 (zoom, pan_x, pan_y)。"""
        if not self.enabled:
            return 1.0, 0.0, 0.0

        zoom = self.current_zoom
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        pan_x = self.current_x - zoom * (VIDEO_WIDTH / 2)
        pan_y = self.current_y - zoom * (VIDEO_HEIGHT / 2)

        return zoom, pan_x, pan_y


# 向后兼容别名
SmartCamera = CameraController
