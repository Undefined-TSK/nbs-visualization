"""轨道操作：合并稀疏层、提取 NBS 轨道数据、计算声部组活跃度时间线。"""
from __future__ import annotations

from typing import List, Tuple, Dict

import pynbs

from .logger import get_logger

from .track_data import TrackData
from .stage_constants import translate_role_name_local, GROUP_ORDER, GROUP_LABELS
from .resources import INSTRUMENT_MAP

logger = get_logger(__name__)


def _merge_tracks(tracks: List[TrackData], total_seconds: float) -> List[TrackData]:
    """合并同名同乐器的稀疏层到密集层，并为重名组添加编号后缀。"""
    dropped = [t for t in tracks if len(t.notes) < 3]
    for t in dropped:
        logger.info("Merge: dropped L%d \"%s\" (only %d notes)", t.layer_id, t.layer_name, len(t.notes))
    tracks = [t for t in tracks if len(t.notes) >= 3]

    groups: Dict[Tuple[str, int], List[TrackData]] = {}
    for t in tracks:
        key = (t.role_name, t.instrument_id)
        groups.setdefault(key, []).append(t)

    merged: List[TrackData] = []
    for key, group in groups.items():
        group.sort(key=lambda t: len(t.notes), reverse=True)
        target = group[0]
        to_keep = []

        for t in group[1:]:
            if t.is_sparse():
                logger.info("Merge: L%d \"%s\" (%d notes) → L%d", t.layer_id, t.layer_name, len(t.notes), target.layer_id)
                target.notes.extend(t.notes)
            else:
                to_keep.append(t)

        if any(t for t in group[1:] if t.is_sparse()):
            target.recompute_derived(total_seconds)

        remaining = [target] + to_keep

        if len(remaining) > 1:
            for i, t in enumerate(remaining):
                if i > 0:
                    t.role_name = f"{t.role_name} {i + 1}"

        merged.extend(remaining)

    return merged


