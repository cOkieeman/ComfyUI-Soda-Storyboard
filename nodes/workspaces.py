"""Editable copies live beside imported files, never in the source project."""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from pathlib import Path

from .bundles import (
    BUNDLE_FORMAT,
    decode_json,
    file_path,
    input_directory,
    original_filename,
    parse_bundle,
    store_upload,
)
from .core import content_hash, core, dumps, inside, load, page_path
from .importing import draft_image, inspect_payload, moss_dimensions, moss_page, png_base64

_WORKSPACE_LOCK = threading.Lock()


def workspace_root(filename: str) -> Path:
    source = file_path(filename)
    return inside(input_directory(), source.stem)


def workspace_bundle(filename: str) -> dict | None:
    root = workspace_root(filename)
    marker_path = inside(root, ".soda/import.json")
    if not marker_path.is_file():
        return None
    io = core("io")
    marker = io.read_json(marker_path)
    if marker.get("source_file") != filename:
        msg = "工作副本身份不匹配，请重新导入文件"
        raise ValueError(msg)
    page = io.read_json(page_path(root, marker["page_id"]))
    character_dir = inside(root, "characters")
    for path in character_dir.glob("*.json"):
        inside(root, path.relative_to(root).as_posix())
    cards = io.load_characters(character_dir)
    return {
        "format": BUNDLE_FORMAT,
        "project": io.read_json(inside(root, "project.json")),
        "page": page,
        "characters": {key: card.to_dict() for key, card in cards.items()},
    }


def import_payload(filename: str) -> bytes:
    bundle = workspace_bundle(filename)
    if bundle is not None:
        return dumps(bundle).encode()
    path = file_path(filename)
    if path.stat().st_size > 16 * 1024 * 1024:
        msg = "分镜文件不能超过 16 MiB"
        raise ValueError(msg)
    return path.read_bytes()


def inspect_import(filename: str, **options: object) -> dict:
    result = dict(inspect_payload(import_payload(filename), **options))
    result["filename"] = filename
    result["original_filename"] = original_filename(filename)
    if result["kind"] == "moss":
        result["title"] = Path(result["original_filename"]).stem.removesuffix(".moss")
    result["editable_copy"] = workspace_bundle(filename) is not None
    return result


def inspect_link(
    project_dir: str,
    page_id: str,
    dialogue_mode: str = "跟随页面",
    slant_mode: str = "cut",
    *,
    include_triggers: bool = True,
) -> dict:
    page, cards = load(project_dir, page_id, dialogue_mode)
    payload = dumps(
        {
            "format": BUNDLE_FORMAT,
            "project": {},
            "page": page.to_dict(),
            "characters": {key: card.to_dict() for key, card in cards.items()},
        }
    ).encode()
    result = dict(inspect_payload(payload, slant_mode=slant_mode, include_triggers=include_triggers))
    result["source_kind"] = "page"
    result["revision"] = content_hash(project_dir, page_id, dialogue_mode, slant_mode, str(include_triggers))
    return result


def import_hash(filename: str, options: dict) -> str:
    try:
        payload = import_payload(filename)
    except (OSError, ValueError, ImportError):
        payload = filename.encode()
    return hashlib.sha256(payload + dumps(options).encode()).hexdigest()


def materialize(filename: str, *, convert_moss: bool = False, width: int = 1024, height: int = 1536) -> tuple:
    with _WORKSPACE_LOCK:
        return _materialize(filename, convert_moss=convert_moss, width=width, height=height)


def _materialize(filename: str, *, convert_moss: bool, width: int, height: int) -> tuple:
    root = workspace_root(filename)
    existing = workspace_bundle(filename)
    if existing is not None:
        return root, existing["page"]["id"]
    if root.exists():
        msg = "同名目录已存在且不是本分镜的工作副本，请重命名文件后重新导入"
        raise ValueError(msg)
    raw = decode_json(file_path(filename).read_bytes())
    if "summary" in raw and "items" in raw:
        if not convert_moss:
            msg = "MOSS JSON 转换为分镜单是近似的，请确认转换后再编辑"
            raise ValueError(msg)
        width, height = moss_dimensions(raw, width, height)
        page, cards, settings = moss_page(raw, width, height), {}, {}
    else:
        page, cards, _, _ = parse_bundle(raw)
        settings = raw.get("project", {}) if raw.get("format") == BUNDLE_FORMAT else {}
    if not page.id:
        page.page_id = "imported"
    destination = page_path(root, page.id)
    card_paths = {key: page_path(root, key) for key in cards}  # validate ids before writing anything
    io = core("io")
    project = core("models").Project.from_dict(
        {
            **settings,
            "default_canvas_width": page.width,
            "default_canvas_height": page.height,
            "reading_direction": page.reading_direction,
        }
    )
    io.write_json(inside(root, "project.json"), project)
    io.write_json(destination, page)
    for key, card in cards.items():
        io.write_json(inside(root, f"characters/{card_paths[key].name}"), card)
    io.write_json(inside(root, ".soda/import.json"), {"source_file": filename, "page_id": page.id})
    return root, page.id


def export_copy(filename: str) -> str:
    bundle = workspace_bundle(filename)
    if bundle is None:
        page, cards, _, _ = parse_bundle(decode_json(file_path(filename).read_bytes()))
        bundle = {
            "format": BUNDLE_FORMAT,
            "project": {},
            "page": page.to_dict(),
            "characters": {key: card.to_dict() for key, card in cards.items()},
        }
    bundle["exported_at"] = datetime.now(UTC).isoformat()
    page, cards, _, _ = parse_bundle(bundle)
    draft = draft_image(page, cards)
    draft.thumbnail((256, 256))
    bundle["sketch_png_base64"] = png_base64(draft)
    stem = Path(original_filename(filename)).stem.removesuffix(".storyboard").removesuffix(".moss")
    return store_upload(f"{stem[:60]}-edited.storyboard.json", dumps(bundle).encode(), "storyboard")
