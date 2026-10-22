"""镜头抖动诊断：对比'无 Kimi' 与 '有脚本' 两种模式下摄像机行为。"""
import os
from nbs_visualizer.stage import extract_tracks
from nbs_visualizer.camera import CameraController

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
tracks, header = extract_tracks(NBS, use_kimi=False)
FPS = 120
print(f"tracks={len(tracks)}  total_seconds={header.song_length/header.tempo:.1f}")

def run(script, label):
    cam = CameraController(tracks, None, kimi_script=script)
    last_ang = cam._shake_ang
    ang_changes = 0
    max_pan = 0.0
    pan_samples = []
    zoom_samples = []
    t0 = 0.0
    for fi in range(int(3.0 * FPS)):
        t = fi / FPS
        cam.update(t)
        zoom, px, py = cam.get_transform()
        pan = (px*px + py*py) ** 0.5
        if pan > max_pan:
            max_pan = pan
        if fi % 30 == 0:
            pan_samples.append(round(pan, 2))
            zoom_samples.append(round(zoom, 3))
        if cam._shake_ang != last_ang:
            ang_changes += 1
            last_ang = cam._shake_ang
    print(f"\n=== {label} ===")
    print(f"  震动方向重选次数(3s): {ang_changes}  (~{ang_changes/3.0:.1f}/s)")
    print(f"  最大镜头平移: {max_pan:.1f} px")
    print(f"  pan 采样(每0.25s): {pan_samples}")
    print(f"  zoom 采样(每0.25s): {zoom_samples}")
    return ang_changes, max_pan

# 无 Kimi（自动导演）
run(None, "无 Kimi（自动导演模式）")
# 有脚本（模拟若干 close/group 切换）—— 用 stub layout 避免 None.get_position
class _StubLayout:
    def get_position(self, layer_id):
        return (960.0, 540.0)
script = {"cameras": [
    {"time": 0.0, "type": "wide", "focus": "all"},
    {"time": 1.0, "type": "group", "focus": 0},
    {"time": 2.0, "type": "close", "focus": tracks[0].layer_id},
]}
try:
    run(script, "有 Kimi 脚本")
except Exception as e:
    print("有脚本用例跳过(诊断桩异常):", e)
