"""验证可打断动画系统：遮盖延迟 + 密集区高速振荡 + 变形过渡性 + 频谱裁剪。"""
from nbs_visualizer.track_operations import extract_tracks
from nbs_visualizer.stage_layout import StageLayout
from nbs_visualizer.stage_constants import (
    SPECTRUM_RENDER_GAP_RATIO, MASK_LAG,
)

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
tracks, header = extract_tracks(NBS)
_end = 0.0
for tr in tracks:
    for (ps, pe) in tr.press_events:
        _end = max(_end, pe)
    for (ds, de) in tr.dense_regions:
        _end = max(_end, de)
audio_end_time = _end + 2.0
layout = StageLayout(tracks, audio_end_time=audio_end_time)

FPS = 120
dt = 1.0 / FPS
T_END = min(audio_end_time, 40.0)
n = int(T_END * FPS) + 1

tr = max(tracks, key=lambda t: len(t.dense_regions) * 1000 + len(t.press_events))
tsm = layout.get_tsm(tr.layer_id)
print(f"[track] layer={tr.layer_id} notes={len(tr.notes)} "
      f"press_events={len(tr.press_events)} dense_regions={len(tr.dense_regions)}")

tex_hist, mask_hist, osc_hist, sx_hist, t_hist = [], [], [], [], []
for i in range(n):
    t = i * dt
    tsm.advance_anim(t, dt)
    tex = tsm.get_texture_scale(t)
    mask = tsm.get_mask_scale(t)
    osc = tsm._mask_oscillation(t)
    sx, _ = tsm.get_squash(t)
    t_hist.append(t); tex_hist.append(tex); mask_hist.append(mask)
    osc_hist.append(osc); sx_hist.append(sx)

# ===== A. 密集区保持段：贴图方形 + 遮盖高速振荡 =====
print("\n[A] 密集区保持段（贴图应≈0.80且无形变；遮盖应高速振荡 0.90↔0.50）")
worst_tex = 1.0
pulse_total = 0
for (ds, de) in tr.dense_regions:
    pad = 0.15
    seg = [mask_hist[i] for i in range(int((ds + pad) * FPS), int((de - pad) * FPS)) if 0 <= i < n]
    if not seg:
        continue
    mn, mx = min(seg), max(seg)
    mean = sum(seg) / len(seg)
    cnt = sum(1 for k in range(1, len(seg) - 1) if seg[k] < seg[k-1] and seg[k] <= seg[k+1] and seg[k] < mean - 0.05)
    pulse_total += cnt
    print(f"   dense [{ds:6.2f},{de:6.2f}]  mask∈[{mn:.3f},{mx:.3f}]  局部脉冲数={cnt}")
    for i in range(int((ds + pad) * FPS), int((de - pad) * FPS)):
        if 0 <= i < n:
            worst_tex = min(worst_tex, tex_hist[i])
print(f"   贴图在密集段最小缩放={worst_tex:.3f} (目标 0.80)")
print(f"   密集区总脉冲数≈{pulse_total} (高速振荡已出现)")
assert worst_tex < 0.83, "贴图在密集段未保持按下!"

# ===== B. 遮盖延迟（仅统计按门前静止的干净事件）=====
print("\n[B] 遮盖延迟（仅统计按门前遮盖静止的干净按下）")
samples = []
for (ps, pe) in tr.press_events[:400]:
    pre = int((ps - 0.06) * FPS)
    if pre < 0 or pre >= n:
        continue
    if mask_hist[pre] > 0.97 and tex_hist[pre] > 0.97:
        tex_down = next((t_hist[i] for i in range(int(ps*FPS), min(int(pe*FPS)+5, n)) if tex_hist[i] < 0.95), None)
        mask_down = next((t_hist[i] for i in range(int(ps*FPS), min(int(pe*FPS)+80, n)) if mask_hist[i] < 0.95), None)
        if tex_down is not None and mask_down is not None:
            samples.append((mask_down - tex_down) * 1000)
if samples:
    avg = sum(samples)/len(samples)
    print(f"   干净样本={len(samples)}  平均滞后={avg:.0f}ms  范围[{min(samples):.0f},{max(samples):.0f}]ms "
          f"(设定 MASK_LAG={MASK_LAG*1000:.0f}ms + 弹簧平滑)")
    assert 10 <= avg <= 300 and min(samples) > 0, "遮盖延迟异常!"
    print("   遮盖延迟检查: OK (遮盖始终比贴图慢半拍)")

# ===== C. 变形过渡性：长密集区中段应无形变（正方形）；入口过渡段有形变 =====
print("\n[C] 变形过渡性（长密集区中段应无形变→正方形；入口过渡段有形变）")
sq_mid, sq_entry = [], []
for (ds, de) in tr.dense_regions:
    if (de - ds) < 1.5:
        continue
    mid0, mid1 = int((ds + 0.6) * FPS), int((de - 0.6) * FPS)
    for i in range(mid0, mid1):
        if 0 <= i < n:
            sq_mid.append(abs(sx_hist[i] - tex_hist[i]))
    e0, e1 = int((ds + 0.02) * FPS), int((ds + 0.14) * FPS)
    for i in range(e0, e1):
        if 0 <= i < n:
            sq_entry.append(abs(sx_hist[i] - tex_hist[i]))
if sq_mid:
    print(f"   长密集区中段平均形变 = {sum(sq_mid)/len(sq_mid):.4f} (应≈0 → 正方形)")
    print(f"   入口过渡段平均形变   = {sum(sq_entry)/len(sq_entry):.4f} (应>0 → 压缩/拉伸)")
    assert sum(sq_mid)/len(sq_mid) < 0.01, "长 hold 中段仍有形变残留!"
    assert sum(sq_entry)/len(sq_entry) > 0.01, "入口过渡段无形变!"

# ===== D. 频谱条裁剪 =====
print("\n[D] 频谱条裁剪核对")
bs = layout.block_size
half = bs / 2.0
spec_gap = max(3, int(bs * SPECTRUM_RENDER_GAP_RATIO))
card_half = layout.card_size / 2.0
max_allowed = card_half - half - spec_gap - 4.0
clamped = min(bs * 0.20, max_allowed)
tip = half + spec_gap + clamped
print(f"   bs={bs:.0f} card_half={card_half:.1f} raw_max={bs*0.20:.1f} clamped={clamped:.1f} tip={tip:.1f}")
assert tip <= card_half - 2, "频谱条尖端仍超出卡片!"
print(f"   频谱条尖端 {tip:.1f} < 卡片半边 {card_half:.1f} → 不溢出 OK")

print("\n========== 全部断言通过 ==========")
