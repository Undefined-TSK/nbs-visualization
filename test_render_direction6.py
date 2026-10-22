"""方向⑥ + 镜头修复 验证：分别渲染 无音频(看抖动修复) / 有音频(看声音驱动) 两段 3s 片。"""
import os, time, cv2
import imageio_ffmpeg
from nbs_visualizer.renderer_audio import render_video

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
MP3 = r"D:/nbs可视化/uploads/植物大战僵尸1.mp3"

print(">>> [A] 无音频渲染（验证镜头抖动修复）...")
t0 = time.time()
outA = render_video(NBS, r"D:/nbs可视化/outputs/test_camera_fixed.mp4",
                   use_kimi=False, max_duration=3)
print(f"   done in {time.time()-t0:.1f}s -> {outA} ({os.path.getsize(outA)} bytes)")

print(">>> [B] 有音频渲染（验证 librosa 声音驱动运镜+粒子）...")
t0 = time.time()
outB = render_video(NBS, r"D:/nbs可视化/outputs/test_audio_driven.mp4",
                   audio_file=MP3, use_kimi=False, max_duration=3)
print(f"   done in {time.time()-t0:.1f}s -> {outB} ({os.path.getsize(outB)} bytes)")

# 解码校验
for tag, out in [("A", outA), ("B", outB)]:
    cap = cv2.VideoCapture(out)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps=cap.get(cv2.CAP_PROP_FPS); cap.release()
    print(f"[{tag}] frames={n} {w}x{h} fps={fps:.0f}")
print("ALL DONE")
