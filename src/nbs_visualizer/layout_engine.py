"""布局引擎：LayoutEngine 计算卡片网格位置、方块尺寸、频谱/内边距开销。"""
from __future__ import annotations

import math
from typing import List, Tuple, Dict

from .track_data import TrackData
from .stage_constants import (
    _optimal_cols,
    BLOCK_BASE_SIZE,
    BLOCK_MIN_SIZE,
    SPECTRUM_EDGE_GAP_RATIO,
    SPECTRUM_BAR_MAX_RATIO,
    CARD_PADDING_RATIO,
)


# ============== 布局引擎 ==============
class LayoutEngine:
    def __init__(self, tracks: List[TrackData]):
        self.tracks = tracks
        self.n = len(tracks)
        self.block_size = BLOCK_BASE_SIZE
        self.card_size = BLOCK_BASE_SIZE
        self.positions: Dict[int, Tuple[int, int]] = {}
        self._compute()

    def _compute(self):
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        n = self.n
        if n == 0:
            return

        cols = _optimal_cols(n)
        rows = math.ceil(n / cols)

        # 整体留白比例（单边），保证四周有足够呼吸感
        pad_ratio = 0.10  # 单边10%，总留白约20%（上下/左右各10%）
        margin_x = int(VIDEO_WIDTH * pad_ratio)
        margin_y = int(VIDEO_HEIGHT * pad_ratio)
        title_area = 0  # 标题已移除
        gap_ratio = 0.18

        avail_w = VIDEO_WIDTH - 2 * margin_x
        avail_h = VIDEO_HEIGHT - 2 * margin_y - title_area

        # 迭代计算最优方块尺寸
        # 先用 BASE_SIZE 估算开销，然后逐步逼近真实值
        bs = BLOCK_BASE_SIZE
        for _ in range(5):  # 迭代收敛
            spec_gap = max(3, int(bs * SPECTRUM_EDGE_GAP_RATIO))
            spec_max = max(6, int(bs * SPECTRUM_BAR_MAX_RATIO))
            card_pad = max(3, int(bs * CARD_PADDING_RATIO))
            card_overhead = 2 * (spec_gap + spec_max + card_pad)
            card_size = bs + card_overhead
            gap = int(bs * gap_ratio)

            total_w = cols * card_size + (cols - 1) * gap
            total_h = rows * card_size + (rows - 1) * gap

            scale_w = avail_w / total_w
            scale_h = avail_h / total_h
            scale = min(scale_w, scale_h)

            if abs(scale - 1.0) < 0.005:
                break

            bs = int(bs * scale)
            bs = max(BLOCK_MIN_SIZE, min(bs, BLOCK_BASE_SIZE))

        # 最终计算
        bs = self.block_size = max(BLOCK_MIN_SIZE, min(bs, BLOCK_BASE_SIZE))
        gap = int(bs * gap_ratio)
        spec_gap = max(3, int(bs * SPECTRUM_EDGE_GAP_RATIO))
        spec_max = max(6, int(bs * SPECTRUM_BAR_MAX_RATIO))
        card_pad = max(3, int(bs * CARD_PADDING_RATIO))

        self.card_size = bs + 2 * (spec_gap + spec_max + card_pad)

        total_w = cols * self.card_size + (cols - 1) * gap
        total_h = rows * self.card_size + (rows - 1) * gap
        start_x = (VIDEO_WIDTH - total_w) // 2 + self.card_size // 2
        start_y = (VIDEO_HEIGHT - total_h) // 2 + self.card_size // 2 + title_area // 2

        for i, track in enumerate(self.tracks):
            row = i // cols
            col = i % cols
            x = start_x + col * (self.card_size + gap)
            y = start_y + row * (self.card_size + gap)
            self.positions[track.layer_id] = (x, y)

    def get_position(self, layer_id: int) -> Tuple[int, int]:
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        return self.positions.get(layer_id, (VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2))

    def get_grid_position(self, layer_id: int) -> Tuple[int, int]:
        """获取轨道的网格坐标 (row, col)。"""
        idx = self._track_index(layer_id)
        if idx < 0:
            return (0, 0)
        cols = _optimal_cols(self.n)
        return (idx // cols, idx % cols)

    def _track_index(self, layer_id: int) -> int:
        for i, t in enumerate(self.tracks):
            if t.layer_id == layer_id:
                return i
        return -1

    def grid_to_pixel(self, row: int, col: int) -> Tuple[float, float]:
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        """网格坐标转像素坐标（中心点）。"""
        cols = _optimal_cols(self.n)
        rows = math.ceil(self.n / cols)
        gap = int(self.block_size * 0.18)
        total_w = cols * self.card_size + (cols - 1) * gap
        total_h = rows * self.card_size + (rows - 1) * gap
        start_x = (VIDEO_WIDTH - total_w) // 2 + self.card_size // 2
        start_y = (VIDEO_HEIGHT - total_h) // 2 + self.card_size // 2
        x = start_x + col * (self.card_size + gap)
        y = start_y + row * (self.card_size + gap)
        return (x, y)
