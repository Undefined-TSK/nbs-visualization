"""方向⑤端到端验证：完整多进程渲染 + H.264 合并。"""
import os
import subprocess
import imageio_ffmpeg
import cv2

from nbs_visualizer.renderer_multiprocess import render_video_multiprocess


def main():
    NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
    OUT = r"D:/nbs可视化/outputs/test_mp_full.mp4"

    print(">>> render_video_multiprocess (max_duration=5, num_workers=4) ...")
    out = render_video_multiprocess(NBS, OUT, max_duration=5, num_workers=4,
                                    progress_callback=lambda p, m: print(f"   [{p:.2f}] {m}"))
    print("<<< output:", out, "exists=", os.path.exists(out), "size=", os.path.getsize(out) if os.path.exists(out) else 0)

    # 解码校验
    cap = cv2.VideoCapture(out)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    print(f"decoded: frames={n} {w}x{h} fps={fps}")

    # 用 ffmpeg 确认编码为 H.264（imageio 只提供 ffmpeg，无 ffprobe）
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", out, "-f", "null", "-"],
                       capture_output=True, text=True)
    probe = (r.stderr or "") + (r.stdout or "")
    print("ffmpeg probe codec line:", [l for l in probe.splitlines() if "Video:" in l])
    assert "h264" in probe.lower(), f"expected H.264, got: {probe[-300:]}"

    # 读一帧确认可解码
    cap = cv2.VideoCapture(out)
    ok, frame = cap.read()
    cap.release()
    assert ok and frame is not None and frame.shape[0] == h
    print("FULL PIPELINE OK: H.264", n, "frames @", int(fps), "fps")


if __name__ == "__main__":
    main()
