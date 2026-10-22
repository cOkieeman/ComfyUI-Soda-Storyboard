"""Pure display geometry for external MOSS layouts; never rewrite source items."""

from __future__ import annotations

import math
import re

MAX_CANVAS = 16384
BBOX_COMPONENTS = 4
# The core MOSS graph defaults to 1024x1536 and accepts dimensions aligned to 16.
# Include the common portrait/landscape variants without changing model settings.
CANVAS_PRESETS = ((1024, 1536), (1536, 1024), (1024, 1024), (768, 1344), (1344, 768))
COLORS = {"object": "#2d805a", "character": "#2563a6", "text": "#b34922"}
PANEL_WORDS = re.compile(r"\bpanels?\b|(?<![风性规表网方])格|コマ", re.IGNORECASE)
LARGE_AREA = 0.12
CONTAINMENT = 0.9
MAX_OVERLAP = 0.12
MIN_TILED_PANELS = 2
TEXT_VERTICAL_RATIO = 1.5


def raw_box(item: dict, fmt: str) -> tuple[float, float, float, float]:
    bbox = item.get("bbox") if isinstance(item, dict) else None
    if not isinstance(bbox, list) or len(bbox) != BBOX_COMPONENTS:
        msg = "MOSS 每个条目必须有四个数值的 bbox"
        raise ValueError(msg)
    a, b, c, d = (float(value) for value in bbox)
    box = (b, a, d, c) if fmt == "yxyx" else (a, b, c, d)
    if not all(math.isfinite(value) for value in box) or box[2] <= box[0] or box[3] <= box[1]:
        msg = "MOSS bbox 必须是有限、面积大于零的矩形"
        raise ValueError(msg)
    return box


def coordinate_mode(value: dict) -> tuple[str, str]:
    space, fmt = value.get("bbox_coord_space", "abs_centralized"), value.get("bbox_format", "yxyx")
    if space not in {"abs_centralized", "abs", "absolute", "normalized"} or fmt not in {"yxyx", "xyxy"}:
        msg = "不支持此 MOSS bbox 坐标空间或格式"
        raise ValueError(msg)
    return space, fmt


def infer_dimensions(value: dict) -> tuple[int, int]:
    space, fmt = coordinate_mode(value)
    bounds = [raw_box(item, fmt) for item in value.get("items", [])]
    if not bounds or space == "normalized":
        return CANVAS_PRESETS[0]
    if space == "abs_centralized":
        width = 2 * max(abs(edge) for box in bounds for edge in (box[0], box[2]))
        height = 2 * max(abs(edge) for box in bounds for edge in (box[1], box[3]))
    else:
        width = max(box[2] for box in bounds)
        height = max(box[3] for box in bounds)
    if width <= 0 or height <= 0:
        return CANVAS_PRESETS[0]
    ratio = width / height
    return min(CANVAS_PRESETS, key=lambda size: abs(math.log((size[0] / size[1]) / ratio)))


def resolve_dimensions(value: dict, width: int = 0, height: int = 0) -> tuple[int, int, bool]:
    canvas = value.get("canvas", {})
    if not isinstance(canvas, dict):
        canvas = {}
    written = (value.get("width", canvas.get("width")), value.get("height", canvas.get("height")))
    inferred = (
        infer_dimensions(value)
        if any(not override and size is None for override, size in zip((width, height), written, strict=True))
        else (0, 0)
    )
    resolved = tuple(
        int(override or (size if size is not None else fallback))
        for override, size, fallback in zip((width, height), written, inferred, strict=True)
    )
    if any(override < 0 for override in (width, height)) or not all(
        1 <= size <= MAX_CANVAS for size in resolved
    ):
        msg = "MOSS 画布宽高必须在 1 到 16384 之间；高级选项填 0 为自动"
        raise ValueError(msg)
    return (
        resolved[0],
        resolved[1],
        any(not override and size is None for override, size in zip((width, height), written, strict=True)),
    )


