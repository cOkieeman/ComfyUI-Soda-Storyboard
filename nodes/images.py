"""One conversion boundary for ComfyUI tensors and PIL geometry operations."""

from __future__ import annotations

import importlib
import math
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageChops, ImageDraw

from .core import core, dumps, parse_info, select_panel, single_prompt
from .geometry import page_at_size

if TYPE_CHECKING:
    from collections.abc import Callable


def tensor_images(batch: Any) -> list[Image.Image]:
    np = importlib.import_module("numpy")
    if batch.ndim != 4 or batch.shape[-1] not in {1, 3, 4} or batch.shape[0] < 1:
        msg = "IMAGE 必须是非空 [B,H,W,C] 张量，C 为 1、3 或 4"
        raise ValueError(msg)
    arrays = batch.detach().cpu().clamp(0, 1).numpy()
    return [
        Image.fromarray(
            np.rint(array * 255).astype(np.uint8).squeeze(-1)
            if array.shape[-1] == 1
            else np.rint(array * 255).astype(np.uint8)
        ).convert("RGB")
        for array in arrays
    ]


def images_tensor(images: list[Image.Image], *, mask: bool = False) -> Any:
    np = importlib.import_module("numpy")
    torch = importlib.import_module("torch")
    arrays = [np.asarray(image.convert("L" if mask else "RGB"), dtype=np.float32) / 255 for image in images]
    return torch.from_numpy(np.stack(arrays))


def map_images(batch: Any, operation: Callable[[Image.Image], Image.Image]) -> tuple[Any]:
    return (images_tensor([operation(image) for image in tensor_images(batch)]),)


def crop_panel(image: Image.Image, page_info: str, selector: str, *, resize: bool) -> tuple:
    page, characters = parse_info(page_info)
    prompt = single_prompt(select_panel(page, selector), characters, page)
    page = page_at_size(page, image.size)
    panel = select_panel(page, selector)
    imaging = core("production.imaging")
    box = imaging.panel_box(panel)
    crop = image.crop(box)
    mask = imaging.quad_mask(panel)
    original_size = crop.size
    if resize:
        ratio = 1024 / max(crop.size)
        size = tuple(max(16, round(v * ratio / 16) * 16) for v in crop.size)
        crop = crop.resize(size, Image.Resampling.LANCZOS)
        mask = mask.resize(size, Image.Resampling.NEAREST)
    metadata = dumps(
        {
            "version": 1,
            "box": box,
            "original_size": original_size,
            "crop_size": crop.size,
            "scale": [crop.width / original_size[0], crop.height / original_size[1]],
            "canvas_size": page.canvas_size,
            "panel_id": panel.id,
            "page_info": page_info,
        }
    )
    return crop, mask, prompt, metadata


def paste_panel(
    original: Image.Image, redrawn: Image.Image, metadata: dict, *, protect_text: bool
) -> Image.Image:
    if metadata.get("version") != 1:
        msg = "panel_box 版本无效，请连接切格节点的 panel_box 输出"
        raise ValueError(msg)
    page, _ = parse_info(metadata["page_info"])
    if list(original.size) != metadata["canvas_size"]:
        msg = "整页图尺寸与切格时不一致，请使用同一整页图或重新切格"
        raise ValueError(msg)
    page = page_at_size(page, original.size)
    panel = select_panel(page, metadata["panel_id"])
    imaging = core("production.imaging")
    box = imaging.panel_box(panel)
    if list(box) != metadata["box"] or list(page.canvas_size) != metadata["canvas_size"]:
        msg = "panel_box 与页面几何不一致，请重新切格"
        raise ValueError(msg)
    crop = original.crop(box)
    patch = redrawn.resize(crop.size, Image.Resampling.LANCZOS).convert("RGB")
    if protect_text:
        patch = imaging.preserve_text(crop, patch, panel, page)
    result = original.copy()
    result.paste(patch, box[:2], imaging.quad_mask(panel))
    return result


def paste_edit_mask(page: Any, panel: Any, *, protect_text: bool) -> Image.Image:
    imaging = core("production.imaging")
    mask = imaging.quad_mask(panel)
    if protect_text:
        # Ask the same core operation which pixels it protects, so tensor-level
        # preservation follows the PIL operation even if core text rules change.
        protected = imaging.preserve_text(
            Image.new("RGB", mask.size, "black"), Image.new("RGB", mask.size, "white"), panel, page
        ).convert("L")
        mask = ImageChops.multiply(mask, protected)
    result = Image.new("L", page.canvas_size)
    result.paste(mask, imaging.panel_box(panel)[:2])
    return result


def character_mask(
    image: Image.Image,
    page_info: str,
    selector: str,
    character_id: str,
    margin: int,
    feather: int,
    scope: str,
) -> Image.Image:
    page, _ = parse_info(page_info)
    panel = select_panel(page, selector)
    imaging = core("production.imaging")
    mask = imaging.figure_mask(panel, page, character_id, margin=margin, feather=feather)
    if scope == "整页":
        full = Image.new("L", page.canvas_size)
        full.paste(mask, imaging.panel_box(panel)[:2])
        return full.resize(image.size, Image.Resampling.NEAREST)
    if scope != "格子":
        msg = "图像范围必须为格子或整页"
        raise ValueError(msg)
    # Nearest preserves the zeroed silhouettes of neighbouring characters.
    return mask.resize(image.size, Image.Resampling.NEAREST)


def cut_quads(
    image: Image.Image, page_info: str, inset: int, border: int, *, redraw_borders: bool = True
) -> Image.Image:
    page, _ = parse_info(page_info)
    if inset < 0 or border < 1:
        msg = "收缩像素不能为负，格框粗细至少为 1"
        raise ValueError(msg)
    ratio = min(image.width / page.canvas_width, image.height / page.canvas_height)
    page = page_at_size(page, image.size)
    inset *= ratio
    border = max(1, round(border * ratio))
    imaging = core("production.imaging")
    quad_bounds = Image.new("L", image.size)
    interiors = Image.new("L", image.size)
    for panel in page.panels:
        box = imaging.panel_box(panel)
        if panel.shape_type == "quad":
            quad_bounds.paste(255, box)
        layer = Image.new("L", image.size)
        layer.paste(imaging.quad_mask(panel, inset=inset), box[:2])
        interiors = ImageChops.lighter(interiors, layer)
    # Clear only the quad margins outside ALL panel interiors. Unioning masks
    # protects neighbours even when their bounding rectangles overlap.
    result = image.copy()
    result.paste("white", mask=ImageChops.subtract(quad_bounds, interiors))
    if not redraw_borders:
        return result
    draw = ImageDraw.Draw(result)
    for panel in page.panels:
        if panel.shape_type == "quad":
            points = imaging.inset_quad(panel.shape["points"], inset)
            draw.line([*points, points[0]], fill="black", width=border, joint="curve")
        else:
            x, y, right, bottom = imaging.panel_box(panel)
            draw.rectangle((x, y, math.ceil(right) - 1, math.ceil(bottom) - 1), outline="black", width=border)
    return result
