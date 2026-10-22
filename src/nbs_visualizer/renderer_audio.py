"""视频渲染主函数 + 音频合成 + 快速预览。"""
from __future__ import annotations

import os
from typing import List, Dict, Optional

import cv2
import numpy as np
from PIL import Image

from .logger import get_logger

from .stage import (
    extract_tracks, compute_group_activity,
    OUTRO_FADEIN_DURATION, OUTRO_WAIT_DURATION,
    OUTRO_FADEOUT_DURATION, OUTRO_BUFFER,
    OUTRO_SCENE_FADE, OUTRO_SCENE_HOLD,
)
from ._core import FPS, VIDEO_WIDTH, VIDEO_HEIGHT

logger = get_logger(__name__)


# ============== 视频生成主函数 ==============
def render_video(nbs_file: str, output_path: str,
                 audio_file: Optional[str] = None,
                 use_kimi: bool = False,
                 danmaku_list: Optional[List[Dict]] = None,
                 kimi_script_override: Optional[Dict] = None,
                 progress_callback=None,
                 max_duration: Optional[float] = None,
                 fps: Optional[int] = None) -> str:
    logger.info("NBS parse: %s", nbs_file)
    # FIXED-B4: 问题49 - extract_tracks返回(tracks, header)，不再二次读取pynbs
    tracks, header = extract_tracks(nbs_file, use_kimi=use_kimi)

    if not tracks:
        raise ValueError("该 NBS 文件没有活跃轨道（所有轨道都没有音符）")

    tps = header.tempo
    if tps <= 0:
        raise ValueError(f"NBS文件tempo值无效: {tps}（文件可能损坏）")
    total_ticks = header.song_length
    total_seconds = total_ticks / tps
    song_name = header.song_name or os.path.splitext(os.path.basename(nbs_file))[0]

    if max_duration is not None and max_duration > 0:
        total_seconds = min(total_seconds, max_duration)
        logger.info("Preview mode: limited to %.1fs", total_seconds)

    logger.info("Song: %s", song_name)
    logger.info("Duration: %.1fs | Tracks: %d | TPS: %s", total_seconds, len(tracks), tps)
    for t in tracks:
        logger.info("  L%d [%s] %s / %s (%d notes)", t.layer_id, t.group, t.role_name, t.instrument_name, len(t.notes))

    # Kimi 歌曲分析（结构 + 镜头脚本 + 弹幕 + 字幕）
    kimi_script = kimi_script_override
    if use_kimi and tracks and kimi_script is None:
        try:
            from .kimi_ai import KimiAIService
            if progress_callback:
                progress_callback(0.02, "分析歌曲结构...")
            activity = compute_group_activity(tracks, total_seconds)
            tracks_info = [{
                "id": t.layer_id,
                "name": t.role_name,
                "instrument": t.instrument_name,
                "group": t.group,
                "group_index": t.group_index,
                "group_name": t.group_name,
                "note_count": len(t.notes),
            } for t in tracks]
            kimi_script = KimiAIService().analyze_song(tracks_info, total_seconds, activity)
            logger.info("Kimi analysis done: %d sections", len(kimi_script.get('sections', [])))
        except Exception as e:
            logger.warning("Kimi analysis skipped: %s", e)
            kimi_script = None

    # 从 Kimi 脚本中提取弹幕
    danmaku_data = kimi_script.get("danmaku", []) if kimi_script else None

    # FIXED-B4: 问题54 - audio_end_time优先使用实际音频时长(ffprobe)，NBS理论时长作后备
    audio_duration = total_seconds
    if audio_file and os.path.exists(audio_file):
        try:
            import subprocess
            ffmpeg = None
            try:
                import imageio_ffmpeg
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception as e:
                logger.warning("Failed to load imageio_ffmpeg: %s", e)
            if not ffmpeg:
                import shutil
                ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
                if not os.path.exists(ffprobe):
                    ffprobe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
                    if not os.path.exists(ffprobe):
                        ffprobe = "ffprobe"
                result = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", audio_file],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    audio_duration = float(result.stdout.strip())
                    logger.info("Audio duration: %.1fs (ffprobe)", audio_duration)
        except Exception as e:
            logger.warning("ffprobe failed, using NBS duration: %s", e)

    from .renderer import FrameRenderer
    # 方向⑥：真实音频频谱（librosa 预计算到帧率），失败则优雅降级为 None
    audio_spectrum = None
    if audio_file and os.path.exists(audio_file) and total_seconds > 0:
        try:
            from .audio_analysis import AudioSpectrum, librosa_available
            if librosa_available():
                audio_spectrum = AudioSpectrum.from_file(
                    audio_file, FPS, total_seconds=total_seconds
                )
                logger.info("Audio spectrum (librosa) built: %d frames x %d bands",
                            audio_spectrum.bands.shape[0], audio_spectrum.n_bands)
        except Exception as e:  # noqa: BLE001
            logger.warning("Audio spectrum analysis skipped: %s", e)
    renderer = FrameRenderer(tracks, song_name, audio_end_time=audio_duration,
                             kimi_script=kimi_script,
                             danmaku_list=danmaku_data if danmaku_data else danmaku_list,
                             audio_spectrum=audio_spectrum)
    fps = int(fps) if fps and fps > 0 else FPS
    total_video_seconds = total_seconds + OUTRO_FADEIN_DURATION + OUTRO_WAIT_DURATION + OUTRO_FADEOUT_DURATION + OUTRO_BUFFER + OUTRO_SCENE_FADE + OUTRO_SCENE_HOLD
    total_frames = int(total_video_seconds * fps) + 1

    logger.info("Render started: %d frames @ %dfps", total_frames, fps)
    # 默认用 ffmpeg libx264 高质量编码（远优于 cv2 内置的 mp4v/MPEG-4 Part2）；
    # 若 ffmpeg/libx264 不可用则回退到 cv2 mp4v。
    ok = _encode_video_ffmpeg(renderer, total_frames, fps, VIDEO_WIDTH, VIDEO_HEIGHT, output_path, progress_callback)
    if not ok:
        logger.warning("ffmpeg H.264 编码失败，回退到 cv2 mp4v")
        _encode_video_cv2(renderer, total_frames, fps, VIDEO_WIDTH, VIDEO_HEIGHT, output_path, progress_callback)

    # 显式释放渲染器内存，避免第二次渲染时numpy内存不足
    del renderer
    del tracks
    import gc
    gc.collect()

    logger.info("Render done: %s", output_path)
    if progress_callback:
        # FIXED-B4: 问题55 - 从0.90开始递增，避免进度倒退
        progress_callback(0.90, "正在合成音频...")

    if audio_file and os.path.exists(audio_file):
        final_path = output_path.replace(".mp4", "_with_audio.mp4")
        logger.info("Muxing audio: %s", audio_file)
        success = _mux_audio(output_path, audio_file, final_path, max_audio_duration=total_seconds)
        if success:
            logger.info("Audio mux done: %s", final_path)
            if progress_callback:
                progress_callback(1.0, "合成完成！")
            return final_path
        else:
            logger.error("Audio mux failed, returning silent video")
            if progress_callback:
                progress_callback(1.0, "音频合成失败，已生成无声视频")
            return output_path

    if progress_callback:
        progress_callback(1.0, "渲染完成！")
    return output_path


