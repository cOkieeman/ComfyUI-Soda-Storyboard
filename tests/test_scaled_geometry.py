from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageChops

if TYPE_CHECKING:
    from types import ModuleType


@pytest.mark.parametrize("size", [(640, 480), (640, 720), (160, 120)])
def test_cut_quads_tracks_actual_image_size(
    plugin: ModuleType, page_info: str, size: tuple[int, int]
) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    result = images.cut_quads(Image.new("RGB", size, "red"), page_info, 0, 1)
    sx, sy = size[0] / 320, size[1] / 240
    assert result.size == size
    # Outside the slanted edge, inside the same panel, and inside its neighbour.
    assert result.getpixel((round(130 * sx), round(18 * sy))) == (255, 255, 255)
    assert result.getpixel((round(70 * sx), round(120 * sy))) == (255, 0, 0)
    assert result.getpixel((round(200 * sx), round(120 * sy))) == (255, 0, 0)
    assert result.getpixel((round(176 * sx), round(120 * sy))) == (0, 0, 0)


@pytest.mark.parametrize("size", [(640, 480), (640, 720)])
def test_crop_paste_uses_scaled_quad_and_metadata(
    plugin: ModuleType, page_info: str, size: tuple[int, int]
) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    original = Image.new("RGB", size, "blue")
    crop, mask, _, payload = images.crop_panel(original, page_info, "left", resize=False)
    metadata = json.loads(payload)
    sx, sy = size[0] / 320, size[1] / 240
    assert crop.size == (round(128 * sx), round(208 * sy))
    assert metadata["canvas_size"] == list(size)
    assert metadata["page_info"] == page_info
    assert mask.getpixel((crop.width - 1, 0)) == 0
    result = images.paste_panel(original, crop, metadata, protect_text=False)
    assert ImageChops.difference(result, original).getbbox() is None
    result = images.paste_panel(original, Image.new("RGB", crop.size, "red"), metadata, protect_text=False)
    assert result.getpixel((round(60 * sx), round(100 * sy))) == (255, 0, 0)
    assert result.getpixel((round(140 * sx), round(18 * sy))) == (0, 0, 255)
    assert result.getpixel((round(220 * sx), round(120 * sy))) == (0, 0, 255)
    with pytest.raises(ValueError, match="重新切格"):
        images.paste_panel(Image.new("RGB", (320, 240)), crop, metadata, protect_text=False)


def test_scaled_paste_preserves_text_and_untouched_tensor_pixels(plugin: ModuleType, page_info: str) -> None:
    torch = pytest.importorskip("torch")
    value = json.loads(page_info)
    value["page"]["texts"] = [{"id": "t", "text": "Hi", "bbox": {"x": 200, "y": 50, "w": 48, "h": 60}}]
    page_info = json.dumps(value)
    nodes = plugin.NODE_CLASS_MAPPINGS
    original = torch.rand(1, 480, 640, 3)
    crop, _, _, metadata = nodes["SodaCropPanel"]().execute(
        original, page_info, "right", resize_to_1024=False
    )
    patch = torch.ones_like(crop)
    result = nodes["SodaPastePanel"]().execute(original, patch, metadata, protect_text=True)[0]
    assert result.shape == original.shape
    assert torch.equal(result[:, :, :352], original[:, :, :352])
    assert torch.equal(result[:, 100:220, 400:496], original[:, 100:220, 400:496])
    assert torch.all(result[:, 240, 540] == 1)


def test_character_mask_tracks_upscaled_full_page(plugin: ModuleType, page_info: str) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    base = images.character_mask(Image.new("RGB", (320, 240)), page_info, "left", "a", 24, 16, "整页")
    result = images.character_mask(Image.new("RGB", (640, 720)), page_info, "left", "a", 24, 16, "整页")
    assert result.tobytes() == base.resize((640, 720), Image.Resampling.NEAREST).tobytes()


def test_letter_page_tracks_scaled_boxes(plugin: ModuleType, page_info: str) -> None:
    torch = pytest.importorskip("torch")
    value = json.loads(page_info)
    value["page"].update(
        dialogue_mode="lettering",
        texts=[
            {
                "id": "t",
                "text": "Hi",
                "direction": "horizontal",
                "bubble": "box",
                "bbox": {"x": 200, "y": 50, "w": 48, "h": 60},
                "font_size": 14,
            }
        ],
    )
    original = torch.zeros(1, 720, 640, 3)
    original[..., 2] = 1
    result = plugin.NODE_CLASS_MAPPINGS["SodaLetterPage"]().execute(original, json.dumps(value))[0]
    assert result.shape == original.shape
    assert torch.all(result[:, 160, 410] == 1)  # white bubble at scaled position
    assert torch.equal(result[:, :140], original[:, :140])
    assert torch.equal(result[:, :, :390], original[:, :, :390])


def test_page_scaling_resolves_text_and_preserves_source(plugin: ModuleType, page_info: str) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    geometry = importlib.import_module(f"{plugin.__name__}.nodes.geometry")
    value = json.loads(page_info)
    value["page"].update(
        texts=[
            {
                "id": "t",
                "text": "Hi",
                "font_size": 14,
                "tail_tip": [20, 70],
                "bbox": {"x": 200, "y": 50, "w": 48, "h": 60},
            }
        ],
        overlays=[{"id": "o", "character_id": "a", "rect": {"x": 100, "y": 40, "w": 80, "h": 180}}],
        objects=[{"id": "obj", "rect": {"x": 5, "y": 6, "w": 20, "h": 30}}],
    )
    value["page"]["panels"][0]["dialogue"] = [{"text": "Hello"}]
    page, _ = adapter.parse_info(json.dumps(value))
    before = page.to_dict()
    base_texts = adapter.core("lettering").layout_texts(page)
    scaled = geometry.page_at_size(page, (640, 720))
    assert scaled.canvas_size == (640, 720)
    assert scaled.panels[0].shape["points"] == [[32, 48], [288, 96], [288, 672], [32, 672]]
    assert scaled.overlays[0].rect.to_dict() == {"type": "rect", "x": 200, "y": 120, "w": 160, "h": 540}
    assert scaled.objects[0].rect.to_dict() == {"type": "rect", "x": 10, "y": 18, "w": 40, "h": 90}
    texts = adapter.core("lettering").layout_texts(scaled)
    assert len(texts) == len(base_texts) == 2
    assert texts[0].extra["font_size"] == 28
    assert texts[0].extra["tail_tip"] == [40, 210]
    for original, transformed in zip(base_texts, texts, strict=True):
        assert transformed.bbox.x == original.bbox.x * 2
        assert transformed.bbox.y == original.bbox.y * 3
        assert transformed.bbox.w == original.bbox.w * 2
        assert transformed.bbox.h == original.bbox.h * 3
    assert page.to_dict() == before