def extract_tracks(nbs_file: str, use_kimi: bool = False) -> Tuple[List[TrackData], object]:
    # FIXED: 问题59 - pynbs.read包裹异常保护，tempo=0防ZeroDivisionError
    # FIXED-B4: 问题49 - 返回(tracks, header)，render_video复用header不再二次读取
    try:
        song = pynbs.read(nbs_file)
    except Exception as e:
        raise RuntimeError(f"无法读取NBS文件: {nbs_file}（{e}）")
    tps = song.header.tempo
    if tps <= 0:
        raise ValueError(f"NBS文件tempo值无效: {tps}（文件可能损坏）")
    total_ticks = song.header.song_length
    total_seconds = total_ticks / tps

    layers = {l.id: l for l in song.layers}
    layer_notes: Dict[int, List] = {}
    for note in song.notes:
        layer_notes.setdefault(note.layer, []).append(note)

    tracks: List[TrackData] = []
    for layer_id, notes_list in layer_notes.items():
        if not notes_list:
            continue
        layer = layers.get(layer_id, None)
        layer_name = layer.name if (layer and layer.name) else f"Layer {layer_id}"
        role_name = translate_role_name_local(layer_name)

        inst_counts = {}
        for n in notes_list:
            inst_counts[n.instrument] = inst_counts.get(n.instrument, 0) + 1
        main_inst = max(inst_counts, key=inst_counts.get)
        inst_info = INSTRUMENT_MAP.get(main_inst, INSTRUMENT_MAP[0])

        track = TrackData(layer_id, layer_name, role_name, main_inst, inst_info[1])
        notes_list.sort(key=lambda n: n.tick)

        for n in notes_list:
            start_t = n.tick / tps
            velocity = (n.velocity if hasattr(n, 'velocity') and n.velocity else 100) / 100.0
            end_t = start_t + 0.3
            track.notes.append((start_t, end_t, n.key, velocity))

        track.recompute_derived(total_seconds)
        if track.is_active:
            tracks.append(track)

    # 合并稀疏层
    logger.info("Merge: processing same-name layers...")
    tracks = _merge_tracks(tracks, total_seconds)
    logger.info("Merge: done, %d tracks remaining", len(tracks))

    # Kimi 角色命名（在合并之后，因为需要知道最终有哪些轨道、同乐器有几个）
    if use_kimi and tracks:
        try:
            from .kimi_ai import KimiAIService
            # 统计同乐器的序号
            inst_seen: Dict[int, int] = {}
            tracks_info = []
            for t in tracks:
                inst_seen[t.instrument_id] = inst_seen.get(t.instrument_id, 0) + 1
                n_notes = len(t.notes)
                span = t.notes[-1][0] - t.notes[0][0] if n_notes > 1 else 1.0
                density = n_notes / max(span, 0.1)
                tracks_info.append({
                    "id": t.layer_id,
                    "instrument_name": t.instrument_name,
                    "layer_name": t.layer_name,
                    "group": t.group,
                    "note_count": n_notes,
                    "density": density,
                    "inst_index": inst_seen[t.instrument_id],
                })

            naming = KimiAIService().name_tracks(tracks_info)
            for t in tracks:
                if t.layer_id in naming and naming[t.layer_id]:
                    info = naming[t.layer_id]
                    if isinstance(info, dict):
                        t.role_name = info.get("name", t.role_name)
                        t.group = info.get("group", t.group)
                    else:
                        t.role_name = info
            logger.info("Kimi role naming done (%d tracks)", len(naming))

            # Kimi 轨道分组（命名之后，独立 API 调用）
            from .kimi_ai import KimiAIService
            grouping = KimiAIService().group_tracks(tracks_info, naming)
            groups = grouping.get("groups", [])
            logger.info("Kimi grouping done (%d groups)", len(groups))
            for g in groups:
                logger.info("  Group %d: %s → %s", g['index'], g['name'], g['track_ids'])

            # 构建 layer_id → (group_index, within_group_pos) 映射
            pos_map = {}
            for g in groups:
                for pos, tid in enumerate(g.get("order", g["track_ids"])):
                    pos_map[tid] = (g["index"], pos)

            # 设置 track 的 group_index 和 group_name
            for t in tracks:
                if t.layer_id in pos_map:
                    gi, _ = pos_map[t.layer_id]
                    t.group_index = gi
                    for g in groups:
                        if g["index"] == gi:
                            t.group_name = g["name"]
                            break

            # 按 group_index + within_group_pos 排序
            tracks.sort(key=lambda t: pos_map.get(t.layer_id, (99, t.layer_id)))
        except Exception as e:
            logger.warning("Kimi role naming/grouping skipped: %s", e)

    # 非 Kimi 模式按原始声部组排序，并设置 group_index
    if not use_kimi or not tracks or not any(t.group_name for t in tracks):
        group_order_map = {g: i for i, g in enumerate(GROUP_ORDER)}
        tracks.sort(key=lambda t: (group_order_map.get(t.group, 99), t.layer_id))
        # FIXED: 问题2 - 非Kimi模式按声部角色设默认group_index，使不同声部分到不同组
        _gi = 0
        _prev_group = None
        for t in tracks:
            if t.group != _prev_group:
                _gi = group_order_map.get(t.group, 0)
                _prev_group = t.group
            t.group_index = _gi
            t.group_name = GROUP_LABELS.get(t.group, t.group)
    return tracks, song.header



def compute_group_activity(tracks: List[TrackData], total_seconds: float,
                           window: float = 1.0, step: float = 0.5) -> List[Dict[str, float]]:
    """
    计算每个声部组（旋律/和声/贝斯/节奏）的活跃度时间线。
    返回列表，每项: {time, melody, harmony, bass, rhythm}，值为 0-1 的活跃度。
    """
    times = []
    t = 0.0
    while t <= total_seconds:
        times.append(t)
        t += step

    result = []
    for ct in times:
        start = max(0, ct - window / 2)
        end = min(total_seconds, ct + window / 2)
        activity = {"melody": 0.0, "harmony": 0.0, "bass": 0.0, "rhythm": 0.0}
        max_act = 0.0

        for track in tracks:
            # 统计窗口内的音符数
            count = 0
            total_vel = 0.0
            # FIXED-B3: 问题50 - 用enumerate替代.index()，避免重复时间戳返回首个匹配
            for idx, ns in enumerate(track.note_starts):
                if start <= ns <= end:
                    count += 1
                    # 用速度近似力度
                    if idx < len(track.notes):
                        total_vel += track.notes[idx][3]
                    else:
                        total_vel += 1.0
                elif ns > end:
                    break

            if count > 0:
                # 活跃度 = 音符密度 * 平均力度
                density = count / max(end - start, 0.1)
                avg_vel = total_vel / count
                act = density * avg_vel * 0.1  # 缩放因子
                activity[track.group] = activity.get(track.group, 0.0) + act
                max_act = max(max_act, activity[track.group])

        # 归一化到 0-1
        if max_act > 0:
            for g in activity:
                activity[g] = min(1.0, activity[g] / max(max_act, 0.001))

        activity["time"] = ct
        result.append(activity)

    return result
