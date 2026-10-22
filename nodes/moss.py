"""Adapt core MOSS imports into the Comfy preview metadata contract."""

from __future__ import annotations

from typing import Any

from .core import core

MAX_CANVAS = 16384
COLORS = {"object": "#2d805a", "character": "#2563a6", "text": "#b34922"}
TEXT_VERTICAL_RATIO = 1.5


def import_page(value: dict, width: int = 0, height: int = 0) -> tuple[Any, dict]:
    source = {"summary": {}, **value}
    source.update({key: size for key, size in (("canvas_width", width), ("canvas_height", height)) if size})
    return core("importers").import_moss(source)


def resolve_dimensions(value: dict, width: int = 0, height: int = 0) -> tuple[int, int, bool]:
    page, report = import_page(value, width, height)
    if min(width, height) < 0 or not all(1 <= size <= MAX_CANVAS for size in page.canvas_size):
        msg = "MOSS 画布宽高必须在 1 到 16384 之间；高级选项填 0 为自动"
        raise ValueError(msg)
    inferred = any(message.startswith("画布尺寸缺失") for message in report["guesses"])
    return page.width, page.height, inferred


def analyze_layout(value: dict, width: int, height: int) -> dict:
    page, report = import_page(value, width, height)
    entities = {
        (kind, entity.id): entity
        for kind, values in (("panel", page.panels), ("text", page.texts), ("object", page.objects))
        for entity in values
    }
    entries = page.extra["moss_import"]["entries"]
    items, panels = [], []
    owners = {}
    for index, entry in enumerate(entries, 1):
        raw = entry["item"]
        entity = entities.get((entry["kind"], entry["id"]))
        shape = None
        bounds = None
        if entity is not None:
            shape = entity.to_dict()[{"panel": "shape", "text": "bbox", "object": "rect"}[entry["kind"]]]
            x, y, w, h = (shape[key] for key in ("x", "y", "w", "h"))
            bounds = (x, y, x + w, y + h)
        item_id = f"item-{index}"
        items.append(
            {
                "id": item_id,
                "index": index,
                "label": str(raw.get("label", "object")) if isinstance(raw, dict) else "object",
                "caption": str(raw.get("caption", "")) if isinstance(raw, dict) else "",
                "text": str(raw.get("text") or "") if isinstance(raw, dict) else "",
                "shape": shape,
                "bounds": bounds,
            }
        )
        if entry["kind"] == "panel":
            panels.append(
                {
                    "id": entity.id,
                    "order": entity.order,
                    "item_id": item_id,
                    "shape": shape,
                    "description": entity.description,
                    "item_ids": [item_id],
                }
            )
        elif entity is not None:
            owners[item_id] = entity.panel_id
    for panel in panels:
        panel["item_ids"].extend(key for key, owner in owners.items() if owner == panel["id"])
    return {
        "items": items,
        "panels": panels,
        "single_canvas": page.extra["canvas_mode"] == "single",
        "report": report,
    }


def boxes(value: dict, width: int, height: int) -> list[tuple[dict, tuple]]:
    layout = analyze_layout(value, width, height)
    return [(value["items"][item["index"] - 1], item["bounds"]) for item in layout["items"] if item["bounds"]]


def item_text(item: dict) -> str:
    if item.get("label") == "text":
        return str(item.get("text") or str(item.get("caption", ""))[:12])
    return str(item.get("caption", ""))[:12] if item.get("label") == "character" else ""


def text_direction(box: tuple) -> str:
    return "vertical" if box[3] - box[1] > (box[2] - box[0]) * TEXT_VERTICAL_RATIO else "horizontal"
