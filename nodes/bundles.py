"""File-only storyboard interchange, independent of project directories."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

from .core import NEGATIVE, core, dialogue_override, dumps, info, inside, relative_lora, resolution

BUNDLE_FORMAT = "soda-storyboard-bundle-v1"
EMPTY_FILE = "上传或拖入 .storyboard.json"
EMPTY_MOSS = "上传或拖入 .moss.json"
MAX_FILE_BYTES = 16 * 1024 * 1024
MISSING_CHARACTERS = "未包含角色卡，LoRA 和外观描述缺失"


def input_directory() -> Path:
    folders = importlib.import_module("folder_paths")
    root = Path(folders.get_input_directory()).resolve()
    directory = (root / "soda-storyboard").resolve()
    if not directory.is_relative_to(root):
        msg = "分镜上传目录不能超出 ComfyUI input 目录"
        raise ValueError(msg)
    return directory


def file_path(filename: str) -> Path:
    if not filename or filename in {EMPTY_FILE, EMPTY_MOSS}:
        msg = "请先导入分镜包" if filename != EMPTY_MOSS else "请先导入 MOSS JSON 或粘贴文本"
        raise ValueError(msg)
    if any(c in filename for c in "/\\:\x00") or filename in {".", ".."}:
        msg = "上传文件名无效"
        raise ValueError(msg)
    root = input_directory()
    path = (root / filename).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != ".json":
        msg = "请选择上传目录内的 JSON 文件"
        raise ValueError(msg)
    return path


def decode_json(payload: bytes) -> dict:
    if len(payload) > MAX_FILE_BYTES:
        msg = "分镜文件不能超过 16 MiB"
        raise ValueError(msg)
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        msg = "分镜文件损坏，无法读取 UTF-8 JSON"
        raise ValueError(msg) from exc
    if not isinstance(value, dict):
        msg = "分镜文件必须包含 JSON 对象"
        raise TypeError(msg)
    return value


def sketch_thumbnail(encoded: str) -> str:
    """Resize a PNG already validated by the core load_bundle boundary."""
    if not encoded:
        return ""
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as source:
        source.thumbnail((512, 512))
        output = io.BytesIO()
        source.convert("RGB").save(output, format="PNG")
        return base64.b64encode(output.getvalue()).decode("ascii")


def parse_bundle(value: dict, dialogue_mode: str = "跟随页面") -> tuple[Any, dict, list[str], str]:
    page, cards, _, warnings = core("bundle").load_bundle(value)
    mode = dialogue_override(dialogue_mode)
    if mode:
        page.dialogue_mode = mode
    sketch = value.get("sketch_png_base64", "") if value.get("format") == BUNDLE_FORMAT else ""
    return page, cards, warnings, sketch_thumbnail(sketch)


def read_bundle(filename: str, dialogue_mode: str = "跟随页面") -> tuple:
    path = file_path(filename)
    if path.stat().st_size > MAX_FILE_BYTES:
        msg = "分镜文件不能超过 16 MiB"
        raise ValueError(msg)
    return parse_bundle(decode_json(path.read_bytes()), dialogue_mode)


def compile_page_bundle(
    page: Any, characters: dict, slant_mode: str = "cut", *, include_triggers: bool = True
) -> dict:
    return core("bundle").compile_bundle(
        {
            "format": BUNDLE_FORMAT,
            "page": page.to_dict(),
            "characters": {key: card.to_dict() for key, card in characters.items()},
        }
        if characters
        else page.to_dict(),
        slant_mode=slant_mode,
        include_triggers=include_triggers,
    )


def comfy_lora(compiled: dict, characters: dict) -> dict:
    """Keep Comfy model subdirectories; selection belongs to compile_bundle."""
    chosen = dict(compiled.get("lora") or {})
    if chosen:
        card = characters[chosen["character_id"]]
        chosen["path"] = relative_lora(card.lora.path)
    return chosen


def result_outputs(page: Any, characters: dict, compiled: dict, *, include_triggers: bool = True) -> tuple:
    chosen = comfy_lora(compiled, characters)
    width, height = compiled["width"], compiled["height"]
    cards = (
        characters
        if include_triggers
        else {
            key: core("models").Character.from_dict({**card.to_dict(), "trigger_words": []})
            for key, card in characters.items()
        }
    )
    return (
        dumps(compiled["moss"]),
        width,
        height,
        resolution(width, height),
        chosen.get("path", ""),
        float(chosen.get("strength", 0.0)),
        NEGATIVE,
        info(page, cards),
    )


def compile_result(
    page: Any, characters: dict, slant_mode: str = "cut", *, include_triggers: bool = True
) -> tuple:
    compiled = compile_page_bundle(page, characters, slant_mode, include_triggers=include_triggers)
    return result_outputs(page, characters, compiled, include_triggers=include_triggers)


def translation_status(warnings: list[str]) -> dict:
    # compile_bundle currently exposes strings, not validation issue codes.
    # Ignore its aggregate TODO warning; only per-panel warnings carry status.
    states = {}
    for warning in warnings:
        match = re.match(r"第 (\d+) 格英文译文(缺失|已过期)，", warning)
        if match:
            states[match[1]] = "missing" if match[2] == "缺失" else "stale"
    return {
        "state": "stale" if "stale" in states.values() else "missing" if states else "fresh",
        "panels": states,
    }


def describe(
    page: Any, characters: dict, warnings: list[str], sketch: str = "", *, compiled: dict | None = None
) -> dict:
    chosen = comfy_lora(compiled or {}, characters)
    texts = core("lettering").page_texts(page)
    dialogue_count = sum(t.kind == "dialogue" for t in texts)
    summary = f"{page.canvas_width}×{page.canvas_height} · {len(page.panels)} 格 · {dialogue_count} 句台词"
    names = {key: card.display_name or key for key, card in characters.items()}
    if chosen:
        chosen["path"] = relative_lora(chosen["path"])
        chosen["display_name"] = names.get(chosen["character_id"], chosen["character_id"])
        chosen["filename"] = Path(chosen["path"]).name
        chosen["name"] = Path(chosen["path"]).stem
        summary += f" · 建议：{chosen['display_name']} LoRA {chosen['strength']:g}"
    appearing = {key for p in page.panels for key in [*p.character_ids, *(f.character_id for f in p.figures)]}
    appearing.update(o.character_id for o in page.overlays)
    warnings = list(warnings)
    if sum(bool(card.lora) for key, card in characters.items() if key in appearing) > 1:
        warnings.append("建议一次只加载一个角色 LoRA")
    return {
        "summary": summary,
        "warnings": warnings,
        "translation_status": translation_status(compiled["warnings"]) if compiled is not None else None,
        "sketch_png_base64": sketch,
        "page_info": info(page, characters),
        "panel_count": len(page.panels),
        "dialogue_count": dialogue_count,
        "lora": chosen,
        "title": str(page.extra.get("title") or page.id),
        "page_id": page.id,
        "reading_direction": page.reading_direction,
        "panels": [
            {**p.to_dict(), "texts": [t.to_dict() for t in texts if t.panel_id == p.id]}
            for p in sorted(page.panels, key=lambda p: p.order)
        ],
        "texts": [t.to_dict() for t in texts],
        "characters": list(characters),
        "character_names": names,
    }


def validate_moss(value: dict) -> dict:
    if not isinstance(value.get("summary"), dict) or not isinstance(value.get("items"), list):
        msg = "MOSS JSON 必须包含 summary 对象和 items 数组"
        raise TypeError(msg)
    return value


def list_files(kind: str) -> list[str]:
    try:
        root = input_directory()
    except ImportError:
        return []
    result = []
    for path in sorted(root.glob("*.json")):
        try:
            safe = file_path(path.name)
            if safe.stat().st_size > MAX_FILE_BYTES:
                continue
            value = decode_json(safe.read_bytes())
            is_moss = "summary" in value and "items" in value
            if (kind == "moss" and is_moss) or (
                kind == "storyboard"
                and (value.get("format") == BUNDLE_FORMAT or "panels" in value or is_moss)
            ):
                result.append(path.name)
        except (OSError, ValueError, TypeError):
            continue
    return result


def store_upload(filename: str, payload: bytes, kind: str) -> str:
    if kind not in {"storyboard", "moss"}:
        msg = "未知上传类型"
        raise ValueError(msg)
    if not filename.lower().endswith(".json") or any(c in filename for c in "/\\:\x00"):
        msg = "请上传不含目录的 .json 文件"
        raise ValueError(msg)
    value = decode_json(payload)
    if kind == "storyboard":
        if "summary" in value and "items" in value:
            validate_moss(value)
        else:
            parse_bundle(value)
    else:
        validate_moss(value)
    suffix = ".storyboard.json" if kind == "storyboard" else ".moss.json"
    # Content addressing avoids silently overwriting a previously imported copy.
    name = f"{Path(filename).stem[:80]}-{hashlib.sha256(payload).hexdigest()[:16]}{suffix}"
    path = file_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            msg = "文件名冲突，请重命名后重试"
            raise ValueError(msg) from None
    metadata_path = upload_metadata_path(name)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the exact original even when the content-addressed name is truncated.
    try:
        with metadata_path.open("x", encoding="utf-8") as handle:
            handle.write(dumps({"original_filename": filename}))
    except FileExistsError:
        pass
    return name


def upload_metadata_path(filename: str) -> Path:
    file_path(filename)
    return inside(input_directory(), f".soda/uploads/{filename}.json")


def original_filename(filename: str) -> str:
    source = file_path(filename)
    metadata_path = upload_metadata_path(filename)
    if metadata_path.is_file():
        metadata = decode_json(metadata_path.read_bytes())
        original = metadata.get("original_filename", "")
        if isinstance(original, str) and original and not any(c in original for c in "/\\:\x00"):
            return original
    # Legacy uploads have no filename metadata; verify the known upload suffix.
    match = re.fullmatch(r"(.+)-([0-9a-f]{16})\.(?:storyboard|moss)\.json", filename)
    if match and source.stat().st_size <= MAX_FILE_BYTES:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        if digest == match[2]:
            return f"{match[1]}.json"
    return filename
