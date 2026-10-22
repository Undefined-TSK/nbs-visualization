"""多进程并行渲染。"""
from __future__ import annotations

import os
import subprocess
from typing import Dict, List, Optional, Tuple, Any

import cv2

from .logger import get_logger

from .stage import (
    OUTRO_FADEIN_DURATION, OUTRO_WAIT_DURATION,
    OUTRO_FADEOUT_DURATION, OUTRO_BUFFER,
    OUTRO_SCENE_FADE, OUTRO_SCENE_HOLD,
)
from .renderer_audio import _mux_audio
from .render_plan import RenderPlan, build_render_plan

logger = get_logger(__name__)


# ============== 多进程并行渲染 ==============

def _render_segment_worker(args: Tuple[Optional[RenderPlan], str, str, int, int, int, Dict[str, Any]]) -> Tuple[int, int, str]:
    """多进程 worker：渲染指定帧区间到临时视频文件。

    Args:
        args: (plan, nbs_file, output_segment_path, start_frame, end_frame, total_frames, kwargs)
            - plan: 主进程经 SharedMemory 传入的渲染计划；为 None 时回退到重新解析 NBS。
            - nbs_file: 原始 NBS 路径（仅用于 SharedMemory 不可用时的回退）。
            - kwargs 包含: use_kimi, danmaku_list, kimi_script_override, audio_end_time

    Returns:
        (start_frame, end_frame, output_segment_path)
    """
    plan, nbs_file, output_segment_path, start_frame, end_frame, total_frames, kwargs = args

    from ._core import FPS, VIDEO_WIDTH, VIDEO_HEIGHT
    from .renderer import FrameRenderer

    use_kimi = kwargs.get("use_kimi", False)
    danmaku_list = kwargs.get("danmaku_list", None)
    kimi_script_override = kwargs.get("kimi_script_override", None)
    audio_end_time = kwargs.get("audio_end_time", None)

    # 主进程已解析 NBS 并经 SharedMemory 传入：优先重建，失败再回退重新解析。
    # 不再在子进程重复调用 Kimi（脚本已由主进程算好并随 kwargs 传入）。
    song_name = ""
    total_seconds = 0.0
    if plan is not None:
        try:
            tracks = plan.reconstruct_tracks()
            song_name = plan.song_name
            total_seconds = plan.total_seconds
        except Exception as e:
            logger.warning("SharedMemory 重建失败，回退 extract_tracks: %s", e)
            tracks = None
    else:
        tracks = None

    if tracks is None:
        from .stage import extract_tracks
        tracks, header = extract_tracks(nbs_file, use_kimi=False)
        song_name = header.song_name or os.path.splitext(os.path.basename(nbs_file))[0]
        total_seconds = header.song_length / header.tempo

    if not tracks:
        raise ValueError("该 NBS 文件没有活跃轨道")

    if audio_end_time is None:
        audio_end_time = total_seconds

    danmaku_data = None
    if kimi_script_override:
        danmaku_data = kimi_script_override.get("danmaku", [])
    if not danmaku_data and danmaku_list:
        danmaku_data = danmaku_list

    renderer = FrameRenderer(tracks, song_name, audio_end_time=audio_end_time,
                             kimi_script=kimi_script_override, danmaku_list=danmaku_data)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_segment_path, fourcc, FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))
    if not out.isOpened():
        raise RuntimeError(f"无法创建视频写入器: {output_segment_path}")

    try:
        for fi in range(start_frame, end_frame):
            t = fi / FPS
            frame = renderer.render(t)
            out.write(frame)
    finally:
        out.release()

    # 显式释放内存
    del renderer
    del tracks
    import gc
    gc.collect()

    return (start_frame, end_frame, output_segment_path)


