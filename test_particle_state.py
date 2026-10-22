"""方向⑦-粒子状态管理 自检：状态机 + 遮盖约束 + 贴图/遮盖挤压区分。"""
import sys, types
sys.path.insert(0, "src")

from nbs_visualizer.particles import NoteParticleSystem, _ParticlePhase
from nbs_visualizer.track_state_machine import TrackStateMachine
from nbs_visualizer.track_data import TrackData
from nbs_visualizer.resources import TextureCache


# ---- 1) 贴图挤压 vs 遮盖挤压 必须不同 ----
td = TrackData(layer_id=0, layer_name="L0", role_name="harp",
               instrument_id=0, instrument_name="Harp")
td.notes = [(1.0, 1.2, 60, 100), (1.1, 1.35, 62, 100)]
td.set_derived_from_notes()
tsm = TrackStateMachine(td)
# 取一个明确的'按下'时刻
t_press = 1.05
sx, sy = tsm.get_squash(t_press)
msx, msy = tsm.get_mask_squash(t_press)
print(f"[squash] tex=({sx:.3f},{sy:.3f})  mask=({msx:.3f},{msy:.3f})")
assert abs(sx - msx) > 0.02 or abs(sy - msy) > 0.02, "贴图与遮盖挤压应当不同"
assert (msx, msy) != (1.0, 1.0), "按下时刻遮盖层应产生克制挤压"
print("  OK: 贴图挤压与遮盖挤压明显不同")


# ---- 2) 粒子状态机 + 遮盖约束 ----
class FakeTex:
    def get_mc_particle(self, name):
        from PIL import Image
        return Image.new("RGBA", (8, 8), (255, 255, 100, 200))

class FakeTSM:
    def __init__(self, active=True):
        self._active = active
    def is_active_at(self, t):
        return self._active
    def get_texture_scale(self, t):
        return 0.9  # 被按下缩小

sysm = NoteParticleSystem(FakeTex())
bs = 100
hl = (255, 80, 80)

# 2a 正常发射（活跃、不遮盖、alpha 足）
sysm.emit(7, 500, 500, 0.0, FakeTSM(True), hl, bs, is_critical=False, card_alpha=1.0, occluded=False)
assert len(sysm.particles) == 1 and sysm._count_by_track[7] == 1
print(f"[emit] 正常发射 ok, count={sysm._count_by_track[7]}")

# 2b 每轨上限 O(1) 拦截：再发 5 个非暴击，应卡在 MAX_PER_TRACK=3
for _ in range(5):
    sysm.emit(7, 500, 500, 0.0, FakeTSM(True), hl, bs, is_critical=False, card_alpha=1.0, occluded=False)
assert len(sysm.particles) == 3 and sysm._count_by_track[7] == 3, f"上限失效: {len(sysm.particles)}"
print(f"[cap] 每轨上限 ok, 实际={len(sysm.particles)} (上限3)")

# 2c 遮盖 / 暗化 / 非按下 三类拦截
before = len(sysm.particles)
sysm.emit(7, 500, 500, 0.0, FakeTSM(True), hl, bs, occluded=True)            # 遮盖
sysm.emit(7, 500, 500, 0.0, FakeTSM(True), hl, bs, card_alpha=0.1)           # 卡片淡出
sysm.emit(7, 500, 500, 0.0, FakeTSM(False), hl, bs)                         # 非按下
assert len(sysm.particles) == before, "遮盖/暗化/非按下 不应发射粒子"
print(f"[occlusion] 遮盖/暗化/非按下 拦截 ok, 粒子数不变={len(sysm.particles)}")

# 2d 相位 RISE->FALL + 移除时计数回退
p = sysm.particles[0]
assert p.phase == _ParticlePhase.RISE
# 推进到 vy>=0 触发转 FALL，再超过 max_life 移除
for _ in range(200):
    sysm.update(1/120)
# 移除后计数应归零
assert sysm._count_by_track[7] == 0, f"移除后计数应为0, 实际{ sysm._count_by_track[7]}"
print(f"[lifecycle] 相位转换+移除回退 ok, 剩余粒子={len(sysm.particles)}")

# 2e 暴击 BURST 无长尾（trail 仅在早期记录）
sysm2 = NoteParticleSystem(FakeTex())
sysm2.emit(1, 100, 100, 0.0, FakeTSM(True), hl, bs, is_critical=True)
for _ in range(3):
    sysm2.update(1/120)
burst = sysm2.particles[0]
assert burst.phase == _ParticlePhase.BURST
assert len(burst.trail) == 0, f"暴击不应留尾, trail={len(burst.trail)}"
print(f"[burst] 暴击径向爆发无长尾 ok, trail={len(burst.trail)}")

print("\nALL PARTICLE STATE CHECKS PASSED")
