from __future__ import annotations

import importlib
import json
import tempfile
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

    import pytest


def test_sketch_and_extract_batches(
    plugin: ModuleType, project: Path, page_info: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    nodes = importlib.import_module(f"{plugin.__name__}.nodes.storyboard")
    monkeypatch.setattr(tempfile, "tempdir", str(project))
    monkeypatch.setattr(nodes, "images_tensor", lambda images: images)
    result = nodes.SodaStoryboardPreview().execute(page_info=page_info)
    sketch = result["result"][0]
    assert len(sketch) == 1
    assert sketch[0].size == (320, 240)
    assert sketch[0].convert("L").getextrema()[0] < 255
    metadata = result["ui"]["soda"][0]
    assert metadata["page_id"] == "p1"
    assert metadata["panels"][0]["shape"]["type"] == "rect"
    assert metadata["moss_json"]
    assert metadata["revision"]
    reference = Image.new("RGB", (320, 240), "white")
    draw = ImageDraw.Draw(reference)
    draw.rectangle((16, 16, 144, 224), outline="black", width=4)
    draw.rectangle((176, 16, 304, 224), outline="black", width=4)
    monkeypatch.setattr(nodes, "tensor_images", lambda _: [reference, reference.copy()])
    layout_json, previews = nodes.SodaExtractLayout().execute(
        None, "rtl", save_template=True, project_dir=str(project)
    )
    layouts = json.loads(layout_json)
    assert len(layouts) == len(previews) == 2
    assert all(result["panel_count"] == 2 for result in layouts)
    templates = list((project / "templates").glob("*.json"))
    assert len(templates) == 2
    assert not list((project / "templates").glob("*.png"))
    for path in templates:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert len(value["panels"]) == 2
        assert all(0 <= panel["x"] < 1 for panel in value["panels"])
