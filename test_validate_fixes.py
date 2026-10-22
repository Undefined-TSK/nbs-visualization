"""验证本次三处修复的几何/数值效果（不渲染视频，纯数值探针）。"""
import math
from nbs_visualizer.track_operations import extract_tracks
from nbs_visualizer.track_state_machine import TrackStateMachine
from nbs_visualizer.stage_layout import StageLayout
from nbs_visualizer.camera import CameraController
from nbs_visualizer.stage_constants import (
    BLOCK_PRESSED_SCALE, DENSE_RECOVERY, DENSE_MASK_PRESSED,
    SPECTRUM_RENDER_GAP_RATIO, BLOCK_BASE_SIZE,
)
from nbs_visualizer import config

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
tracks, header = extract_tracks(NBS)
layout = StageLayout(tracks, audio_end_time=99.0)
bs = layout.block_size
cap = bs + 2 * max(3, int(bs * SPECTRUM_RENDER_GAP_RATIO)) - 2 * 2  # _block_size_cap
_sg = max(3, int(bs * SPECTRUM_RENDER_GAP_RATIO))
print(f"[layout] bs={bs}  block_size_cap(full_px)={cap}  spectrum_inner_half={(bs//2)+_sg:.1f}")
print(f"[const] BLOCK_PRESSED_SCALE={BLOCK_PRESSED_SCALE}  DENSE_RECOVERY={DENSE_RECOVERY}  DENSE_MASK_PRESSED={DENSE_MASK_PRESSED}")
print(f"[check] texture_pressed({BLOCK_PRESSED_SCALE}) < mask_recovery({DENSE_RECOVERY})? {BLOCK_PRESSED_SCALE < DENSE_RECOVERY}")
print(f"[check] pressed steady size {BLOCK_PRESSED_SCALE*bs:.1f} < cap {cap}? {BLOCK_PRESSED_SCALE*bs < cap}")

# 取最活跃轨道，扫描整曲，统计：最大绘制尺寸、是否超出 cap、贴图/遮盖缩放在密集区关系
tr = max(tracks, key=lambda t: len(t.notes))
tsm = layout.get_tsm(tr.layer_id)
max_t = max((n[1] for n in tr.notes), default=10.0)
max_drawn = 0.0
over_cap = 0
tex_vs_mask_dense = []
for i in range(0, int(max_t * 120) + 1):
    t = i / 120.0
    # 贴图
    ts, phase = tsm._texture_scale_phase(t)
    sqx, sqy = tsm._squash_for(ts, phase)
    drawn = bs * ts * max(sqx, sqy)
    max_drawn = max(max_drawn, drawn)
    if drawn > cap + 0.5:
        over_cap += 1
    # 密集区关系
    for (ds, de) in tr.dense_regions:
        if ds <= t < de:
            ms = tsm._dense_mask_cycle(t, ds, de)
            tex_vs_mask_dense.append((ts, ms, ms > ts))

print(f"\n[texture squash] max drawn full size over whole song = {max_drawn:.1f}px  cap={cap}  over_cap_frames={over_cap}")
print(f"[texture] rest=1.0  pressed={BLOCK_PRESSED_SCALE}  max_squash_scale={max_drawn/bs:.3f}x")

# 密集区：遮盖是否始终高于贴图（即高斯脉冲峰值可见）
if tex_vs_mask_dense:
    above = sum(1 for (_, ms, a) in tex_vs_mask_dense if a)
    print(f"[dense mask] samples={len(tex_vs_mask_dense)}  mask>texture (visible ring) = {above}/{len(tex_vs_mask_dense)} "
          f"({100*above/len(tex_vs_mask_dense):.0f}%)  mask range=[{min(m for _,m,_ in tex_vs_mask_dense):.2f},{max(m for _,m,_ in tex_vs_mask_dense):.2f}]")

# ============ 摄像机晃动幅度 ============
print("\n[camera] 模拟 60s 无脚本(自动导演) 模式，记录摄像机中心漂移与屏幕位移")
from nbs_visualizer._core import VIDEO_WIDTH, VIDEO_HEIGHT
cam = CameraController(tracks, layout, kimi_script=None, stage=layout)
cx_list, cy_list, zoom_list, panx_list, pany_list = [], [], [], [], []
for i in range(0, 60 * 120):
    t = i / 120.0
    cam.update(t)
    z, px, py = cam.get_transform()
    cx_list.append(cam.current_x); cy_list.append(cam.current_y)
    zoom_list.append(z); panx_list.append(px); pany_list.append(py)
amp_cx = max(cx_list) - min(cx_list)
amp_cy = max(cy_list) - min(cy_list)
amp_zoom = max(zoom_list) - min(zoom_list)
amp_panx = max(panx_list) - min(panx_list)
amp_pany = max(pany_list) - min(pany_list)
print(f"  摄像机中心漂移: X={amp_cx:.1f}px  Y={amp_cy:.1f}px  (纯位置晃动，不含缩放)")
print(f"  缩放范围: {min(zoom_list):.2f} ~ {max(zoom_list):.2f}  (峰峰 {amp_zoom:.2f})")
print(f"  屏幕位移(pan): X={amp_panx:.1f}px  Y={amp_pany:.1f}px  (含缩放放大的视觉效果)")
print("DONE")
