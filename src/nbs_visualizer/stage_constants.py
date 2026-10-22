"""舞台常量：方块尺寸、密集区参数、卡片样式、尾奏时序、频谱比例、调色板、角色分组映射。"""
from __future__ import annotations

import re

# ============== Stage Constants ==============
BLOCK_BASE_SIZE = 120
BLOCK_MIN_SIZE = 50
BLOCK_PRESSED_SCALE = 0.80        # 按下后贴图缩放（用户反馈：原 0.72 太小，放大到 0.80；仍需 < DENSE_RECOVERY 以免遮挡密集区遮盖）
BLOCK_PRESS_DURATION = 0.12      # 非密集区按下时长（快按，方案A确认）
BLOCK_HOLD_DURATION = 0.0        # 非密集区保持时长（跟音符走）
BLOCK_RELEASE_DURATION = 0.45    # 非密集区回弹时长（弹回，ease-out-back）

DENSE_THRESHOLD = 0.05          # (废弃) 旧版逐间隔阈值，保留以兼容旧引用
DENSE_WINDOW = 0.5             # 密集检测：以每音符为中心 ±秒 的局部密度窗口
DENSE_MIN_COUNT = 7            # 窗口内音符数 ≥ 此值判定为密集区（≈7+ 音符/秒）
DENSE_CYCLE = 0.16              # 密集区蒙版循环周期（用户要求"高速震荡"：从 0.20 降到 0.16 ≈ 6.25Hz）
DENSE_RECOVERY = 0.90           # 蒙版静止时的缩放（用户反馈：需 > BLOCK_PRESSED_SCALE 以保证密集区遮盖高斯脉冲可见）
DENSE_MASK_PRESSED = 0.50       # 密集区蒙版脉冲最低缩放
DENSE_GAUSSIAN_SIGMA = 0.12    # 高斯脉冲宽度（越小脉冲越窄越尖锐）
DENSE_TEXTURE_HELD = True       # 贴图在密集区保持按下
MASK_PRESS_SCALE = 0.85         # 非密集区：遮盖按下环（略大于贴图 0.80 以露出细环；用户要求"遮罩同步按下"）
# ===== 可打断动画系统参数 =====
MASK_LAG = 0.10                 # 遮盖比贴图"慢半拍"的延迟（秒）。所有阶段（按下/回弹/等待）都整体后移，营造延迟感
MASK_SMOOTH_TIME = 0.04         # 遮盖弹簧收敛时间（已提速~33%，仍叠加在 MASK_LAG 之上，保持"慢半拍后快速响应"）
TEX_SMOOTH_TIME = 0.07          # 贴图弹簧收敛时间（已提速~30%：过渡更快但仍有~20帧动画，不突变/不卡顿）
DENSE_HOLD_PAD = 0.15           # 密集区"保持段"两侧留白（秒），避免高速振荡与回弹/按下冲突
DENSE_OSC_SIGMA = 0.10          # 高速高斯振荡每个周期的脉冲宽度（相对周期，越小越尖锐）
# 挤压拉伸由弹簧"速度"推导 → 天然只在按下/回弹过渡瞬间出现，保持期归零（正方形）
# 弹簧已提速，峰值速度同比增大；增益按比例下调使"形变幅度不变、只是过渡更快"（避免撞到 DEFORM_MAX 上限被削平）
DEFORM_VEL_GAIN = 0.06          # 速度→形变增益（贴图），峰值约 ±0.12（与提速前幅度一致，仅更快）
DEFORM_MAX = 0.14               # 贴图形变幅度上限
MASK_DEFORM_VEL_GAIN = 0.033    # 遮盖形变增益（更克制，同比提速后保持幅度不变）

CARD_PADDING_RATIO = 0.02
CARD_CORNER_LEN_RATIO = 0.07
CARD_SHADOW_COLOR = (0, 0, 0, 40)
BLOCK_BACKING_COLOR = (75, 75, 80, 200)  # 灰色蒙版（78%不透明，半透明）

RESTING_THRESHOLD = 2.5
STATE_TRANSITION_DURATION = 0.8
CARD_BORDER_INACTIVE = (139, 139, 139, 153)

