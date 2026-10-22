"""
NBS Visualizer v4 — Minecraft Note Block 音乐可视化引擎
- 卡片式网格布局（每轨 = 一个 MC 贴图方块 + 卡片框）
- 按声部角色排序的严格网格，所有方块大小间距统一
- 方形频谱排列（沿贴图4边向外生长，5-6px空隙）
- 浅色点阵背景（现代UI风格）
- 白色虚线缝线边框 + 四角L型角标
- 统一文字标签（右上角=声部角色，左下角=乐器名），在贴图图层之上
- 方块按下/弹开非线性动画
- 像素艺术整数缩放（最近邻插值，仅用new贴图）
- Kimi API 声部角色名翻译（本地映射优先 + API fallback）
"""

import os
import math
import bisect
import random
import re
from typing import List, Dict, Optional, Tuple, Any

import numpy as np
import pynbs
from PIL import Image, ImageDraw, ImageFont

import cv2

from . import config

# ============== CONFIG ==============
# 类型安全配置：单一事实来源（pydantic）。所有标量常量从 CONFIG 派生，
# 既保证类型安全，又保持 `from ._core import FPS` 等旧导入兼容。
from .config_schema import RenderConfig, CONFIG
VIDEO_WIDTH = CONFIG.video_width
VIDEO_HEIGHT = CONFIG.video_height
FPS = CONFIG.fps  # 原为 60，改为 120 可大幅提升动画丝滑度

from .stage import (
    TrackData, LayoutEngine, StaticGroupLayout, extract_tracks, translate_role_name_local, get_role_group, _optimal_cols,
    _merge_tracks, compute_group_activity, ROLE_GROUPS, ROLE_NAME_MAP, GROUP_PALETTE, BLOCK_BASE_SIZE, BLOCK_MIN_SIZE, BLOCK_PRESSED_SCALE, BLOCK_PRESS_DURATION,
    BLOCK_HOLD_DURATION, BLOCK_RELEASE_DURATION, DENSE_THRESHOLD, DENSE_CYCLE, DENSE_RECOVERY, CARD_PADDING_RATIO, CARD_CORNER_LEN_RATIO,
    CARD_SHADOW_COLOR, BLOCK_BACKING_COLOR, RESTING_THRESHOLD, STATE_TRANSITION_DURATION, CARD_BORDER_INACTIVE, OUTRO_FADEIN_DURATION, OUTRO_WAIT_DURATION, OUTRO_FADEOUT_DURATION, OUTRO_BUFFER, SPECTRUM_BAR_MAX_RATIO, SPECTRUM_EDGE_GAP_RATIO,
    StageLayout, TrackStateMachine,
)


# 密集音符快速循环模式

# 方形频谱
SPECTRUM_BARS = CONFIG.spectrum_bars
SPECTRUM_BARS_PER_EDGE = CONFIG.spectrum_bars_per_edge
SPECTRUM_BAR_WIDTH = CONFIG.spectrum_bar_width
SPECTRUM_BAR_MIN_HEIGHT = CONFIG.spectrum_bar_min_height
SPECTRUM_SMOOTH_FACTOR = CONFIG.spectrum_smooth_factor
SPECTRUM_STEP = CONFIG.spectrum_step

# 卡片
SPECTRUM_ACTIVE_BOOST = CONFIG.spectrum_active_boost

# 8色调色板（按组索引分配，相邻色可区分）
# 每色: (base卡片底8%, highlight激活边框/频谱85%, dark标签底40%)
# 非激活边框色 (MC灰槽)

# 全局固定色
TEXT_STROKE_COLOR = (0, 0, 0, 199)  # #000000 at 78%
LABEL_COLOR_ROLE = (255, 255, 255, 252)  # #FFFFFF at 99%
LABEL_COLOR_INST = (255, 255, 255, 233)  # #FFFFFF at 91%

# 尾奏（3阶段：fade-in + wait + fade-out per spec §5）

# Playing/Resting 状态系统 (§3)

# 摄像机
CAMERA_ENABLED = CONFIG.camera_enabled        # 摄像机开关
# 背景
BG_COLOR = CONFIG.bg_color
DOT_COLOR = CONFIG.dot_color
DOT_SPACING = CONFIG.dot_spacing
DOT_RADIUS = CONFIG.dot_radius  # FIXED-B4: 问题15 - 点阵半径从1提高到2，增强可见度

# 文字
TEXT_STROKE_WIDTH = CONFIG.text_stroke_width  # Spec §8: stroke_width=1
LABEL_FONT_RATIO = CONFIG.label_font_ratio

# 粒子（浅色背景上的微妙粒子）
PARTICLE_COUNT = CONFIG.particle_count
PARTICLE_SPEED_MIN = CONFIG.particle_speed_min
PARTICLE_SPEED_MAX = CONFIG.particle_speed_max
PARTICLE_SIZE_MIN = CONFIG.particle_size_min
PARTICLE_SIZE_MAX = CONFIG.particle_size_max
PARTICLE_ALPHA_MIN = CONFIG.particle_alpha_min
PARTICLE_ALPHA_MAX = CONFIG.particle_alpha_max

# FIXED-MC: 元问题C - 路径从 config.py 导入，消除硬编码绝对路径
from .resources import (
    FONT_CANDIDATES, INSTRUMENT_MAP, load_font, TextureCache,
)

ASSETS_DIR = config.ASSETS_DIR
TEXTURES_DIR = config.TEXTURES_DIR

MC_TEX_BASE = config.MC_TEX_BASE
MC_PARTICLE_DIR = config.MC_PARTICLE_DIR
MC_GUI_DIR = config.MC_GUI_DIR
MC_BLOCK_DIR = config.MC_BLOCK_DIR

# 角色名 → 分组


# 英文 → 中文 角色名本地映射


# ============== 工具函数 ==============
# load_font 迁移至 .resources，以下直接导入
from .utils import ease_out_back, ease_out_cubic, ease_in_cubic, ease_in_out_cubic, clamp, lerp








# ============== 纹理缓存 ==============
# TextureCache 迁移至 .resources，上方已导入


# ============== 粒子系统（迁移至 .particles）==============
from .particles import NoteParticleSystem, EnchantGlint, CollectionParticles, _SleepParticleSystem, Crosshair, NoteParticle, CollectionParticle, SleepParticle, BgParticle



# ============== 轨道数据 ==============










from .spectrum import SpectrumAnalyzer












from .spectrum import _spectrum_bar_pos


# ============== 布局引擎 ==============


# ============== 静态分组布局引擎 ==============


# ============== 智能摄像机 ==============
from .camera import SmartCamera, CameraController



# ============== 粒子系统 ==============
from .particles import ParticleSystem


# ============== 弹幕系统 ==============
from .ui import DanmakuSystem, Danmaku, Subtitle, CardRenderer



# ============== 帧渲染器 ==============
from .renderer import FrameRenderer, render_video, _mux_audio, preview_frame



# ============== 辅助绘制函数 ==============




# FIXED-B3: 问题35 - 删除未使用的_hsv_to_rgb函数




# ============== 视频生成主函数 ==============




# ============== 快速预览 ==============


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        nbs_path = sys.argv[1]
        out = sys.argv[2] if len(sys.argv) >= 3 else "preview.png"
        t = float(sys.argv[3]) if len(sys.argv) >= 4 else 0.5
        preview_frame(nbs_path, out, t)
    else:
        print("用法: python nbs_visualizer.py <nbs_file> [output_png] [time_s]")
