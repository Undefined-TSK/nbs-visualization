"""整曲渲染运行脚本（植物大战僵尸1）。

用法:
    venv_python run_full_song.py

输出: outputs/pvz1_full_with_audio.mp4
日志: outputs/full_render.log
"""
import os
import sys
import time
import logging
import traceback

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(APP_ROOT, "src"))

# 日志同时打到文件和控制台
log_path = os.path.join(APP_ROOT, "outputs", "full_render.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("full_song")

NBS = r"D:\MCMusic\植物大战僵尸1.nbs"
MP3 = r"D:\MCMusic\植物大战僵尸1.mp3"
OUT = os.path.join(APP_ROOT, "outputs", "pvz1_full_with_audio.mp4")


def main():
    t0 = time.time()
    logger.info("=" * 60)
    logger.info("FULL SONG RENDER START")
    logger.info("NBS : %s", NBS)
    logger.info("MP3 : %s", MP3)
    logger.info("OUT : %s", OUT)
    logger.info("=" * 60)

    # 进度回调：每 100 帧上报一次
    last_log = [0]

    def progress(frame_index, total_frames, phase=None):
        if total_frames and frame_index - last_log[0] >= 200:
            pct = 100.0 * frame_index / total_frames
            elapsed = time.time() - t0
            fps_now = frame_index / elapsed if elapsed > 0 else 0
            logger.info(
                "progress %.1f%%  (%d/%d frames)  elapsed=%.0fs  %.1f fps",
                pct, frame_index, total_frames, elapsed, fps_now,
            )
            last_log[0] = frame_index

    try:
        from nbs_visualizer import render_video
        out = render_video(
            nbs_file=NBS,
            output_path=OUT,
            audio_file=MP3,
            use_kimi=True,
            max_duration=None,  # 整曲
            fps=120,
            progress_callback=progress,
        )
        elapsed = time.time() - t0
        logger.info("=" * 60)
        logger.info("RENDER COMPLETE in %.1f min -> %s", elapsed / 60.0, out)
        logger.info("=" * 60)
    except Exception:
        logger.error("RENDER FAILED after %.1f min", (time.time() - t0) / 60.0)
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
