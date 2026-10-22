"""渲染关键帧 PNG（ASCII 路径避免 opencv 中文路径写入失败）+ 单块放大裁剪，用于核验修复。"""
import os, cv2, numpy as np
from nbs_visualizer.track_operations import extract_tracks
from nbs_visualizer.renderer import FrameRenderer
from nbs_visualizer.stage_constants import BLOCK_PRESSED_SCALE, DENSE_RECOVERY

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
OUTDIR = r"D:/fixframes_tmp"
os.makedirs(OUTDIR, exist_ok=True)

tracks, header = extract_tracks(NBS, use_kimi=False)
song_name = header.song_name or "song"
renderer = FrameRenderer(tracks, song_name, audio_end_time=999.0, kimi_script=None, danmaku_list=None, audio_spectrum=None)
layout = renderer.stage

tr = max(tracks, key=lambda t: len(t.notes))
press_t = tr.press_events[0][0] if tr.press_events else 0.5
dr = tr.dense_regions[0] if tr.dense_regions else (2.0, 3.0)
print(f"press_t={press_t:.3f} dense={dr} BLOCK_PRESSED_SCALE={BLOCK_PRESSED_SCALE} DENSE_RECOVERY={DENSE_RECOVERY}")

targets = {
    "01_rest": 0.30,
    "02_press_start": press_t,
    "03_press_hold": press_t + 0.05,
    "04_release": press_t + 0.20,
    "05_dense_enter": dr[0] + 0.05,
    "06_dense_pulse": dr[0] + 0.15,
}
for name, t in targets.items():
    frame = renderer.render(t)
    png = os.path.join(OUTDIR, name + ".png")
    ok = cv2.imwrite(png, frame)
    print(f"  full  {name} t={t:.3f} ok={ok}")

# 单块放大裁剪：取最活跃轨道方块中心，裁 360x360 区域并 2x 上采样
cx, cy = layout.get_position(tr.layer_id, 0.0)
cx, cy = int(round(cx)), int(round(cy))
half = 200
for name, t in {"A_press_crop": press_t + 0.03, "B_dense_crop": dr[0] + 0.12}.items():
    frame = renderer.render(t)
    h, w = frame.shape[:2]
    x0, x1 = max(0, cx-half), min(w, cx+half)
    y0, y1 = max(0, cy-half), min(h, cy+half)
    crop = frame[y0:y1, x0:x1]
    crop = cv2.resize(crop, (crop.shape[1]*2, crop.shape[0]*2), interpolation=cv2.INTER_NEAREST)
    png = os.path.join(OUTDIR, name + ".png")
    ok = cv2.imwrite(png, crop)
    print(f"  crop  {name} t={t:.3f} ok={ok}  center=({cx},{cy})")
print("DONE", OUTDIR)
