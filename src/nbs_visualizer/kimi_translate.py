"""
Kimi API 翻译模块：将英文层名翻译为中文声部角色名。
- 本地映射表优先（零成本，覆盖常见名）
- 命中不了的批量提交 Kimi API
- 结果缓存到本地 JSON，下次同层名直接复用

配置：从环境变量 KIMI_API_KEY 读取密钥（通过 config.py 的 load_dotenv 自动加载 .env）。
"""

import json
import os
import urllib.request
from typing import Dict, List, Optional

from .config import get_kimi_api_key
from .logger import get_logger

logger = get_logger(__name__)

# 本地缓存文件路径
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
CACHE_FILE = os.path.join(CACHE_DIR, "role_translations.json")

# Kimi API 配置
KIMI_API_URL = "https://api.moonshot.cn/v1/chat/completions"
KIMI_MODEL = "kimi-k2.6"
REQUEST_TIMEOUT = 60

SYSTEM_PROMPT = """你是 Minecraft Note Block Studio (NBS) 音乐编排领域的专业术语翻译专家。

## 背景
用户使用 NBS 软件制作音乐，每个轨道（Layer）有一个英文名，代表该轨道在编曲中扮演的「声部角色」。你需要将这些英文名翻译成简洁专业的中文角色名。

## NBS 20种音色标准对照表（供参考，这些是乐器名，不是角色名）
harp=钢琴, double bass=贝斯, bass drum=底鼓, snare drum=小军鼓, click=击鼓沿,
guitar=吉他, flute=长笛, bell=铃铛, chime=管钟, xylophone=木琴,
iron xylophone=颤片琴, cowbell=牛铃, didgeridoo=迪吉里杜管, bit=方波, banjo=班卓琴,
pling=电钢琴, trumpet=小号, exposedtrumpet=斑驳小号, weatheredtrumpet=锈蚀小号, oxidizedtrumpet=氧化小号

## 翻译规则
1. 翻译的是「声部角色名」，不是乐器名。例如 "Lead Synth" 应翻译为「主旋」而非「合成器」
2. 翻译要符合中文音乐制作圈的常用叫法，简洁（2-4个字最佳，最多6个字）
3. 打击乐/节奏类：统一归为「节奏」（除非名称明确具体乐器，如 Snare=小军鼓、Kick=底鼓、HiHat=踩镲）
4. 旋律类：Melody→主旋、Lead→主旋、Countermelody→副旋、Main Melody→主旋
5. 和声类：Harmony→和声、Chords→和声、Choir→合唱、Pad→铺底、Strings→弦乐
6. 低音类：Bass→贝斯、Bassline→贝斯、Low→低音
7. 效果类：FX→效果、SFX→音效、Transition→转场
8. 人声类：Vocal→人声、Lead Vocal→主唱、Backing Vocal→副唱
9. 如果名字是纯数字或完全无法判断角色，翻译成「声部N」（N为序号）
10. 同一英文词在不同语境下可能扮演不同角色，要根据完整名称判断

## 输出格式
严格输出 JSON：{"原名1": "中文名1", "原名2": "中文名2", ...}
不要输出任何解释文字，只输出 JSON。
"""


class RoleNameTranslator:
    """声部角色名翻译：本地缓存 → Kimi API fallback。"""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key

    def _load_cache(self) -> Dict[str, str]:
        """加载本地翻译缓存。"""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save_cache(self, cache: Dict[str, str]) -> None:
        """保存翻译缓存。"""
        os.makedirs(CACHE_DIR, exist_ok=True)
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.warning("Failed to save translation cache: %s", e)

    def _call_api(self, names: List[str]) -> Dict[str, str]:
        """调用 Kimi API 批量翻译。返回 {原名: 中文名} 字典。"""
        if not names:
            return {}

        user_msg = "请翻译以下声部角色名为中文（输出 JSON）：\n" + "\n".join(
            f"- {name}" for name in names
        )

        payload = json.dumps({
            "model": KIMI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        }).encode("utf-8")

        api_key = get_kimi_api_key(self._api_key)
        req = urllib.request.Request(
            KIMI_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                content = data["choices"][0]["message"]["content"]
                content = content.strip()
                if content.startswith("```"):
                    content = content.strip("`")
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()
                result = json.loads(content)
                return {str(k): str(v) for k, v in result.items()}
        except Exception as e:
            logger.error("Kimi API translation failed: %s", e)
            return {}

    def translate(self, names: List[str], use_api: bool = True) -> Dict[str, str]:
        """批量翻译声部角色名。

        - names: 待翻译的英文名列表
        - use_api: 是否允许调用 API（False=只用本地映射）
        返回 {原名: 中文名} 字典，失败的项保留原名。
        """
        if not names:
            return {}

        unique_names = list(dict.fromkeys(names))
        result: Dict[str, str] = {}

        cache = self._load_cache()
        uncached: List[str] = []
        for name in unique_names:
            if name in cache:
                result[name] = cache[name]
            else:
                uncached.append(name)

        if not uncached or not use_api:
            for name in uncached:
                result[name] = name
            return result

        translations = self._call_api(uncached)

        for name in uncached:
            if name in translations and translations[name]:
                result[name] = translations[name]
                cache[name] = translations[name]
            else:
                result[name] = name

        if translations:
            self._save_cache(cache)

        return result


if __name__ == "__main__":
    test_names = [
        "Synth Bass 1", "Square Lead", "Strings 2",
        "Nylon-str.Gt", "Choir Aahs", "FretlessBass",
        "Vibraphone", "Clavinet", "Polysynth",
    ]
    print("Testing Kimi translation...")
    translator = RoleNameTranslator()
    result = translator.translate(test_names, use_api=True)
    for eng, cn in result.items():
        print(f"  {eng} → {cn}")
