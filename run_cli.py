"""
Quick test: render a single NBS file from command line.
Usage:
    python run_cli.py input.nbs
    python run_cli.py input.nbs output.mp4
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbs_visualizer import render_video


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_cli.py <input.nbs> [output.mp4]")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.isfile(input_file):
        print(f"Error: {input_file} not found")
        sys.exit(1)

    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        base = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join("outputs", base + "_visualization.mp4")

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    def progress(pct, msg=""):
        p = int(pct * 100) if pct <= 1.0 else int(pct)
        bar = "█" * (p // 2) + "░" * (50 - p // 2)
        print(f"\r  [{bar}] {p}%", end="", flush=True)

    print(f"Input:  {input_file}")
    print(f"Output: {output_file}")
    print()
    render_video(input_file, output_file, progress_callback=progress, use_kimi=True)  # FIXED: 问题1 - 传入use_kimi=True启用Kimi API分组/命名/字幕/弹幕/摄像机
    size = os.path.getsize(output_file)
    print(f"\n\nDone! Video saved to: {output_file} ({size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
