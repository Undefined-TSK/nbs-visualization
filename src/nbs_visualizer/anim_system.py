"""可打断的物理动画原语（类手机动画：随时改变目标值，平滑过渡、无间断、无顿挫）。

核心思想（对应手机动画的 interruptible 特性）：
  传统 time-based 补间在「开始/结束」或「目标中途改变」时会产生速度突变（顿挫感）。
  本模块用 **临界阻尼弹簧 (SmoothDamp)** 表示每个动画量：
    - 状态 = (value, velocity)，每帧用 dt 推进；
    - 只在需要时调用 set_target() 改变目标值；
    - 弹簧从「当前 value+velocity」平滑重收敛到新目标，位置与速度始终连续 (C1)。
  因此：
    - 起始 / 结束无顿挫（速度连续，没有突变）；
    - 动画进行中若目标再次改变（连续音符、密集区切换），从当前状态平滑接续，
      绝不跳变 —— 这就是「可打断」特性。
"""
from __future__ import annotations

import math


class SmoothAnim:
    """临界阻尼平滑动画标量（Unity SmoothDamp 实现，Game Programming Gems 4）。

    位置与速度连续（C1 连续）：对目标值的任意中间切换都不会产生跳变，
    天然支持「随时打断 / 改变状态参数」而保持连贯。
    """

    __slots__ = ("value", "target", "vel", "smooth_time", "max_speed")

    def __init__(self, value: float = 0.0, smooth_time: float = 0.12,
                 max_speed: float = 1e9):
        self.value = float(value)
        self.target = float(value)
        self.vel = 0.0
        # smooth_time 越小，收敛越快（响应越灵敏）；越大越柔和
        self.smooth_time = max(1e-4, float(smooth_time))
        self.max_speed = max(0.0, float(max_speed))

    def set_target(self, target: float) -> None:
        self.target = float(target)

    def snap(self, value: float) -> None:
        """瞬间设定当前值（无过渡），并清零速度。用于初始化对齐。"""
        self.value = float(value)
        self.target = float(value)
        self.vel = 0.0

    def advance(self, dt: float):
        """推进 dt 秒，更新 value/velocity。返回最新 value。

        dt<=0 时仅返回当前值，不推进（避免重复帧破坏连续性）。
        """
        if dt <= 0.0:
            return self.value
        # 临界阻尼：omega = 2 / smooth_time
        omega = 2.0 / self.smooth_time
        x = omega * dt
        # SmoothDamp 的归一化系数（保证无超调、速度连续）
        exp = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)
        change = self.value - self.target
        temp = (self.vel + omega * change) * dt
        self.vel = (self.vel - omega * temp) * exp
        self.value = self.target + (change + temp) * exp

        # 限速（极端 dt 或超大目标差时防止数值爆裂）
        if self.max_speed < 1e8:
            if self.vel > self.max_speed:
                self.vel = self.max_speed
            elif self.vel < -self.max_speed:
                self.vel = -self.max_speed
        return self.value

    def get_velocity(self) -> float:
        return self.vel
