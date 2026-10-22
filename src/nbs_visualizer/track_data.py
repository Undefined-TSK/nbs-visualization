"""轨道数据模型：TrackData 充血模型，管理音符、密集区、频谱、按压事件等派生数据。"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .spectrum import SpectrumAnalyzer
from .stage_constants import (
    get_role_group, DENSE_THRESHOLD, DENSE_CYCLE,
    DENSE_WINDOW, DENSE_MIN_COUNT, BLOCK_PRESS_DURATION,
)


# ============== 轨道数据 ==============
class TrackData:
    __slots__ = (
        "layer_id", "layer_name", "role_name", "instrument_id",
        "instrument_name", "group", "group_index", "group_name",
        "notes", "is_active",
        "press_events", "spectrum_times", "spectrum_values", "note_starts", "dense_regions",
    )

    def __init__(self, layer_id, layer_name, role_name, instrument_id, instrument_name):
        self.layer_id = layer_id
        self.layer_name = layer_name
        self.role_name = role_name
        self.instrument_id = instrument_id
        self.instrument_name = instrument_name
        self.group = get_role_group(role_name)
        self.group_index = 0  # 由 Kimi 分组结果设置
        self.group_name = ""  # 由 Kimi 分组结果设置
        self.notes: List[Tuple[float, float, int, float]] = []
        self.is_active = False
        self.press_events: List[Tuple[float, float]] = []
        self.spectrum_times = None
        self.spectrum_values = None
        self.note_starts: List[float] = []
        self.dense_regions: List[Tuple[float, float]] = []

    def _compute_dense_regions(self) -> None:
        """检测密集音符区域（密度窗口法）。

        旧版用固定间隔阈值(0.05s)，会把整首中等密度旋律漏掉，只在极密爆发处
        才触发，导致"密集高斯脉冲"几乎不可见。改为：以每音符为中心统计 ±DENSE_WINDOW
        秒内的音符数，达到 DENSE_MIN_COUNT 即判为密集；连续密集音符合并成区域。
        这样能抓得住整段持续快速旋律，而非零散的瞬时爆发。
        """
        notes = self.notes
        if len(notes) < 4:
            self.dense_regions = []
            return
        import bisect as _b
        times = [n[0] for n in notes]
        dense_flags = []
        for t0 in times:
            lo = _b.bisect_left(times, t0 - DENSE_WINDOW)
            hi = _b.bisect_right(times, t0 + DENSE_WINDOW)
            dense_flags.append((hi - lo) >= DENSE_MIN_COUNT)

        regions: List[Tuple[float, float]] = []
        start: Optional[float] = None
        for i, flag in enumerate(dense_flags):
            if flag and start is None:
                start = times[i]
            elif not flag and start is not None:
                regions.append((start, times[i - 1] + DENSE_CYCLE * 2))
                start = None
        if start is not None:
            regions.append((start, times[-1] + DENSE_CYCLE * 2))
        self.dense_regions = regions

    def set_derived_from_notes(self) -> None:
        """仅由音符重建派生数据（note_starts / dense_regions / press_events / is_active），不重算频谱。

        供 SharedMemory 反序列化后重建轨道使用，避免子进程重复 FFT 频谱分析。
        """
        self.notes.sort(key=lambda x: x[0])
        self.note_starts = [n[0] for n in self.notes]
        self._compute_dense_regions()

        press_events: List[Tuple[float, float]] = []
        if self.notes:
            # 关键修复：每个音符起点触发一次独立的"按下事件"（信封=按下时长），
            # 仅当相邻"起点间隔" <= MERGE_WINDOW(0.05s) 视为同一和弦按下而合并。
            # 旧版用 s - cur_e <= 0.08 合并，等效"相邻起点差<=0.38s 就合并"，
            # 密集旋律里所有音符被并成单个贯穿全曲的巨型事件，导致贴图永久钉在
            # 0.72、遮盖永久 1.0，所有按下/回弹/密集动画全部失效。
            # 注意：必须基于"起点间隔"判定，不能基于事件终点（否则阈值被 0.3s 的
            # 音符时长撑大，仍然会巨型合并）。
            MERGE_WINDOW = 0.05
            cur_s = self.notes[0][0]
            last_s = cur_s
            for i in range(1, len(self.notes)):
                s, e, k, v = self.notes[i]
                if s - last_s <= MERGE_WINDOW:
                    last_s = s  # 同一和弦（同时按下），并入当前事件
                else:
                    press_events.append((cur_s, cur_s + BLOCK_PRESS_DURATION))
                    cur_s = s
                    last_s = s
            press_events.append((cur_s, cur_s + BLOCK_PRESS_DURATION))
        self.press_events = press_events
        self.is_active = len(self.notes) > 0

    def recompute_derived(self, total_seconds: float) -> None:
        """重新计算派生数据：排序、note_starts、dense_regions、press_events、频谱。"""
        self.set_derived_from_notes()

        analyzer = SpectrumAnalyzer()
        self.spectrum_times, self.spectrum_values = analyzer.compute_spectrum(self, total_seconds)

    def is_sparse(self) -> bool:
        """判断轨道是否稀疏（可安全合并）。"""
        n = len(self.notes)
        if n < 10:
            return True
        if n >= 50:
            return False
        span = self.notes[-1][0] - self.notes[0][0]
        if span < 0.1:
            return False
        density = n / span
        return density < 5.0
