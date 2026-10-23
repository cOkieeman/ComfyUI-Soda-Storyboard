from __future__ import annotations

import importlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Self
from unittest.mock import Mock

import pytest
from PIL import Image, ImageChops, ImageDraw
from soda_storyboard.bundle import load_bundle
from soda_storyboard.captions import source_hash
from soda_storyboard.moss_roundtrip import entity_hash


@pytest.fixture
def review(project: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    folders = ModuleType("folder_paths")
    folders.get_input_directory = lambda: str(project / "input")
    monkeypatch.setitem(sys.modules, "folder_paths", folders)
    return {
        "format": "soda-storyboard-bundle-v1",
        "project": {"lora_policy": "none"},
        "page": json.loads((project / "pages/p1.json").read_text(encoding="utf-8")),
        "characters": {
            key: json.loads((project / f"characters/{key}.json").read_text(encoding="utf-8"))
            for key in ("a", "b")
        },
    }


@pytest.mark.parametrize("state", ["fresh", "stale", "legacy", "missing", "custom"])
def test_crop_caption_obeys_core_selection(plugin: ModuleType, review: dict, state: str) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    raw = review["page"]["panels"][0]
    raw.update(caption_en="OBSOLETE_RED_CAR", use_custom_caption=state == "custom", description="新蓝船")
    page, cards, _, _ = load_bundle(review)
    raw["caption_auto_en"] = (
        {
            "text": "FRESH_BLUE_BOAT",
            "format": "old" if state == "legacy" else "scene-v1",
            "source_hash": source_hash(page.panels[0], page, cards) if state == "fresh" else "old",
        }
        if state != "missing"
        else None
    )
    page, cards, _, _ = load_bundle(review)
    prompt = images.crop_panel(Image.new("RGB", (320, 240)), adapter.info(page, cards), "left", resize=False)[
        2
    ]
    assert ("OBSOLETE_RED_CAR" in prompt) == (state == "custom")
    assert ("FRESH_BLUE_BOAT" in prompt) == (state == "fresh")
    if state not in {"fresh", "custom"}:
        assert "新蓝船" in prompt
    assert "panel:" not in prompt
    assert "no panel borders" in prompt


@pytest.mark.parametrize("kind", ["bundle", "bare", "moss"])
def test_reject_non_flux_canvas(plugin: ModuleType, review: dict, kind: str) -> None:
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    review["page"].update(canvas_width=1000, canvas_height=1000)
    value = review if kind == "bundle" else review["page"]
    if kind == "moss":
        value = {"summary": {}, "items": [], "width": 1000, "height": 1000}
    with pytest.raises(ValueError, match="16"):
        importing.inspect_payload(json.dumps(value).encode())


def test_recompile_preserves_none_policy_all_paths(plugin: ModuleType, review: dict, project: Path) -> None:
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    workspaces = importlib.import_module(f"{plugin.__name__}.nodes.workspaces")
    bundles = importlib.import_module(f"{plugin.__name__}.nodes.bundles")
    (project / "project.json").write_text(json.dumps(review["project"]), encoding="utf-8")
    assert importing.inspect_payload(json.dumps(review).encode())["result"][4:6] == ("", 0.0)
    assert workspaces.inspect_link(str(project), "p1")["result"][4:6] == ("", 0.0)
    result = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardPage"]().execute(str(project), "p1")
    assert result[4:6] == ("", 0.0)
    name = bundles.store_upload("policy.json", json.dumps(review).encode(), "storyboard")
    exported = bundles.decode_json(bundles.file_path(workspaces.export_copy(name)).read_bytes())
    assert exported["project"]["lora_policy"] == "none"


def test_legacy_translation_is_never_fresh(plugin: ModuleType, review: dict) -> None:
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    for raw in review["page"]["panels"]:
        raw["caption_auto_en"] = {"text": "Legacy text", "source_hash": "old"}
    metadata = importing.inspect_payload(json.dumps(review).encode(), include_triggers=False)
    assert metadata["translation_status"] == {"state": "legacy", "panels": {"2": "legacy", "1": "legacy"}}


def test_scaled_crop_keeps_preserved_caption(plugin: ModuleType, review: dict) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    page, cards, _, _ = load_bundle(review)
    panel = page.panels[0]
    page.extra["moss_import"] = {
        "entries": [
            {
                "kind": "panel",
                "id": panel.id,
                "snapshot": entity_hash(panel.to_dict()),
                "item": {"caption": "PRESERVED_SCENE"},
            }
        ]
    }
    prompt = images.crop_panel(
        Image.new("RGB", (640, 480)), adapter.info(page, cards), panel.id, resize=False
    )[2]
    assert "PRESERVED_SCENE" in prompt


@pytest.mark.parametrize("identifier", ["p.1", "a?b", "trailing ", "CON", "aux", "COM1", "LPT9", "a\x01b"])
@pytest.mark.parametrize("entity", ["page", "character"])
def test_edit_ids_rejected_before_any_write(
    plugin: ModuleType, review: dict, identifier: str, entity: str
) -> None:
    bundles = importlib.import_module(f"{plugin.__name__}.nodes.bundles")
    workspaces = importlib.import_module(f"{plugin.__name__}.nodes.workspaces")
    if entity == "page":
        review["page"]["id"] = identifier
    else:
        review["characters"][identifier] = {**review["characters"].pop("a"), "id": identifier}
        for panel in review["page"]["panels"]:
            panel["character_ids"] = [identifier if key == "a" else key for key in panel["character_ids"]]
            for figure in panel["figures"]:
                if figure["character_id"] == "a":
                    figure["character_id"] = identifier
    name = bundles.store_upload("ids.json", json.dumps(review).encode(), "storyboard")
    with pytest.raises(ValueError, match="id"):
        workspaces.materialize(name)
    assert not workspaces.workspace_root(name).exists()


def test_upload_atomic_publication_and_metadata_repair(
    plugin: ModuleType, review: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundles = importlib.import_module(f"{plugin.__name__}.nodes.bundles")
    payload = json.dumps(review).encode()
    bundles.input_directory().mkdir(parents=True, exist_ok=True)
    original_open, original_read = Path.open, Path.read_bytes
    partial_read = threading.Event()

    class DelayedWriter:
        def __init__(self, handle: object) -> None:
            self.handle = handle

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            self.handle.close()

        def write(self, data: bytes) -> int:
            # Hold an old-style final-file writer until another request has
            # actually observed its incomplete contents (or the bounded timeout).
            partial_read.wait(timeout=1)
            return self.handle.write(data)

    def checked_open(path: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        handle = original_open(path, mode, *args, **kwargs)
        if "x" in mode and path.suffix == ".json":
            return DelayedWriter(handle)
        return handle

    def observed_read(path: Path) -> bytes:
        data = original_read(path)
        if path.name.endswith(".storyboard.json") and not data:
            partial_read.set()
        return data

    monkeypatch.setattr(Path, "open", checked_open)
    monkeypatch.setattr(Path, "read_bytes", observed_read)
    with ThreadPoolExecutor(max_workers=4) as pool:
        names = list(pool.map(lambda _: bundles.store_upload("same.json", payload, "storyboard"), range(8)))
    assert len(set(names)) == 1
    name = names[0]
    bundles.upload_metadata_path(name).write_text("{broken", encoding="utf-8")
    assert bundles.original_filename(name).endswith(".json")
    assert bundles.store_upload("same.json", payload, "storyboard") == name
    assert (
        bundles.decode_json(bundles.upload_metadata_path(name).read_bytes())["original_filename"]
        == "same.json"
    )
    assert bundles.file_path(name).read_bytes() == payload


def test_corrupt_upload_label_falls_back_and_reupload_repairs(plugin: ModuleType, review: dict) -> None:
    bundles = importlib.import_module(f"{plugin.__name__}.nodes.bundles")
    payload = json.dumps(review).encode()
    name = bundles.store_upload("label.json", payload, "storyboard")
    bundles.upload_metadata_path(name).write_text("{broken", encoding="utf-8")
    assert bundles.original_filename(name) == "label.json"
    assert bundles.store_upload("label.json", payload, "storyboard") == name
    assert bundles.decode_json(bundles.upload_metadata_path(name).read_bytes()) == {
        "original_filename": "label.json"
    }


def test_failed_upload_leaves_no_visible_file_and_can_retry(
    plugin: ModuleType, review: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundles = importlib.import_module(f"{plugin.__name__}.nodes.bundles")
    fsync = bundles.os.fsync
    monkeypatch.setattr(bundles.os, "fsync", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        bundles.store_upload("interrupted.json", json.dumps(review).encode(), "storyboard")
    assert bundles.list_files("storyboard") == []
    assert not list(bundles.input_directory().rglob(".upload-*.tmp"))
    monkeypatch.setattr(bundles.os, "fsync", fsync)
    bundles.store_upload("interrupted.json", json.dumps(review).encode(), "storyboard")
    assert len(bundles.list_files("storyboard")) == 1


@pytest.mark.parametrize("reused", [False, True])
def test_editor_state_failure_reaps_only_new_process(
    plugin: ModuleType, project: Path, monkeypatch: pytest.MonkeyPatch, *, reused: bool
) -> None:
    routes = importlib.import_module(f"{plugin.__name__}.routes")
    edit = importlib.import_module("soda_storyboard.edit")
    health = {"service": "soda-storyboard", "pid": 123, "instance_id": "test", "project_dir": str(project)}
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(edit, "health", lambda _: health if reused else {})
    monkeypatch.setattr(edit, "launch", Mock(return_value=(process, 8780, health)))
    monkeypatch.setattr(edit, "write_state", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        routes.editor_start(str(project), "p1")
    assert process.terminate.call_count == (0 if reused else 1)
    assert process.wait.call_count == (0 if reused else 1)


def test_editor_state_failure_uses_matched_interpreter_identity(
    plugin: ModuleType, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    routes = importlib.import_module(f"{plugin.__name__}.routes")
    edit = importlib.import_module("soda_storyboard.edit")
    health = {"service": "soda-storyboard", "pid": 123, "instance_id": "child", "project_dir": str(project)}
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(edit, "health", Mock(side_effect=[{}, health]))
    monkeypatch.setattr(edit, "launch", Mock(return_value=(process, 8780, health)))
    monkeypatch.setattr(edit, "write_state", Mock(side_effect=OSError("disk full")))
    kill = Mock()
    monkeypatch.setattr(edit.os, "kill", kill)
    with pytest.raises(OSError, match="disk full"):
        routes.editor_start(str(project), "p1")
    kill.assert_called_once_with(123, edit.signal.SIGTERM)
    process.terminate.assert_not_called()
    process.wait.assert_called_once_with(timeout=5)


def test_cut_can_preserve_original_borders(plugin: ModuleType, page_info: str) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    source = Image.new("RGB", (320, 240), "white")
    ImageDraw.Draw(source).rectangle((181, 21, 299, 218), outline="black", width=2)
    before = images.cut_quads(source, page_info, 12, 3)
    after = images.cut_quads(source, page_info, 12, 3, redraw_borders=False)
    assert before.getpixel((176, 100)) == (0, 0, 0)
    assert after.getpixel((176, 100)) == (255, 255, 255)
    assert after.getpixel((181, 100)) == (0, 0, 0)
    clipped = images.cut_quads(Image.new("RGB", (320, 240), "red"), page_info, 12, 3, redraw_borders=False)
    assert clipped.getpixel((20, 20)) == (255, 255, 255)
    assert clipped.getpixel((70, 120)) == (255, 0, 0)
    assert clipped.getpixel((200, 120)) == (255, 0, 0)
    assert (
        ImageChops.difference(source.crop((176, 16, 304, 224)), after.crop((176, 16, 304, 224))).getbbox()
        is None
    )
    schema = plugin.NODE_CLASS_MAPPINGS["SodaCutQuads"].INPUT_TYPES()
    assert schema["optional"]["redraw_borders"][1]["default"] is True