def _get_ffmpeg_exe():
    """返回可用的 ffmpeg 可执行文件路径（优先 imageio_ffmpeg，其次系统 PATH）。"""
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    import shutil
    return shutil.which("ffmpeg")


def _encode_video_ffmpeg(renderer, total_frames: int, fps: int, w: int, h: int,
                         output_path: str, progress_callback=None) -> bool:
    """用 ffmpeg + libx264 高质量编码。逐帧通过 stdin 管道写入，内存友好。失败时返回 False。"""
    import subprocess
    ffmpeg = _get_ffmpeg_exe()
    if not ffmpeg:
        return False
    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-an", output_path,
    ]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.warning("ffmpeg 启动失败: %s", e)
        return False
    try:
        for fi in range(total_frames):
            t = fi / fps
            frame = renderer.render(t)
            proc.stdin.write(np.ascontiguousarray(frame).astype(np.uint8).tobytes())
            if progress_callback and fi % 10 == 0:
                progress_callback(min(0.90, fi / total_frames), f"渲染中... {fi}/{total_frames}")
    except Exception as e:
        logger.warning("ffmpeg 写入中断: %s", e)
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        return False
    try:
        proc.stdin.close()
    except Exception:
        pass
    rc = proc.wait()
    return rc == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0


def _encode_video_cv2(renderer, total_frames: int, fps: int, w: int, h: int,
                      output_path: str, progress_callback=None):
    """回退编码：cv2 内置 mp4v（MPEG-4 Part2，画质较低）。"""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
    if not out.isOpened():
        raise RuntimeError(f"无法创建视频写入器: {output_path}（编码器不可用或路径无效）")
    try:
        for fi in range(total_frames):
            t = fi / fps
            frame = renderer.render(t)
            out.write(frame)
            if progress_callback and fi % 10 == 0:
                progress_callback(min(0.90, fi / total_frames), f"渲染中... {fi}/{total_frames}")
    finally:
        out.release()


def _mux_audio(video_path: str, audio_path: str, output_path: str,
               max_audio_duration: Optional[float] = None) -> bool:
    import subprocess
    import shutil

    ffmpeg = None
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        logger.warning("Failed to load imageio_ffmpeg for audio mux: %s", e)
    if not ffmpeg:
        ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        # FIXED-MC: 元问题C - ffmpeg fallback路径从 config.py 导入
        from . import config
        for p in config.FFMPEG_FALLBACK_PATHS:
            if os.path.exists(p):
                ffmpeg = p
                break
    if not ffmpeg:
        logger.error("ffmpeg not found, please install it")
        return False

    video_abs = os.path.abspath(video_path)
    audio_abs = os.path.abspath(audio_path)
    output_abs = os.path.abspath(output_path)

    cmd = [
        ffmpeg, "-y",
        "-i", video_abs,
        "-i", audio_abs,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v",
        "-map", "1:a",
    ]
    if max_audio_duration is not None and max_audio_duration > 0:
        cmd.extend(["-t", str(max_audio_duration + OUTRO_FADEIN_DURATION + OUTRO_WAIT_DURATION + OUTRO_FADEOUT_DURATION + OUTRO_BUFFER)])
    cmd.extend(["-shortest", output_abs])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=300)
        if result.returncode != 0:
            logger.error("ffmpeg error: %s", result.stderr[-500:])
            return False
        return True
    except Exception as e:
        logger.error("ffmpeg exception: %s", e)
        return False


# ============== 快速预览 ==============
def preview_frame(nbs_file: str, output_png: str, t: float = 0.0,
                  use_kimi: bool = False):
    from .renderer import FrameRenderer
    # FIXED-B4: 问题49 - extract_tracks返回(tracks, header)，复用header
    tracks, header = extract_tracks(nbs_file, use_kimi=use_kimi)
    if not tracks:
        logger.error("No active tracks")
        return
    song_name = header.song_name or os.path.splitext(os.path.basename(nbs_file))[0]
    renderer = FrameRenderer(tracks, song_name)
    frame_pil = Image.fromarray(cv2.cvtColor(renderer.render(t), cv2.COLOR_BGR2RGB))
    frame_pil.save(output_png)
    logger.info("Preview frame saved: %s", output_png)
