"""
HyperFrames 导出器：把 NBS 解析结果导出为 HyperFrames 项目目录。

输出目录内容：
    index.html      由 hyperframes/index.template.html 替换令牌生成
    song_data.js    window.SONG_DATA = {...}（曲目元数据 + 轨道 + 音符）
    gsap.min.js     从 hyperframes 安装目录复制（离线渲染）
    simhei.ttf      中文字体
    textures/*.png  使用到的 MC 乐器贴图
    audio.*         可选的外部音频
"""
from __future__ import annotations

import glob
import json
import os
import shutil
from typing import Optional

from .stage import extract_tracks, GROUP_PALETTE, GROUP_LABELS
from .resources import INSTRUMENT_MAP
from . import config

# 与 index.template.html 中的时序保持一致
INTRO_SECONDS = 1.0
OUTRO_SECONDS = 2.4

_WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_PATH = os.path.join(_WORKSPACE, "hyperframes", "index.template.html")


def _css_rgba(rgba) -> str:
    r, g, b, a = rgba
    return f"rgba({r},{g},{b},{a / 255:.3f})"


def _css_rgb_dark(rgba, factor: float = 0.55) -> str:
    r, g, b = rgba[0], rgba[1], rgba[2]
    return f"rgb({int(r * factor)},{int(g * factor)},{int(b * factor)})"


def _find_gsap() -> Optional[str]:
    """在 hyperframes 安装目录里找 vendor 的 gsap.min.js。"""
    home = os.path.expanduser("~")
    patterns = [
        os.path.join(home, ".npm", "_npx", "*", "node_modules", "hyperframes",
                     "dist", "vendor", "npm", "gsap@*", "dist", "gsap.min.js"),
    ]
    for pat in patterns:
        matches = sorted(glob.glob(pat))
        if matches:
            return matches[-1]
    return None


def export_project(nbs_file: str, project_dir: str,
                   audio_file: Optional[str] = None,
                   max_duration: Optional[float] = None,
                   use_kimi: bool = False) -> dict:
    """解析 NBS 并生成 HyperFrames 项目目录。返回导出摘要。"""
    tracks, header = extract_tracks(nbs_file, use_kimi=use_kimi)
    if not tracks:
        raise ValueError("该 NBS 文件没有活跃轨道（所有轨道都没有音符）")

    tps = header.tempo
    if tps <= 0:
        raise ValueError(f"NBS文件tempo值无效: {tps}")
    total_seconds = header.song_length / tps
    if max_duration is not None and max_duration > 0:
        total_seconds = min(total_seconds, max_duration)
    total_seconds = round(total_seconds, 3)

    song_name = header.song_name or os.path.splitext(os.path.basename(nbs_file))[0]
    song_author = getattr(header, "song_author", "") or getattr(header, "original_author", "") or ""

    # ---------- 分组（按 group_index 首次出现顺序） ----------
    groups = []
    group_pos = {}
    for t in tracks:
        if t.group_index not in group_pos:
            group_pos[t.group_index] = len(groups)
            groups.append({
                "index": t.group_index,
                "name": t.group_name or GROUP_LABELS.get(t.group, t.group),
                "tracks": [],
            })
        groups[group_pos[t.group_index]]["tracks"].append(tracks.index(t))

    # ---------- 调色板 ----------
    palette = [{
        "base": _css_rgba(p["base"][:3] + (max(p["base"][3], 60),)),
        "hl": _css_rgba(p["hl"]),
        "text": _css_rgb_dark(p["hl"]),
    } for p in GROUP_PALETTE]

    # ---------- 轨道 ----------
    tracks_data = []
    used_textures = set()
    note_total = 0
    for t in tracks:
        tex = INSTRUMENT_MAP.get(t.instrument_id, INSTRUMENT_MAP[0])[0]
        used_textures.add(tex)
        notes = [[round(s, 3), k, round(v, 3)]
                 for (s, e, k, v) in t.notes if s < total_seconds]
        note_total += len(notes)
        tracks_data.append({
            "role": t.role_name,
            "inst": t.instrument_name,
            "group_index": t.group_index,
            "texture": tex,
            "notes": notes,
        })

    data = {
        "meta": {
            "name": song_name,
            "author": song_author,
            "tempo": tps,
            "duration": total_seconds,
        },
        "palette": palette,
        "groups": groups,
        "tracks": tracks_data,
    }

    # ---------- 写项目目录 ----------
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
    os.makedirs(project_dir)
    tex_out = os.path.join(project_dir, "textures")
    os.makedirs(tex_out)

    with open(os.path.join(project_dir, "song_data.js"), "w", encoding="utf-8") as f:
        f.write("window.SONG_DATA = ")
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    for tex in used_textures:
        src = os.path.join(config.TEXTURES_DIR, tex)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(tex_out, tex))

    font_src = os.path.join(config.ASSETS_DIR, "fonts", "simhei.ttf")
    if os.path.exists(font_src):
        shutil.copy2(font_src, os.path.join(project_dir, "simhei.ttf"))

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    gsap_src = _find_gsap()
    if gsap_src:
        shutil.copy2(gsap_src, os.path.join(project_dir, "gsap.min.js"))
    else:
        html = html.replace(
            '<script src="gsap.min.js"></script>',
            '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>')

    audio_clip = ""
    if audio_file and os.path.exists(audio_file):
        ext = os.path.splitext(audio_file)[1].lower()
        audio_name = "audio" + ext
        shutil.copy2(audio_file, os.path.join(project_dir, audio_name))
        audio_clip = (
            f'  <audio id="bgm" data-start="{INTRO_SECONDS}" '
            f'data-duration="{total_seconds}" data-track-index="1" '
            f'src="{audio_name}" data-volume="1"></audio>')

    data_duration = round(INTRO_SECONDS + total_seconds + OUTRO_SECONDS, 3)
    html = (html
            .replace("%%DATA_DURATION%%", str(data_duration))
            .replace("%%INTRO%%", str(INTRO_SECONDS))
            .replace("%%AUDIO_CLIP%%", audio_clip))
    with open(os.path.join(project_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "project_dir": project_dir,
        "song_name": song_name,
        "duration": total_seconds,
        "data_duration": data_duration,
        "tracks": len(tracks_data),
        "notes": note_total,
        "groups": len(groups),
    }
