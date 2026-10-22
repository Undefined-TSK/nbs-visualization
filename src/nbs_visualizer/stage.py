"""舞台系统：re-export 兼容层。

模块拆分后，stage.py 仅保留 re-export 以兼容现有导入：
- stage_constants: 常量和辅助函数
- track_data: TrackData 充血模型
- track_operations: _merge_tracks / extract_tracks / compute_group_activity
- layout_engine: LayoutEngine
- track_state_machine: TrackStateMachine
- stage_layout: StageLayout / _StateDictView / _NoteTimesDictView
- particles: 粒子系统
"""
from __future__ import annotations

# ============== 粒子系统（迁移至 .particles）==============
from .particles import NoteParticleSystem, EnchantGlint, CollectionParticles, _SleepParticleSystem, Crosshair

# ============== Re-export（兼容现有导入）==============
from .stage_constants import (
    ROLE_GROUPS, ROLE_NAME_MAP, GROUP_PALETTE, GROUP_ORDER, GROUP_LABELS,
    BLOCK_BASE_SIZE, BLOCK_MIN_SIZE, BLOCK_PRESSED_SCALE, BLOCK_PRESS_DURATION,
    BLOCK_HOLD_DURATION, BLOCK_RELEASE_DURATION,
    DENSE_THRESHOLD, DENSE_CYCLE, DENSE_RECOVERY,
    CARD_PADDING_RATIO, CARD_CORNER_LEN_RATIO, CARD_SHADOW_COLOR, BLOCK_BACKING_COLOR,
    RESTING_THRESHOLD, STATE_TRANSITION_DURATION, CARD_BORDER_INACTIVE,
    OUTRO_FADEIN_DURATION, OUTRO_WAIT_DURATION, OUTRO_FADEOUT_DURATION, OUTRO_BUFFER,
    OUTRO_SCENE_FADE, OUTRO_SCENE_HOLD,
    SPECTRUM_BAR_MAX_RATIO, SPECTRUM_EDGE_GAP_RATIO,
    translate_role_name_local, get_role_group, _optimal_cols,
)
from .track_data import TrackData
from .track_operations import _merge_tracks, extract_tracks, compute_group_activity
from .layout_engine import LayoutEngine
from .track_state_machine import TrackStateMachine
from .stage_layout import StageLayout, _StateDictView, _NoteTimesDictView

# 向后兼容别名
StaticGroupLayout = StageLayout
