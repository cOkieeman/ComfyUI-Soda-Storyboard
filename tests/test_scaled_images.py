from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageChops

if TYPE_CHECKING:
    from types import ModuleType


@pytest.mark.parametrize("size", [(640, 480), (640, 720), (160, 120)])
def test_scaled_cut_keeps_panel_geometry(plugin: ModuleType, page_info: str, size: tuple[int, int]) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    sx, sy = size[0] / 320, size[1] / 240
    result = images.cut_quads(Image.new("RGB", size, "red"), page_info, 2, 1)
    assert result.size == size
    assert result.getpixel((round(140 * sx), round(20 * sy))) == (255, 255, 255)
    assert result.getpixel((round(70 * sx), round(120 * sy))) == (255, 0, 0)
    assert result.getpixel((round(200 * sx), round(120 * sy))) == (255, 0, 0)
    assert result.getpixel((round(176 * sx), round(100 * sy))) == (0, 0, 0)


@pytest.mark.parametrize("size", [(640, 480), (640, 720), (160, 120)])
def test_scaled_crop_paste_roundtrip(plugin: ModuleType, page_info: str, size: tuple[int, int]) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    original = Image.new("RGB", size, "blue")
    crop, mask, _, raw_metadata = images.crop_panel(original, page_info, "left", resize=False)
    sx, sy = size[0] / 320, size[1] / 240
    assert crop.size == (round(128 * sx), round(208 * sy))
    assert mask.size == crop.size
    metadata = json.loads(raw_metadata)
    assert metadata["canvas_size"] == list(size)
    result = images.paste_panel(original, crop, metadata, protect_text=True)
    assert ImageChops.difference(result, original).getbbox() is None
    result = images.paste_panel(original, Image.new("RGB", (1024, 1024), "red"), metadata, protect_text=False)
    assert result.getpixel((round(70 * sx), round(120 * sy))) == (255, 0, 0)
    assert result.getpixel((round(200 * sx), round(120 * sy))) == (0, 0, 255)
    enlarged, enlarged_mask, _, _ = images.crop_panel(original, page_info, "left", resize=True)
    assert max(enlarged.size) == 1024
    assert all(side % 16 == 0 for side in enlarged.size)
    assert enlarged_mask.size == enlarged.size


def test_scaled_paste_rejects_stale_crop(plugin: ModuleType, page_info: str) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    original = Image.new("RGB", (640, 720))
    crop, _, _, raw_metadata = images.crop_panel(original, page_info, "left", resize=False)
    with pytest.raises(ValueError, match="重新切格"):
        images.paste_panel(original.resize((320, 240)), crop, json.loads(raw_metadata), protect_text=False)


def test_scaled_character_mask_protects_neighbors(plugin: ModuleType, page_info: str) -> None:
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    full = images.character_mask(Image.new("RGB", (640, 720)), page_info, "left", "a", 50, 16, "整页")
    assert full.size == (640, 720)
    assert full.getpixel((46 * 2, 116 * 3)) > 0
    assert full.getpixel((106 * 2, 116 * 3)) == 0
    cropped = images.character_mask(Image.new("RGB", (640, 1024)), page_info, "left", "a", 50, 16, "格子")
    assert cropped.getpixel((round(90 / 128 * 640), round(100 / 208 * 1024))) == 0


def test_scaled_text_boxes_font_sizes_and_protection(plugin: ModuleType, page_info: str) -> None:
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    page, characters = adapter.parse_info(page_info)
    value = page.to_dict()
    value["texts"] = [
        {
            "id": "t",
            "text": "Hi",
            "bbox": {"x": 200, "y": 50, "w": 48, "h": 60},
            "font_size": 12,
            "tail_tip": [15, 20],
            "bubble": "box",
        }
    ]
    page = adapter.core("models").Page.from_dict(value)
    before = page.to_dict()
    updated = adapter.info(page, characters)
    original = Image.new("RGB", (640, 720), "blue")
    crop, _, _, metadata = images.crop_panel(original, updated, "right", resize=False)
    result = images.paste_panel(
        original, Image.new("RGB", crop.size, "red"), json.loads(metadata), protect_text=True
    )
    assert result.getpixel((420, 180)) == (0, 0, 255)
    assert result.getpixel((540, 360)) == (255, 0, 0)
    scaled = images.page_at_size(page, original.size)
    assert scaled.canvas_size == original.size
    assert scaled.texts[0].bbox.to_dict() == {"type": "rect", "x": 400, "y": 150, "w": 96, "h": 180}
    assert scaled.texts[0].extra["font_size"] == 24
    assert scaled.texts[0].extra["tail_tip"] == [30, 60]
    assert page.to_dict() == before
    scaled.dialogue_mode = "lettering"
    result = adapter.core("production.lettering").letter_image(original, scaled)
    assert result.getpixel((402, 152)) == (255, 255, 255)
    assert result.getpixel((202, 52)) == (0, 0, 255)


def test_scaled_tensor_paste_preserves_unedited_float_pixels(plugin: ModuleType, page_info: str) -> None:
    torch = pytest.importorskip("torch")
    nodes = plugin.NODE_CLASS_MAPPINGS
    original = torch.rand(2, 720, 640, 3)
    crop, _, _, metadata = nodes["SodaCropPanel"]().execute(
        original, page_info, "right", resize_to_1024=False
    )
    result = nodes["SodaPastePanel"]().execute(original, crop, metadata)[0]
    assert result.shape == original.shape
    assert torch.equal(result[:, :, :352], original[:, :, :352])


def test_scaled_letter_node_uses_actual_image_size(plugin: ModuleType, page_info: str) -> None:
    pytest.importorskip("torch")
    adapter = importlib.import_module(f"{plugin.__name__}.nodes.core")
    images = importlib.import_module(f"{plugin.__name__}.nodes.images")
    page, characters = adapter.parse_info(page_info)
    value = page.to_dict()
    value.update(
        dialogue_mode="lettering",
        texts=[
            {
                "id": "t",
                "text": "Hi",
                "bbox": {"x": 200, "y": 50, "w": 48, "h": 60},
                "bubble": "box",
            }
        ],
    )
    updated = adapter.info(adapter.core("models").Page.from_dict(value), characters)
    original = images.images_tensor([Image.new("RGB", (640, 720), "blue")])
    result = plugin.NODE_CLASS_MAPPINGS["SodaLetterPage"]().execute(original, updated)[0]
    assert result.shape == original.shape
    assert tuple(result[0, 152, 402].tolist()) == (1, 1, 1)
    assert tuple(result[0, 52, 202].tolist()) == (0, 0, 1)
