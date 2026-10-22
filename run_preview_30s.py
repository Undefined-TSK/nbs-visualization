import os, time, traceback
from nbs_visualizer.renderer_audio import render_video

NBS = r'D:/nbs可视化/uploads/植物大战僵尸1.nbs'
MP3 = r'D:/nbs可视化/uploads/植物大战僵尸1.mp3'
OUT = r'D:/nbs可视化/outputs/preview_30s_v4.mp4'
LOG = r'D:/nbs可视化/render_30s.log'

log = open(LOG, 'w', buffering=1, encoding='utf-8')
def cb(p, m):
    log.write(f"[{p:.3f}] {m}\n")
    log.flush()

t0 = time.time()
log.write("START render 30s preview with audio\n")
try:
    out = render_video(NBS, OUT, audio_file=MP3, use_kimi=False,
                       max_duration=30, fps=120, progress_callback=cb)
    log.write(f"DONE path={out} exists={os.path.exists(out)} "
              f"size={os.path.getsize(out) if os.path.exists(out) else 0}\n")
except Exception:
    log.write("ERR\n" + traceback.format_exc() + "\n")
log.write(f"ELAPSED {time.time()-t0:.1f}s\n")
log.close()