def render_video_multiprocess(
    nbs_file: str,
    output_path: str,
    audio_file: Optional[str] = None,
    use_kimi: bool = False,
    danmaku_list: Optional[List[Dict]] = None,
    kimi_script_override: Optional[Dict] = None,
    progress_callback=None,
    num_workers: Optional[int] = None,
    max_duration: Optional[float] = None,
) -> str:
    """多进程并行渲染视频。

    将总帧数分成 N 段（N=CPU核心数），每段独立渲染，最后用 ffmpeg concat 合并。
    主进程仅解析 NBS 一次（经 SharedMemory 将音符+频谱传给子进程），子进程不重复解析。
    最终合并统一重新编码为 H.264（libx264 CRF16），与主渲染管线画质一致。

    Args:
        num_workers: 进程数，默认=CPU核心数（最多8，避免内存溢出）

    Returns:
        最终输出视频路径
    """
    import multiprocessing
    import tempfile

    if num_workers is None:
        num_workers = min(os.cpu_count() or 4, 8)

    logger.info("MultiProc: %d workers", num_workers)

    # ---- 第1步：预计算元数据（主进程，仅一次）----
    from .stage import extract_tracks, compute_group_activity

    tracks, header = extract_tracks(nbs_file, use_kimi=use_kimi)
    if not tracks:
        raise ValueError("该 NBS 文件没有活跃轨道")

    tps = header.tempo
    total_ticks = header.song_length
    total_seconds = total_ticks / tps
    if max_duration is not None and max_duration > 0:
        total_seconds = min(total_seconds, max_duration)
        logger.info("MultiProc preview mode: limited to %.1fs", total_seconds)
    song_name = header.song_name or os.path.splitext(os.path.basename(nbs_file))[0]

    logger.info("Song: %s | Duration: %.1fs | Tracks: %d", song_name, total_seconds, len(tracks))

    # Kimi 分析（主进程执行，避免多进程重复调用）
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
            logger.warning("Kimi skipped: %s", e)
            kimi_script = None

    danmaku_data = kimi_script.get("danmaku", []) if kimi_script else None
    if not danmaku_data and danmaku_list:
        danmaku_data = danmaku_list

    # 获取实际音频时长
    audio_duration = total_seconds
    if audio_file and os.path.exists(audio_file):
        try:
            import shutil
            ffmpeg = None
            try:
                import imageio_ffmpeg
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception as e:
                logger.warning("Failed to load imageio_ffmpeg for multiproc: %s", e)
            if not ffmpeg:
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
                    logger.info("Audio duration: %.1fs", audio_duration)
        except Exception as e:
            logger.warning("ffprobe failed: %s", e)

    from ._core import FPS
    total_video_seconds = total_seconds + OUTRO_FADEIN_DURATION + OUTRO_WAIT_DURATION + OUTRO_FADEOUT_DURATION + OUTRO_BUFFER + OUTRO_SCENE_FADE + OUTRO_SCENE_HOLD
    total_frames = int(total_video_seconds * FPS) + 1

    logger.info("MultiProc: %d frames, %d segments", total_frames, num_workers)

    # ---- 第1.5步：将解析结果打包进共享内存（子进程免重复解析）----
    shm_handle = None
    plan: Optional[RenderPlan] = None
    try:
        plan, shm_handle = build_render_plan(
            tracks, header, total_seconds, song_name, audio_duration
        )
        logger.info("SharedMemory plan built: shm=%s size=%d bytes, %d tracks",
                    plan.shm_name, int(plan.shm_size * 8), len(tracks))
    except Exception as e:
        logger.warning("SharedMemory 构建失败，回退为子进程重新解析: %s", e)
        plan = None

    # ---- 第2步：分段 ----
    overlap_frames = 10  # 重叠帧，消除拼接痕迹
    frames_per_worker = total_frames // num_workers
    segments = []
    for i in range(num_workers):
        start = i * frames_per_worker
        if i == num_workers - 1:
            end = total_frames
        else:
            end = (i + 1) * frames_per_worker + overlap_frames  # 多渲染overlap帧
        segments.append((start, end))

    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="nbs_render_")
    logger.info("MultiProc temp dir: %s", temp_dir)

    # 构造 worker 参数
    worker_kwargs = {
        "use_kimi": use_kimi,
        "danmaku_list": danmaku_data,
        "kimi_script_override": kimi_script,
        "audio_end_time": audio_duration,
    }

    worker_args = []
    for i, (start, end) in enumerate(segments):
        seg_path = os.path.join(temp_dir, f"segment_{i:03d}.mp4")
        worker_args.append((plan, nbs_file, seg_path, start, end, total_frames, worker_kwargs))

    # ---- 第3步：并行渲染 ----
    if progress_callback:
        progress_callback(0.05, f"启动 {num_workers} 个渲染进程...")

    completed = 0
    total_segment_frames = sum(e - s for s, e in segments)

    def _progress_update():
        nonlocal completed
        completed += 1
        if progress_callback:
            # 渲染进度：0.05 → 0.90
            pct = 0.05 + 0.85 * (completed / num_workers)
            progress_callback(min(0.90, pct), f"已完成 {completed}/{num_workers} 段")

    # Windows 下 multiprocessing 必须用 spawn 且函数在顶层
    # 由于 _render_segment_worker 已在模块顶层，可直接使用
    with multiprocessing.Pool(processes=num_workers) as pool:
        results = []
        for result in pool.imap_unordered(_render_segment_worker, worker_args):
            results.append(result)
            _progress_update()

    # 共享内存不再需要，立即释放
    if shm_handle is not None:
        try:
            shm_handle.close()
            shm_handle.unlink()
        except Exception as e:
            logger.warning("SharedMemory 释放失败: %s", e)

    # 按起始帧排序
    results.sort(key=lambda x: x[0])
    segment_paths = [r[2] for r in results]

    logger.info("MultiProc: all %d segments done", len(segment_paths))

    # ---- 第4步：用 ffmpeg 合并并统一编码为 H.264 ----
    if progress_callback:
        progress_callback(0.90, "合并视频分段...")

    # 生成 concat list 文件
    concat_list_path = os.path.join(temp_dir, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for sp in segment_paths:
            # ffmpeg concat demuxer 需要转义单引号
            escaped = sp.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    # 找 ffmpeg
    ffmpeg = None
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        logger.warning("Failed to load imageio_ffmpeg for concat: %s", e)
    if not ffmpeg:
        import shutil
        ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        from . import config
        for p in config.FFMPEG_FALLBACK_PATHS:
            if os.path.exists(p):
                ffmpeg = p
                break

    if not ffmpeg:
        logger.warning("MultiProc: ffmpeg not found, returning first segment (mp4v)")
        # 退化：直接返回第一段
        import shutil as sh
        sh.copy(segment_paths[0], output_path)
        _cleanup_temp_dir(temp_dir)
        return output_path

    # 执行 concat + 重新编码为 H.264（libx264 CRF16），保证最终画质与主管线一致
    cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-an", output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=600)
        if result.returncode != 0:
            logger.error("MultiProc H.264 concat error: %s", result.stderr[-500:])
            # 退化方案：返回第一段（mp4v）
            logger.warning("MultiProc: H.264 concat failed, returning first segment")
            import shutil as sh
            sh.copy(segment_paths[0], output_path)
        else:
            logger.info("MultiProc H.264 concat done: %s", output_path)
    except Exception as e:
        logger.error("MultiProc concat exception: %s", e)
        import shutil as sh
        sh.copy(segment_paths[0], output_path)

    # ---- 第5步：音频合成 ----
    if audio_file and os.path.exists(audio_file):
        if progress_callback:
            progress_callback(0.95, "合成音频...")
        final_path = output_path.replace(".mp4", "_with_audio.mp4")
        logger.info("Muxing audio: %s", audio_file)
        success = _mux_audio(output_path, audio_file, final_path)
        if success:
            logger.info("Audio mux done: %s", final_path)
            if progress_callback:
                progress_callback(1.0, "渲染完成！")
            # 清理临时文件
            _cleanup_temp_dir(temp_dir)
            return final_path
        else:
            logger.error("Audio mux failed, returning silent video")

    if progress_callback:
        progress_callback(1.0, "渲染完成！")

    _cleanup_temp_dir(temp_dir)
    return output_path


def _cleanup_temp_dir(temp_dir: str):
    """清理临时目录。"""
    import shutil
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("MultiProc temp dir cleaned: %s", temp_dir)
    except Exception as e:
        logger.warning("Failed to cleanup temp dir: %s", e)
