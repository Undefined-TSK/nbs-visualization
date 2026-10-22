"""探针：实证 track_state_machine 在真实 NBS 上的缩放输出，定位 HTML 效果缺失根因。"""
import os
from nbs_visualizer.track_operations import extract_tracks
from nbs_visualizer.track_state_machine import TrackStateMachine
from nbs_visualizer.stage_layout import StageLayout
from nbs_visualizer import config

NBS = r"D:/nbs可视化/uploads/植物大战僵尸1.nbs"
tracks, header = extract_tracks(NBS)
print(f"[tracks] count={len(tracks)}")
for tr in tracks[:4]:
    tsm = TrackStateMachine(tr, audio_end_time=99.0)
    pe = len(tr.press_events)
    dr = len(tr.dense_regions)
    print(f"  L{tr.layer_id:2d} notes={len(tr.notes):4d} press_events={pe:4d} dense_regions={dr}  first_dense={tr.dense_regions[:2]}")

# 取最活跃的轨道做统计
tr = max(tracks, key=lambda t: len(t.notes))
print(f"\n[stats] L{tr.layer_id} notes={len(tr.notes)} press_events={len(tr.press_events)} dense_regions={len(tr.dense_regions)}")
gaps = [tr.notes[i+1][0] - tr.notes[i][0] for i in range(len(tr.notes)-1)]
gaps_sorted = sorted(gaps)
import statistics
print(f"  gaps: min={min(gaps):.3f} median={statistics.median(gaps):.3f} max={max(gaps):.3f}")
print(f"  gaps<=0.05:{sum(1 for g in gaps if g<=0.05)}  <=0.10:{sum(1 for g in gaps if g<=0.10)}  <=0.13:{sum(1 for g in gaps if g<=0.13)}  <=0.20:{sum(1 for g in gaps if g<=0.20)}")
print("  dense_regions sample:", tr.dense_regions[:3])
