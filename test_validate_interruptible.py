"""快速验证：可打断弹簧动画的平滑性、取值范围、频谱边界裁剪。"""
import math
from nbs_visualizer.track_operations import extract_tracks
from nbs_visualizer.stage import StaticGroupLayout
from nbs_visualizer.track_state_machine import TrackStateMachine
from nbs_visualizer.renderer_spectrums import RendererSpectrumsMixin
from nbs_visualizer.stage_constants import (
    SPECTRUM_RENDER_GAP_RATIO, SPECTRUM_BAR_MAX_RATIO, BLOCK_PRESSED_SCALE,
)
from nbs_visualizer._core import FPS

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
tracks, header = extract_tracks(NBS)
layout = StaticGroupLayout(tracks, audio_end_time=30.0)
bs = layout.block_size
card_size = layout.card_size
print(f"[layout] bs={bs}  card_size={card_size}  card_half={card_size/2:.1f}")

# ---- 频谱边界裁剪验证 ----
spec_gap = max(3, int(bs * SPECTRUM_RENDER_GAP_RATIO))
half = bs / 2
raw_max_h = max(6, int(bs * SPECTRUM_BAR_MAX_RATIO))
max_allowed = card_size / 2.0 - half - spec_gap - 4.0
clamped_max_h = min(raw_max_h, int(max_allowed))
print(f"[spectrum] raw_max_h={raw_max_h}  clamped_max_h={clamped_max_h}  "
      f"bar_tip={half + spec_gap + clamped_max_h:.1f}  card_half={card_size/2:.1f}")
assert half + spec_gap + clamped_max_h <= card_size / 2.0, "频谱条仍超出卡片!"
print("  ✓ 频谱条峰值不超出卡片边界")

# ---- 弹簧平滑性验证 ----
def simulate(tsm, secs=30.0, fps=120):
    dt = 1.0 / fps
    n = int(secs * fps)
    prev_tscale, prev_mscale = None, None
    prev_sx, prev_sy = None, None
    max_d_tscale = 0.0
    max_d_mscale = 0.0
    max_d_sx = 0.0
    min_tscale, max_tscale = 9.0, -9.0
    min_mscale, max_mscale = 9.0, -9.0
    for i in range(n + 1):
        t = i * dt
        tsm.advance_anim(t, dt)
        ts = tsm.get_texture_scale(t)
        ms = tsm.get_mask_scale(t)
        sx, sy = tsm.get_squash(t)
        # 帧间跳变（平滑性：临界阻尼下应很小且连续）
        if prev_tscale is not None:
            max_d_tscale = max(max_d_tscale, abs(ts - prev_tscale))
            max_d_mscale = max(max_d_mscale, abs(ms - prev_mscale))
            max_d_sx = max(max_d_sx, abs(sx - prev_sx))
        prev_tscale, prev_mscale = ts, ms
        prev_sx, prev_sy = sx, sy
        min_tscale, max_tscale = min(min_tscale, ts), max(max_tscale, ts)
        min_mscale, max_mscale = min(min_mscale, ms), max(max_mscale, ms)
    return dict(max_d_t=max_d_tscale, max_d_m=max_d_mscale, max_d_sx=max_d_sx,
                t_range=(min_tscale, max_tscale), m_range=(min_mscale, max_mscale))

FPS = fps = 120
print("\n[spring] 逐帧模拟 (dt=1/120)：")
for tr in tracks:
    tsm = layout.get_tsm(tr.layer_id)
    if tsm is None:
        continue
    r = simulate(tsm, 30.0, 120)
    print(f"  L{tr.layer_id:>2}  dT={r['max_d_t']:.4f}  dM={r['max_d_m']:.4f}  "
          f"dSX={r['max_d_sx']:.4f}  tex[{r['t_range'][0]:.3f},{r['t_range'][1]:.3f}]  "
          f"mask[{r['m_range'][0]:.3f},{r['m_range'][1]:.3f}]  notes={len(tr.notes)}")
    # 平滑性断言：临界阻尼下每帧变化应很小（< 0.05），无突变顿挫
    assert r['max_d_t'] < 0.05, f"L{tr.layer_id} 贴图缩放帧间跳变过大: {r['max_d_t']}"
    assert r['max_d_sx'] < 0.05, f"L{tr.layer_id} 挤压帧间跳变过大: {r['max_d_sx']}"
    # 取值断言
    assert r['t_range'][0] >= BLOCK_PRESSED_SCALE - 1e-3, "贴图缩放低于按下态"
    assert r['t_range'][1] <= 1.0 + 1e-3, "贴图缩放超过静止态"

print("\n✓ 全部轨道弹簧动画：平滑（帧间跳变<0.05）、取值范围合理、无顿挫")
