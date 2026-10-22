"""方向⑤验证：SharedMemory 往返保真 + 多进程 worker 3秒分片渲染。"""
import os
import cv2
import numpy as np

from nbs_visualizer.stage import extract_tracks
from nbs_visualizer.render_plan import build_render_plan, RenderPlan
from nbs_visualizer.renderer_multiprocess import _render_segment_worker

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
OUT = r"D:/nbs可视化/outputs/test_mp_segment.mp4"

tracks, header = extract_tracks(NBS, use_kimi=False)
total_seconds = header.song_length / header.tempo
print(f"[main] tracks={len(tracks)} total_seconds={total_seconds:.2f}")

# ---- SharedMemory 往返 ----
plan, shm = build_render_plan(tracks, header, total_seconds, "song", total_seconds)
print(f"[plan] shm={plan.shm_name} size={plan.shm_size*8} bytes tracks={len(plan.tracks_meta)}")

recon = plan.reconstruct_tracks()

# 校验：轨道数、音符数、首音符、频谱形状/值
assert len(recon) == len(tracks), f"track count mismatch {len(recon)} != {len(tracks)}"
ok_notes = ok_spec = 0
for a, b in zip(tracks, recon):
    assert len(a.notes) == len(b.notes), f"note count mismatch L{a.layer_id}"
    # 首音符比对（float 容差）
    if a.notes and b.notes:
        for j in range(4):
            assert abs(a.notes[0][j] - b.notes[0][j]) < 1e-6, f"note value mismatch L{a.layer_id} field {j}"
        ok_notes += 1
    if a.spectrum_values is not None and b.spectrum_values is not None:
        assert a.spectrum_values.shape == b.spectrum_values.shape, "spec shape mismatch"
        assert np.allclose(a.spectrum_values, b.spectrum_values, atol=1e-6), "spec values mismatch"
        ok_spec += 1
print(f"[roundtrip] notes-checked={ok_notes} spectrum-checked={ok_spec}  OK")

# 释放共享内存
shm.close()
shm.unlink()

# ---- 多进程 worker：3 秒分片（0..360 帧 @120fps）----
# 重新构建一份共享内存供 worker 读取（上一处已 unlink）。
kwargs = {"use_kimi": False, "danmaku_list": None,
          "kimi_script_override": None, "audio_end_time": total_seconds}
plan2, shm2 = build_render_plan(tracks, header, total_seconds, "song", total_seconds)
try:
    res = _render_segment_worker((plan2, NBS, OUT, 0, 360, 360, kwargs))
    print(f"[worker] returned {res}")
    # 校验输出
    cap = cv2.VideoCapture(OUT)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    print(f"[worker] output frames={n} size={w}x{h} exists={os.path.exists(OUT)}")
    assert n == 360, f"expected 360 frames, got {n}"
    assert w == 1920 and h == 1080, f"unexpected dims {w}x{h}"
    print("[worker] 3s segment render OK")
finally:
    shm2.close()
    shm2.unlink()

print("ALL DIRECTION-5 CHECKS PASSED")
