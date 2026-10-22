"""核心渲染管线：背景、图层合成、OpenCV输出、视频编码。"""
from __future__ import annotations

import math
import bisect
from typing import List, Dict, Optional, Any

from PIL import Image, ImageDraw

import cv2
import numpy as np

from .logger import get_logger

from .utils import clamp, lerp
from .resources import TextureCache, load_font
from .spectrum import SpectrumAnalyzer
from .particles import (
    NoteParticleSystem, CollectionParticles, EnchantGlint,
    Crosshair, ParticleSystem, _SleepParticleSystem,
)
from .camera import CameraController
from .stage import (
    TrackData, LayoutEngine, StaticGroupLayout,
    OUTRO_WAIT_DURATION, OUTRO_FADEOUT_DURATION, OUTRO_BUFFER,
    OUTRO_SCENE_FADE, OUTRO_SCENE_HOLD,
)
from .ui import DanmakuSystem, CardRenderer

from ._core import (
    VIDEO_WIDTH, VIDEO_HEIGHT, FPS, LABEL_FONT_RATIO,
)

from .renderer_painter import RendererPainter
from .renderer_spectrums import RendererSpectrumsMixin
from .renderer_subtitles import RendererSubtitlesMixin

logger = get_logger(__name__)


class FrameRenderer:
    def __init__(self, tracks: List[TrackData], song_name: str = "",
                 audio_end_time: float = 0.0,
                 kimi_script: Optional[Dict] = None,
                 danmaku_list: Optional[List[Dict]] = None,
                 audio_spectrum: Optional[Any] = None):
        # 方向⑥：真实音频频谱时间轴（librosa 预计算），None 时无音频驱动副作用
        self.audio_spectrum = audio_spectrum
        self.tracks = tracks
        self.song_name = song_name
        self.audio_end_time = audio_end_time
        self.kimi_script = kimi_script
        self.layout = LayoutEngine(tracks)
        self.textures = TextureCache()
        self._spectrum = SpectrumAnalyzer(audio_spectrum=self.audio_spectrum)
        self.particles = ParticleSystem(self.textures)
        # 静态分组布局（位置固定 + playing/resting状态机）
        self.stage = StaticGroupLayout(tracks, audio_end_time)
        # 弹幕系统
        self.danmaku = DanmakuSystem(danmaku_list)
        # 智能摄像机
        self.camera = CameraController(tracks, self.layout, kimi_script, stage=self.stage)
        # FIXED-B3: 问题35 - 删除未使用的font_title
        bs = self.stage.block_size
        font_size = max(11, int(bs * LABEL_FONT_RATIO))
        self.font_label = load_font(font_size, bold=True)
        # FIXED-B3: 问题60 - 组标签字号下限从max(12,bs*0.08)提高到max(14,bs*0.10)
        self.font_group = load_font(max(14, int(bs * 0.10)), bold=True)
        self.font_subtitle = load_font(max(14, int(bs * 0.09)), bold=True)
        # MC 视觉效果系统
        self.note_particles = NoteParticleSystem(self.textures)
        self.enchant_glint = EnchantGlint(self.textures)
        self.collection_particles = CollectionParticles(self.textures)
        self.crosshair = Crosshair(self.textures)
        # FIXED-B3: 问题22 - 睡眠粒子系统
        self.sleep_particles = _SleepParticleSystem(self.textures)
        # 上一帧状态（检测 playing→resting 切换，触发回收粒子）
        self._prev_states: Dict[int, str] = {tr.layer_id: self.stage.get_state(tr.layer_id) for tr in tracks}
        # 上一帧音符时间索引（检测新音符，触发音符粒子）
        self._prev_note_idx: Dict[int, int] = {tr.layer_id: 0 for tr in tracks}
        # FIXED-B3: 问题31 - Solo聚光灯状态
        self._solo_active_id: Optional[int] = None
        self._solo_candidate_id: Optional[int] = None
        self._solo_candidate_start: float = 0.0
        self._solo_alpha: float = 0.0
        # 阴影/边框/角标/活动度 lerp 状态已迁移至 TrackStateMachine
        # 卡片渲染器
        self.card_renderer = CardRenderer(
            self.textures,
            {"label": self.font_label, "group": self.font_group, "subtitle": self.font_subtitle},
        )
        # 组合式绘制组件（替代多重继承 Mixin）：每个绘制职责独立成对象，可单独测试/替换
        self.painter = RendererPainter(self)
        self.spectrum_painter = RendererSpectrumsMixin(self)
        self.ui_painter = RendererSubtitlesMixin(self)

    def render(self, t: float) -> np.ndarray:
        bg = self.textures.get_background().copy()

        # 方向⑥：实时音频能量（0..1），驱动运镜推近与粒子发射强度；无音频时为 0
        audio_energy = self.audio_spectrum.get_energy(t) if self.audio_spectrum else 0.0

        self.particles.update(1.0 / FPS)
        self.particles.draw(bg)

        # 更新状态机
        self.stage.update(t)

        # 推进可打断动画弹簧：每个轨道独立，目标随音符/密集区实时切换，
        # 弹簧从当前状态平滑重收敛 → 起始/结束无顿挫、进行中打断无跳变。
        dt = 1.0 / FPS
        for tr in self.tracks:
            self.stage.get_tsm(tr.layer_id).advance_anim(t, dt)

        # 检测状态切换 → 触发回收粒子
        for tr in self.tracks:
            lid = tr.layer_id
            cur_state = self.stage.get_state(lid)
            prev_state = self._prev_states.get(lid, "resting")
            if prev_state == "playing" and cur_state == "resting":
                pos = self.stage.positions.get(lid)
                if pos:
                    cx, cy = pos
                    half = self.stage.card_size / 2
                    self.collection_particles.emit(cx, cy, half)
            self._prev_states[lid] = cur_state

        # 检测新音符 → 触发音符粒子
        # FIXED-B4: 问题27 - 和弦时仅最高音(最大key)发射粒子，避免多轨同时爆粒子
        new_notes = []  # (lid, note_t, key, cx, cy, bs, is_dense, is_critical, hl)
        for tr in self.tracks:
            lid = tr.layer_id
            times = self.stage.get_note_times(lid)
            if not times:
                continue
            cur_idx = bisect.bisect_right(times, t)
            prev_idx = self._prev_note_idx.get(lid, 0)
            if cur_idx > prev_idx and cur_idx > 0:
                note_t = times[cur_idx - 1]
                if abs(note_t - t) < 0.1 and t <= self.audio_end_time:
                    pos = self.stage.positions.get(lid)
                    if pos:
                        cx, cy = pos
                        bs = self.stage.block_size
                        # 密集区域检测
                        is_dense = any(s <= note_t <= e for s, e in tr.dense_regions)
                        # 强拍检测（间隔 > 0.5s）
                        prev_note_t = times[cur_idx - 2] if cur_idx >= 2 else 0
                        is_critical = (note_t - prev_note_t) > 0.5 and not is_dense
                        # 获取当前音符的key值
                        key_val = 60  # 默认中音C
                        for n in tr.notes:
                            if abs(n[0] - note_t) < 0.001:
                                key_val = n[2]
                                break
                        palette = self.stage.get_color(lid)
                        hl = palette["hl"]
                        # 密集区域每2个音符发1个粒子
                        skip_dense = is_dense and (cur_idx % 2 != 0)
                        new_notes.append((lid, note_t, key_val, cx, cy, bs, is_dense, is_critical, hl, skip_dense))
            self._prev_note_idx[lid] = cur_idx

        # 和弦去重：同时间戳(±0.02s)只保留最高音(key最大)的粒子
        if new_notes:
            new_notes.sort(key=lambda x: x[2], reverse=True)  # 按key降序
            emitted_times = []
            for nn in new_notes:
                lid, note_t, key_val, cx, cy, bs, is_dense, is_critical, hl, skip_dense = nn
                if skip_dense:
                    continue
                # 检查是否已有同时刻的更高音已发射
                if any(abs(note_t - et) < 0.02 for et in emitted_times):
                    continue
                emitted_times.append(note_t)
                # 仅在贴图处于'按下'英雄时刻发射；被遮盖/暗化的轨道不发射
                tsm = self.stage.get_tsm(lid)
                if tsm.is_active_at(t):
                    card_alpha = self.stage.get_alpha(lid, t)
                    occluded = (self._solo_active_id is not None
                                and lid != self._solo_active_id
                                and self._solo_alpha > 0.01)
                    self.note_particles.emit(
                        lid, cx, cy, t, tsm, hl, bs,
                        is_critical=is_critical,
                        card_alpha=card_alpha,
                        occluded=occluded,
                        intensity=1.0 + audio_energy * 2.5,
                    )
                    # 触发附魔光效（密集区）
                    if is_dense:
                        self.enchant_glint.activate(lid, t)

        # 退出密集区域 → 取消附魔光效
        for tr in self.tracks:
            lid = tr.layer_id
            in_dense = any(s <= t <= e for s, e in tr.dense_regions)
            if not in_dense and self.enchant_glint.is_active(lid):
                self.enchant_glint.deactivate(lid)

        # FIXED-B3: 问题22 - resting状态卡片发射睡眠粒子(0.8s间隔)
        if self.sleep_particles._emit_timer >= self.sleep_particles.EMIT_INTERVAL:
            self.sleep_particles._emit_timer = 0.0
            for tr in self.tracks:
                lid = tr.layer_id
                if self.stage.get_state(lid) == "resting":
                    if self.stage.get_alpha(lid, t) > 0.3:
                        pos = self.stage.get_position(lid, t)
                        if pos:
                            cx, cy = pos
                            half = self.stage.card_size / 2
                            self.sleep_particles.emit(cx, cy, half)

        # 更新粒子系统
        self.note_particles.update(dt)
        self.collection_particles.update(dt)
        self.crosshair.update(dt)
        self.sleep_particles.update(dt)

        # 更新弹幕
        self.danmaku.update(t, dt)

        # 尾奏频谱衰减（与卡片alpha同步：衰减3.0s→淡出2.0s，HC#18）
        _, outro_scale = self.stage.get_outro_effects(t)
        spec_decay = 1.0
        if self.audio_end_time > 0 and t > self.audio_end_time:
            dt_outro = t - self.audio_end_time
            decay_end = OUTRO_WAIT_DURATION
            fadeout_end = decay_end + OUTRO_FADEOUT_DURATION
            if dt_outro < decay_end:
                # 衰减阶段: 1.0 → 0.7
                p = dt_outro / decay_end
                p = clamp(p, 0, 1)
                p = 3 * p * p - 2 * p * p * p
                spec_decay = lerp(1.0, 0.7, p)
            elif dt_outro < fadeout_end:
                # 淡出阶段: 0.7 → 0.0
                p = clamp((dt_outro - decay_end) / OUTRO_FADEOUT_DURATION, 0, 1)
                p = 3 * p * p - 2 * p * p * p
                spec_decay = lerp(0.7, 0.0, p)
            else:
                spec_decay = 0.0

        # ===== 在独立图层渲染所有元素 =====
        elements = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT),
                             (0, 0, 0, 0))

        # FIXED-B3: 问题62 - 组标签移到elements层，zoom>1时受camera transform
        self.painter._draw_group_labels(elements)

        # FIXED-B3: 问题31 - Solo聚光灯检测 + _solo_alpha平滑过渡
        solo_track = self.painter._get_solo_track(t)
        solo_smooth = 1.0 - math.exp(-dt / 0.5)
        if solo_track is not None:
            self._solo_active_id = solo_track
            self._solo_alpha += (1.0 - self._solo_alpha) * solo_smooth
        else:
            self._solo_alpha += (0.0 - self._solo_alpha) * solo_smooth
            if self._solo_alpha < 0.01:
                self._solo_active_id = None

        self.painter._draw_all_cards(elements, t)

        # FIXED-B3: 问题31 - Solo遮罩层：非Solo卡片叠加(0,0,0,25)暗化
        if self._solo_alpha > 0.01 and self._solo_active_id is not None:
            mask_a = int(25 * self._solo_alpha)
            md = ImageDraw.Draw(elements)
            for tr in self.tracks:
                if tr.layer_id == self._solo_active_id:
                    continue
                tr_alpha = self.stage.get_alpha(tr.layer_id, t)
                if tr_alpha <= 0.01:
                    continue
                pos = self.stage.get_position(tr.layer_id, t)
                if pos:
                    mcx, mcy = pos
                    mhalf = self.stage.card_size // 2
                    md.rectangle(
                        [int(mcx - mhalf), int(mcy - mhalf),
                         int(mcx + mhalf), int(mcy + mhalf)],
                        fill=(0, 0, 0, mask_a))

        self.spectrum_painter._draw_all_spectrums(elements, t, spec_decay)
        self.painter._draw_blocks(elements, t, outro_scale)
        self.painter._draw_all_labels(elements, t)

        # 音符粒子 + 回收粒子（在元素层，随镜头动）
        # 独奏聚光灯开启时，非聚焦轨道的粒子同步变暗（贴合'遮盖行为不同'）
        dim_tracks = (
            {tr.layer_id for tr in self.tracks
             if self._solo_active_id is not None and tr.layer_id != self._solo_active_id}
            if self._solo_alpha > 0.01 else None
        )
        self.note_particles.draw(elements, dim_tracks)
        self.collection_particles.draw(elements)
        # FIXED-B3: 问题22 - 睡眠粒子(在元素层，随镜头动)
        self.sleep_particles.draw(elements)

        # 附魔光效（在贴图周围，不覆盖贴图）
        for tr in self.tracks:
            lid = tr.layer_id
            if self.enchant_glint.is_active(lid) and self.stage.get_alpha(lid, t) > 0.3:
                pos = self.stage.positions.get(lid)
                if pos:
                    cx, cy = pos
                    bs = self.stage.block_size
                    palette = self.stage.get_color(lid)
                    hl = palette["hl"][:3]
                    self.enchant_glint.draw(elements, lid, int(cx), int(cy), bs, t, hl)

        # 镜头变换只作用于元素层（音频能量驱动推近）
        self.camera.update(t, audio_energy=audio_energy)
        zoom, pan_x, pan_y = self.camera.get_transform()

        # FIXED-B3: 问题31 - Solo摄像机慢推(不要硬切)
        if self._solo_alpha > 0.01 and self._solo_active_id is not None:
            spos = self.stage.get_position(self._solo_active_id, t)
            if spos:
                scx, scy = spos
                solo_zoom = 1.3
                solo_pan_x = scx - solo_zoom * (VIDEO_WIDTH / 2)
                solo_pan_y = scy - solo_zoom * (VIDEO_HEIGHT / 2)
                a = self._solo_alpha
                zoom = zoom * (1 - a) + solo_zoom * a
                pan_x = pan_x * (1 - a) + solo_pan_x * a
                pan_y = pan_y * (1 - a) + solo_pan_y * a

        # 无论放大缩小，都使用高质量采样。affine transform 仅支持 NEAREST/BILINEAR/BICUBIC，
        # 其中 BICUBIC 质量最高且能保留动画锐度（LANCZOS 在 transform 中不被支持，故用 BICUBIC）。
        resample_mode = Image.Resampling.BICUBIC
        if abs(zoom - 1.0) > 0.001 or abs(pan_x) > 0.5 or abs(pan_y) > 0.5:
            elements = elements.transform(
                (VIDEO_WIDTH, VIDEO_HEIGHT),
                Image.AFFINE,
                (zoom, 0, pan_x, 0, zoom, pan_y),
                resample=resample_mode,
            )

        bg.alpha_composite(elements)

        # FIXED-B2: 问题53 - 字幕和弹幕移到PIL阶段，避免每帧4次BGR↔RGB转换
        ui_overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        # 弹幕（UI层，不随镜头动）
        self.painter._draw_danmaku(ui_overlay)
        # Kimi 字幕（UI层）
        if self.kimi_script and "subtitles" in self.kimi_script and t < self.audio_end_time:
            self.ui_painter._draw_kimi_subtitles(ui_overlay, t)
        # 准星（固定层，不随镜头动）- PIL阶段绘制
        cam_type, focus = self.camera._get_script_camera(t)
        self.crosshair.set_visible(cam_type in ("group", "close"))
        self.crosshair.draw(ui_overlay)
        bg.alpha_composite(ui_overlay)

        # 尾奏全场景淡出（黑幕渐入）
        if self.audio_end_time > 0 and t > self.audio_end_time:
            dt_outro = t - self.audio_end_time
            scene_fade_start = OUTRO_WAIT_DURATION + OUTRO_FADEOUT_DURATION + OUTRO_BUFFER
            scene_fade_end = scene_fade_start + OUTRO_SCENE_FADE
            if dt_outro >= scene_fade_start:
                if dt_outro < scene_fade_end:
                    p = clamp((dt_outro - scene_fade_start) / OUTRO_SCENE_FADE, 0, 1)
                    p = 3 * p * p - 2 * p * p * p  # smoothstep
                    black_alpha = int(255 * p)
                    black_overlay = Image.new("RGBA", bg.size, (0, 0, 0, black_alpha))
                    bg.alpha_composite(black_overlay)
                else:
                    bg.paste((0, 0, 0), (0, 0, bg.size[0], bg.size[1]))

        # 运动模糊：将上一帧和当前帧按同屏按下密度融合（密集段拖影更强）
        if hasattr(self, '_prev_frame'):
            # 同屏正在按下的音轨越多，拖影越强（0.18 平静 → 0.42 密集爆发）
            try:
                pressing = sum(
                    1 for tr in self.tracks
                    if self.stage.get_tsm(tr.layer_id).is_active_at(t)
                )
            except Exception:
                pressing = 0
            norm = max(0.0, min(1.0, pressing / 10.0))
            blend = 0.18 + 0.24 * norm
            # 必须在转换为 BGR 之前混合，否则颜色会错乱
            bg = Image.blend(self._prev_frame, bg, 1 - blend)

        self._prev_frame = bg.copy()

        rgb = np.array(bg.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        return bgr


# ============== re-export（兼容现有导入） ==============
from .renderer_audio import render_video, _mux_audio, preview_frame
from .renderer_multiprocess import render_video_multiprocess


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        nbs_path = sys.argv[1]
        out = sys.argv[2] if len(sys.argv) >= 3 else "preview.png"
        t = float(sys.argv[3]) if len(sys.argv) >= 4 else 0.5
        preview_frame(nbs_path, out, t)
    else:
        print("用法: python nbs_visualizer.py <nbs_file> [output_png] [time_s]")
