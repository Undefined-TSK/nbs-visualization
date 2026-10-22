"""频谱系统：FFT分析、频带映射、频谱柱绘制位置。"""
from __future__ import annotations

import math
import numpy as np
from typing import List, Tuple, Optional

from .utils import clamp, lerp


class SpectrumAnalyzer:
    """轨道频谱分析与查询。"""

    def __init__(self, audio_spectrum: Optional[Any] = None):
        # 真实音频频谱（librosa 预计算，AudioSpectrum 实例）。
        # 非空时，底部频谱条以真实音频 FFT 为主驱动，叠加音符底色保留每卡差异；
        # 为空（无音频）时，沿用原有音符驱动逻辑。
        self.audio_spectrum = audio_spectrum

    def compute_spectrum(self, track, total_seconds: float,
                         step: float = None) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """计算轨道频谱时间序列，返回 (times, values)。

        对每个时间步，根据当前活跃音符的音高和包络计算 32 频带的能量分布。
        """
        from ._core import SPECTRUM_STEP, SPECTRUM_BARS, SPECTRUM_SMOOTH_FACTOR
        from ._core import OUTRO_FADEIN_DURATION, OUTRO_WAIT_DURATION, OUTRO_FADEOUT_DURATION, OUTRO_BUFFER
        if step is None:
            step = SPECTRUM_STEP
        nb = SPECTRUM_BARS

        def key_to_band(key: int) -> int:
            freq = 440.0 * (2.0 ** ((key - 45) / 12.0))
            if freq <= 20:
                return 0
            band = int((math.log2(freq / 20.0) / math.log2(400.0)) * nb)
            return clamp(band, 0, nb - 1)

        n_steps = int((total_seconds + OUTRO_FADEIN_DURATION + OUTRO_WAIT_DURATION + OUTRO_FADEOUT_DURATION + OUTRO_BUFFER + 1.0) // step) + 1
        all_values = np.zeros((n_steps, nb), dtype=np.float32)
        prev = np.zeros(nb, dtype=np.float32)
        alpha = SPECTRUM_SMOOTH_FACTOR

        for si in range(n_steps):
            tt = si * step
            spec = np.zeros(nb, dtype=np.float32)
            for (s, e, k, v) in track.notes:
                if s <= tt < e:
                    dur = e - s
                    if dur <= 0:
                        continue
                    lt = (tt - s) / dur
                    if lt < 0.08:
                        env = lt / 0.08
                    elif lt < 0.55:
                        env = 1.0
                    else:
                        env = max(0.1, 1.0 - (lt - 0.55) / 0.45)
                    band = key_to_band(k)
                    spec[band] += v * env
            mx = spec.max()
            if mx > 0:
                spec /= mx
            smoothed = prev * (1.0 - alpha) + spec * alpha
            all_values[si] = smoothed
            prev = smoothed

        times = np.arange(n_steps, dtype=np.float32) * step
        return times, all_values

    def get_spectrum_at(self, track, t: float) -> List[float]:
        """获取轨道在时间 t 的频谱值列表（线性插值）。

        若已注入真实音频频谱，则底部频谱条以真实音频 FFT 为主驱动
        （系数 0.9），叠加音符驱动底色（系数 0.5）保留每卡差异，
        使频谱条随真实音乐起伏。
        """
        from ._core import SPECTRUM_STEP, SPECTRUM_BARS
        nb = SPECTRUM_BARS

        if self.audio_spectrum is not None:
            audio_bands = self.audio_spectrum.get_bands(t)
            if len(audio_bands) != nb:
                # 频带数不一致时做最近邻映射（正常两者均为 32，不会触发）
                audio_bands = [audio_bands[min(len(audio_bands) - 1,
                                               int(round(i * len(audio_bands) / nb)))]
                               for i in range(nb)]
            note_spec = self._note_spectrum(track, t, nb)
            return [clamp(audio_bands[i] * 0.9 + note_spec[i] * 0.5, 0.0, 1.0)
                    for i in range(nb)]

        # 无音频：沿用原有音符驱动逻辑（保持向后兼容）
        if track.spectrum_values is None or len(track.spectrum_values) == 0:
            return [0.05] * SPECTRUM_BARS

        step = SPECTRUM_STEP
        n = len(track.spectrum_times)
        idx_f = t / step
        idx1 = int(idx_f)
        idx2 = idx1 + 1

        if idx1 >= n:
            return [0.05] * SPECTRUM_BARS
        if idx2 >= n:
            return track.spectrum_values[idx1].tolist()

        a = idx_f - idx1
        s1 = track.spectrum_values[idx1]
        s2 = track.spectrum_values[idx2]
        return [float(lerp(s1[i], s2[i], a)) for i in range(SPECTRUM_BARS)]

    def _note_spectrum(self, track, t: float, nb: int) -> List[float]:
        """仅取音符驱动的频谱底色（0..1），用于与真实音频混合。"""
        from ._core import SPECTRUM_STEP
        if track.spectrum_values is None or len(track.spectrum_values) == 0:
            return [0.0] * nb
        step = SPECTRUM_STEP
        n = len(track.spectrum_times)
        idx_f = t / step
        idx1 = int(idx_f)
        if idx1 >= n:
            return track.spectrum_values[n - 1].tolist() if n > 0 else [0.0] * nb
        if idx1 + 1 >= n:
            return track.spectrum_values[idx1].tolist()
        a = idx_f - idx1
        s1 = track.spectrum_values[idx1]
        s2 = track.spectrum_values[idx1 + 1]
        return [float(lerp(s1[i], s2[i], a)) for i in range(nb)]


def _spectrum_bar_pos(bar_idx: int, cx: float, cy: float,
                      half: float, spec_gap: int, bpe: int):
    """计算频谱柱在方形四周的位置（纯几何工具函数）。"""
    spacing = (2 * half) / bpe
    half_bpe = bpe // 2

    if bar_idx < half_bpe:
        pos = bar_idx + half_bpe
        x = cx - half + spacing * (pos + 0.5)
        y = cy - half - spec_gap
        return (x, y, 0, -1)
    elif bar_idx < half_bpe + bpe:
        pos = bar_idx - half_bpe
        x = cx + half + spec_gap
        y = cy - half + spacing * (pos + 0.5)
        return (x, y, 1, 0)
    elif bar_idx < half_bpe + 2 * bpe:
        pos = bpe - 1 - (bar_idx - half_bpe - bpe)
        x = cx - half + spacing * (pos + 0.5)
        y = cy + half + spec_gap
        return (x, y, 0, 1)
    elif bar_idx < half_bpe + 3 * bpe:
        pos = bpe - 1 - (bar_idx - half_bpe - 2 * bpe)
        x = cx - half - spec_gap
        y = cy - half + spacing * (pos + 0.5)
        return (x, y, -1, 0)
    else:
        pos = half_bpe - 1 - (bar_idx - half_bpe - 3 * bpe)
        x = cx - half + spacing * (pos + 0.5)
        y = cy - half - spec_gap
        return (x, y, 0, -1)
