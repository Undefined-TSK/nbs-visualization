#!/usr/bin/env python3
"""NBS -> LilyPond 五线谱。

映射依据（由 /workspace/.uploads 实际数据验证）：
  MIDI = key + 21        key 33..57 -> F#3..F#5，中位 48 -> A4
  1 tick = 1/16 音符      ticks_per_beat = 4
  BPM = tempo * 15       tempo 8 -> 120 BPM

用法:
  python3 nbs2ly.py INPUT.nbs [-o OUTDIR] [--title TITLE]
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pynbs

TICKS_PER_BEAT = 4
TICK_UNITS = 16          # 1 tick == 16th note
MIDI_OFFSET = 21

# NBS 原版音色 id -> 名称
NBS_INSTRUMENTS = {
    0: "Harp", 1: "Double Bass", 2: "Bass Drum", 3: "Snare Drum",
    4: "Click", 5: "Guitar", 6: "Flute", 7: "Bell", 8: "Chime",
    9: "Xylophone", 10: "Iron Xylophone", 11: "Cow Bell",
    12: "Didgeridoo", 13: "Bit", 14: "Banjo", 15: "Pling",
}
PERCUSSION_IDS = {2, 3, 4}

# 每个声部一个独立颜色（印刷可分辨）
GROUP_PALETTE = [
    "#c0392b", "#d68910", "#b7950b", "#1e8449", "#16a085", "#2471a3",
    "#2e86c1", "#6c3483", "#a04000", "#7d3c98", "#117864", "#c2185b",
]

SHARP_NAMES = ["c", "cis", "d", "dis", "e", "f", "fis", "g", "gis", "a", "ais", "b"]
FLAT_NAMES = ["c", "des", "d", "ees", "e", "f", "ges", "g", "aes", "a", "bes", "b"]

# 大调主音音级 -> (lilypond 名, 调号变音数, 是否用升号)
MAJOR_KEYS = {
    0: ("c", 0, True), 1: ("des", 5, False), 2: ("d", 2, True),
    3: ("ees", 3, False), 4: ("e", 4, True), 5: ("f", 1, False),
    6: ("ges", 6, False), 7: ("g", 1, True), 8: ("aes", 4, False),
    9: ("a", 3, True), 10: ("bes", 2, False), 11: ("b", 5, True),
}
MINOR_NAMES = ["c", "cis", "d", "ees", "e", "f", "fis", "g", "gis", "a", "bes", "b"]

MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]


@dataclass
class Group:
    name: str
    color_role: str = "其他"
    clef: str = "treble"
    percussion: bool = False
    median: int = 60
    chord_ratio: float = 1.0
    events: dict[int, list[tuple[int, int]]] = field(default_factory=lambda: collections.defaultdict(list))
    # tick -> [(midi, velocity)]


def color_expr(hex_color: str) -> str:
    r = int(hex_color[1:3], 16) / 255.0
    g = int(hex_color[3:5], 16) / 255.0
    b = int(hex_color[5:7], 16) / 255.0
    return f"#(rgb-color {r:.3f} {g:.3f} {b:.3f})"


def midi_to_ly(midi: int, sharps: bool = True) -> str:
    name = (SHARP_NAMES if sharps else FLAT_NAMES)[midi % 12]
    octave = midi // 12 - 1           # C4 = 60 -> 4
    marks = octave - 3                # lilypond: c' == C4
    if marks > 0:
        return name + "'" * marks
    if marks < 0:
        return name + "," * (-marks)
    return name


def choose_key(pitch_classes: collections.Counter) -> tuple[str, bool, bool]:
    """选调号：让「临时记号总数 + 调号复杂度」最小。

    返回 (调名, 是否大调, 是否用升号记谱)。
    """
    total = sum(pitch_classes.values())
    if total == 0:
        return "c", True, True

    best = (1e9, "c", True, True)
    for tonic in range(12):
        for is_major in (True, False):
            if is_major:
                _, n_acc, sharps = MAJOR_KEYS[tonic]
                name = MAJOR_KEYS[tonic][0]
                steps = MAJOR_STEPS
            else:
                rel = (tonic + 3) % 12
                _, n_acc, sharps = MAJOR_KEYS[rel]
                name = MINOR_NAMES[tonic]
                steps = MINOR_STEPS
            in_key = {(tonic + s) % 12 for s in steps}
            miss = sum(w for pc, w in pitch_classes.items() if pc not in in_key)
            # 临时记号按出现次数加权，调号按复杂度轻罚，避免选到 6/7 个升降号
            cost = miss / total + 0.035 * n_acc
            if cost < best[0]:
                best = (cost, name, is_major, sharps)
    return best[1], best[2], best[3]


def duration_token(ticks: int) -> str:
    """ticks(1 tick = 1/16) -> LilyPond 时值后缀, 如 16*3"""
    ticks = max(1, int(ticks))
    return f"16*{ticks}"


def build_lilypond(song, title: str) -> str:
    h = song.header
    tempo = float(h.tempo or 10)
    bpm = round(tempo * 15)
    beats_per_bar = int(h.time_signature or 4)
    bar_ticks = beats_per_bar * TICKS_PER_BEAT
    song_ticks = int(h.song_length or (max((n.tick for n in song.notes), default=0) + 1))

    layers_by_id = {l.id: l for l in song.layers}

    # ---- 分组：按轨道名合并 ----
    groups: dict[str, Group] = {}
    group_inst: dict[str, int] = {}
    for note in song.notes:
        layer = layers_by_id.get(note.layer)
        if layer is None:
            continue
        name = (layer.name or "").strip() or NBS_INSTRUMENTS.get(note.instrument, f"Instrument {note.instrument}")
        name = re.sub(r"\s+", " ", name)
        if name not in groups:
            groups[name] = Group(name=name)
            group_inst[name] = note.instrument
        groups[name].events[note.tick].append((note.key + MIDI_OFFSET, note.velocity))
        if note.instrument in PERCUSSION_IDS:
            groups[name].percussion = True

    # ---- 角色 / 谱号 ----
    for g in groups.values():
        pitches = [m for evs in g.events.values() for m, _ in evs]
        g.median = sorted(pitches)[len(pitches) // 2] if pitches else 60
        starts = len(g.events)
        g.chord_ratio = (len(pitches) / starts) if starts else 1.0
        # 谱号取「离音区最近」的那个，尽量减少加线
        g.clef = "percussion" if g.percussion else (
            "treble" if abs(g.median - 71) <= abs(g.median - 50) else "bass")

    melodic = [g for g in groups.values() if not g.percussion and g.events]
    if melodic:
        lo = min(g.median for g in melodic)
        hi = max(g.median for g in melodic)
        span = max(1, hi - lo)
        melody = max(melodic, key=lambda g: (g.median, len(g.events)))
        for g in melodic:
            if g is melody:
                g.color_role = "旋律"
            elif g.median <= lo + span * 0.2:
                g.color_role = "低音"
            elif g.chord_ratio >= 1.5:
                g.color_role = "和声"
            else:
                g.color_role = "副旋律"
    for g in groups.values():
        if g.percussion:
            g.color_role = "打击"
        elif not g.events:
            g.color_role = "其他"

    # ---- 调性 ----
    pc = collections.Counter()
    for n in song.notes:
        pc[(n.key + MIDI_OFFSET) % 12] += 1
    key_tonic, key_major, use_sharps = choose_key(pc)

    # ---- 生成各声部：按音高从上到下排序，打击乐置底 ----
    ordered = sorted(groups.values(), key=lambda g: (g.percussion, -g.median))
    staves = []
    for gi, g in enumerate(ordered):
        color = GROUP_PALETTE[gi % len(GROUP_PALETTE)]
        inst = NBS_INSTRUMENTS.get(group_inst.get(g.name, 0), g.name)

        body = []
        cursor = 0
        for tick in sorted(g.events):
            if tick < cursor:
                continue
            gap = tick - cursor
            # 空隙用休止符，按小节切开
            while gap > 0:
                in_bar = cursor % bar_ticks
                room = bar_ticks - in_bar
                if in_bar == 0 and gap >= bar_ticks:
                    body.append("R1")
                    cursor += bar_ticks
                    gap -= bar_ticks
                else:
                    take = min(gap, room)
                    body.append(f"r{duration_token(take)}")
                    cursor += take
                    gap -= take
            evs = g.events[tick]
            # 同刻多音 -> 和弦（去重，保留力度大的）
            best: dict[int, int] = {}
            for m, v in evs:
                best[m] = max(best.get(m, 0), v)
            pitches = sorted(best)
            if g.percussion:
                # 打击乐：固定单线节奏谱，避免音高造成的大跳
                chord = "c'"
            elif len(pitches) == 1:
                chord = midi_to_ly(pitches[0], use_sharps)
            else:
                chord = "<" + " ".join(midi_to_ly(m, use_sharps) for m in pitches) + ">"
            nxt = min((t for t in g.events if t > tick), default=song_ticks)
            dur = max(1, min(nxt - tick, 4))
            body.append(f"{chord}{duration_token(dur)}")
            cursor = tick + dur

        # 谱表头
        clef = "percussion" if g.percussion else g.clef
        ce = color_expr(color)
        color_setup = (
            f"        \\override Staff.StaffSymbol.color = {ce}\n"
            f"        \\override NoteHead.color = {ce}\n"
            f"        \\override Stem.color = {ce}\n"
            f"        \\override Beam.color = {ce}\n"
            f"        \\override Rest.color = {ce}\n"
            f"        \\override Dots.color = {ce}\n"
        )
        extra = "        \\override NoteHead.style = #'cross\n" if g.percussion else ""
        ts_hide = "        \\override Staff.TimeSignature.stencil = ##f\n" if gi > 0 else ""
        label_markup = (
            f"\\markup \\with-color {ce} \\column {{ "
            f"\\line {{ \\bold \"{inst[:16]}\" }} "
            f"\\line {{ \\fontsize #-2 \"{g.color_role}\" }} }}"
        )
        staves.append(
            f"  \\new Staff \\with {{\n"
            f"    instrumentName = {label_markup}\n"
            f"    shortInstrumentName = \\markup \\with-color {ce} \"{inst[:7]}\"\n"
            f"  }} {{\n"
            f"        \\global\n"
            f"        \\clef {clef}\n"
            f"{ts_hide}{extra}{color_setup}"
            f"        {' '.join(body) if body else 'R1'}\n"
            f"        \\bar \"|.\"\n"
            f"  }}\n"
        )

    # ---- 页首编制表 ----
    NICE = {"c": "C", "cis": "C♯", "des": "D♭", "d": "D", "ees": "E♭", "e": "E",
            "f": "F", "fis": "F♯", "ges": "G♭", "g": "G", "gis": "G♯",
            "aes": "A♭", "a": "A", "ais": "A♯", "bes": "B♭", "b": "B"}
    base_names = [NBS_INSTRUMENTS.get(group_inst.get(g.name, 0), g.name) for g in ordered]
    name_count = collections.Counter(base_names)
    lines = []
    for gi, g in enumerate(ordered):
        ce = color_expr(GROUP_PALETTE[gi % len(GROUP_PALETTE)])
        inst = base_names[gi]
        if name_count[inst] > 1:
            inst = f"{inst} ({g.name[:12]})"
        lines.append(f'\\line {{ \\with-color {ce} \\bold "{inst}" "   ·   {g.color_role}" }}')
    legend = (
        "\\markup \\override #'(font-name . \"Noto Sans CJK SC\") \\fontsize #-2 "
        "\\column { " + " ".join(lines) + " }"
    )
    secs = int(song_ticks / max(tempo, 1e-6))
    meta = (f"{secs // 60}:{secs % 60:02d}   ·   {bpm} BPM   ·   "
            f"{NICE.get(key_tonic, key_tonic)} {'大调' if key_major else '小调'}   ·   "
            f"{beats_per_bar}/4   ·   {len(ordered)} 声部")

    header = (
        "\\version \"2.24.3\"\n"
        "\\language \"nederlands\"\n\n"
        f"global = {{ \\tempo 4 = {bpm} \\time {beats_per_bar}/4 "
        f"\\key {key_tonic} \\{'major' if key_major else 'minor'} }}\n\n"
        "\\paper {\n"
        "  #(set-paper-size \"a4\")\n"
        "  top-margin = 16\\mm  bottom-margin = 16\\mm\n"
        "  left-margin = 40\\mm right-margin = 14\\mm\n"
        "  system-system-spacing.basic-distance = #18\n"
        "  ragged-bottom = ##t\n"
        "  ragged-last-bottom = ##t\n"
        "  print-page-number = ##t\n"
        "}\n\n"
    )
    score = (
        "\\header {\n"
        f"  title = \\markup \\override #'(font-name . \"Noto Sans CJK SC\") \\fontsize #3 \"{title}\"\n"
        f"  subtitle = \\markup \\override #'(font-name . \"Noto Sans CJK SC\") \\fontsize #-2 \"{meta}\"\n"
        f"  subsubtitle = {legend}\n"
        "  tagline = ##f\n"
        "}\n\n"
        "\\score {\n"
        "  \\new StaffGroup <<\n"
        f"{''.join(staves)}"
        "  >>\n"
        "  \\layout {\n"
        "    \\context {\n"
        "      \\Score\n"
        "      \\override TimeSignature.color = #black\n"
        "      \\override KeySignature.color = #black\n"
        "      \\override BarNumber.break-visibility = ##(#t #t #t)\n"
        "      barNumberVisibility = #(every-nth-bar-number-visible 4)\n"
        "    }\n"
        "    \\context {\n"
        "      \\Staff\n"
        "      \\RemoveEmptyStaves\n"
        "      \\override VerticalAxisGroup.remove-first = ##t\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    return header + score


def compile_ly(ly_path: Path, outdir: Path, stem: str) -> list[Path]:
    # lilypond 会 chdir 到 -o 目录，必须用绝对路径
    ly_path = ly_path.resolve()
    outdir = outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    outputs = []
    # PDF
    subprocess.run(
        ["lilypond", "-dno-point-and-click", "-o", str(outdir / stem), str(ly_path)],
        check=True, capture_output=True,
    )
    outputs.append(outdir / f"{stem}.pdf")
    # SVG（每页一个文件）
    svgdir = outdir / f"{stem}_svg"
    svgdir.mkdir(exist_ok=True)
    subprocess.run(
        ["lilypond", "-dbackend=svg", "-dno-point-and-click",
         "-o", str(svgdir / "page"), str(ly_path)],
        check=True, capture_output=True,
    )
    outputs.extend(sorted(svgdir.glob("page*.svg")))
    return outputs


def clean_title(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_", "", stem)
    return stem.replace("_", " ").strip()


def convert(path: Path, outdir: Path, title: str | None = None) -> list[Path]:
    song = pynbs.read(str(path))
    title = title or clean_title(path)
    ly = build_lilypond(song, title)
    outdir.mkdir(parents=True, exist_ok=True)
    ly_path = outdir / f"{path.stem}.ly"
    ly_path.write_text(ly, encoding="utf-8")
    return compile_ly(ly_path, outdir, path.stem)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--outdir", default="/workspace/outputs/scores")
    ap.add_argument("--title")
    args = ap.parse_args()
    outs = convert(Path(args.input), Path(args.outdir), args.title)
    for o in outs:
        print(o)
    return 0


if __name__ == "__main__":
    sys.exit(main())