def boxes(value: dict, width: int, height: int) -> list[tuple[dict, tuple]]:
    space, fmt = coordinate_mode(value)
    result = []
    for item in value["items"]:
        x, y, right, bottom = raw_box(item, fmt)
        if space == "abs_centralized":
            x, right = x + width // 2, right + width // 2
            y, bottom = y + height // 2, bottom + height // 2
        elif space == "normalized":
            x, right, y, bottom = x * width, right * width, y * height, bottom * height
        result.append((item, (max(0, x), max(0, y), min(width, right), min(height, bottom))))
    return result


def area(box: tuple) -> float:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def intersection(first: tuple, second: tuple) -> float:
    return area(
        (
            max(first[0], second[0]),
            max(first[1], second[1]),
            min(first[2], second[2]),
            min(first[3], second[3]),
        )
    )


def detect_panels(items: list[dict], width: int, height: int) -> list[dict]:
    """Use named panels or multiple large, tiled object boxes, excluding containers."""
    objects = [item for item in items if item["label"] in {"object", "panel"} and area(item["bounds"]) > 0]
    explicit = [item for item in objects if item["label"] == "panel" or PANEL_WORDS.search(item["caption"])]
    candidates = list(
        {
            item["id"]: item
            for item in [
                *explicit,
                *(item for item in objects if area(item["bounds"]) >= width * height * LARGE_AREA),
            ]
        }.values()
    )
    leaves = [
        item
        for item in candidates
        if not any(
            other is not item
            and area(item["bounds"]) > area(other["bounds"]) * 1.05
            and intersection(item["bounds"], other["bounds"]) >= area(other["bounds"]) * CONTAINMENT
            for other in candidates
        )
    ]
    tiled = [
        item
        for item in leaves
        if all(
            other is item
            or intersection(item["bounds"], other["bounds"])
            <= min(area(item["bounds"]), area(other["bounds"])) * MAX_OVERLAP
            for other in leaves
        )
    ]
    selected = [item for item in leaves if item in explicit]
    if len(tiled) >= MIN_TILED_PANELS:
        selected = list({item["id"]: item for item in [*selected, *tiled]}.values())
    # Small y differences within a row do not reverse right-to-left manga order.
    ordered = sorted(selected, key=lambda item: item["bounds"][1])
    rows: list[list[dict]] = []
    for item in ordered:
        row = next(
            (row for row in rows if abs(row[0]["bounds"][1] - item["bounds"][1]) <= height * 0.06), None
        )
        if row is None:
            rows.append([item])
        else:
            row.append(item)
    return [item for row in rows for item in sorted(row, key=lambda item: -item["bounds"][0])]


def analyze_layout(value: dict, width: int, height: int) -> dict:
    items = []
    for index, (raw, bounds) in enumerate(boxes(value, width, height), 1):
        x, y, right, bottom = bounds
        items.append(
            {
                "id": f"item-{index}",
                "index": index,
                "label": str(raw.get("label", "object")),
                "caption": str(raw.get("caption", "")),
                "text": str(raw.get("text") or ""),
                "bounds": bounds,
                "shape": {"type": "rect", "x": x, "y": y, "w": max(0, right - x), "h": max(0, bottom - y)},
            }
        )
    panels = [
        {
            "id": f"moss-panel-{index}",
            "order": index,
            "item_id": item["id"],
            "shape": item["shape"],
            "description": item["caption"],
            "item_ids": [],
        }
        for index, item in enumerate(detect_panels(items, width, height), 1)
    ]
    bounds_by_id = {item["id"]: item["bounds"] for item in items}
    for item in items:
        owners = [
            (
                intersection(
                    item["bounds"],
                    bounds_by_id[panel["item_id"]],
                ),
                panel,
            )
            for panel in panels
        ]
        if owners:
            overlap, owner = max(owners, key=lambda pair: pair[0])
            if overlap > 0 and overlap >= area(item["bounds"]) * 0.5:
                owner["item_ids"].append(item["id"])
    return {"items": items, "panels": panels, "single_canvas": not panels}


def item_text(item: dict) -> str:
    if item.get("label") == "text":
        return str(item.get("text") or str(item.get("caption", ""))[:12])
    return str(item.get("caption", ""))[:12] if item.get("label") == "character" else ""


def text_direction(box: tuple) -> str:
    return "vertical" if box[3] - box[1] > (box[2] - box[0]) * TEXT_VERTICAL_RATIO else "horizontal"
