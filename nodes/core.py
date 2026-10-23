"""Small adapters around the public soda-storyboard API."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any

INSTALL = "请先安装 soda-storyboard：pip install -r requirements.txt（在本节点包目录运行）"
NEGATIVE = "low quality, blurry, bad anatomy, extra limbs, watermark, signature, rough sketch lines"
FIRST_PRINTABLE = 32
type JSON = dict[str, Any]


def core(module: str) -> Any:
    try:
        return importlib.import_module(f"soda_storyboard.{module}")
    except ImportError as exc:
        raise RuntimeError(INSTALL) from exc


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def project_root(directory: str) -> Path:
    if not directory.strip():
        msg = "请填写分镜项目目录"
        raise ValueError(msg)
    root = Path(directory).expanduser().resolve(strict=True)
    if not root.is_dir():
        msg = "分镜项目目录必须是文件夹"
        raise ValueError(msg)
    return root


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        msg = "路径不能超出分镜项目目录"
        raise ValueError(msg)
    return path


def page_path(root: Path, page_id: str) -> Path:
    if not page_id or page_id in {".", ".."} or any(c in page_id for c in "/\\:"):
        msg = "页面 id 无效，请填写 pages 目录内的文件名（不含 .json）"
        raise ValueError(msg)
    return inside(root, f"pages/{page_id}.json")


def editable_id(identifier: str) -> str:
    """Match the core editor and reject Windows device/control names before writes."""
    if (
        not identifier
        or identifier != identifier.strip()
        or any(c in identifier for c in '/\\:.\x00?*<>|"')
        or any(ord(c) < FIRST_PRINTABLE for c in identifier)
        or re.fullmatch(
            r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]", identifier, re.IGNORECASE
        )
    ):
        raise ValueError(f"编辑副本 id 无效：{identifier!r}；不能包含点号、路径字符或 Windows 保留名")
    return identifier


def generation_canvas(width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width % 16 or height % 16:
        raise ValueError(f"生成画布宽高必须是 16 的正整数倍（当前 {width}×{height}），请先调整分镜画布和几何")


def content_hash(project_dir: str, page_id: str, *options: str) -> str:
    root = project_root(project_dir)
    paths = [page_path(root, page_id)]
    if inside(root, "project.json").is_file():
        paths.append(inside(root, "project.json"))
    directory = inside(root, "characters")
    paths.extend(sorted(directory.glob("*.json")))
    digest = hashlib.sha256(dumps(options).encode())
    for path in paths:
        safe = inside(root, path.relative_to(root).as_posix())
        digest.update(safe.relative_to(root).as_posix().encode())
        digest.update(safe.read_bytes())
    return digest.hexdigest()


def load(project_dir: str, page_id: str, dialogue_mode: str = "跟随页面") -> tuple[Any, dict]:
    io = core("io")
    root = project_root(project_dir)
    project_file = inside(root, "project.json")
    character_dir = inside(root, "characters")
    for path in character_dir.glob("*.json"):
        inside(root, path.relative_to(root).as_posix())
    characters = io.load_characters(character_dir)
    page, characters, _, _ = core("bundle").load_bundle(
        {
            "format": "soda-storyboard-bundle-v1",
            "page": io.read_json(page_path(root, page_id)),
            "project": io.read_json(project_file) if project_file.is_file() else {},
            "characters": {key: card.to_dict() for key, card in characters.items()},
        }
    )
    mode = dialogue_override(dialogue_mode)
    if mode:
        page.dialogue_mode = mode
    return page, characters


def dialogue_override(dialogue_mode: str) -> str | None:
    modes = {"跟随页面": None, "MOSS 画字": "moss_text", "程序排字": "lettering"}
    if dialogue_mode not in modes:
        msg = "未知台词模式"
        raise ValueError(msg)
    return modes[dialogue_mode]


def info(page: Any, characters: dict) -> str:
    return dumps(
        {
            "version": 1,
            "page": page.to_dict(),
            "project": {"lora_policy": page.lora_policy},
            "characters": {k: v.to_dict() for k, v in characters.items()},
        }
    )


def parse_info(page_info: str) -> tuple[Any, dict]:
    models = core("models")
    value = json.loads(page_info)
    if not isinstance(value, dict) or value.get("version") != 1 or "page" not in value:
        msg = "page_info 无效，请连接载入分镜页的 page_info 输出"
        raise ValueError(msg)
    page_data = {
        **value["page"],
        "lora_policy": value.get("project", {}).get(
            "lora_policy", value["page"].get("lora_policy", "single")
        ),
    }
    return models.Page.from_dict(page_data), {
        k: models.Character.from_dict(v) for k, v in value.get("characters", {}).items()
    }


def resolution(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        msg = "宽高必须大于 0"
        raise ValueError(msg)
    return dumps({"version": 1, "width": width, "height": height})


def select_panel(page: Any, selector: str) -> Any:
    panels = sorted(page.panels, key=lambda p: p.order)
    for panel in panels:
        if panel.id == selector:
            return panel
    if selector.isdecimal() and 1 <= int(selector) <= len(panels):
        return panels[int(selector) - 1]
    msg = f"找不到格子 {selector}，请填写格子 id 或从 1 开始的阅读顺序编号"
    raise ValueError(msg)


def single_prompt(panel: Any, characters: dict, page: Any = None) -> str:
    if page is None:
        page = core("models").Page.from_dict({"id": "single", "panels": [panel.to_dict()]})
    captions = core("captions")
    caption = captions.panel_caption(panel, page, characters)
    # Strip only the compiler-owned page location. Keep custom and preserved text verbatim.
    if not captions.custom_caption_enabled(panel, page) and captions.preserved_caption(panel, page) is None:
        for language, separator in (("en", ": "), ("zh", "：")):
            position = core("panel_positions").panel_positions(page, language).get(panel.id)
            if position:
                caption = caption.removeprefix(position + separator)
    return (
        "A single manga illustration, one frame, no panel borders, "
        f"no gutters, no text, no speech bubbles. {caption}"
    )


def relative_lora(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or PureWindowsPath(path).drive or ".." in normalized.split("/"):
        msg = "角色卡 LoRA 路径必须相对于 ComfyUI models/loras，不能使用绝对路径或 .."
        raise ValueError(msg)
    return normalized.replace("/", os.sep)
