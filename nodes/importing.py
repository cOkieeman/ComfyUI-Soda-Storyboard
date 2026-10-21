"""Generate the visible draft and exact MOSS text for every input format."""

from __future__ import annotations

import base64
import hashlib
import io
import math
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .bundles import compile_result, decode_json, describe, parse_bundle, validate_moss
from .core import NEGATIVE, core, dumps, info, resolution

MAX_CANVAS = 16384
BBOX_COMPONENTS = 4
MIN_LABEL_SIZE = 8


def png_base64(image: Image.Image) -> str:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def draft_image(page: Any, characters: dict) -> Image.Image:
    scale = min(1.0, 1024 / max(page.canvas_size))
    with TemporaryDirectory(prefix="soda-draft-") as directory:
        path = Path(directory) / "draft.png"
        core("preview").render_preview(page, path, characters, scale=scale, style="sketch")
        with Image.open(path) as image:
            return image.convert("RGB")


def moss_dimensions(value: dict, width: int, height: int) -> tuple[int, int]:
    canvas = value.get("canvas", {})
    if not isinstance(canvas, dict):
        canvas = {}
    width = int(value.get("width", canvas.get("width", width)))
    height = int(value.get("height", canvas.get("height", height)))
    if not 1 <= width <= MAX_CANVAS or not 1 <= height <= MAX_CANVAS:
        msg = "MOSS 画布宽高必须在 1 到 16384 之间"
        raise ValueError(msg)
    return width, height


def moss_boxes(value: dict, width: int, height: int) -> list[tuple[dict, tuple]]:
    result = []
    space, fmt = value.get("bbox_coord_space", "abs_centralized"), value.get("bbox_format", "yxyx")
    if space not in {"abs_centralized", "abs", "absolute", "normalized"} or fmt not in {"yxyx", "xyxy"}:
        msg = "不支持此 MOSS bbox 坐标空间或格式"
        raise ValueError(msg)
    for item in value["items"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("bbox"), list)
            or len(item["bbox"]) != BBOX_COMPONENTS
        ):
            msg = "MOSS 每个条目必须有四个数值的 bbox"
            raise ValueError(msg)
        a, b, c, d = (float(v) for v in item["bbox"])
        x, y, right, bottom = (b, a, d, c) if fmt == "yxyx" else (a, b, c, d)
        if space == "abs_centralized":
            x, right, y, bottom = x + width // 2, right + width // 2, y + height // 2, bottom + height // 2
        elif space == "normalized":
            x, right, y, bottom = x * width, right * width, y * height, bottom * height
        if not all(math.isfinite(v) for v in (x, y, right, bottom)) or right <= x or bottom <= y:
            msg = "MOSS bbox 必须是有限、面积大于零的矩形"
            raise ValueError(msg)
        result.append((item, (max(0, x), max(0, y), min(width, right), min(height, bottom))))
    return result


def moss_page(value: dict, width: int, height: int) -> Any:
    panels, texts = [], []
    for index, (item, box) in enumerate(moss_boxes(value, width, height), 1):
        x, y, right, bottom = box
        if right <= x or bottom <= y:
            continue
        shape = {"type": "rect", "x": x, "y": y, "w": right - x, "h": bottom - y}
        label = item.get("label", "object")
        if label == "text":
            texts.append(
                {
                    "id": f"text-{index}",
                    "text": str(item.get("text", "")),
                    "bbox": {key: shape[key] for key in ("x", "y", "w", "h")},
                    "kind": "dialogue",
                    "bubble": "box",
                    "direction": "horizontal",
                }
            )
        elif label in {"object", "panel"}:
            panels.append(
                {
                    "id": f"panel-{index}",
                    "order": len(panels) + 1,
                    "shape": shape,
                    "description": str(item.get("caption", "")),
                    "caption_en": str(item.get("caption", "")),
                }
            )
    if not panels:
        panels = [
            {"id": "panel-1", "order": 1, "shape": {"type": "rect", "x": 0, "y": 0, "w": width, "h": height}}
        ]
    return core("models").Page.from_dict(
        {
            "id": "imported",
            "canvas_width": width,
            "canvas_height": height,
            "panel_gap": 0,
            "panels": panels,
            "texts": texts,
            "style_prompt": str(value["summary"].get("caption", "")),
        }
    )


