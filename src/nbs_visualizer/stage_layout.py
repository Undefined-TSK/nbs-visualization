"""静态分组布局引擎：StageLayout + 向后兼容的字典视图。"""
from __future__ import annotations

from typing import List, Optional, Tuple, Dict

from .logger import get_logger

from .stage_constants import BLOCK_BASE_SIZE, GROUP_PALETTE
from .track_data import TrackData
from .track_state_machine import TrackStateMachine
from .layout_calculator import compute_static_layout

logger = get_logger(__name__)


# ============== 向后兼容的字典视图 ==============
class _StateDictView:
    """dict-like 视图，委托给 TrackStateMachine.state"""
    def __init__(self, tsms: Dict[int, TrackStateMachine]):
        self._tsms = tsms
    def get(self, key, default=None):
        tsm = self._tsms.get(key)
        return tsm.state if tsm is not None else default
    def __getitem__(self, key):
        return self._tsms[key].state
    def __contains__(self, key):
        return key in self._tsms


class _NoteTimesDictView:
    """dict-like 视图，委托给 TrackStateMachine._note_times"""
    def __init__(self, tsms: Dict[int, TrackStateMachine]):
        self._tsms = tsms
    def get(self, key, default=None):
        tsm = self._tsms.get(key)
        return tsm._note_times if tsm is not None else default
    def __getitem__(self, key):
        return self._tsms[key]._note_times
    def __contains__(self, key):
        return key in self._tsms


# ============== 静态分组布局引擎 ==============
class StageLayout:
    """
    静态分组布局引擎 (§1-5):
    - Kimi 确定分组（1-8组），按重要性纵向排列（最重要在顶部）
    - 组内按重要性从左到右排列
    - 位置固定不动，只有 playing/resting 透明度变化
    - 三态系统: playing(α=1.0) / resting(α=0.5) / hidden(α=0.0, 仅尾奏)
    """

    MARGIN_RATIO = 0.05        # 5% 边距
    LABEL_HEIGHT = 30          # 组标签高度（横排）
    CARD_TARGET_SIZE = 110     # 目标卡片大小（方块尺寸）
    CARD_MIN_SIZE = 80         # 卡片最小尺寸（低于此值触发砍轨道）
    SPACING_RATIO = 0.10       # 卡片间距 = card_size × 0.10
    MIN_GROUPS = 3             # 最少3组
    MAX_GROUPS = 6             # 最多6组
    GROUP_GAP = 16             # 组与组之间的固定间距(px)
    ROW_GAP_RATIO = 0.08       # 组内行间距系数
    MAX_CARDS_PER_ROW = 10     # 每行最多卡片数
    MAX_ROW_DIFF = 1           # 最大行差（最多允许有的组比其他组多1行）

    def __init__(self, tracks: List[TrackData], audio_end_time: float = 0.0):
        self.tracks = tracks
        self.audio_end_time = audio_end_time
        self.positions: Dict[int, Tuple[float, float]] = {}
        self.group_bounds: List[Dict] = []
        self.n_groups = 0
        self.block_size = BLOCK_BASE_SIZE
        self.card_size = BLOCK_BASE_SIZE + 20

        # 逐轨状态机
        self._tsms: Dict[int, TrackStateMachine] = {}
        for tr in tracks:
            self._tsms[tr.layer_id] = TrackStateMachine(tr, audio_end_time)

        # 向后兼容的字典视图（委托给 TrackStateMachine）
        self._states = _StateDictView(self._tsms)
        self._note_times = _NoteTimesDictView(self._tsms)

        self._compute_layout()

    def _compute_layout(self):
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        self.positions, self.group_bounds, self.n_groups, self.block_size, self.card_size = \
            compute_static_layout(
                self.tracks, VIDEO_WIDTH, VIDEO_HEIGHT,
                self.MARGIN_RATIO, self.LABEL_HEIGHT,
                self.CARD_TARGET_SIZE, self.CARD_MIN_SIZE,
                self.SPACING_RATIO, self.ROW_GAP_RATIO,
                self.MAX_GROUPS, self.GROUP_GAP,
                self.MAX_CARDS_PER_ROW, self.MAX_ROW_DIFF,
            )

    def update(self, t: float):
        """更新 playing/resting 状态机。位置固定不变。"""
        for tr in self.tracks:
            tsm = self._tsms.get(tr.layer_id)
            if tsm is not None:
                tsm.update_state(t)

    def get_position(self, layer_id: int, t: float = 0) -> Tuple[float, float]:
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        pos = self.positions.get(layer_id)
        if pos is None:
            return (VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2)
        dy, _ = self.get_outro_effects(t)
        return (pos[0], pos[1] + dy)

    def is_visible(self, layer_id: int) -> bool:
        """轨道是否在布局中可见（被布局保护砍掉的轨道返回False）。"""
        return layer_id in self.positions

    def get_alpha(self, layer_id: int, t: float) -> float:
        """返回透明度: 1.0=完全可见, 0.5=半透明(resting), 0.0=不可见。"""
        tsm = self._tsms.get(layer_id)
        if tsm is not None:
            return tsm.get_alpha(t)
        return 0.5

    def get_outro_effects(self, t: float) -> Tuple[float, float]:
        """返回 (dy, scale) 尾奏漂移和收缩。"""
        if self.audio_end_time <= 0 or t <= self.audio_end_time:
            return 0.0, 1.0
        # 委托给任意一个 TrackStateMachine（outro 效果对所有轨道相同）
        for tsm in self._tsms.values():
            return tsm.get_outro_effects(t)
        return 0.0, 1.0

    def get_group_index(self, layer_id: int) -> int:
        for tr in self.tracks:
            if tr.layer_id == layer_id:
                return tr.group_index
        return 0

    def get_color(self, layer_id: int) -> Dict:
        gi = self.get_group_index(layer_id)
        return GROUP_PALETTE[gi % len(GROUP_PALETTE)]

    def get_state(self, layer_id: int) -> str:
        """返回轨道当前状态: 'playing' | 'resting' | 'hidden'"""
        tsm = self._tsms.get(layer_id)
        return tsm.state if tsm is not None else "resting"

    def get_note_times(self, layer_id: int) -> List[float]:
        """返回轨道的音符起始时间列表"""
        tsm = self._tsms.get(layer_id)
        return tsm._note_times if tsm is not None else []

    def get_tsm(self, layer_id: int) -> Optional[TrackStateMachine]:
        """返回轨道的 TrackStateMachine 实例"""
        return self._tsms.get(layer_id)

    def get_card_rect(self, layer_id: int) -> Tuple[float, float, float, float]:
        """返回卡片矩形 (cx, cy, card_w, card_h)"""
        pos = self.positions.get(layer_id, (0, 0))
        cs = self.card_size
        return (pos[0], pos[1], cs, cs)

    def get_group_center(self, group_idx: int) -> Tuple[float, float]:
        """返回组中心坐标"""
        for gb in self.group_bounds:
            if gb.get("color_idx", -1) == group_idx % len(GROUP_PALETTE):
                return (gb["label_x"], gb["label_y"])
        return (0.0, 0.0)

    def get_stage_bounds(self) -> Tuple[int, int, int, int]:
        """返回舞台边界 (left, top, right, bottom)"""
        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT
        margin_x = int(VIDEO_WIDTH * self.MARGIN_RATIO)
        margin_y = int(VIDEO_HEIGHT * self.MARGIN_RATIO)
        return (margin_x, margin_y, VIDEO_WIDTH - margin_x, VIDEO_HEIGHT - margin_y)

    def get_group_bounds(self) -> List[Dict]:
        """返回所有组的边界信息"""
        return self.group_bounds
