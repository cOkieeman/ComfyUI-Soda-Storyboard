"""Small adapters around the public soda-storyboard API."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path, PureWindowsPath
from typing import Any

INSTALL = "请先安装 soda-storyboard：pip install -r requirements.txt（在本节点包目录运行）"
NEGATIVE = "low quality, blurry, bad anatomy, extra limbs, watermark, signature, rough sketch lines"
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
        {"version": 1, "page": page.to_dict(), "characters": {k: v.to_dict() for k, v in characters.items()}}
    )


def parse_info(page_info: str) -> tuple[Any, dict]:
    models = core("models")
    value = json.loads(page_info)
    if not isinstance(value, dict) or value.get("version") != 1 or "page" not in value:
        msg = "page_info 无效，请连接载入分镜页的 page_info 输出"
        raise ValueError(msg)
    return models.Page.from_dict(value["page"]), {
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


def single_prompt(panel: Any, characters: dict) -> str:
    compiler = core("compiler")
    caption = (panel.caption_en or "").strip()
    if not caption:
        description = panel.description.strip()
        if not description:
            msg = f"格子 {panel.id} 缺少画面描述，请填写 caption_en 或 description"
            raise ValueError(msg)
        shot = compiler.SHOT_PHRASES.get(panel.shot, panel.shot.replace("_", "-"))
        angle = compiler.ANGLE_PHRASES.get(panel.angle, panel.angle.replace("_", "-"))
        caption = f"{shot}, {angle}: {description}"
    ids = list(dict.fromkeys([*panel.character_ids, *(f.character_id for f in panel.figures)]))
    return ". ".join(
        [
            (
                "A single manga illustration, one frame, no panel borders, "
                "no gutters, no text, no speech bubbles"
            ),
            caption,
            *(compiler.character_caption(identifier, characters, language="en") for identifier in ids),
        ]
    )


def relative_lora(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or PureWindowsPath(path).drive or ".." in normalized.split("/"):
        msg = "角色卡 LoRA 路径必须相对于 ComfyUI models/loras，不能使用绝对路径或 .."
        raise ValueError(msg)
    return normalized.replace("/", os.sep)
