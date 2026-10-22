from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from soda_storyboard.bundle import compile_bundle, export_bundle, load_bundle
from soda_storyboard.captions import source_hash

if TYPE_CHECKING:
    from types import ModuleType


def legacy_bundle(project: Path) -> dict:
    return {
        "format": "soda-storyboard-bundle-v1",
        "project": json.loads((project / "project.json").read_text(encoding="utf-8")),
        "page": json.loads((project / "pages/p1.json").read_text(encoding="utf-8")),
        "characters": {
            key: json.loads((project / f"characters/{key}.json").read_text(encoding="utf-8"))
            for key in ("a", "b")
        },
    }


@pytest.mark.parametrize("include_triggers", [True, False])
@pytest.mark.parametrize("dialogue_mode", ["跟随页面", "MOSS 画字", "程序排字"])
def test_real_core_export_and_legacy_bundle_match_public_compiler(
    plugin: ModuleType, project: Path, dialogue_mode: str, *, include_triggers: bool
) -> None:
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    exported = export_bundle(project / "pages/p1.json")
    for value in (legacy_bundle(project), json.loads(Path(exported["path"]).read_text(encoding="utf-8"))):
        payload = json.dumps(value).encode()
        expected = compile_bundle(
            value,
            dialogue_mode={"跟随页面": None, "MOSS 画字": "moss_text", "程序排字": "lettering"}[
                dialogue_mode
            ],
            include_triggers=include_triggers,
        )
        metadata = importing.inspect_payload(
            payload, dialogue_mode=dialogue_mode, include_triggers=include_triggers
        )
        result = metadata["result"]
        assert json.loads(result[0]) == expected["moss"]
        assert metadata["moss_json"] == result[0]
        assert result[1:3] == (expected["width"], expected["height"])
        assert expected["lora"]["filename"] == result[4].replace("\\", "/").rsplit("/", 1)[-1]
        assert result[5] == expected["lora"]["strength"]
        assert set(expected["warnings"]) <= set(metadata["warnings"])
        assert json.dumps(value).encode() == payload


@pytest.mark.parametrize("state", ["fresh", "stale", "missing"])
def test_translation_status_comes_from_compile_warnings(
    plugin: ModuleType, project: Path, state: str
) -> None:
    value = legacy_bundle(project)
    page, cards, _, _ = load_bundle(value)
    for raw, panel in zip(value["page"]["panels"], page.panels, strict=True):
        if state != "missing":
            raw["caption_auto_en"] = {
                "text": "A young traveler beside a river",
                "source_hash": source_hash(panel, page, cards) if state == "fresh" else "old",
            }
    expected = compile_bundle(value)
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    metadata = importing.inspect_payload(json.dumps(value).encode())
    assert metadata["translation_status"]["state"] == state
    if state == "fresh":
        assert metadata["translation_status"]["panels"] == {}
    else:
        assert set(metadata["translation_status"]["panels"].values()) == {state}
    assert set(expected["warnings"]) <= set(metadata["warnings"])
    assert json.loads(metadata["moss_json"]) == expected["moss"]


def test_mixed_translation_warnings_keep_both_statuses(plugin: ModuleType, project: Path) -> None:
    value = legacy_bundle(project)
    value["page"]["panels"][0]["caption_auto_en"] = {"text": "Old text", "source_hash": "old"}
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    metadata = importing.inspect_payload(json.dumps(value).encode())
    assert metadata["translation_status"] == {"state": "stale", "panels": {"2": "stale", "1": "missing"}}


def test_bare_page_overlay_uses_core_missing_card_fallback(plugin: ModuleType, project: Path) -> None:
    value = legacy_bundle(project)["page"]
    value["overlays"] = [
        {
            "id": "overlay",
            "character_id": "unknown",
            "rect": {"x": 40, "y": 40, "w": 60, "h": 100},
        }
    ]
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    metadata = importing.inspect_payload(json.dumps(value).encode())
    assert json.loads(metadata["moss_json"]) == compile_bundle(value)["moss"]


@pytest.mark.parametrize("sketch", ["bad-base64", None])
def test_bare_page_sketch_extra_is_not_parsed_as_bundle_thumbnail(
    plugin: ModuleType, project: Path, sketch: str | None
) -> None:
    value = legacy_bundle(project)["page"]
    value["sketch_png_base64"] = sketch
    bundles = importlib.import_module(f"{plugin.__name__}.nodes.bundles")
    _, _, _, thumbnail = bundles.parse_bundle(value)
    assert thumbnail == ""
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    assert (
        json.loads(importing.inspect_payload(json.dumps(value).encode())["moss_json"])
        == compile_bundle(value)["moss"]
    )
