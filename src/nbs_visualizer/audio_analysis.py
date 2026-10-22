"""
真实音频频谱分析（librosa FFT）。

在渲染前一次性把整首歌的 STFT 幅度聚合为「帧率 × 频带数」的能量时间轴，
渲染时只需按时间查表，避免在 120fps 下每帧实时做 FFT（那样太慢）。

设计：
- 使用 librosa 解码 + STFT，取对数间隔的 n_bands 个频带（低频→高频）。
- 全曲自适应归一化到 0..1，再重采样到渲染帧率（fps）。
- 渲染层调用 `get_bands(t)` 拿当前帧的频带能量，驱动底部频谱条与方块脉冲。
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

try:
    import librosa
    _HAS_LIBROSA = True
except Exception:  # noqa: BLE001
    _HAS_LIBROSA = False


def librosa_available() -> bool:
    return _HAS_LIBROSA


class AudioSpectrum:
    """真实音频的频带能量时间轴（已重采样到渲染帧率）。"""

    def __init__(self, bands: np.ndarray, times: np.ndarray, fps: int, n_bands: int):
        # bands: (n_frames, n_bands)，归一化到 0..1
        self.bands = np.asarray(bands, dtype=np.float32)
        self.times = np.asarray(times, dtype=np.float32)
        self.fps = fps
        self.n_bands = n_bands

    @classmethod
    def from_file(cls, path: str, fps: int, n_bands: int = 32,
                  total_seconds: Optional[float] = None) -> "AudioSpectrum":
        if not _HAS_LIBROSA:
            raise RuntimeError("librosa 未安装，无法做真实音频频谱分析")
        y, sr = librosa.load(path, sr=None, mono=True)
        if y.size == 0:
            raise RuntimeError(f"音频文件为空或无法解码: {path}")

        # STFT 幅度（dB）
        n_fft = 2048
        hop = 512
        S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop))
        S_db = librosa.amplitude_to_db(S, ref=np.max)

        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
        fmin = max(freqs[1], 20.0)
        fmax = min(freqs[-1], sr / 2.0)
        fmax = max(fmax, fmin * 1.5)
        band_edges = np.logspace(np.log10(fmin), np.log10(fmax), n_bands + 1)

        n_frames = S_db.shape[1]
        band_energy = np.zeros((n_frames, n_bands), dtype=np.float32)
        for b in range(n_bands):
            lo, hi = band_edges[b], band_edges[b + 1]
            idx = np.where((freqs >= lo) & (freqs < hi))[0]
            if idx.size == 0:
                idx = np.array([np.argmin(np.abs(freqs - 0.5 * (lo + hi)))])
            band_energy[:, b] = S_db[idx].mean(axis=0)

        # 全曲自适应归一化到 0..1
        mn, mx = float(band_energy.min()), float(band_energy.max())
        if mx - mn > 1e-6:
            band_energy = (band_energy - mn) / (mx - mn)
        else:
            band_energy = np.zeros_like(band_energy)

        frame_times = librosa.frames_to_time(
            np.arange(n_frames), sr=sr, hop_length=hop, n_fft=n_fft
        )
        if total_seconds is None:
            total_seconds = float(frame_times[-1]) if frame_times.size else 0.0

        out_frames = max(1, int(total_seconds * fps) + 1)
        out_times = np.arange(out_frames) / fps
        bands_resampled = np.zeros((out_frames, n_bands), dtype=np.float32)
        for b in range(n_bands):
            bands_resampled[:, b] = np.interp(
                out_times, frame_times, band_energy[:, b], left=0.0, right=0.0
            )
        return cls(bands_resampled, out_times, fps, n_bands)

    @classmethod
    def empty(cls, fps: int, n_bands: int) -> "AudioSpectrum":
        return cls(np.zeros((1, n_bands), dtype=np.float32),
                   np.array([0.0], dtype=np.float32), fps, n_bands)

    def get_bands(self, t: float) -> List[float]:
        """返回时间 t 的 n_bands 频带能量（0..1）。"""
        if self.bands.shape[0] == 0:
            return [0.0] * self.n_bands
        i0 = int(t * self.fps)
        if i0 < 0:
            i0 = 0
        if i0 >= self.bands.shape[0]:
            i0 = self.bands.shape[0] - 1
        return self.bands[i0].tolist()

    def get_energy(self, t: float) -> float:
        """总体能量（0..1），可用于全局脉冲。"""
        b = self.get_bands(t)
        if not b:
            return 0.0
        return float(np.mean(b))
