"""验证：提速后过渡动画仍"明显有动画"(不突变), 且形变幅度保持(不撞上限)。
直接测量 SmoothAnim 收敛速度（不受歌曲事件重叠干扰）。"""
import sys
sys.path.insert(0, "src")
from nbs_visualizer.anim_system import SmoothAnim
from nbs_visualizer.stage_constants import (
    TEX_SMOOTH_TIME, MASK_SMOOTH_TIME, DEFORM_VEL_GAIN, MASK_DEFORM_VEL_GAIN,
    DEFORM_MAX, BLOCK_PRESSED_SCALE,
)

FPS = 120
dt = 1.0 / FPS

def measure(smooth_time, target, start=1.0):
    a = SmoothAnim(start, smooth_time=smooth_time)
    frames_80 = frames_95 = None
    peak_v = 0.0
    for i in range(200):
        a.set_target(target)
        a.advance(dt)
        peak_v = max(peak_v, abs(a.vel))
        if frames_80 is None and abs(a.value - target) <= 0.20 * 0.20:  # 80% of the way
            frames_80 = i + 1
        if frames_95 is None and abs(a.value - target) <= 0.05 * 0.20:  # 95%
            frames_95 = i + 1
            break
    return frames_80, frames_95, peak_v

f80, f95, pv = measure(TEX_SMOOTH_TIME, BLOCK_PRESSED_SCALE)
print(f"TEX_SMOOTH_TIME={TEX_SMOOTH_TIME}")
print(f"  贴图 1.0→{BLOCK_PRESSED_SCALE}: 80%过渡 {f80}帧/{f80/FPS*1000:.0f}ms, 95% {f95}帧/{f95/FPS*1000:.0f}ms")

f80m, f95m, pvm = measure(MASK_SMOOTH_TIME, 0.85)
print(f"MASK_SMOOTH_TIME={MASK_SMOOTH_TIME}")
print(f"  遮盖 1.0→0.85: 80%过渡 {f80m}帧/{f80m/FPS*1000:.0f}ms, 95% {f95m}帧/{f95m/FPS*1000:.0f}ms")

# 形变幅度估计: e_peak = |v_peak| * GAIN (临界阻尼, 单步目标切换)
e_tex = pv * DEFORM_VEL_GAIN
e_mask = pvm * MASK_DEFORM_VEL_GAIN
print(f"DEFORM_VEL_GAIN={DEFORM_VEL_GAIN} (贴图峰值形变≈{e_tex:.4f}, 上限{DEFORM_MAX})")
print(f"MASK_DEFORM_VEL_GAIN={MASK_DEFORM_VEL_GAIN} (遮盖峰值形变≈{e_mask:.4f})")

# 断言: 过渡明显可见(>5帧, <40帧/330ms), 形变不撞上限
assert 5 <= f95 <= 40, f"过渡过快(突变)或过慢: {f95}帧"
assert e_tex <= DEFORM_MAX - 0.002, "贴图形变撞上限被削平"
print("OK: 提速后仍明显有动画, 形变幅度保持在合理区间(不撞上限)")
