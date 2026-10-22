"""FrameRenderer 绘制方法 mixin。"""
from __future__ import annotations

from typing import Optional
from PIL import Image

from .logger import get_logger

from .stage import TrackData, BLOCK_BACKING_COLOR
from .stage_constants import SPECTRUM_RENDER_GAP_RATIO
from ._core import FPS


def _block_size_cap(bs: int) -> int:
    """方块最大允许绘制的完整边长（px）。

    边界约束：方块（贴图/遮盖）在挤压拉伸形变时，其最大完整边长不得超过
    "频谱条内侧边界" = bs + 2*spec_gap，否则会溢出遮挡频谱条或邻块内容。
    留 2px 安全余量，避免形变峰值恰好贴到频谱条上。
    spec_gap 使用渲染间隙(SPECTRUM_RENDER_GAP_RATIO)，与频谱条实际绘制位置一致。
    """
    spec_gap = max(3, int(bs * SPECTRUM_RENDER_GAP_RATIO))
    margin = 2
    return bs + 2 * spec_gap - 2 * margin

logger = get_logger(__name__)


class RendererPainter:
    """FrameRenderer 绘制方法组件（原 Mixin 重构为组合）。"""

    """FrameRenderer 绘制方法组件（原 Mixin 重构为组合）。"""

    def __init__(self, host):
        self.host = host

    """FrameRenderer 的绘制方法 mixin。"""

    # FIXED-B3: 问题31 - Solo聚光灯检测
    def _get_solo_track(self, t: float) -> Optional[int]:
        """检测Solo聚光灯轨道。
        条件：某轨道最活跃持续2s+，且第二活跃轨道<30%的Solo活跃度。
        返回Solo轨道layer_id，不满足返回None。
        """
        if len(self.host.tracks) < 2:
            return None
        activities = [(tr.layer_id, self.host.stage.get_tsm(tr.layer_id).get_activity_ratio(t)) for tr in self.host.tracks]
        activities.sort(key=lambda x: x[1], reverse=True)
        top_id, top_activity = activities[0]
        second_activity = activities[1][1]
        if top_activity < 0.15 or second_activity >= top_activity * 0.3:
            self.host._solo_candidate_id = None
            self.host._solo_candidate_start = t
            return None
        if self.host._solo_candidate_id == top_id:
            if t - self.host._solo_candidate_start >= 2.0:
                return top_id
        else:
            self.host._solo_candidate_id = top_id
            self.host._solo_candidate_start = t
        return None

    def _draw_group_labels(self, img: Image.Image):
        """绘制组标签（委托给 CardRenderer）。"""
        for gb in self.host.stage.group_bounds:
            label_w = getattr(self.host.stage, 'LABEL_WIDTH', 70)
            self.host.card_renderer.draw_group_label(
                img, gb, label_w, self.host.font_group,
            )

    def _draw_danmaku(self, pil_img: Image.Image):
        """绘制弹幕。"""
        if not self.host.danmaku._active:
            return
        # FIXED-B2: 问题53 - 直接在PIL overlay上绘制，无需BGR↔RGB转换
        self.host.danmaku.draw(pil_img)

    def _draw_all_cards(self, img: Image.Image, t: float):
        bs = self.host.stage.block_size
        card_size = self.host.stage.card_size

        for track in self.host.tracks:
            if not self.host.stage.is_visible(track.layer_id):
                continue
            alpha = self.host.stage.get_alpha(track.layer_id, t)
            if alpha <= 0.01:
                continue

            cx, cy = self.host.stage.get_position(track.layer_id, t)
            tsm = self.host.stage.get_tsm(track.layer_id)
            is_active = tsm.is_active_at(t)
            palette = self.host.stage.get_color(track.layer_id)
            if tsm is None:
                continue
            is_solo = self.host._solo_active_id is not None and track.layer_id == self.host._solo_active_id
            solo_alpha = self.host._solo_alpha if is_solo else 0.0
            tsm.update_visual(t, 1.0 / FPS, is_active, is_solo, solo_alpha, palette)

            self.host.card_renderer.draw_card(
                img, t, tsm, cx, cy, card_size, bs, palette, alpha, is_active,
            )

    def _draw_block(self, img: Image.Image, track: TrackData,
                    cx: int, cy: int, bs: int,
                    tex_scale: float, mask_scale: float,
                    sx: float = 1.0, sy: float = 1.0,
                    msx: float = 1.0, msy: float = 1.0):
        """绘制蒙版（灰色）+贴图，分别用不同scale；sx/sy 为贴图英雄挤压，msx/msy 为遮盖层克制挤压。
        使用2倍超采样（HiDPI）并采用 round() + Lanczos，修复像素截断和抗锯齿问题。"""
        cap = _block_size_cap(bs)
        # 蒙版（灰色半透明）—— 使用独立的遮盖挤压(msx,msy)，与贴图英雄挤压区分开
        msize_x = min(int(round(bs * mask_scale * msx * 2)) // 2, cap)
        msize_y = min(int(round(bs * mask_scale * msy * 2)) // 2, cap)
        if msize_x >= 4 and msize_y >= 4:
            mx = int(round(cx - msize_x / 2))
            my = int(round(cy - msize_y / 2))
            backing = Image.new("RGBA", (msize_x, msize_y), BLOCK_BACKING_COLOR)
            img.alpha_composite(backing, (mx, my))
        # 贴图（英雄挤压 sx/sy）
        tsize_x = min(int(round(bs * tex_scale * sx * 2)) // 2, cap)
        tsize_y = min(int(round(bs * tex_scale * sy * 2)) // 2, cap)
        if tsize_x >= 4 and tsize_y >= 4:
            tx = int(round(cx - tsize_x / 2))
            ty = int(round(cy - tsize_y / 2))

            # 超采样：先取原尺寸2倍的图，再缩放到目标尺寸（Lanczos 高质量抗锯齿）
            base = max(tsize_x, tsize_y) * 2
            block_img = self.host.textures.get_block(track.instrument_id, base)
            block_img = block_img.resize((tsize_x, tsize_y), Image.Resampling.LANCZOS)

            img.alpha_composite(block_img, (tx, ty))

    def _draw_blocks(self, img: Image.Image, t: float,
                     outro_scale: float = 1.0):
        """绘制所有方块，outro_scale < 1 时应用尾奏收缩。"""
        bs = self.host.stage.block_size
        for track in self.host.tracks:
            if not self.host.stage.is_visible(track.layer_id):
                continue
            alpha = self.host.stage.get_alpha(track.layer_id, t)
            if alpha <= 0.01:
                continue

            cx, cy = self.host.stage.get_position(track.layer_id, t)
            tsm = self.host.stage.get_tsm(track.layer_id)
            tex_scale = tsm.get_texture_scale(t) * outro_scale
            mask_scale = tsm.get_mask_scale(t) * outro_scale
            sqx, sqy = tsm.get_squash(t)          # 贴图英雄挤压
            msqx, msqy = tsm.get_mask_squash(t)   # 遮盖层克制挤压（与贴图不同）

            if alpha >= 1.0:
                self._draw_block(img, track, int(cx), int(cy), bs, tex_scale, mask_scale, sqx, sqy, msqx, msqy)
            else:
                # 带透明度：先画到局部临时图层（支持挤压拉伸非均匀尺寸）
                cap = _block_size_cap(bs)
                msize = min(int(round(bs * mask_scale * msqx)), cap)
                my_sz = min(int(round(bs * mask_scale * msqy)), cap)
                tsize = min(int(round(bs * tex_scale * sqx)), cap)
                ty_sz = min(int(round(bs * tex_scale * sqy)), cap)
                max_w = max(msize, tsize)
                max_h = max(my_sz, ty_sz)
                if max_w < 4 or max_h < 4:
                    continue
                pad = 2
                ov_w = max_w + pad * 2
                ov_h = max_h + pad * 2
                ox = int(round(cx - max_w / 2)) - pad
                oy = int(round(cy - max_h / 2)) - pad
                local_overlay = Image.new("RGBA", (ov_w, ov_h), (0, 0, 0, 0))

                # 蒙版
                if msize >= 4 and my_sz >= 4:
                    mlx = (ov_w - msize) // 2
                    mly = (ov_h - my_sz) // 2
                    backing = Image.new("RGBA", (msize, my_sz), BLOCK_BACKING_COLOR)
                    local_overlay.alpha_composite(backing, (mlx, mly))

                # 贴图
                if tsize >= 4 and ty_sz >= 4:
                    tlx = (ov_w - tsize) // 2
                    tly = (ov_h - ty_sz) // 2
                    base = max(tsize, ty_sz) * 2
                    block_img = self.host.textures.get_block(track.instrument_id, base)
                    block_img = block_img.resize((tsize, ty_sz), Image.Resampling.LANCZOS)
                    local_overlay.alpha_composite(block_img, (tlx, tly))

                r, g, b, a = local_overlay.split()
                a = a.point(lambda x: max(0, min(255, round(x * alpha))))
                local_overlay = Image.merge("RGBA", (r, g, b, a))
                img.alpha_composite(local_overlay, (ox, oy))

    def _draw_all_labels(self, img: Image.Image, t: float):
        bs = self.host.stage.block_size

        for track in self.host.tracks:
            alpha = self.host.stage.get_alpha(track.layer_id, t)
            if alpha <= 0.01:
                continue

            cx, cy = self.host.stage.get_position(track.layer_id, t)
            tsm = self.host.stage.get_tsm(track.layer_id)
            if tsm is None:
                continue

            self.host.card_renderer.draw_card_labels(
                img, t, tsm, cx, cy, bs, alpha,
            )
