import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# 本文件位于 <项目根>/src/nbs_visualizer/config.py，上溯 3 层到项目根，
# 保证 assets 等资源路径在任意运行目录下都正确（不再依赖 cwd）。
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

TEXTURES_DIR = os.path.join(ASSETS_DIR, "textures")

MC_TEX_BASE = os.path.join(ASSETS_DIR, "mc")
MC_PARTICLE_DIR = os.path.join(MC_TEX_BASE, "particle")
MC_GUI_DIR = os.path.join(MC_TEX_BASE, "gui", "sprites")
MC_BLOCK_DIR = os.path.join(MC_TEX_BASE, "block")
MC_FONT_DIR = os.path.join(MC_TEX_BASE, "font")

FONT_DIR = os.path.join(ASSETS_DIR, "fonts")

EXTERNAL_MC_TEX_BASE = r"D:\Downloads\mre-for-windows\mre-output\Mechanomania自己玩\assets\minecraft\textures"
EXTERNAL_FONT_DIR = os.path.join(os.path.dirname(EXTERNAL_MC_TEX_BASE), "font")

FFMPEG_FALLBACK_PATHS = [
    "C:/ffmpeg/bin/ffmpeg.exe",
    "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
]


def get_kimi_api_key(override: Optional[str] = None) -> str:
    """从环境变量读取 Kimi API Key，未配置则报错。"""
    key = override or os.environ.get("KIMI_API_KEY")
    if not key:
        raise RuntimeError(
            "KIMI_API_KEY 未配置：请设置环境变量 KIMI_API_KEY，"
            "或在项目根目录 .env 文件中配置（参考 .env.example）"
        )
    return key

