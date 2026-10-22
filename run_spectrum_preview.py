"""短预览：验证频谱条已随真实音频起伏，且其它动画无回归。"""
import os
import sys
import time
import traceback

from nbs_visualizer import render_video

NBS = "D:/MCMusic/植物大战僵尸1.nbs"
MP3 = "D:/MCMusic/植物大战僵尸1.mp3"
OUT = "outputs/spectrum_test_6s_with_audio.mp4"

if __name__ == "__main__":
    t0 = time.time()
    try:
        out = render_video(
            NBS, OUT,
            audio_file=MP3,
            use_kimi=False,        # 跳过 Kimi 省时，专注验证频谱/动画
            max_duration=6,        # 仅前 6 秒（引擎会追加 ~9s 尾版）
        )
        print("OK ->", out, "  (%.1fs)" % (time.time() - t0))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
