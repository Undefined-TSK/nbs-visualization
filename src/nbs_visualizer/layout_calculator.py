"""静态布局计算器：从 StageLayout._compute_layout 提取的独立函数。"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple, Dict

from .logger import get_logger

from .stage_constants import GROUP_PALETTE
from .track_data import TrackData

logger = get_logger(__name__)


def _calc_full_card(block_size: int,
                    spec_gap: int, spec_max: int, card_pad: int) -> int:
    """计算含频谱+内边距的完整卡片尺寸。"""
    return block_size + 2 * (spec_gap + spec_max + card_pad)


def compute_static_layout(
    tracks: List[TrackData],
    video_width: int,
    video_height: int,
    margin_ratio: float,
    label_height: int,
    card_target_size: int,
    card_min_size: int,
    spacing_ratio: float,
    row_gap_ratio: float,
    max_groups: int,
    group_gap: int,
    max_cards_per_row: int,
    max_row_diff: int,
) -> Tuple[Dict[int, Tuple[float, float]], List[Dict], int, int, int]:
    """计算所有卡片的固定位置。
    新布局v2：左对齐 + 横排顶标签 + 组内自动换行。
    返回 (positions, group_bounds, n_groups, block_size, card_size)。
    """
    from .stage_constants import (
        SPECTRUM_EDGE_GAP_RATIO, SPECTRUM_BAR_MAX_RATIO, CARD_PADDING_RATIO,
    )

    group_dict: Dict[int, List[TrackData]] = {}
    for tr in tracks:
        gi = tr.group_index
        group_dict.setdefault(gi, []).append(tr)

    n_groups = len(group_dict)
    if n_groups == 0:
        return {}, [], 0, 0, 0

    sorted_gis = sorted(group_dict.keys())

    # 组合并：超过max_groups时，将最小组并入相邻组
    if n_groups > max_groups:
        group_list = []
        for gi in sorted_gis:
            tr_list = group_dict[gi]
            name = tr_list[0].group_name if tr_list[0].group_name else f"组{gi+1}"
            group_list.append({"gi": gi, "name": name, "tracks": tr_list})

        while len(group_list) > max_groups:
            min_idx = min(range(len(group_list)), key=lambda i: len(group_list[i]["tracks"]))
            if min_idx == 0:
                merge_into = 1
            elif min_idx == len(group_list) - 1:
                merge_into = min_idx - 1
            else:
                left_size = len(group_list[min_idx - 1]["tracks"])
                right_size = len(group_list[min_idx + 1]["tracks"])
                merge_into = min_idx - 1 if left_size <= right_size else min_idx + 1

            small_g = group_list[min_idx]
            target_g = group_list[merge_into]
            target_g["tracks"].extend(small_g["tracks"])
            if len(small_g["tracks"]) > len(target_g["tracks"]):
                target_g["name"] = small_g["name"]
            group_list.pop(min_idx)
            logger.info("Group merge: \"%s\"(%d tracks) → \"%s\"(%d tracks)",
                       small_g['name'], len(small_g['tracks']),
                       target_g['name'], len(target_g['tracks']))

        group_dict = {}
        for new_gi, g in enumerate(group_list):
            for tr in g["tracks"]:
                tr.group_index = new_gi
                tr.group_name = g["name"]
            group_dict[new_gi] = g["tracks"]
        sorted_gis = sorted(group_dict.keys())
        n_groups = len(group_dict)
        logger.info("Group merge done: %d groups remaining", n_groups)

    margin_x = int(video_width * margin_ratio)
    margin_y = int(video_height * margin_ratio)
    avail_w = video_width - 2 * margin_x
    avail_h = video_height - 2 * margin_y

    def _calc_full(bs):
        spec_gap = max(3, int(bs * SPECTRUM_EDGE_GAP_RATIO))
        spec_max = max(6, int(bs * SPECTRUM_BAR_MAX_RATIO))
        card_pad = max(3, int(bs * CARD_PADDING_RATIO))
        full = bs + 2 * (spec_gap + spec_max + card_pad)
        return full, spec_gap, spec_max, card_pad

    cards_avail_w = avail_w
    label_gap = 4

    def _calc_layout(bs):
        fc, sg, sm, cp = _calc_full(bs)
        card_sp = max(4, int(bs * spacing_ratio))
        row_sp = max(4, int(bs * row_gap_ratio))

        raw_cpr = int((cards_avail_w + card_sp) / (fc + card_sp))
        cpr = max(1, min(raw_cpr, max_cards_per_row))

        total_h = 0
        group_info = []
        for gi in sorted_gis:
            n_cards = len(group_dict[gi])
            rows = math.ceil(n_cards / cpr)
            group_h = label_height + label_gap + rows * fc + (rows - 1) * row_sp
            group_info.append({
                "rows": rows,
                "group_h": group_h,
                "n_cards": n_cards,
                "cards_per_row": cpr,
            })
            total_h += group_h

        total_h += (n_groups - 1) * group_gap
        return total_h, group_info, fc, card_sp, row_sp, cpr

    lo = card_min_size
    hi = card_target_size + 60
    best_bs = card_min_size
    best_info = None

    for bs in range(hi, lo - 1, -1):
        th, ginfo, fc, csp, rsp, cpr = _calc_layout(bs)
        if th <= avail_h:
            best_bs = bs
            best_info = (th, ginfo, fc, csp, rsp, cpr)
            break

    if best_info is None:
        best_info = _calc_layout(card_min_size)
        best_bs = card_min_size

    total_h, group_info, full_card, card_spacing, row_spacing, cards_per_row = best_info
    block_size = best_bs
    card_size = full_card

    # --- 鲁棒性保护 ---
    needs_recompute = False

    # 1. 行差保护
    rows_list = [g["rows"] for g in group_info]
    min_rows = min(rows_list)
    max_rows = max(rows_list)
    row_diff = max_rows - min_rows

    if row_diff > max_row_diff:
        logger.info("Layout protection: row diff too large (%d-%d=%d > %d), adjusting...",
                    max_rows, min_rows, row_diff, max_row_diff)
        for gi_idx, gi in enumerate(sorted_gis):
            tr_list = group_dict[gi]
            info = group_info[gi_idx]
            max_allowed = (min_rows + max_row_diff) * cards_per_row
            if len(tr_list) > max_allowed:
                tr_list.sort(key=lambda t: len(t.notes), reverse=True)
                removed = tr_list[max_allowed:]
                group_dict[gi] = tr_list[:max_allowed]
                logger.info("  Group %d (%s): %d→%d tracks, removed %d",
                            gi, tr_list[0].group_name, len(tr_list), max_allowed, len(removed))
        needs_recompute = True

    # 2. 最小卡片保护
    if best_bs < card_min_size:
        logger.info("Layout protection: card too small (%dpx < %dpx), trimming cold tracks...",
                    best_bs, card_min_size)
        all_tracks = []
        for gi in sorted_gis:
            for tr in group_dict[gi]:
                all_tracks.append((gi, tr))
        all_tracks.sort(key=lambda x: len(x[1].notes), reverse=True)

        target_bs = card_min_size
        best_n = len(all_tracks)
        for n_tracks in range(len(all_tracks), 2, -1):
            test_tracks = all_tracks[:n_tracks]
            test_groups = {}
            for gi, tr in test_tracks:
                test_groups.setdefault(gi, []).append(tr)
            test_sorted = sorted(test_groups.keys())

            fc, sg, sm, cp = _calc_full(target_bs)
            card_sp = max(4, int(target_bs * spacing_ratio))
            row_sp = max(4, int(target_bs * row_gap_ratio))
            cpr = max(1, min(int((cards_avail_w + card_sp) / (fc + card_sp)), max_cards_per_row))
            total_h = 0
            ng = len(test_sorted)
            for gi in test_sorted:
                n_c = len(test_groups[gi])
                rows = math.ceil(n_c / cpr)
                gh = label_height + label_gap + rows * fc + (rows - 1) * row_sp
                total_h += gh
            total_h += (ng - 1) * group_gap

            if total_h <= avail_h:
                best_n = n_tracks
                break

        if best_n < len(all_tracks):
            kept = all_tracks[:best_n]
            group_dict = {}
            for gi, tr in kept:
                group_dict.setdefault(gi, []).append(tr)
            sorted_gis = sorted(group_dict.keys())
            n_groups = len(group_dict)
            logger.info("  Kept %d/%d tracks, removed %d", best_n, len(all_tracks), len(all_tracks)-best_n)
            needs_recompute = True

    if needs_recompute:
        best_bs = card_min_size
        for bs in range(card_target_size + 60, card_min_size - 1, -1):
            fc, sg, sm, cp = _calc_full(bs)
            card_sp = max(4, int(bs * spacing_ratio))
            row_sp = max(4, int(bs * row_gap_ratio))
            cpr = max(1, min(int((cards_avail_w + card_sp) / (fc + card_sp)), max_cards_per_row))
            total_h = 0
            ginfo = []
            for gi in sorted_gis:
                n_c = len(group_dict[gi])
                rows = math.ceil(n_c / cpr)
                gh = label_height + label_gap + rows * fc + (rows - 1) * row_sp
                ginfo.append({"rows": rows, "group_h": gh, "n_cards": n_c, "cards_per_row": cpr})
                total_h += gh
            total_h += (n_groups - 1) * group_gap
            if total_h <= avail_h:
                best_bs = bs
                best_info = (total_h, ginfo, fc, card_sp, row_sp, cpr)
                break

        total_h, group_info, full_card, card_spacing, row_spacing, cards_per_row = best_info
        block_size = best_bs
        card_size = full_card
        logger.info("Layout protection done: block_size=%dpx, %d groups", best_bs, n_groups)

    # 垂直居中
    start_y = margin_y + (avail_h - total_h) / 2
    current_y = start_y
    cards_start_x = margin_x

    positions: Dict[int, Tuple[float, float]] = {}
    group_bounds: List[Dict] = []

    for gi_idx, gi in enumerate(sorted_gis):
        tr_list = group_dict[gi]
        name = tr_list[0].group_name if tr_list[0].group_name else f"组{gi + 1}"
        info = group_info[gi_idx]
        n_cards = info["n_cards"]
        rows = info["rows"]
        group_h = info["group_h"]

        y_top = current_y

        label_x = cards_start_x
        label_y = y_top
        label_w = avail_w
        label_h = label_height

        cards_y_start = y_top + label_h + label_gap

        for card_idx, tr in enumerate(tr_list):
            row = card_idx // cards_per_row
            col_in_row = card_idx % cards_per_row
            row_count = cards_per_row if row < rows - 1 else (n_cards - row * cards_per_row)

            row_total_w = row_count * full_card + (row_count - 1) * card_spacing
            row_start_x = cards_start_x + (cards_avail_w - row_total_w) / 2

            cx = row_start_x + col_in_row * (full_card + card_spacing) + full_card / 2
            cy = cards_y_start + row * (full_card + row_spacing) + full_card / 2
            positions[tr.layer_id] = (cx, cy)

        group_bounds.append({
            "y_top": y_top,
            "y_bottom": y_top + group_h,
            "label_x": label_x,
            "label_y": label_y + label_h / 2,
            "label_w": label_w,
            "label_h": label_h,
            "name": name,
            "color_idx": gi_idx % len(GROUP_PALETTE),
            "n_cards": n_cards,
            "n_rows": rows,
            "track_ids": [tr.layer_id for tr in tr_list],
            "is_horizontal_label": True,
        })

        current_y = y_top + group_h + group_gap

    logger.info("Layout v2: block_size=%dpx, full_card=%dpx, cards_per_row=%d, %d groups",
                best_bs, full_card, cards_per_row, n_groups)

    return positions, group_bounds, n_groups, block_size, card_size
