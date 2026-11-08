"""
HyperFrames 渲染入口：用 HyperFrames 引擎把 NBS 渲染成可视化视频。

用法:
    python run_hyper.py input.nbs [output.mp4]
    python run_hyper.py input.nbs output.mp4 --audio song.mp3
    python run_hyper.py input.nbs --fps 30 --quality draft
    python run_hyper.py input.nbs --preview 10      # 只渲染前 10 秒
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.nbs_visualizer.hf_export import export_project  # noqa: E402

BUILD_DIR = os.path.join("outputs", "hf_build")

# 可选的 Chrome/Chromium 可执行文件路径（hyperframes 需要）
_BROWSER_CANDIDATES = [
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/opt/google/chrome/chrome",
]


def _browser_env() -> dict:
    env = dict(os.environ)
    if not env.get("HYPERFRAMES_BROWSER_PATH"):
        for p in _BROWSER_CANDIDATES:
            if os.path.exists(p):
                env["HYPERFRAMES_BROWSER_PATH"] = p
                break
    return env


def main():
    ap = argparse.ArgumentParser(description="NBS → HyperFrames 视频渲染")
    ap.add_argument("input", help="输入 .nbs 文件")
    ap.add_argument("output", nargs="?", default=None, help="输出 mp4 路径")
    ap.add_argument("--audio", default=None, help="可选音频文件 (.mp3/.wav/.ogg/.m4a)")
    ap.add_argument("--fps", default="30", choices=["24", "30", "60"])
    ap.add_argument("--quality", default="standard", choices=["draft", "standard", "high"])
    ap.add_argument("--preview", type=float, default=None, help="只渲染前 N 秒")
    ap.add_argument("--kimi", action="store_true", help="启用 Kimi 角色命名/分组")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    if args.output:
        output_file = os.path.abspath(args.output)
    else:
        base = os.path.splitext(os.path.basename(args.input))[0]
        output_file = os.path.abspath(os.path.join("outputs", base + "_hyperframes.mp4"))
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    project_dir = os.path.abspath(BUILD_DIR)
    print(f"[1/3] 导出 HyperFrames 项目 → {project_dir}")
    info = export_project(
        args.input, project_dir,
        audio_file=args.audio,
        max_duration=args.preview,
        use_kimi=args.kimi,
    )
    print(f"      《{info['song_name']}》 {info['duration']:.1f}s | "
          f"{info['tracks']} 轨 / {info['groups']} 组 / {info['notes']} 音符")

    print("[2/3] hyperframes lint")
    lint = subprocess.run(["npx", "hyperframes", "lint", project_dir],
                          capture_output=True, text=True)
    out = (lint.stdout + lint.stderr).strip()
    if out:
        print(out[-2000:])

    print(f"[3/3] hyperframes render (fps={args.fps}, quality={args.quality})")
    render = subprocess.run(
        ["npx", "hyperframes", "render", project_dir,
         "--output", output_file,
         "--fps", args.fps, "--quality", args.quality],
        cwd=project_dir, env=_browser_env())
    if render.returncode != 0:
        print("Render failed.")
        sys.exit(render.returncode)

    size = os.path.getsize(output_file)
    print(f"\nDone! Video saved to: {output_file} ({size / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
