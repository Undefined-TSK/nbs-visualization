import os, sys, traceback

out = r'D:\nbs可视化\_file_listing.txt'
path = r'D:\nbs可视化'
lines = []
try:
    entries = list(os.scandir(path))
    lines.append(f"Total entries in root: {len(entries)}")
    for e in entries:
        t = "DIR " if e.is_dir() else "FILE"
        try:
            size = e.stat().st_size if e.is_file() else 0
        except:
            size = -1
        lines.append(f"{t} | {e.name} | {size}")
    lines.append("=== FULL WALK ===")
    for root, dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                size = os.path.getsize(fp)
            except:
                size = -1
            lines.append(f"{fp} | {size}")
except Exception as ex:
    lines.append("ERROR:")
    lines.append(traceback.format_exc())
with open(out, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
