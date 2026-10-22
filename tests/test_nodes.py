from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageChops
from soda_storyboard.bundle import compile_bundle
from soda_storyboard.io import load_characters, write_json
from soda_storyboard.models import Page

if TYPE_CHECKING:
    from types import ModuleType


def test_registration(plugin: ModuleType) -> None:
    assert len(plugin.NODE_CLASS_MAPPINGS) == 11
    assert plugin.WEB_DIRECTORY == "./web"
    assert plugin.NODE_CLASS_MAPPINGS.keys() == plugin.NODE_DISPLAY_NAME_MAPPINGS.keys()
    for cls in plugin.NODE_CLASS_MAPPINGS.values():
        assert cls.CATEGORY == "Soda Storyboard"
        assert callable(getattr(cls(), cls.FUNCTION))
        assert cls.INPUT_TYPES()["required"]


@pytest.mark.parametrize("slant", ["cut", "hint"])
def test_compile_contract(plugin: ModuleType, project: Path, slant: str) -> None:
    result = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardPage"]().execute(
        str(project), "p1", slant_mode=slant
    )
    expected = compile_bundle(
        {
            "format": "soda-storyboard-bundle-v1",
            "project": json.loads((project / "project.json").read_text(encoding="utf-8")),
            "page": json.loads((project / "pages/p1.json").read_text(encoding="utf-8")),
            "characters": {
                key: card.to_dict() for key, card in load_characters(project / "characters").items()
            },
        },
        slant_mode=slant,
    )["moss"]
    actual = json.loads(result[0])
    assert actual == expected
    assert result[1:3] == (320, 240)
    assert json.loads(result[3]) == {"version": 1, "width": 320, "height": 240}
    assert result[4:6] == (str(Path("characters") / "a.safetensors"), 0.8)
    assert all(isinstance(result[i], str) for i in (0, 3, 4, 6, 7))


def test_override_and_validation(plugin: ModuleType, project: Path) -> None:
    node = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardPage"]()
    result = node.execute(str(project), "p1", "程序排字")
    assert json.loads(result[-1])["page"]["dialogue_mode"] == "lettering"
    value = json.loads((project / "pages/p1.json").read_text(encoding="utf-8"))
    value["canvas_width"] = -1
    write_json(project / "pages/p1.json", value)
    with pytest.raises(ValueError, match="分镜页校验失败"):
        node.execute(str(project), "p1")


def test_hash_content_not_timestamp(plugin: ModuleType, project: Path) -> None:
    node = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardPage"]
    before = node.IS_CHANGED(str(project), "p1")
    target = project / "pages/p1.json"
    target.write_bytes(target.read_bytes() + b" ")
    changed = node.IS_CHANGED(str(project), "p1")
    assert changed != before
    target = project / "characters/a.json"
    target.write_bytes(target.read_bytes() + b" ")
    assert node.IS_CHANGED(str(project), "p1") != changed
    assert node.IS_CHANGED(str(project), "p1", slant_mode="hint") != node.IS_CHANGED(str(project), "p1")


def test_moss_file_and_text(plugin: ModuleType, tmp_path: Path) -> None:
    node = plugin.NODE_CLASS_MAPPINGS["SodaLoadMossJSON"]()
    value = {"summary": {"caption": "test"}, "items": []}
    path = tmp_path / "page.moss.json"
    write_json(path, value)
    assert node.execute(str(path), 320, 240) == node.execute(json.dumps(value), 320, 240)
    before = node.IS_CHANGED(str(path), 320, 240)
    value["items"] = [{"label": "object", "caption": "tree"}]
    write_json(path, value)
    assert node.IS_CHANGED(str(path), 320, 240) != before
    with pytest.raises(ValueError, match="宽高"):
        node.execute(json.dumps(value), 0, 240)


