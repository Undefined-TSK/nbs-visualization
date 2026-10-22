"""
SharedMemory 渲染计划：主进程解析 NBS 一次，将音符与频谱压缩进共享内存，
子进程通过名字附加并重建 TrackData，避免每个 worker 重复解析 NBS 与重复 FFT 频谱分析。

设计要点：
- RenderPlan 仅含可 pickle 的元信息（shm 名 + 偏移 + 标量元数据），大数组留在共享内存。
- 主进程持有 SharedMemory 句柄直到所有子进程完成，之后 close() + unlink()。
- 子进程 attach() 按名字打开共享内存并重建轨道；失败时回退到重新 extract_tracks。
"""
from __future__ import annotations

import multiprocessing.shared_memory as _shm
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from ._core import SPECTRUM_BARS
from .track_data import TrackData


@dataclass
class _TrackMeta:
    layer_id: int
    layer_name: str
    role_name: str
    instrument_id: int
    instrument_name: str
    group: str
    group_index: int
    group_name: str
    is_active: bool
    notes_offset: int
    notes_count: int
    spec_offset: int
    spec_count: int


@dataclass
class RenderPlan:
    """可 pickle 的共享内存渲染计划（不含大数组本身）。"""
    shm_name: str
    shm_size: int
    total_seconds: float
    song_name: str
    tempo: float
    song_length: int
    audio_end_time: float
    tracks_meta: List[_TrackMeta]
    spec_times_offset: int
    spec_times_count: int

    def attach(self) -> Tuple[np.ndarray, _shm.SharedMemory]:
        """按名字打开共享内存并返回 (float64 视图, 句柄)。调用方负责 handle.close()。"""
        handle = _shm.SharedMemory(self.shm_name)
        buf = np.ndarray((self.shm_size,), dtype=np.float64, buffer=handle.buf)
        return buf, handle

    def reconstruct_tracks(self) -> List[TrackData]:
        buf, handle = self.attach()
        try:
            tracks: List[TrackData] = []
            for meta in self.tracks_meta:
                td = TrackData(meta.layer_id, meta.layer_name, meta.role_name,
                               meta.instrument_id, meta.instrument_name)
                td.group = meta.group
                td.group_index = meta.group_index
                td.group_name = meta.group_name
                td.is_active = meta.is_active

                no, nc = meta.notes_offset, meta.notes_count
                if nc > 0:
                    notes_arr = buf[no:no + nc * 4].reshape(nc, 4)
                    for r in range(nc):
                        s, e, k, v = notes_arr[r]
                        td.notes.append((float(s), float(e), int(round(k)), float(v)))

                so, sc = meta.spec_offset, meta.spec_count
                if sc > 0:
                    td.spectrum_values = buf[so:so + sc * SPECTRUM_BARS].reshape(sc, SPECTRUM_BARS).copy()
                if self.spec_times_count > 0:
                    td.spectrum_times = buf[self.spec_times_offset:
                                           self.spec_times_offset + self.spec_times_count].copy()

                td.set_derived_from_notes()
                tracks.append(td)
            return tracks
        finally:
            handle.close()


def build_render_plan(tracks: List[TrackData], header, total_seconds: float,
                      song_name: str, audio_end_time: float
                      ) -> Tuple[RenderPlan, _shm.SharedMemory]:
    """主进程：将轨道数据打包进共享内存。

    返回 (plan, shm_handle)。调用方必须持有 shm_handle 直到所有子进程完成，
    然后调用 shm_handle.close() 与 shm_handle.unlink()。
    """
    if not tracks:
        raise ValueError("build_render_plan: 没有活跃轨道")

    n_tracks = len(tracks)
    notes_total = sum(len(t.notes) for t in tracks)
    spec_steps = 0
    for t in tracks:
        if t.spectrum_values is not None and len(t.spectrum_values) > 0:
            spec_steps = len(t.spectrum_values)
            break

    # 布局（以 float64 元素计）：notes(N*4) + 每轨频谱(sc*32) + 共享 spec_times(sc)
    notes_region = notes_total * 4
    spec_region = n_tracks * spec_steps * SPECTRUM_BARS
    times_region = spec_steps
    total = notes_region + spec_region + times_region

    buf = np.zeros(total, dtype=np.float64)
    cursor = 0
    tracks_meta: List[_TrackMeta] = []

    for t in tracks:
        no = cursor
        nc = len(t.notes)
        if nc > 0:
            arr = np.asarray(t.notes, dtype=np.float64).reshape(nc * 4)
            buf[no:no + nc * 4] = arr
        cursor += nc * 4

        so = cursor
        sc = spec_steps
        if sc > 0 and t.spectrum_values is not None:
            sv = np.asarray(t.spectrum_values, dtype=np.float64).reshape(sc * SPECTRUM_BARS)
            buf[so:so + sc * SPECTRUM_BARS] = sv
        cursor += sc * SPECTRUM_BARS

        tracks_meta.append(_TrackMeta(
            layer_id=t.layer_id, layer_name=t.layer_name, role_name=t.role_name,
            instrument_id=t.instrument_id, instrument_name=t.instrument_name,
            group=t.group, group_index=t.group_index, group_name=t.group_name,
            is_active=t.is_active, notes_offset=no, notes_count=nc,
            spec_offset=so, spec_count=sc,
        ))

    spec_times_offset = cursor
    if spec_steps > 0:
        first = next((t for t in tracks
                      if t.spectrum_times is not None and len(t.spectrum_times) > 0), None)
        if first is not None:
            buf[spec_times_offset:spec_times_offset + spec_steps] = \
                np.asarray(first.spectrum_times, dtype=np.float64)

    shm_handle = _shm.SharedMemory(create=True, size=int(buf.nbytes))
    shared = np.ndarray((total,), dtype=np.float64, buffer=shm_handle.buf)
    shared[:] = buf

    plan = RenderPlan(
        shm_name=shm_handle.name,
        shm_size=total,
        total_seconds=total_seconds,
        song_name=song_name,
        tempo=getattr(header, "tempo", 0),
        song_length=getattr(header, "song_length", 0),
        audio_end_time=audio_end_time,
        tracks_meta=tracks_meta,
        spec_times_offset=spec_times_offset,
        spec_times_count=spec_steps,
    )
    return plan, shm_handle
