"""验证修复后：扫描 L1 时间段，确认贴图/遮盖 scale 真实随音符变化（不再卡死）。"""
from nbs_visualizer.track_operations import extract_tracks
from nbs_visualizer.track_state_machine import TrackStateMachine

tracks, _ = extract_tracks(r"D:/nbs可视化/uploads/植物大战僵尸1.nbs")
tr = max(tracks, key=lambda t: len(t.notes))  # L1
tsm = TrackStateMachine(tr, audio_end_time=99.0)
print(f"L{tr.layer_id}: notes={len(tr.notes)} press_events={len(tr.press_events)} dense_regions={len(tr.dense_regions)}")

print(f"\n{'t':>6} {'inDense':>7} {'tex':>6} {'mask':>6} {'tphase':>8} {'mphase':>9} {'ring':>6}")
bs = 90
prev_tex = None
changes = 0
for i in range(580, 640):  # t=29.0 .. 32.0 (非密集间隙，验证逐音符按下/回弹)
    t = i * 0.05
    in_dense = any(ds <= t < de for ds, de in tr.dense_regions)
    tex = tsm.get_texture_scale(t)
    mask = tsm.get_mask_scale(t)
    sp, tp = tsm._texture_scale_phase(t)
    mp, mpp = tsm.get_mask_scale_phase(t)
    ring = bs * mask - bs * tex
    if prev_tex is not None and abs(tex - prev_tex) > 0.01:
        changes += 1
    prev_tex = tex
    print(f"{t:6.2f} {str(in_dense):>7} {tex:6.3f} {mask:6.3f} {tp:>8} {mpp:>9} {ring:6.1f}")
print(f"\ntex 变化次数(相邻>0.01): {changes}/45  -> 动画在动={'YES' if changes>5 else 'NO'}")
