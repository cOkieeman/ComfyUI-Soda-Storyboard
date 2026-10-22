from __future__ import annotations

import asyncio
import base64
import importlib
import io
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image


@pytest.fixture
def imports(plugin: ModuleType, project: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    folders = ModuleType("folder_paths")
    folders.get_input_directory = lambda: str(project / "input")
    monkeypatch.setitem(sys.modules, "folder_paths", folders)
    monkeypatch.setattr(tempfile, "tempdir", str(project))
    bundles = importlib.import_module(f"{plugin.__name__}.nodes.bundles")
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    workspaces = importlib.import_module(f"{plugin.__name__}.nodes.workspaces")
    importing.inspect_payload.cache_clear()
    page = json.loads((project / "pages/p1.json").read_text(encoding="utf-8"))
    cards = {
        key: json.loads((project / f"characters/{key}.json").read_text(encoding="utf-8"))
        for key in ("a", "b")
    }
    bundle = {
        "format": bundles.BUNDLE_FORMAT,
        "project": {"style_prompt": "Watercolor art"},
        "page": page,
        "characters": cards,
        "exported_at": "2026-01-01T00:00:00Z",
    }
    moss = {
        "summary": {"caption": "A comic"},
        "width": 320,
        "height": 240,
        "bbox_coord_space": "abs_centralized",
        "bbox_format": "yxyx",
        "items": [
            {"label": "object", "bbox": [-104, -144, 104, -16], "caption": "A traveler"},
            {"label": "object", "bbox": [-104, 16, 104, 144], "caption": "A river"},
            {"label": "character", "bbox": [-50, -130, 70, -60], "caption": "A smiling person"},
            {"label": "text", "bbox": [-90, 24, -30, 120], "caption": "speech", "text": "你好"},
        ],
    }
    return SimpleNamespace(
        bundles=bundles,
        importing=importing,
        workspaces=workspaces,
        bundle=bundle,
        page=page,
        moss=moss,
        project=project,
    )


@pytest.mark.parametrize("kind", ["bundle", "page", "moss"])
def test_three_formats_have_visible_draft_and_exact_prompt(imports: SimpleNamespace, kind: str) -> None:
    value = getattr(imports, kind)
    name = imports.bundles.store_upload("test.json", json.dumps(value).encode(), "storyboard")
    result = imports.workspaces.inspect_import(name)
    assert result["source_kind"] == kind
    assert result["original_filename"] == "test.json"
    assert result["width"] == 320
    assert result["height"] == 240
    assert json.loads(result["moss_json"]) == json.loads(result["result"][0])
    assert result["page_info"] == result["result"][7]
    with Image.open(io.BytesIO(base64.b64decode(result["draft_png_base64"]))) as draft:
        assert draft.size == (320, 240)
        assert draft.convert("L").getextrema()[0] < 255
        if kind == "moss":
            colors = {draft.getpixel((x, y)) for y in range(draft.height) for x in range(draft.width)}
            assert (45, 128, 90) in colors
            assert (37, 99, 166) in colors
            assert (179, 73, 34) in colors
    if kind == "moss":
        assert json.loads(result["moss_json"]) == value
        assert result["kind"] == "moss"
        assert len(result["panels"]) == 2
        assert result["panel_count"] == 2
        assert result["items"] == value["items"]
        assert result["summary"] == "320×240 · 4 个条目 · 1 个文字条目 · 2 格"
    elif kind == "page":
        assert imports.bundles.MISSING_CHARACTERS in result["warnings"]
        assert result["result"][4:6] == ("", 0.0)
        assert "LoRA" not in result["summary"]
    else:
        assert "Watercolor art" in result["moss_json"]
        assert "建议：" in result["summary"]
        assert "建议一次只加载一个角色 LoRA" in result["warnings"]
        assert result["lora"]["path"] == str(Path("characters") / "a.safetensors")
        assert "safetensors" not in result["summary"]


def test_panel_metadata_contains_reading_order_shapes_characters_and_text(imports: SimpleNamespace) -> None:
    imports.bundle["page"]["title"] = "河边相遇"
    imports.bundle["characters"]["a"]["display_name"] = "Sylvia"
    imports.bundle["page"]["panels"][1].update(
        shot="close_up", description="树下的旅人", dialogue=[{"speaker_id": "a", "text": "你好"}]
    )
    imports.bundle["page"]["texts"] = [
        {"id": "narrator", "text": "黄昏时分", "kind": "narration", "panel_id": "left"}
    ]
    metadata = imports.importing.inspect_payload(json.dumps(imports.bundle).encode())
    assert metadata["title"] == "河边相遇"
    assert metadata["page_id"] == "p1"
    assert metadata["reading_direction"] == "rtl"
    assert metadata["character_names"] == {"a": "Sylvia", "b": "b"}
    right, left = metadata["panels"]
    assert (right["id"], left["id"]) == ("right", "left")
    assert right["shot"] == "close_up"
    assert right["description"] == "树下的旅人"
    assert right["shape"] == {"type": "rect", "x": 176, "y": 16, "w": 128, "h": 208}
    assert left["shape"]["type"] == "quad"
    assert right["character_ids"] == ["a"]
    assert right["texts"][0]["text"] == "你好"
    assert right["texts"][0]["speaker_id"] == "a"
    assert left["texts"][0]["kind"] == "narration"
    assert len(metadata["texts"]) == 2
    assert metadata["lora"]["display_name"] == "Sylvia"
    assert metadata["lora"]["name"] == "a"
    assert metadata["lora"]["filename"] == "a.safetensors"


@pytest.mark.parametrize(
    "original", ["page-abcd1234abcd1234.storyboard.json", "长" * 90 + ".storyboard.json"]
)
def test_original_upload_filename_is_retained(imports: SimpleNamespace, original: str) -> None:
    name = imports.bundles.store_upload(original, json.dumps(imports.bundle).encode(), "storyboard")
    metadata = imports.workspaces.inspect_import(name)
    assert metadata["original_filename"] == original
    assert imports.bundles.list_files("storyboard") == [name]
    imports.workspaces.materialize(name)
    assert imports.workspaces.inspect_import(name)["original_filename"] == original
    assert imports.workspaces.inspect_import(name)["source_kind"] == "bundle"


def test_legacy_upload_hash_is_removed_only_when_it_matches_content(imports: SimpleNamespace) -> None:
    bundles = imports.bundles
    name = bundles.store_upload("scene.storyboard.json", json.dumps(imports.bundle).encode(), "storyboard")
    bundles.upload_metadata_path(name).unlink()
    assert bundles.original_filename(name) == "scene.storyboard.json"
    user_filename = "scene-0123456789abcdef.storyboard.json"
    bundles.file_path(user_filename).write_bytes(bundles.file_path(name).read_bytes())
    assert bundles.original_filename(user_filename) == user_filename


def test_triggers_are_optional_appearance_is_not(imports: SimpleNamespace) -> None:
    name = imports.bundles.store_upload("bundle.json", json.dumps(imports.bundle).encode(), "storyboard")
    enabled = imports.workspaces.inspect_import(name, include_triggers=True)
    disabled = imports.workspaces.inspect_import(name, include_triggers=False)
    for key in ("a", "b"):
        assert f"person_{key}" in enabled["moss_json"]
        assert f"person_{key}" not in disabled["moss_json"]
    assert "年轻的旅人" in enabled["moss_json"]
    assert "年轻的旅人" in disabled["moss_json"]
    assert disabled["result"][4:6] == enabled["result"][4:6]
    assert imports.bundle["characters"]["a"]["trigger_words"] == ["person_a"]


def test_bundle_project_defaults(imports: SimpleNamespace) -> None:
    for key in ("canvas_width", "canvas_height", "reading_direction"):
        imports.bundle["page"].pop(key, None)
    imports.bundle["project"].update(
        default_canvas_width=320,
        default_canvas_height=240,
        reading_direction="ltr",
        default_style_prefix="ink wash",
    )
    page, _, _, _ = imports.bundles.parse_bundle(imports.bundle)
    assert page.canvas_size == (320, 240)
    assert page.reading_direction == "ltr"
    assert page.style_prefix == "ink wash"


@pytest.mark.parametrize(
    "payload",
    [b"broken", b"\xff", b"[]", b'{"format":"wrong"}', b'{"format":"soda-storyboard-bundle-v1","page":null}'],
)
def test_bad_upload_does_not_write_files(imports: SimpleNamespace, payload: bytes) -> None:
    with pytest.raises((ValueError, TypeError)):
        imports.bundles.store_upload("broken.json", payload, "storyboard")
    assert imports.bundles.list_files("storyboard") == []


def test_upload_directory_lists_and_paths(imports: SimpleNamespace) -> None:
    bundles = imports.bundles
    payload = json.dumps(imports.bundle).encode()
    name = bundles.store_upload("page.storyboard.json", payload, "storyboard")
    assert bundles.store_upload("page.storyboard.json", payload, "storyboard") == name
    moss_name = bundles.store_upload("layout.moss.json", json.dumps(imports.moss).encode(), "storyboard")
    assert bundles.file_path(name).parent == (imports.project / "input/soda-storyboard").resolve()
    assert set(bundles.list_files("storyboard")) == {name, moss_name}
    assert bundles.list_files("moss") == [moss_name]
    for path in ("../page.json", "nested/page.json", "nested\\page.json", "C:page.json"):
        with pytest.raises(ValueError, match="不含目录"):
            bundles.store_upload(path, payload, "storyboard")
        with pytest.raises(ValueError, match="文件名无效"):
            bundles.file_path(path)


def test_moss_conversion_requires_confirmation(imports: SimpleNamespace) -> None:
    name = imports.bundles.store_upload("layout.json", json.dumps(imports.moss).encode(), "storyboard")
    with pytest.raises(ValueError, match="近似"):
        imports.workspaces.materialize(name)
    root, page_id = imports.workspaces.materialize(name, convert_moss=True)
    converted = json.loads((root / "pages" / f"{page_id}.json").read_text(encoding="utf-8"))
    assert len(converted["panels"]) == 2
    assert converted["panels"][0]["description"] == "A traveler"
    assert converted["texts"][0]["text"] == "你好"
    assert converted["texts"][0]["bbox"] == {"type": "rect", "x": 184.0, "y": 30.0, "w": 96.0, "h": 60.0}
    assert imports.workspaces.materialize(name) == (root, page_id)
    assert imports.workspaces.inspect_import(name)["kind"] == "page"


def test_editor_save_refreshes_preview_prompt_and_hash(imports: SimpleNamespace, plugin: ModuleType) -> None:
    bundles, workspaces = imports.bundles, imports.workspaces
    name = bundles.store_upload("bundle.json", json.dumps(imports.bundle).encode(), "storyboard")
    source = bundles.file_path(name).read_bytes()
    node = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboard"]
    before = workspaces.inspect_import(name)
    first_hash = node.IS_CHANGED(name)
    root, page_id = workspaces.materialize(name)
    page_path = root / "pages" / f"{page_id}.json"
    page = json.loads(page_path.read_text(encoding="utf-8"))
    page["panels"][0]["caption_en"] = "A changed scene with a lantern"
    page["panels"][0]["use_custom_caption"] = True
    page["panels"][0]["figures"][0]["pose"] = "sit"
    page_path.write_text(json.dumps(page), encoding="utf-8")
    after = workspaces.inspect_import(name)
    assert before["revision"] != after["revision"]
    assert before["draft_png_base64"] != after["draft_png_base64"]
    assert "A changed scene with a lantern" in after["moss_json"]
    assert node.IS_CHANGED(name) != first_hash
    assert bundles.file_path(name).read_bytes() == source
    exported = workspaces.export_copy(name)
    assert exported != name
    assert bundles.original_filename(exported) == "bundle-edited.storyboard.json"
    exported_data = bundles.decode_json(bundles.file_path(exported).read_bytes())
    assert exported_data["format"] == bundles.BUNDLE_FORMAT
    assert exported_data["page"]["panels"][0]["caption_en"] == page["panels"][0]["caption_en"]
    assert exported_data["sketch_png_base64"]


def test_unified_node_outputs_same_displayed_draft(
    imports: SimpleNamespace, plugin: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    nodes = importlib.import_module(f"{plugin.__name__}.nodes.storyboard")
    monkeypatch.setattr(nodes, "images_tensor", lambda images: images)
    name = imports.bundles.store_upload("page.json", json.dumps(imports.bundle).encode(), "storyboard")
    result = nodes.SodaLoadStoryboard().execute(name)
    assert len(result["result"]) == 9
    visible = result["ui"]["soda"][0]
    assert result["result"][0] == visible["moss_json"]
    assert result["result"][-1][0].size == (320, 240)
    assert imports.importing.png_base64(result["result"][-1][0]) == visible["draft_png_base64"]


def test_empty_selection_does_not_error_during_cache_probe(plugin: ModuleType) -> None:
    imported = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboard"]()
    linked = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardPage"]()
    assert imported.IS_CHANGED() == imported.IS_CHANGED()
    assert linked.IS_CHANGED("", "") == linked.IS_CHANGED("", "")
    with pytest.raises(ValueError, match="请先导入分镜包"):
        imported.execute()
    with pytest.raises(ValueError, match="请先选择项目和页面"):
        linked.execute("", "")


def test_linked_preview_matches_execution_and_tracks_project_settings(
    imports: SimpleNamespace, plugin: ModuleType
) -> None:
    linked = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboardPage"]()
    directory = str(imports.project)
    before = imports.workspaces.inspect_link(directory, "p1", include_triggers=False)
    assert before["result"] == linked.execute(directory, "p1", include_triggers=False)
    assert "person_a" not in before["moss_json"]
    project_path = imports.project / "project.json"
    settings = json.loads(project_path.read_text(encoding="utf-8"))
    settings["style_prompt"] = "New watercolor style"
    project_path.write_text(json.dumps(settings), encoding="utf-8")
    after = imports.workspaces.inspect_link(directory, "p1", include_triggers=False)
    assert before["revision"] != after["revision"]
    assert "New watercolor style" in after["moss_json"]


def test_import_draft_tensor_shape(imports: SimpleNamespace, plugin: ModuleType) -> None:
    torch = pytest.importorskip("torch")
    pytest.importorskip("numpy")
    name = imports.bundles.store_upload("draft.json", json.dumps(imports.bundle).encode(), "storyboard")
    draft = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboard"]().execute(name)["result"][-1]
    assert draft.shape == (1, 240, 320, 3)
    assert draft.dtype == torch.float32
    assert 0 <= float(draft.min()) <= float(draft.max()) <= 1


def test_import_routes_upload_inspect_edit_export(
    imports: SimpleNamespace, plugin: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    routes = importlib.import_module(f"{plugin.__name__}.routes")
    web = ModuleType("aiohttp.web")
    web.json_response = lambda payload, status=200: (status, payload)
    monkeypatch.setitem(sys.modules, "aiohttp.web", web)
    payload = json.dumps(imports.bundle).encode()
    field = SimpleNamespace(
        name="file", filename="test.json", read_chunk=AsyncMock(side_effect=[payload, b""])
    )
    request = SimpleNamespace(
        remote="127.0.0.1",
        host="localhost:8188",
        headers={},
        query={},
        content_length=len(payload) + 100,
        multipart=AsyncMock(return_value=SimpleNamespace(next=AsyncMock(return_value=field))),
    )
    code, response = asyncio.run(routes.dispatch(request, "upload"))
    assert code == 200
    assert response["original_filename"] == "test.json"
    name = response["name"]
    code, listed = asyncio.run(routes.dispatch(request, "files"))
    assert code == 200
    assert listed == {"files": [name], "file_labels": {name: "test.json"}}
    request.query = {"filename": name}
    code, metadata = asyncio.run(routes.dispatch(request, "inspect"))
    assert code == 200
    assert metadata["draft_png_base64"]
    assert metadata["moss_json"]
    request.query["revision"] = metadata["revision"]
    assert asyncio.run(routes.dispatch(request, "inspect"))[1]["unchanged"] is True
    request.json = AsyncMock(return_value={"filename": name})
    request.content_length = 100
    start = Mock(return_value={"url": "http://127.0.0.1:8780/#page=p1"})
    monkeypatch.setattr(routes, "editor_start", start)
    code, opened = asyncio.run(routes.dispatch(request, "edit_import"))
    assert code == 200
    assert Path(opened["project_dir"]).is_relative_to(imports.project / "input")
    start.assert_called_once()
    code, exported = asyncio.run(routes.dispatch(request, "export"))
    assert code == 200
    assert exported["bundle"]["format"] == imports.bundles.BUNDLE_FORMAT
    request.remote = "10.0.0.1"
    assert asyncio.run(routes.dispatch(request, "upload"))[0] == 403
