"""资源管理：纹理加载、字体加载、TextureCache。"""
import os
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from . import config
from .logger import get_logger

logger = get_logger(__name__)

FONT_CANDIDATES = [
    os.path.join(config.FONT_DIR, "msyhbd.ttc"),
    os.path.join(config.FONT_DIR, "msyh.ttc"),
    os.path.join(config.FONT_DIR, "simhei.ttf"),
    os.path.join(config.FONT_DIR, "arial.ttf"),
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

INSTRUMENT_MAP = {
    0:  ("note_block(new).png",       "钢琴"),
    1:  ("oak_planks(new).png",       "贝斯"),
    2:  ("cobblestone(new).png",      "底鼓"),
    3:  ("sand(new).png",             "小军鼓"),
    4:  ("glass(new).png",            "击鼓沿"),
    5:  ("white_wool(new).png",       "吉他"),
    6:  ("clay(new).png",             "长笛"),
    7:  ("gold_block(new).png",       "铃铛"),
    8:  ("packed_ice(new).png",       "管钟"),
    9:  ("bone_block_side(new).png",  "木琴"),
    10: ("iron_block(new).png",       "颤片琴"),
    11: ("soul_sand(new).png",        "牛铃"),
    12: ("pumpkin_side(new).png",     "迪吉里杜管"),
    13: ("emerald_block(new).png",    "方波"),
    14: ("hay_block_side(new).png",   "班卓琴"),
    15: ("glowstone(new).png",        "电钢琴"),
    16: ("copper_block(new).png",     "小号"),
    17: ("exposed_copper(new).png",   "斑驳小号"),
    18: ("weathered_copper(new).png", "锈蚀小号"),
    19: ("oxidized_copper(new).png",  "氧化小号"),
}


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    mc_font_candidates = [
        os.path.join(config.MC_FONT_DIR, "unifont.ttf"),
        os.path.join(config.MC_FONT_DIR, "unifont_jp.ttf"),
        os.path.join(config.MC_FONT_DIR, "Minecraftia.ttf"),
        os.path.join(config.MC_FONT_DIR, "mc.ttf"),
    ]
    sys_paths = list(FONT_CANDIDATES)
    if not bold:
        sys_paths = sys_paths[1:] + [sys_paths[0]]
    paths = mc_font_candidates + sys_paths if not bold else sys_paths
    for fp in paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception as e:
                logger.warning("Font load failed %s: %s", fp, e)
                continue
    return ImageFont.load_default()


class TextureCache:
    def __init__(self):
        self._block_cache = {}
        self._bg_cache: Optional[Image.Image] = None
        self._particle_cache: List[Image.Image] = []

    def get_block(self, instrument_id: int, size: int) -> Image.Image:
        key = (instrument_id, size)
        if key in self._block_cache:
            return self._block_cache[key]

        info = INSTRUMENT_MAP.get(instrument_id, INSTRUMENT_MAP[0])
        path = os.path.join(config.TEXTURES_DIR, info[0])
        if not os.path.exists(path):
            path = os.path.join(config.TEXTURES_DIR, "note_block(new).png")

        img = Image.open(path).convert("RGBA")
        src_w, src_h = img.width, img.height

        factor = max(1, size // max(src_w, src_h))
        scaled_w, scaled_h = src_w * factor, src_h * factor
        if scaled_w != src_w:
            img = img.resize((scaled_w, scaled_h), Image.Resampling.NEAREST)

        if scaled_w != size or scaled_h != size:
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            px = round((size - scaled_w) / 2)
            py = round((size - scaled_h) / 2)
            canvas.alpha_composite(img, (px, py))
            img = canvas

        self._block_cache[key] = img
        return img

    def get_background(self) -> Image.Image:
        if self._bg_cache is not None:
            return self._bg_cache

        from ._core import VIDEO_WIDTH, VIDEO_HEIGHT, BG_COLOR, DOT_SPACING, DOT_RADIUS, DOT_COLOR

        bg = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (*BG_COLOR, 255))

        dot_layer = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dot_layer)
        for y in range(DOT_SPACING // 2, VIDEO_HEIGHT, DOT_SPACING):
            for x in range(DOT_SPACING // 2, VIDEO_WIDTH, DOT_SPACING):
                dd.ellipse(
                    [x - DOT_RADIUS, y - DOT_RADIUS, x + DOT_RADIUS, y + DOT_RADIUS],
                    fill=(*DOT_COLOR, 127),
                )
        bg.alpha_composite(dot_layer)

        shadow = Image.new("RGBA", (VIDEO_WIDTH, 50), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        for y in range(50):
            a = int(12 * (1 - y / 50))
            sd.line([(0, y), (VIDEO_WIDTH, y)], fill=(0, 0, 0, a))
        bg.alpha_composite(shadow, (0, 0))

        self._bg_cache = bg
        return bg

    def get_particles(self) -> List[Image.Image]:
        if self._particle_cache:
            return self._particle_cache

        for i in range(8):
            path = os.path.join(config.TEXTURES_DIR, f"particle_{i}.png")
            if os.path.exists(path):
                p = Image.open(path).convert("RGBA")
                self._particle_cache.append(p)

        if not self._particle_cache:
            for i in range(8):
                s = 2 + i % 3
                p = Image.new("RGBA", (s, s), (0, 0, 0, 0))
                ImageDraw.Draw(p).ellipse([0, 0, s-1, s-1], fill=(255, 255, 255, 100))
                self._particle_cache.append(p)

        return self._particle_cache

    def _load_mc_texture(self, path: str) -> Optional[Image.Image]:
        if not os.path.exists(path):
            return None
        try:
            return Image.open(path).convert("RGBA")
        except Exception as e:
            logger.warning("Texture load failed %s: %s", path, e)
            return None

    def get_mc_particle(self, name: str) -> Optional[Image.Image]:
        cache_key = f"mc_particle_{name}"
        if cache_key in self._block_cache:
            return self._block_cache[cache_key]
        path = os.path.join(config.MC_PARTICLE_DIR, name)
        img = self._load_mc_texture(path)
        self._block_cache[cache_key] = img
        return img

    def get_mc_gui(self, *path_parts: str) -> Optional[Image.Image]:
        cache_key = f"mc_gui_{'_'.join(path_parts)}"
        if cache_key in self._block_cache:
            return self._block_cache[cache_key]
        path = os.path.join(config.MC_GUI_DIR, *path_parts)
        img = self._load_mc_texture(path)
        self._block_cache[cache_key] = img
        return img

    def get_mc_block(self, name: str) -> Optional[Image.Image]:
        cache_key = f"mc_block_{name}"
        if cache_key in self._block_cache:
            return self._block_cache[cache_key]
        path = os.path.join(config.MC_BLOCK_DIR, name)
        img = self._load_mc_texture(path)
        self._block_cache[cache_key] = img
        return img