def moss_preview(value: dict, width: int, height: int) -> Image.Image:
    scale = min(1.0, 1024 / max(width, height))
    image = Image.new("RGB", (max(1, round(width * scale)), max(1, round(height * scale))), "white")
    draw = ImageDraw.Draw(image)
    path = core("preview").find_font()
    font = ImageFont.truetype(str(path), 14) if path else ImageFont.load_default(size=14)
    if not value["items"]:
        draw.rectangle((0, 0, image.width - 1, image.height - 1), outline="#2d805a", width=2)
        draw.text(
            (8, 8), str(value["summary"].get("caption", "No layout boxes"))[:120], font=font, fill="black"
        )
    colors = {"text": "#b34922", "character": "#2563a6", "object": "#2d805a", "panel": "#2d805a"}
    for item, bounds in moss_boxes(value, width, height):
        box = tuple(round(v * scale) for v in bounds)
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        color = colors.get(item.get("label", "object"), "#666666")
        draw.rectangle(box, outline=color, width=2)
        text = str(item.get("caption", ""))[:100]
        if item.get("text"):
            text += "\n" + str(item["text"])
        # Clip each label to its own bbox rather than spilling into neighbours.
        if box[2] - box[0] < MIN_LABEL_SIZE or box[3] - box[1] < MIN_LABEL_SIZE:
            continue
        label = Image.new("RGB", (box[2] - box[0] - 4, box[3] - box[1] - 4), "white")
        label_draw = ImageDraw.Draw(label)
        limit = max(1, (label.width - 8) // 14)
        rows = []
        max_rows = max(1, label.height // 18)
        for line in io.StringIO(text):
            for start in range(0, len(line), limit):
                rows.append(line[start : start + limit].rstrip("\n"))
                if len(rows) >= max_rows:
                    break
            if len(rows) >= max_rows:
                break
        label_draw.multiline_text((4, 4), "\n".join(rows), font=font, fill=color)
        image.paste(label, (box[0] + 2, box[1] + 2), None)
        draw.rectangle(box, outline=color, width=2)
    return image


def inspect_page(
    page: Any, cards: dict, warnings: list[str], *, slant_mode: str = "cut", include_triggers: bool = True
) -> dict:
    result = compile_result(page, cards, slant_mode, include_triggers=include_triggers)
    metadata = describe(page, cards, warnings)
    metadata.update(
        moss_json=result[0],
        width=result[1],
        height=result[2],
        page_info=result[7],
        kind="page",
        draft_png_base64=png_base64(draft_image(page, cards)),
        result=result,
    )
    return metadata


@lru_cache(maxsize=8)
def inspect_payload(
    payload: bytes,
    *,
    width: int = 1024,
    height: int = 1536,
    dialogue_mode: str = "跟随页面",
    slant_mode: str = "cut",
    include_triggers: bool = True,
) -> dict:
    value = decode_json(payload)
    if "summary" in value and "items" in value:
        validate_moss(value)
        width, height = moss_dimensions(value, width, height)
        page = moss_page(value, width, height)
        result = (dumps(value), width, height, resolution(width, height), "", 0.0, NEGATIVE, info(page, {}))
        metadata = describe(page, {}, [])
        metadata.update(
            kind="moss",
            moss_json=result[0],
            width=width,
            height=height,
            result=result,
            draft_png_base64=png_base64(moss_preview(value, width, height)),
            warnings=["MOSS JSON 没有分镜结构；转为分镜单是近似转换，请检查格子和文字位置。"],
        )
    else:
        page, cards, warnings, _ = parse_bundle(value, dialogue_mode)
        metadata = inspect_page(
            page, cards, warnings, slant_mode=slant_mode, include_triggers=include_triggers
        )
    metadata["revision"] = hashlib.sha256(
        payload + dumps([width, height, dialogue_mode, slant_mode, include_triggers]).encode()
    ).hexdigest()
    return metadata