def test_missing_core_has_actionable_error(plugin: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    real_import = importlib.import_module

    def missing(name: str, package: str | None = None) -> ModuleType:
        if name.startswith("soda_storyboard"):
            raise ModuleNotFoundError(name)
        return real_import(name, package)

    monkeypatch.setattr(adapter.importlib, "import_module", missing)
    assert len(plugin.NODE_CLASS_MAPPINGS) == 11
    with pytest.raises(RuntimeError, match=r"请先安装 soda-storyboard.*pip install"):
        plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardPage"]().execute("unused", "p1")


def test_import_without_core(plugin: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins  # noqa: PLC0415 -- isolate the import guard to this test
    import sys  # noqa: PLC0415 -- only needed while loading an independent package

    original = builtins.__import__

    def guarded(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("soda_storyboard"):
            raise ModuleNotFoundError(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    spec = importlib.util.spec_from_file_location("soda_without_core", plugin.__file__)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert len(module.NODE_CLASS_MAPPINGS) == 11


def test_crop_paste_roundtrip(plugin: ModuleType, page_info: str) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    original = Image.new("RGB", (320, 240), "#286b9a")
    crop, mask, prompt, metadata = images.crop_panel(original, page_info, "left", resize=False)
    assert crop.size == (128, 208)
    assert mask.getpixel((127, 0)) == 0
    assert mask.getpixel((64, 100)) == 255
    assert "one frame" in prompt
    assert "no speech bubbles" in prompt
    assert "multi_panel" not in prompt
    assert "Japanese manga layout" not in prompt
    result = images.paste_panel(original, crop, json.loads(metadata), protect_text=True)
    assert ImageChops.difference(result, original).getbbox() is None
    patch = Image.new("RGB", crop.size, "red")
    result = images.paste_panel(original, patch, json.loads(metadata), protect_text=False)
    assert result.crop((160, 0, 320, 240)).tobytes() == original.crop((160, 0, 320, 240)).tobytes()
    assert result.getpixel((143, 16)) == original.getpixel((143, 16))
    assert result.getpixel((60, 100)) == (255, 0, 0)
    resized = images.crop_panel(original, page_info, "1", resize=True)[0]
    assert max(resized.size) == 1024
    assert all(v % 16 == 0 for v in resized.size)


def test_character_mask_excludes_other(plugin: ModuleType, page_info: str) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    crop = Image.new("RGB", (128, 208))
    mask = images.character_mask(crop, page_info, "left", "a", 50, 16, "格子")
    assert mask.getpixel((30, 100)) > 0
    assert mask.getpixel((90, 100)) == 0
    assert mask.getpixel((127, 0)) == 0
    full = images.character_mask(Image.new("RGB", (320, 240)), page_info, "left", "a", 50, 16, "整页")
    assert full.size == (320, 240)
    assert full.getpixel((106, 116)) == 0
    assert full.getpixel((46, 116)) > 0


def test_cut_quads_preserves_neighbor(plugin: ModuleType, page_info: str) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    original = Image.new("RGB", (320, 240), "red")
    result = images.cut_quads(original, page_info, 12, 3)
    assert result.getpixel((20, 20)) == (255, 255, 255)
    assert result.getpixel((70, 120)) == (255, 0, 0)
    assert result.getpixel((200, 120)) == (255, 0, 0)


def test_cut_overlapping_bounds_do_not_erase_neighbor(plugin: ModuleType) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    page = Page.from_dict(
        {
            "id": "diagonal",
            "canvas_width": 208,
            "canvas_height": 112,
            "panels": [
                {
                    "id": "a",
                    "order": 1,
                    "shape": {"type": "quad", "points": [[0, 0], [100, 0], [40, 100], [0, 100]]},
                },
                {
                    "id": "b",
                    "order": 2,
                    "shape": {"type": "quad", "points": [[110, 0], [200, 0], [200, 100], [50, 100]]},
                },
            ],
        }
    )
    result = images.cut_quads(Image.new("RGB", page.canvas_size, "red"), adapter.info(page, {}), 2, 1)
    assert result.getpixel((80, 80)) == (255, 0, 0)
    assert result.getpixel((55, 80)) == (255, 255, 255)


def test_preserve_text_and_lettering(plugin: ModuleType, page_info: str) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    page, characters = adapter.parse_info(page_info)
    value = page.to_dict()
    value["texts"] = [{"id": "t", "text": "Hi", "bbox": {"x": 200, "y": 50, "w": 48, "h": 60}}]
    page = Page.from_dict(value)
    updated = adapter.info(page, characters)
    original = Image.new("RGB", (320, 240), "blue")
    crop, _, _, metadata = images.crop_panel(original, updated, "right", resize=False)
    patch = Image.new("RGB", crop.size, "red")
    result = images.paste_panel(original, patch, json.loads(metadata), protect_text=True)
    assert result.getpixel((210, 60)) == (0, 0, 255)
    assert result.getpixel((270, 120)) == (255, 0, 0)
    editable = images.paste_edit_mask(page, page.panels[1], protect_text=True)
    assert editable.getpixel((210, 60)) == 0
    assert editable.getpixel((270, 120)) == 255
    lettering = adapter.core("production.lettering")
    assert lettering.letter_image(original, page).tobytes() == original.tobytes()
    page.dialogue_mode = "lettering"
    assert lettering.letter_image(original, page).tobytes() != original.tobytes()


def test_unsafe_paths_rejected(plugin: ModuleType, project: Path) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    for identifier in ("../p1", "..", "x\\p1", "C:p1"):
        with pytest.raises(ValueError, match="id 无效"):
            adapter.page_path(project, identifier)
    for path in ("/models/a", "C:\\models\\a", "../a.safetensors"):
        with pytest.raises(ValueError, match="LoRA 路径"):
            adapter.relative_lora(path)


@pytest.mark.parametrize("name", ["characters/actor.safetensors", "characters\\actor.safetensors"])
def test_lora_path_uses_native_separator(plugin: ModuleType, name: str) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    assert adapter.relative_lora(name) == str(Path("characters") / "actor.safetensors")
    assert adapter.relative_lora("") == ""


def test_tensor_batches(plugin: ModuleType, page_info: str) -> None:
    torch = pytest.importorskip("torch")
    pytest.importorskip("numpy")
    nodes = plugin.NODE_CLASS_MAPPINGS
    images = torch.rand(2, 240, 320, 3)
    crop, mask, prompt, box = nodes["SodaCropPanel"]().execute(
        images, page_info, "right", resize_to_1024=False
    )
    assert crop.shape == (2, 208, 128, 3)
    assert mask.shape == (2, 208, 128)
    assert isinstance(prompt, str)
    pasted = nodes["SodaPastePanel"]().execute(images, crop, box)[0]
    assert pasted.shape == images.shape
    assert torch.equal(pasted[:, :, :176], images[:, :, :176])
    assert pasted.dtype == torch.float32
    cut = nodes["SodaCutQuads"]().execute(images, page_info)[0]
    assert cut.shape == images.shape
    masks = nodes["SodaCharacterMask"]().execute(crop, page_info, "right", "a")[0]
    assert masks.shape == crop.shape[:3]
    broadcast = nodes["SodaPastePanel"]().execute(images[:1], crop, box)[0]
    assert broadcast.shape == images.shape
