"""Generate the visible draft and exact MOSS text for every input format."""

from __future__ import annotations

import base64
import hashlib
import io
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .bundles import (
    BUNDLE_FORMAT,
    compile_page_bundle,
    decode_json,
    describe,
    parse_bundle,
    result_outputs,
    validate_moss,
)
from .core import NEGATIVE, core, dumps, info, resolution
from .moss import COLORS, analyze_layout, boxes, import_page, item_text, resolve_dimensions, text_direction

MIN_LABEL_SIZE = 8
MAX_FONT_SIZE = 24
MIN_FONT_SIZE = 5


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


def moss_dimensions(value: dict, width: int = 0, height: int = 0) -> tuple[int, int]:
    resolved_width, resolved_height, _ = resolve_dimensions(value, width, height)
    return resolved_width, resolved_height


def moss_boxes(value: dict, width: int, height: int) -> list[tuple[dict, tuple]]:
    return boxes(value, width, height)


def moss_page(value: dict, width: int, height: int) -> Any:
    return import_page(value, width, height)[0]


def text_lines(text: str, font: Any, width: int) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for char in paragraph:
            if line and font.getlength(line + char) > width:
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
    return lines


def label_layout(
    text: str, width: int, height: int, direction: str, path: Any, *, max_size: int = MAX_FONT_SIZE
) -> tuple:
    for size in range(max_size, MIN_FONT_SIZE - 1, -1):
        font = ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size=size)
        advance = size + 3
        if direction == "vertical":
            capacity = max(1, height // advance)
            lines = [
                paragraph[start : start + capacity]
                for paragraph in text.split("\n")
                for start in range(0, len(paragraph), capacity)
            ]
            fits = (
                len(lines) * advance <= width
                and max((len(line) for line in lines), default=0) * advance <= height
            )
        else:
            lines = text_lines(text, font, width)
            fits = len(lines) * advance <= height
        if fits:
            break
    return font, lines, size + 3


def moss_preview(value: dict, width: int, height: int) -> Image.Image:
    scale = min(1.0, 1024 / max(width, height))
    image = Image.new("RGB", (max(1, round(width * scale)), max(1, round(height * scale))), "white")
    draw = ImageDraw.Draw(image)
    path = core("preview").find_font()
    rendered = []
    for item, bounds in moss_boxes(value, width, height):
        box = tuple(round(v * scale) for v in bounds)
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        color = COLORS.get(item.get("label", "object"), COLORS["object"])
        draw.rectangle(box, outline=color, width=2)
        rendered.append((item, box, color))
    # Transparent labels do not erase other object/character/text boundaries.
    for item, box, color in sorted(rendered, key=lambda entry: entry[0].get("label") == "text"):
        text = item_text(item)
        if not text or box[2] - box[0] < MIN_LABEL_SIZE or box[3] - box[1] < MIN_LABEL_SIZE:
            continue
        width, height = box[2] - box[0] - 6, box[3] - box[1] - 6
        if item.get("label") != "text":
            height = min(height, 56)
        direction = text_direction(box) if item.get("label") == "text" else "horizontal"
        font, lines, advance = label_layout(
            text, width, height, direction, path, max_size=24 if item.get("label") == "text" else 16
        )
        label = Image.new("RGBA", (width, height))
        label_draw = ImageDraw.Draw(label)
        for index, line in enumerate(lines):
            if direction == "vertical":
                for row, char in enumerate(line):
                    label_draw.text(
                        (width - (index + 1) * advance, row * advance),
                        char,
                        font=font,
                        fill=color,
                        stroke_width=1,
                        stroke_fill="white",
                    )
            else:
                label_draw.text(
                    (0, index * advance), line, font=font, fill=color, stroke_width=1, stroke_fill="white"
                )
        image.paste(label, (box[0] + 3, box[1] + 3), label)
    return image


def inspect_page(
    page: Any,
    cards: dict,
    warnings: list[str],
    *,
    slant_mode: str = "cut",
    include_triggers: bool = True,
    draft: Image.Image | None = None,
) -> dict:
    compiled = compile_page_bundle(page, cards, slant_mode, include_triggers=include_triggers)
    result = result_outputs(page, cards, compiled, include_triggers=include_triggers)
    metadata = describe(
        page, cards, list(dict.fromkeys([*warnings, *compiled["warnings"]])), compiled=compiled
    )
    metadata.update(
        moss_json=result[0],
        width=result[1],
        height=result[2],
        page_info=result[7],
        kind="page",
        source_kind="page",
        draft_png_base64=png_base64(draft if draft is not None else draft_image(page, cards)),
        result=result,
    )
    return metadata


@lru_cache(maxsize=8)
def inspect_payload(
    payload: bytes,
    *,
    width: int = 0,
    height: int = 0,
    dialogue_mode: str = "跟随页面",
    slant_mode: str = "cut",
    include_triggers: bool = True,
) -> dict:
    value = decode_json(payload)
    if "summary" in value and "items" in value:
        validate_moss(value)
        width, height, inferred = resolve_dimensions(value, width, height)
        layout = analyze_layout(value, width, height)
        text_count = layout["report"]["text_count"]
        layout_label = f"{len(layout['panels'])} 格" if layout["panels"] else "单画布"
        page = moss_page(value, width, height)
        result = (dumps(value), width, height, resolution(width, height), "", 0.0, NEGATIVE, info(page, {}))
        metadata = describe(page, {}, [])
        metadata.update(
            kind="moss",
            source_kind="moss",
            title="",
            page_id="",
            panels=layout["panels"],
            panel_count=len(layout["panels"]),
            single_canvas=layout["single_canvas"],
            moss_layout=layout,
            dimensions_inferred=inferred,
            text_count=text_count,
            legend=[
                {"label": name, "color": COLORS[kind]}
                for kind, name in (("object", "物件"), ("character", "角色"), ("text", "文字"))
            ],
            items=value["items"],
            summary=(
                f"{width}×{height} · {len(value['items'])} 个条目 · {text_count} 个文字条目 · {layout_label}"
            ),
            moss_json=result[0],
            width=width,
            height=height,
            result=result,
            draft_png_base64=png_base64(moss_preview(value, width, height)),
            warnings=[
                *([f"画布尺寸为推断值：{width}×{height}"] if inferred else []),
                *layout["report"]["guesses"],
                *layout["report"]["warnings"],
                *(
                    [f"{len(layout['report']['unrecognized_items'])} 个条目无法识别，原始 JSON 已保留。"]
                    if layout["report"]["unrecognized_items"]
                    else []
                ),
                "MOSS JSON 转为分镜单是近似转换，请检查格子和文字位置。",
            ],
        )
    else:
        page, cards, warnings, _ = parse_bundle(value, dialogue_mode)
        metadata = inspect_page(
            page, cards, warnings, slant_mode=slant_mode, include_triggers=include_triggers
        )
        metadata["source_kind"] = "bundle" if value.get("format") == BUNDLE_FORMAT else "page"
    metadata["revision"] = hashlib.sha256(
        payload + dumps([width, height, dialogue_mode, slant_mode, include_triggers]).encode()
    ).hexdigest()
    return metadata
