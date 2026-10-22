from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING

import pytest
from soda_storyboard.canvas_sizes import infer_dimensions
from soda_storyboard.importers import import_moss

if TYPE_CHECKING:
    from types import ModuleType


@pytest.fixture
def moss(plugin: ModuleType) -> ModuleType:
    return importlib.import_module(f"{plugin.__name__}.nodes.moss")


def two_panels() -> dict:
    return {
        "summary": {"caption": "A two panel comic"},
        "bbox_format": "yxyx",
        "bbox_coord_space": "abs_centralized",
        "items": [
            {"label": "object", "caption": "Upper panel", "bbox": [-740, -490, -20, 490]},
            {"label": "object", "caption": "下方的格子", "bbox": [20, -490, 740, 490]},
            {"label": "character", "caption": "A traveler", "bbox": [40, -200, 700, 250]},
            {
                "label": "text",
                "caption": "Vertical Chinese narration",
                "text": "旅途开始了",
                "bbox": [-700, 350, -300, 450],
            },
            {
                "label": "text",
                "caption": "Horizontal dialogue",
                "text": "你好，欢迎光临",
                "bbox": [100, -350, 180, 200],
            },
        ],
    }


def livestream() -> dict:
    return {
        "summary": {"caption": "直播界面"},
        "items": [
            {"label": "object", "caption": "头像", "bbox": [-740, -510, -660, -440]},
            {"label": "character", "caption": "手持团扇的主播", "bbox": [-620, -360, 610, 360]},
            {"label": "object", "caption": "团扇", "bbox": [-260, -110, 200, 170]},
            {"label": "text", "caption": "Nickname", "text": "清月如故", "bbox": [-730, -430, -690, -270]},
            {"label": "text", "caption": "Follow button", "text": "关注", "bbox": [-730, -260, -670, -150]},
        ],
    }


@pytest.mark.parametrize(
    ("bbox", "expected"),
    [
        ([-740, -490, 740, 490], (1024, 1536)),
        ([-490, -740, 490, 740], (1536, 1024)),
        ([-500, -500, 500, 500], (1024, 1024)),
        ([-670, -380, 670, 380], (768, 1344)),
    ],
)
def test_canvas_inference(moss: ModuleType, bbox: list[int], expected: tuple[int, int]) -> None:
    value = {"items": [{"label": "object", "bbox": bbox}]}
    assert moss.resolve_dimensions(value) == (*expected, True)


def test_written_dimensions_and_user_overrides(moss: ModuleType) -> None:
    value = {**two_panels(), "canvas": {"width": 640, "height": 960}}
    assert moss.resolve_dimensions(value) == (640, 960, False)
    assert moss.resolve_dimensions(value, 768, 1344) == (768, 1344, False)
    assert moss.resolve_dimensions({**value, "width": 800, "height": 1200}) == (800, 1200, False)
    assert moss.resolve_dimensions({"items": []}) == (1024, 1536, True)


def test_detection_distinguishes_panels_from_livestream_objects(moss: ModuleType) -> None:
    assert len(moss.analyze_layout(two_panels(), 1024, 1536)["panels"]) == 2
    layout = moss.analyze_layout(livestream(), 1024, 1536)
    assert layout["panels"] == []
    assert layout["single_canvas"] is True
    assert len(layout["items"]) == 5


def test_detection_of_containing_background_follows_core(moss: ModuleType) -> None:
    value = {
        "items": [
            {"label": "object", "caption": "背景", "bbox": [-750, -500, 750, 500]},
            {"label": "object", "caption": "左边场景", "bbox": [-700, -470, 700, -20]},
            {"label": "object", "caption": "右边场景", "bbox": [-700, 20, 700, 470]},
        ]
    }
    layout = moss.analyze_layout(value, 1024, 1536)
    page, _ = import_moss(value)
    assert [panel["id"] for panel in layout["panels"]] == [panel.id for panel in page.panels]
    value["items"] = value["items"][:1]
    assert moss.analyze_layout(value, 1024, 1536)["single_canvas"] is True


def test_real_text_and_orientation(moss: ModuleType) -> None:
    item = {"label": "text", "caption": "Vertical English placeholder", "text": "你好世界"}
    assert moss.item_text(item) == "你好世界"
    assert moss.item_text({"label": "text", "caption": "Fallback description"}) == "Fallback des"
    assert moss.text_direction((0, 0, 60, 200)) == "vertical"
    assert moss.text_direction((0, 0, 200, 60)) == "horizontal"


def test_ambiguous_panel_word_follows_core(moss: ModuleType) -> None:
    value = {"items": [{"label": "object", "caption": "水墨风格的背景", "bbox": [-700, -450, 700, 450]}]}
    page, _ = import_moss(value)
    assert moss.analyze_layout(value, 1024, 1536)["single_canvas"] == (page.extra["canvas_mode"] == "single")


