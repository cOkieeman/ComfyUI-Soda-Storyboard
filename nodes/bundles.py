"""File-only storyboard interchange, independent of project directories."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

from .core import NEGATIVE, core, dumps, info, relative_lora, resolution

BUNDLE_FORMAT = "soda-storyboard-bundle-v1"
EMPTY_FILE = "上传或拖入 .storyboard.json"
EMPTY_MOSS = "上传或拖入 .moss.json"
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_SKETCH_BYTES = 2 * 1024 * 1024
MAX_SKETCH_PIXELS = 4_000_000
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
    if not encoded:
        return ""
    if not isinstance(encoded, str) or len(encoded) > MAX_SKETCH_BYTES * 2:
        msg = "草稿缩略图无效或超过大小限制"
        raise ValueError(msg)
    try:
        payload = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(payload)) as source:
            _check_sketch(source, len(payload))
            source.thumbnail((512, 512))
            output = io.BytesIO()
            source.convert("RGB").save(output, format="PNG")
            return base64.b64encode(output.getvalue()).decode("ascii")
    except (OSError, ValueError, binascii.Error, Image.DecompressionBombError) as exc:
        msg = f"草稿缩略图损坏：{exc}"
        raise ValueError(msg) from exc


def _check_sketch(source: Image.Image, byte_count: int) -> None:
    if (
        byte_count > MAX_SKETCH_BYTES
        or source.format != "PNG"
        or source.width * source.height > MAX_SKETCH_PIXELS
    ):
        msg = "草稿缩略图必须为不超过 2 MiB、400 万像素的 PNG"
        raise ValueError(msg)


def page_defaults(raw: dict, settings: dict) -> dict:
    project = core("models").Project.from_dict(settings)
    defaults = {
        "canvas_width": project.default_canvas_width,
        "canvas_height": project.default_canvas_height,
        "reading_direction": project.reading_direction,
        "style_prefix": project.default_style_prefix,
        "dialogue_mode": project.default_dialogue_mode,
        "text_direction": project.text_direction,
        "color_mode": project.color_mode,
        "style_prompt": project.style_prompt,
        "tags": project.tags,
    }
    # Respect page aliases too: a page's explicit canvas/style/direction wins.
    aliases = {
        "canvas_width": ("width", "canvas", "canvas_size"),
        "canvas_height": ("height", "canvas", "canvas_size"),
        "reading_direction": ("direction",),
        "style_prefix": ("style",),
        "dialogue_mode": ("lettering_mode",),
    }
    result = dict(raw)
    for key, value in defaults.items():
        if key not in result and not any(alias in result for alias in aliases.get(key, ())):
            result[key] = value
    if not result.get("style_prompt"):
        result["style_prompt"] = project.style_prompt
    if not result.get("style_prefix") and not result.get("style"):
        result["style_prefix"] = project.default_style_prefix
    return result


def parse_bundle(value: dict, dialogue_mode: str = "跟随页面") -> tuple[Any, dict, list[str], str]:
    models = core("models")
    if value.get("format") == BUNDLE_FORMAT:
        page, settings, characters = value.get("page"), value.get("project", {}), value.get("characters", {})
        sketch = value.get("sketch_png_base64", "")
    elif "panels" in value and value.get("format", "soda-storyboard-page-v1") in {
        "soda-storyboard-page-v1",
        "soda-storyboard/v1",
        "",
    }:
        page, settings, characters, sketch = value, {}, {}, ""
    else:
        msg = "不是 soda-storyboard-bundle-v1 分镜包或单独分镜单"
        raise ValueError(msg)
    if not isinstance(page, dict) or not isinstance(settings, dict) or not isinstance(characters, dict):
        msg = "分镜包的 page、project、characters 必须是对象"
        raise TypeError(msg)
    page = models.Page.from_dict(page_defaults(page, settings))
    cards = {key: models.Character.from_dict(card) for key, card in characters.items()}
    if any(key != card.id for key, card in cards.items()):
        msg = "分镜包的角色 id 必须与角色卡 id 一致"
        raise ValueError(msg)
    modes = {"跟随页面": None, "MOSS 画字": "moss_text", "程序排字": "lettering"}
    if dialogue_mode not in modes:
        msg = "未知台词模式"
        raise ValueError(msg)
    if modes[dialogue_mode]:
        page.dialogue_mode = modes[dialogue_mode]
    report = core("validation").validate_page(page, cards).to_dict()
    if report["errors"]:
        msg = "分镜页校验失败：\n" + "\n".join(error["message"] for error in report["errors"])
        raise ValueError(msg)
    warnings = [] if cards else [MISSING_CHARACTERS]
    return page, cards, warnings, sketch_thumbnail(sketch)


def read_bundle(filename: str, dialogue_mode: str = "跟随页面") -> tuple:
    path = file_path(filename)
    if path.stat().st_size > MAX_FILE_BYTES:
        msg = "分镜文件不能超过 16 MiB"
        raise ValueError(msg)
    return parse_bundle(decode_json(path.read_bytes()), dialogue_mode)


def compile_result(
    page: Any, characters: dict, slant_mode: str = "cut", *, include_triggers: bool = True
) -> tuple:
    generation_page, generation_cards = copy.deepcopy(page), copy.deepcopy(characters)
    compiler = core("compiler")
    if not include_triggers:
        for card in generation_cards.values():
            card.trigger_words = []
    for panel in generation_page.panels:
        if panel.caption_en:
            ids = list(dict.fromkeys([*panel.character_ids, *(f.character_id for f in panel.figures)]))
            details = "; ".join(compiler.character_caption(key, generation_cards) for key in ids)
            if details:
                panel.caption_en = f"{panel.caption_en}. {details}"
    compiled = compiler.compile_page(generation_page, generation_cards, slant_mode=slant_mode)
    lora = core("production.api").select_lora(page, characters) or {}
    width, height = page.canvas_size
    return (
        dumps(compiled),
        width,
        height,
        resolution(width, height),
        relative_lora(lora.get("path", "")),
        float(lora.get("strength", 0.0)),
        NEGATIVE,
        info(page, generation_cards),
    )


def describe(page: Any, characters: dict, warnings: list[str], sketch: str = "") -> dict:
    chosen = core("production.api").select_lora(page, characters) or {}
    texts = core("lettering").page_texts(page)
    dialogue_count = sum(t.kind == "dialogue" for t in texts)
    main = chosen.get("character_id", "无主角 LoRA")
    summary = (
        f"{page.canvas_width}×{page.canvas_height} · {len(page.panels)} 格 · {dialogue_count} 句台词 · "
        f"建议：{main} LoRA {chosen.get('path', '无')} 强度 {chosen.get('strength', 0)}"
    )
    appearing = {key for p in page.panels for key in [*p.character_ids, *(f.character_id for f in p.figures)]}
    appearing.update(o.character_id for o in page.overlays)
    warnings = list(warnings)
    if sum(bool(card.lora) for key, card in characters.items() if key in appearing) > 1:
        warnings.append("建议一次只加载一个角色 LoRA")
    return {
        "summary": summary,
        "warnings": warnings,
        "sketch_png_base64": sketch,
        "page_info": info(page, characters),
        "panel_count": len(page.panels),
        "dialogue_count": dialogue_count,
        "lora": chosen,
        "panels": [{"id": p.id, "order": p.order} for p in sorted(page.panels, key=lambda p: p.order)],
        "characters": list(characters),
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
    return name
