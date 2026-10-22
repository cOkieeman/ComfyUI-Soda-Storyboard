from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from soda_storyboard.io import write_json

if TYPE_CHECKING:
    from types import ModuleType


@pytest.fixture(scope="session")
def plugin() -> ModuleType:
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "soda_comfy", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path: Path) -> Path:
    write_json(tmp_path / "project.json", {"id": "demo", "title": "Demo"})
    for identifier in ("a", "b"):
        write_json(
            tmp_path / "characters" / f"{identifier}.json",
            {
                "id": identifier,
                "display_name": identifier,
                "appearance_en": "a young traveler",
                "appearance_zh": "年轻的旅人",
                "trigger_words": [f"person_{identifier}"],
                "lora": {"path": f"characters/{identifier}.safetensors", "strength": 0.8},
            },
        )
    write_json(
        tmp_path / "pages/p1.json",
        {
            "id": "p1",
            "canvas_width": 320,
            "canvas_height": 240,
            "dialogue_mode": "moss_text",
            "panels": [
                {
                    "id": "left",
                    "order": 2,
                    "caption_en": "Two travelers walking beside a river",
                    "shape": {"type": "quad", "points": [[16, 16], [144, 32], [144, 224], [16, 224]]},
                    "character_ids": ["a", "b"],
                    "figures": [
                        {"character_id": "a", "bbox": {"x": 30, "y": 60, "w": 35, "h": 120}},
                        {"character_id": "b", "bbox": {"x": 90, "y": 60, "w": 35, "h": 120}},
                    ],
                },
                {
                    "id": "right",
                    "order": 1,
                    "caption_en": "A traveler rests under a tree",
                    "shape": {"type": "rect", "x": 176, "y": 16, "w": 128, "h": 208},
                    "character_ids": ["a"],
                    "figures": [{"character_id": "a", "position": "center"}],
                },
            ],
        },
    )
    return tmp_path


@pytest.fixture
def page_info(plugin: ModuleType, project: Path) -> str:
    result = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardPage"]().execute(str(project), "p1")
    assert isinstance(json.loads(result[-1]), dict)
    return result[-1]
