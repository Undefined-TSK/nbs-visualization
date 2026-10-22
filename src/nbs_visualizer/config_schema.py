"""
类型安全的渲染配置（pydantic）。

集中管理跨模块共享的渲染常量，作为单一事实来源（Single Source of Truth）。
`_core` 模块的全局常量都从本配置派生，既保证类型安全，又保持
`from ._core import FPS` 等旧导入向后兼容。

可通过 JSON 文件覆盖默认值（见 RenderConfig.load）。
"""
from __future__ import annotations

import json
import os
from typing import Tuple

from pydantic import BaseModel, Field


class RenderConfig(BaseModel):
    # ---------- 视频基础 ----------
    video_width: int = Field(1920, ge=1, le=7680)
    video_height: int = Field(1080, ge=1, le=4320)
    fps: int = Field(120, ge=1, le=240, description="原 60，改为 120 大幅提升动画丝滑度")

    # ---------- 背景点阵 ----------
    bg_color: Tuple[int, int, int] = (228, 228, 234)
    dot_color: Tuple[int, int, int] = (200, 200, 210)
    dot_spacing: int = 22
    dot_radius: int = 2  # 点阵半径，FIXED-B4 问题15 从 1 提高到 2 增强可见度

    # ---------- 频谱 ----------
    spectrum_bars: int = 32
    spectrum_bars_per_edge: int = 8
    spectrum_bar_width: int = 5
    spectrum_bar_min_height: int = 2
    spectrum_smooth_factor: float = 0.92
    spectrum_step: float = 0.03
    spectrum_active_boost: float = 1.6

    # ---------- 摄像机 ----------
    camera_enabled: bool = True

    # ---------- 粒子（浅色背景上的微妙粒子）----------
    particle_count: int = 20
    particle_speed_min: int = 3
    particle_speed_max: int = 10
    particle_size_min: int = 1
    particle_size_max: int = 3
    particle_alpha_min: float = 0.08
    particle_alpha_max: float = 0.22

    # ---------- 文字 ----------
    text_stroke_width: int = 1
    label_font_ratio: float = 0.13

    @classmethod
    def load(cls, path: "str | None" = None) -> "RenderConfig":
        """从 JSON 文件（可选）加载配置；缺失/非法字段回退默认值。"""
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls.model_validate(data)
            except Exception as e:  # noqa: BLE001
                from .logger import get_logger
                get_logger(__name__).warning("RenderConfig 加载失败，使用默认值: %s", e)
        return cls()


# 全局单例：单一事实来源。所有模块通过 `from .config_schema import CONFIG` 或
# `from ._core import FPS` 等派生常量访问。可用 RenderConfig.load("config.json") 覆盖。
CONFIG = RenderConfig.load()
