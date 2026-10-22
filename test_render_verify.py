"""验证渲染：5 秒含密集段，带音频，验证 press 动画 + 密集高斯脉冲 + 遮盖同步。"""
import os
from nbs_visualizer.renderer_audio import render_video

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
MP3 = r"D:/nbs可视化/uploads/植物大战僵尸1.mp3"
OUT = r"D:/nbs可视化/outputs/test_anim_fix_5s.mp4"

print(">>> render_video (max_duration=5, audio) ...")
out = render_video(
    NBS, OUT,
    audio_file=MP3 if os.path.exists(MP3) else None,
    use_kimi=False, max_duration=5,
    progress_callback=lambda p, m: print(f"   [{p:.2f}] {m}"),
)
print("<<< output:", out, "exists=", os.path.exists(out),
      "size=", os.path.getsize(out) if os.path.exists(out) else 0)
