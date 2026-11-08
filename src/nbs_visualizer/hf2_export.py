"""
HyperFrames v2 导出器：把 NBS（+ 可选 LRC）导出为一个可渲染的 HyperFrames 项目目录。

架构约定（硬约束）：
    - 渲染引擎 = HyperFrames CLI 主时间轴（paused GSAP timeline）
    - 3D = three.js，走官方 adapter 契约 `window.__hfThreeRender_<id> = { state, render }`
    - 本模块只做「数据 -> 资产」的转换，不包含任何自研渲染引擎

输出目录：
    index.html      由 hyperframes2/index.template.html 替换令牌生成
    song_data.js    window.SONG_DATA = {...}（meta / style / groups / tracks / lyric / flashes）
    vendor/three.module.js
    vendor/gsap.min.js
    audio.*         可选音频
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
from typing import Iterable, List, Optional

from .stage import extract_tracks, GROUP_LABELS
from .resources import INSTRUMENT_MAP
from . import config

_WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_PATH = os.path.join(_WORKSPACE, "hyperframes2", "index.template.html")
VENDOR_DIRS = [os.path.join(_WORKSPACE, "vendor"), os.path.join(_WORKSPACE, "hyperframes2", "vendor")]

FONT_FILES = {
    "NotoSansCJKsc-Bold.otf": "/usr/share/fonts/opentype/noto-cjk-otf/NotoSansCJKsc-Bold.otf",
    "FiraCode-Bold.ttf": "/usr/share/fonts/truetype/firacode/FiraCode-Bold.ttf",
    "SmileySans-Oblique.otf": "/usr/share/fonts/opentype/smiley-sans/SmileySans-Oblique.otf",
}

INTRO_SECONDS = 0.4
OUTRO_SECONDS = 2.0

_CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


# ---------------------------------------------------------------- LRC

_TIME_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")


def parse_lrc(text: str) -> List[dict]:
    """解析 LRC，返回 [{start, end, text, words:[{t,s}]}]。

    支持一行多个时间标签；忽略 [ar:] 等元信息行。
    """
    raw = []
    for line in text.splitlines():
        tags = list(_TIME_RE.finditer(line))
        if not tags:
            continue
        body = _TIME_RE.sub("", line).strip()
        if not body:
            continue
        for m in tags:
            mm, ss, frac = m.group(1), m.group(2), m.group(3) or "0"
            ms = int(frac) * (10 ** (3 - len(frac)))
            raw.append([int(mm) * 60 + int(ss) + ms / 1000.0, body])
    raw.sort(key=lambda x: x[0])
    if not raw:
        return []

    lines = []
    for i, (start, body) in enumerate(raw):
        end = raw[i + 1][0] if i + 1 < len(raw) else start + 3.0
        lines.append({"start": round(start, 3), "end": round(max(end, start + 0.35), 3),
                      "text": body, "words": []})

    for idx, line in enumerate(lines):
        line["id"] = idx
        line["words"] = _split_words(line["text"], line["start"], line["end"])
    return lines


def _split_words(text: str, start: float, end: float) -> List[dict]:
    """CJK 按字，拉丁按词切分，并把时间均匀铺满整行。"""
    tokens: List[str] = []
    buf = ""
    for ch in text:
        if ch.isspace():
            if buf:
                tokens.append(buf)
                buf = ""
            continue
        if _CJK_RE.match(ch) or ch in "，。！？、；：,.!?;:":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    # 标点不单独占时，挂到前一个 token
    merged: List[str] = []
    for tk in tokens:
        if merged and tk in "，。！？、；：,.!?;:":
            merged[-1] += tk
        else:
            merged.append(tk)
    if not merged:
        return []
    span = max(0.2, end - start)
    step = span / len(merged)
    return [{"t": tk, "s": round(start + i * step, 3)} for i, tk in enumerate(merged)]


def derive_flashes(lines: List[dict], min_gap: float = 1.6) -> List[dict]:
    """生成整屏快闪大字：每 ≥min_gap 秒取一行作为重音（段落起点必取）。"""
    out: List[dict] = []
    prev_flash = -99.0
    prev_end = -99.0
    for line in lines:
        section_start = line["start"] - prev_end >= 0.9
        if section_start or line["start"] - prev_flash >= min_gap:
            head = line["text"].strip()
            if head:
                out.append({"t": round(line["start"], 3), "d": 0.62, "text": head[:8]})
                prev_flash = line["start"]
        prev_end = line["end"]
    return out[:24]


# ---------------------------------------------------------------- textures

def _data_uri(path: str) -> str:
    with open(path, "rb") as f:
        b = f.read()
    return "data:image/png;base64," + base64.b64encode(b).decode("ascii")


def _texture_uri(tex_name: str) -> str:
    src = os.path.join(config.TEXTURES_DIR, tex_name)
    if os.path.exists(src):
        return _data_uri(src)
    fallback = os.path.join(config.TEXTURES_DIR, "cobblestone(new).png")
    return _data_uri(fallback) if os.path.exists(fallback) else ""


# ---------------------------------------------------------------- export

def export_project(nbs_file: str, project_dir: str,
                   style: str = "blockframe",
                   audio_file: Optional[str] = None,
                   lrc_file: Optional[str] = None,
                   lrc_text: Optional[str] = None,
                   max_duration: Optional[float] = None,
                   intro: float = INTRO_SECONDS,
                   outro: float = OUTRO_SECONDS) -> dict:
    tracks, header = extract_tracks(nbs_file)
    if not tracks:
        raise ValueError("该 NBS 文件没有活跃轨道")

    tps = header.tempo
    if tps <= 0:
        raise ValueError(f"NBS tempo 无效: {tps}")
    song_total = header.song_length / tps
    if max_duration and max_duration > 0:
        song_total = min(song_total, max_duration)
    song_total = round(song_total, 3)

    song_name = header.song_name or os.path.splitext(os.path.basename(nbs_file))[0]
    song_author = getattr(header, "song_author", "") or ""

    # ---- 分组 ----
    groups, gpos = [], {}
    for i, t in enumerate(tracks):
        if t.group_index not in gpos:
            gpos[t.group_index] = len(groups)
            groups.append({"name": t.group_name or GROUP_LABELS.get(t.group, t.group), "tracks": []})
        groups[gpos[t.group_index]]["tracks"].append(i)

    # ---- 轨道 ----
    tracks_data = []
    note_total = 0
    for t in tracks:
        tex_name = INSTRUMENT_MAP.get(t.instrument_id, INSTRUMENT_MAP[0])[0]
        notes = sorted(([round(s, 3), k, round(v, 3), round(max(0.05, e - s), 3)]
                        for (s, e, k, v) in t.notes if s < song_total), key=lambda n: n[0])
        note_total += len(notes)
        tracks_data.append({
            "role": t.role_name,
            "inst": t.instrument_name,
            "texture": _texture_uri(tex_name),
            "notes": notes,
        })

    # ---- 歌词 ----
    lyric_text = lrc_text
    if lrc_file and os.path.exists(lrc_file):
        with open(lrc_file, "r", encoding="utf-8-sig") as f:
            lyric_text = f.read()
    lyric = [l for l in parse_lrc(lyric_text) if l["start"] < song_total] if lyric_text else []
    flashes = [f for f in derive_flashes(lyric) if f["t"] < song_total] if lyric else []

    data = {
        "meta": {
            "name": song_name,
            "author": song_author,
            "tempo": tps,
            "duration": song_total,
        },
        "style": style,
        "intro": intro,
        "outro": outro,
        "groups": groups,
        "tracks": tracks_data,
        "lyric": lyric,
        "flashes": flashes,
    }

    # ---- 写目录 ----
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
    os.makedirs(project_dir)
    os.makedirs(os.path.join(project_dir, "vendor"), exist_ok=True)

    with open(os.path.join(project_dir, "song_data.js"), "w", encoding="utf-8") as f:
        f.write("window.SONG_DATA = ")
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    for v in ("three.min.js", "gsap.min.js"):
        for d in VENDOR_DIRS:
            src = os.path.join(d, v)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(project_dir, "vendor", v))
                break

    # 字体（@font-face 引用，lint 要求必须随项目提供）
    font_out = os.path.join(project_dir, "assets", "fonts")
    os.makedirs(font_out, exist_ok=True)
    for name, src in FONT_FILES.items():
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(font_out, name))

    audio_clip = ""
    if audio_file and os.path.exists(audio_file):
        ext = os.path.splitext(audio_file)[1].lower()
        name = "audio" + ext
        shutil.copy2(audio_file, os.path.join(project_dir, name))
        audio_clip = (
            f'  <audio id="bgm" data-start="{intro}" data-duration="{song_total}" '
            f'data-track-index="1" src="{name}" data-volume="1"></audio>')

    total = round(intro + song_total + outro, 3)
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    html = (html
            .replace("%%STYLE%%", style)
            .replace("%%DURATION%%", str(total))
            .replace("%%INTRO%%", str(intro))
            .replace("%%AUDIO_CLIP%%", audio_clip))
    with open(os.path.join(project_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "project_dir": project_dir,
        "style": style,
        "song_name": song_name,
        "song_seconds": song_total,
        "total_seconds": total,
        "tracks": len(tracks_data),
        "notes": note_total,
        "groups": len(groups),
        "lyric_lines": len(lyric),
        "flashes": len(flashes),
    }


def parse_lrc_file(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return parse_lrc(f.read())


__all__ = ["export_project", "parse_lrc", "parse_lrc_file", "derive_flashes", "INTRO_SECONDS", "OUTRO_SECONDS"]