def test_preview_draws_chinese_text_instead_of_english_caption(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import ImageDraw  # noqa: PLC0415 -- keep rendering dependencies inside this test

    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    original = ImageDraw.ImageDraw.text
    drawn = []

    def record_text(draw: ImageDraw.ImageDraw, xy: tuple, text: str, **kwargs: object) -> None:
        drawn.append(text)
        original(draw, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)
    value = {
        "items": [
            {
                "label": "text",
                "caption": "Vertical English placeholder",
                "text": "真正的中文",
                "bbox": [-90, -25, 90, 25],
            },
        ]
    }
    importing.moss_preview(value, 320, 240)
    assert "".join(drawn) == "真正的中文"


@pytest.mark.parametrize("item", [None, "bad", {"bbox": [0, 0, 0, 0]}, {"bbox": [0, 0, float("nan"), 20]}])
def test_bad_boxes_are_reported_and_preserved_by_core(moss: ModuleType, item: object) -> None:
    value = {"items": [item]}
    assert moss.resolve_dimensions(value)[:2] == infer_dimensions(value)
    layout = moss.analyze_layout(value, 1024, 1536)
    assert layout["report"]["unrecognized_items"]
    assert layout["items"][0]["shape"] is None
    assert moss.boxes(value, 1024, 1536) == []


@pytest.mark.parametrize("sample", [two_panels, livestream])
def test_external_samples_match_core(moss: ModuleType, plugin: ModuleType, sample: object) -> None:
    value = sample()
    page, report = import_moss(value)
    assert moss.resolve_dimensions(value)[:2] == page.canvas_size == infer_dimensions(value)
    layout = moss.analyze_layout(value, *page.canvas_size)
    assert [panel["shape"] for panel in layout["panels"]] == [panel.shape for panel in page.panels]
    assert [panel["id"] for panel in layout["panels"]] == [panel.id for panel in page.panels]
    assert layout["single_canvas"] == (page.extra["canvas_mode"] == "single")
    assert len(layout["panels"]) == report["panel_count"]
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    metadata = importing.inspect_payload(json.dumps(value).encode())
    effective_page, _ = import_moss({**value, "canvas_width": page.width, "canvas_height": page.height})
    assert json.loads(metadata["page_info"])["page"] == effective_page.to_dict()
    assert json.loads(metadata["moss_json"]) == value


def test_inspection_preserves_moss_and_reports_inference(plugin: ModuleType) -> None:
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    value = two_panels()
    result = importing.inspect_payload(json.dumps(value).encode())
    assert (result["width"], result["height"]) == (1024, 1536)
    assert result["dimensions_inferred"] is True
    assert any("画布尺寸为推断值：1024×1536" in warning for warning in result["warnings"])
    assert result["panel_count"] == 2
    assert result["text_count"] == 2
    assert result["single_canvas"] is False
    assert json.loads(result["result"][0]) == value
    overridden = importing.inspect_payload(json.dumps(value).encode(), width=768, height=1344)
    assert (overridden["width"], overridden["height"]) == (768, 1344)
    assert overridden["dimensions_inferred"] is False
    assert json.loads(overridden["result"][0]) == value


def test_single_canvas_does_not_invent_preview_panels(plugin: ModuleType) -> None:
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    result = importing.inspect_payload(json.dumps(livestream()).encode())
    assert result["panels"] == []
    assert result["panel_count"] == 0
    assert result["single_canvas"] is True
    assert result["text_count"] == 2


def test_inspection_keeps_unrecognized_entries_without_breaking_preview(plugin: ModuleType) -> None:
    importing = importlib.import_module(f"{plugin.__name__}.nodes.importing")
    value = livestream()
    value["items"].extend([None, "unknown", {"label": "text", "bbox": [0, 0, 0, 0]}])
    _, report = import_moss(value)
    metadata = importing.inspect_payload(json.dumps(value).encode())
    assert metadata["text_count"] == report["text_count"]
    assert len(metadata["moss_layout"]["report"]["unrecognized_items"]) == 3
    assert any("3 个条目无法识别" in warning for warning in metadata["warnings"])
    assert json.loads(metadata["moss_json"]) == value
    assert metadata["draft_png_base64"]


def test_new_import_nodes_default_to_automatic_dimensions(plugin: ModuleType) -> None:
    required = plugin.NODE_CLASS_MAPPINGS["SodaLoadStoryboard"].INPUT_TYPES()["required"]
    for name in ("width", "height"):
        assert required[name][1]["default"] == 0
        assert required[name][1]["min"] == 0
