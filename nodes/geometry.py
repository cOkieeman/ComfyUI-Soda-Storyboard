"""Map storyboard page geometry to the actual diffusion or upscaled image."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from .core import core

if TYPE_CHECKING:
    from soda_storyboard.models import Page, RectShape, Text


def _scale_rect(rect: RectShape, sx: float, sy: float) -> None:
    rect.x *= sx
    rect.y *= sy
    rect.w *= sx
    rect.h *= sy


def _scale_text(text: Text, sx: float, sy: float) -> None:
    if text.bbox is not None:
        _scale_rect(text.bbox, sx, sy)
    lettering = core("production.lettering")
    font_size = lettering.font_size_override(text)
    if font_size is not None:
        text.extra["font_size"] = font_size * min(sx, sy)
    tip = lettering.shout_tail_tip(text)
    if tip is not None:
        text.extra["tail_tip"] = [tip[0] * sx, tip[1] * sy]


def page_at_size(page: Page, size: tuple[int, int]) -> Page:
    """Scale finishing geometry without resizing the image or changing page_info.

    X/Y positions follow each image axis independently. Fonts use the smaller
    ratio so lettering remains legible when an image's aspect ratio changes.
    Resolve automatic text positions before transforming them, otherwise the
    core's fixed layout margins would shift bubbles after a second sample.
    """
    if min(*page.canvas_size, *size) <= 0:
        raise ValueError("分镜画布和图片尺寸必须大于 0")
    if page.canvas_size == size:
        return page
    sx, sy = size[0] / page.canvas_width, size[1] / page.canvas_height
    ratio = min(sx, sy)

    scaled = deepcopy(page)
    scaled.canvas_width, scaled.canvas_height = size
    scaled.panel_gap = round(page.panel_gap * ratio)
    # Core fonts are normalized to a 1024-wide page; avoid applying sx twice.
    scaled.text_font_size = page.text_font_size * ratio / sx
    scaled.texts = deepcopy(core("lettering").layout_texts(page))
    for panel in scaled.panels:
        if panel.shape_type == "quad":
            panel.shape["points"] = [[x * sx, y * sy] for x, y in panel.shape["points"]]
        else:
            for key, factor in (("x", sx), ("y", sy), ("w", sx), ("h", sy)):
                panel.shape[key] *= factor
        # layout_texts has already converted these into scaled.texts.
        panel.dialogue = []
        panel.sfx = []
    for text in scaled.texts:
        _scale_text(text, sx, sy)
    for item in [*scaled.overlays, *scaled.objects]:
        _scale_rect(item.rect, sx, sy)
    return scaled
