from __future__ import annotations

import importlib
import json
import logging
import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from soda_storyboard.production.graphs import DEFAULTS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def lora_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    path = tmp_path / "actor.safetensors"
    path.touch()
    model, patched, weights = object(), object(), {"lora": object()}
    folder_paths = ModuleType("folder_paths")
    folder_paths.get_full_path = Mock(return_value=str(path))
    sd = ModuleType("comfy.sd")
    sd.load_lora_for_models = Mock(return_value=(patched, None))
    utils = ModuleType("comfy.utils")
    utils.load_torch_file = Mock(return_value=weights)
    monkeypatch.setitem(sys.modules, "folder_paths", folder_paths)
    monkeypatch.setitem(sys.modules, "comfy.sd", sd)
    monkeypatch.setitem(sys.modules, "comfy.utils", utils)
    return SimpleNamespace(
        model=model, patched=patched, weights=weights, path=path, folders=folder_paths, sd=sd, utils=utils
    )


def test_lora_loads_string_name(plugin: ModuleType, lora_runtime: SimpleNamespace) -> None:
    node = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardLoRA"]()
    result = node.execute(lora_runtime.model, "characters/actor.safetensors", 0.7)
    assert result == (lora_runtime.patched,)
    assert node.RETURN_TYPES == ("MODEL",)
    assert node.INPUT_TYPES()["required"]["lora_name"][0] == "STRING"
    lora_runtime.folders.get_full_path.assert_called_once_with(
        "loras", str(Path("characters") / "actor.safetensors")
    )
    lora_runtime.utils.load_torch_file.assert_called_once_with(str(lora_runtime.path), safe_load=True)
    lora_runtime.sd.load_lora_for_models.assert_called_once_with(
        lora_runtime.model, None, lora_runtime.weights, 0.7, 0.0
    )


@pytest.mark.parametrize("name", ["", "   "])
def test_empty_lora_is_passthrough(plugin: ModuleType, lora_runtime: SimpleNamespace, name: str) -> None:
    node = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardLoRA"]()
    assert node.execute(lora_runtime.model, name, 1.0)[0] is lora_runtime.model
    lora_runtime.folders.get_full_path.assert_not_called()
    lora_runtime.utils.load_torch_file.assert_not_called()
    lora_runtime.sd.load_lora_for_models.assert_not_called()


@pytest.mark.parametrize("missing", [None, "nonexistent.safetensors"])
def test_missing_lora_has_chinese_error(
    plugin: ModuleType, lora_runtime: SimpleNamespace, missing: str | None
) -> None:
    lora_runtime.folders.get_full_path.return_value = missing
    with pytest.raises(ValueError, match=r"找不到 LoRA.*actor\.safetensors"):
        plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardLoRA"]().execute(
            lora_runtime.model, "actor.safetensors", 1.0
        )
    lora_runtime.utils.load_torch_file.assert_not_called()
    lora_runtime.sd.load_lora_for_models.assert_not_called()


@pytest.mark.parametrize("caption", [None, "", "   "])
def test_crop_without_english_caption(plugin: ModuleType, page_info: str, caption: str | None) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    value = json.loads(page_info)
    panel = value["page"]["panels"][0]
    panel.update(caption_en=caption, description="两位旅人在河边交谈", shot="close_up", angle="low")
    crop, _, prompt, _ = images.crop_panel(
        Image.new("RGB", (320, 240)), json.dumps(value), "left", resize=False
    )
    assert crop.size == (128, 208)
    for phrase in (
        "特写",
        "仰视",
        "年轻的旅人",
        "两位旅人在河边交谈",
        "one frame",
        "no panel borders",
        "no text",
        "no speech bubbles",
    ):
        assert phrase in prompt
    assert "multi_panel" not in prompt
    assert "Panel 2" not in prompt
    assert "Top-" not in prompt