OUTRO_FADEIN_DURATION = 0.5    # 初始保持阶段
OUTRO_WAIT_DURATION = 3.0      # 衰减阶段 3.0s（HC#18: 正常→衰减）
OUTRO_FADEOUT_DURATION = 2.0   # 淡出阶段 2.0s（HC#18: 衰减→淡出）
OUTRO_BUFFER = 0.5             # 缓冲 0.5s
OUTRO_SCENE_FADE = 2.0         # 全场景淡出（黑幕渐入）2.0s
OUTRO_SCENE_HOLD = 1.0         # 黑幕保持 1.0s

SPECTRUM_BAR_MAX_RATIO = 0.20
# 布局用间隙比例：控制卡片(cell)留白，保持方块尺寸较大（仅 ~4px）。
SPECTRUM_EDGE_GAP_RATIO = 0.035
# 渲染/裁剪用间隙比例：频谱条实际绘制与方块边界裁剪都以此为准。
# 取较大值(0.10)使频谱条与方块之间留出充足空间，让 squash/stretch 形变完整保留在
# "频谱条围成的正方形边界"内，不再溢出遮挡频谱条或邻块。布局卡片尺寸仍用上面的小值，
# 因此方块本身不会被缩小。
SPECTRUM_RENDER_GAP_RATIO = 0.10

GROUP_PALETTE = [
    # 0: 冰蓝
    {"base": (168, 216, 234, 20),  "hl": (91, 192, 222, 217),  "dark": (70, 130, 160, 102)},
    # 1: 暖铜
    {"base": (213, 184, 149, 20),  "hl": (230, 126, 34, 217),  "dark": (160, 120, 80, 102)},
    # 2: 雾紫
    {"base": (197, 185, 205, 20),  "hl": (155, 126, 222, 217),  "dark": (120, 100, 160, 102)},
    # 3: 苔绿
    {"base": (162, 217, 162, 20),  "hl": (39, 174, 96, 217),   "dark": (60, 130, 90, 102)},
    # 4: 暖橙
    {"base": (255, 183, 149, 20),  "hl": (255, 109, 0, 217),   "dark": (180, 90, 50, 102)},
    # 5: 灰蓝
    {"base": (179, 205, 224, 20),  "hl": (100, 160, 200, 217),  "dark": (80, 120, 150, 102)},
    # 6: 陶土
    {"base": (220, 195, 175, 20),  "hl": (190, 140, 100, 217),  "dark": (140, 100, 70, 102)},
    # 7: 灰紫
    {"base": (200, 190, 210, 20),  "hl": (150, 130, 180, 217),  "dark": (110, 90, 130, 102)},
]

ROLE_GROUPS = {
    "主旋": "melody", "副旋": "melody", "主唱": "melody", "副唱": "melody",
    "旋律": "melody", "主旋律": "melody", "副旋律": "melody",
    "钢琴": "melody", "长笛": "melody", "铃铛": "melody", "吉他": "melody",
    "管钟": "melody", "木琴": "melody", "颤片琴": "melody", "班卓琴": "melody",
    "电钢琴": "melody", "方波": "melody", "牛铃": "melody", "击鼓沿": "melody",
    "小号": "melody", "斑驳小号": "melody", "锈蚀小号": "melody", "氧化小号": "melody",
    "迪吉里杜管": "melody", "人声": "melody", "人声哼鸣": "melody",
    "竖琴": "melody", "颤音琴": "melody", "古钢琴": "melody", "合成器": "melody",
    "尼龙吉他": "melody", "钢弦吉他": "melody", "清音吉他": "melody",
    "失真吉他": "melody", "过载吉他": "melody", "汽笛琴": "melody",
    "水晶音": "melody", "亮音": "melody", "萨克斯": "melody",
    "长号": "melody", "单簧管": "melody", "双簧管": "melody",
    "合成弦乐": "harmony", "弦乐": "harmony", "和声": "harmony",
    "合唱": "harmony", "铺底": "harmony", "pad": "harmony", "辅音": "harmony",
    "贝斯": "bass", "低音": "bass",
    "合成铜管": "bass", "合成铜管2": "bass",
    "节奏": "rhythm", "小军鼓": "rhythm", "底鼓": "rhythm",
    "低音鼓": "rhythm", "踩镲": "rhythm", "打击乐": "rhythm",
    "电子鼓": "rhythm", "反向镲": "rhythm",
    "效果": "fx", "音效": "fx", "转场": "fx",
    "前奏": "fx", "尾奏": "fx", "桥段": "fx",
    "海浪": "fx", "掌声": "fx", "排箫": "fx",
    "铜管": "fx", "贝斯主旋": "fx",
}

