"""方向⑦ 集成验证：单进程渲染 3 秒切片，验证粒子/遮盖新行为可跑通且产物正常。"""
import os
from nbs_visualizer.renderer_audio import render_video

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
OUT = r"D:/nbs可视化/outputs/test_particles_v2_3s.mp4"

print(">>> render_video(max_duration=3) ...")
out = render_video(NBS, OUT, max_duration=3, progress_callback=None)
print("<<< output:", out, "exists=", os.path.exists(out),
      "size=", os.path.getsize(out) if os.path.exists(out) else 0)

import cv2
cap = cv2.VideoCapture(out)
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()
print(f"decoded: frames={n} {w}x{h} fps={fps}")
assert n > 300, "帧数异常"
print("INTEGRATION OK")