def test_caption_can_use_unicode_punctuation(plugin: ModuleType, page_info: str) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    page, characters = adapter.parse_info(page_info)
    page.panels[0].caption_en = "A traveler’s smile"
    page.panels[0].use_custom_caption = True
    assert "A traveler’s smile" in adapter.single_prompt(page.panels[0], characters)


def test_crop_without_scene_keeps_core_figure_semantics(plugin: ModuleType, page_info: str) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    page, characters = adapter.parse_info(page_info)
    page.panels[0].caption_en = ""
    page.panels[0].description = "  "
    prompt = adapter.single_prompt(page.panels[0], characters, page)
    assert "年轻的旅人" in prompt
    assert "no panel borders" in prompt


def test_mask_scope_default(plugin: ModuleType) -> None:
    schema = plugin.NODE_CLASS_MAPPINGS["SodaCharacterMask"].INPUT_TYPES()["required"]
    assert schema["scope"][1]["default"] == "格子"
    assert "整页" in schema["scope"][1]["tooltip"]


@pytest.mark.parametrize(
    ("installed", "warn"),
    [
        ("0.3.0", True),
        ("0.3.1", True),
        ("0.4.0rc1", True),
        ("0.4.0", True),
        ("0.4.1", False),
        ("0.10.0", False),
    ],
)
def test_core_version_warning(
    plugin: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    installed: str,
    *,
    warn: bool,
) -> None:
    compatibility = importlib.import_module(f"{plugin.__name__}.compatibility")
    monkeypatch.setattr(compatibility.metadata, "version", lambda _: installed)
    with caplog.at_level(logging.WARNING):
        compatibility.check_core_version()
    messages = [record.getMessage() for record in caplog.records]
    assert bool(messages) is warn
    if warn:
        assert len(messages) == 1
        assert "0.4.1" in messages[0]
        assert r".\python_embeded\python.exe" in messages[0]
        assert compatibility.CORE_REQUIREMENT in messages[0]
        assert "pip install" in messages[0]
        assert "\n" not in messages[0]


def test_missing_core_version_does_not_break_import(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    compatibility = importlib.import_module(f"{plugin.__name__}.compatibility")

    def missing(_: str) -> str:
        name = "soda-storyboard"
        raise PackageNotFoundError(name)

    monkeypatch.setattr(compatibility.metadata, "version", missing)
    compatibility.check_core_version()


def test_wheel_dependency_matches_metadata() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").strip()
    assert requirements in metadata["project"]["dependencies"]
    assert requirements == "soda-storyboard>=0.4.4"
    assert "@" not in requirements
    assert "git+" not in requirements


@pytest.mark.parametrize("filename", ["soda_storyboard_standard.json", "stretch-color.json"])
def test_workflow_uses_manual_lora_and_real_models(filename: str) -> None:
    text = (ROOT / "example_workflows" / filename).read_text(encoding="utf-8")
    graph = json.loads(text)
    nodes = graph["nodes"]
    load = next(n for n in nodes if n["type"] == "SodaLoadStoryboard")
    assert load["widgets_values"][0] == ""
    loras = [n for n in nodes if n["type"] in {"LoraLoaderModelOnly", "SodaLoadStoryboardLoRA"}]
    if filename == "soda_storyboard_standard.json":
        assert len(loras) == 1
        assert loras[0]["mode"] == 4
        assert [i["name"] for i in loras[0]["inputs"]] == ["model"]
        assert loras[0]["widgets_values"][0] == ""
    else:
        assert not loras
    unet = next(n for n in nodes if n["type"] == "UNETLoader")
    clip = next(n for n in nodes if n["type"] == "CLIPLoader")
    assert unet["widgets_values"][0] == DEFAULTS["sft"].replace("\\", "/").rsplit("/", 1)[-1]
    assert clip["widgets_values"][0] == DEFAULTS["clip"]
    assert "/" not in unet["widgets_values"][0]
    for placeholder in ("hero.safetensors", "moss_image_sft.safetensors", "qwen3.5_9b.safetensors"):
        assert placeholder not in text