GROUP_ORDER = ["melody", "harmony", "bass", "rhythm", "fx"]
GROUP_LABELS = {
    "melody": "旋律", "harmony": "和声", "bass": "贝斯",
    "rhythm": "节奏", "fx": "效果",
}

ROLE_NAME_MAP = {
    "melody": "主旋", "lead": "主旋", "main": "主旋",
    "main melody": "主旋", "primary": "主旋", "melodies": "主旋",
    "countermelody": "副旋", "counter melody": "副旋",
    "counter-melody": "副旋", "countermelodies": "副旋",
    "harmony": "和声", "chords": "和声", "chord": "和声",
    "harmonies": "和声", "backing": "和声",
    "pad": "铺底", "strings": "弦乐", "string": "弦乐",
    "strings 1": "弦乐", "strings 2": "弦乐",
    "syn.strings": "合成弦乐", "syn.strings1": "合成弦乐",
    "synth strings": "合成弦乐",
    "bass": "贝斯", "bassline": "贝斯", "bass line": "贝斯",
    "low": "低音", "synth bass": "贝斯",
    "synth bass 1": "贝斯", "synth bass 2": "贝斯",
    "fingeredbass": "贝斯", "fretlessbass": "贝斯",
    "percussion": "节奏", "drums": "节奏", "drum": "节奏",
    "rhythm": "节奏", "beat": "节奏", "drum kit": "节奏",
    "snare": "小军鼓", "kick": "底鼓", "bass drum": "底鼓",
    "hihat": "踩镲", "hi hat": "踩镲", "hat": "踩镲",
    "bells": "铃铛", "bell": "铃铛", "chime": "管钟",
    "flute": "长笛", "guitar": "吉他", "piano": "钢琴",
    "vocal": "人声", "vocals": "人声", "voice": "人声",
    "singer": "主唱", "lead vocal": "主唱",
    "backing vocal": "副唱", "backup vocal": "副唱",
    "choir": "合唱", "choir aahs": "合唱",
    "fx": "效果", "effects": "效果", "sound effects": "音效",
    "sfx": "音效", "transition": "转场",
    "intro": "前奏", "outro": "尾奏", "bridge": "桥段",
    "square lead": "主旋", "saw lead": "主旋",
    "brass": "铜管", "trumpet": "小号", "trombone": "长号",
    "tenor sax": "萨克斯", "sax": "萨克斯",
    "clarinet": "单簧管", "oboe": "双簧管",
    "vibraphone": "颤音琴", "clavinet": "古钢琴",
    "polysynth": "合成器", "synth brass": "合成铜管",
    "synth brass2": "合成铜管2",
    "nylon-str.gt": "尼龙吉他", "steel-str.gt": "钢弦吉他",
    "clean guitar": "清音吉他", "distortiongt": "失真吉他",
    "overdrive gt": "过载吉他", "calliope": "汽笛琴",
    "crystal": "水晶音", "harp": "竖琴",
    "piano 1": "钢琴", "piano 2": "钢琴",
    "e.piano 1": "电钢琴", "e.piano 2": "电钢琴",
    "synth drum": "电子鼓", "reverse cym.": "反向镲",
    "seashore": "海浪", "applause": "掌声",
    "voice oohs": "人声哼鸣", "pan flute": "排箫",
    "brightness": "亮音", "bass+lead": "贝斯主旋",
}

def translate_role_name_local(name: str) -> str:
    if not name:
        return "未知"
    key = name.strip().lower()
    if key in ROLE_NAME_MAP:
        return ROLE_NAME_MAP[key]
    cleaned = re.sub(r'\s*\d+\s*$', '', key).strip()
    if cleaned in ROLE_NAME_MAP:
        return ROLE_NAME_MAP[cleaned]
    nospace = re.sub(r'\s+', '', key)
    if nospace in ROLE_NAME_MAP:
        return ROLE_NAME_MAP[nospace]
    return name


def get_role_group(role_name: str) -> str:
    return ROLE_GROUPS.get(role_name, "melody")


def _optimal_cols(n: int) -> int:
    if n <= 0: return 1
    if n <= 3: return n
    if n <= 6: return 3
    if n <= 9: return 3
    if n <= 12: return 4
    if n <= 20: return 5
    if n <= 30: return 6
    return 7
