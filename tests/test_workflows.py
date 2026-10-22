from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "example_workflows"
FILENAMES = ("soda_storyboard_standard.json", "stretch-color.json")
SCHEMA_FILE = Path(__file__).parent / "fixtures" / "comfy_workflow_core_schema.json"
CORE_SCHEMA = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))["nodes"]
MODEL_FILES = {
    "UNETLoader": "moss_image_sft_int8_convrot.safetensors",
    "CLIPLoader": "qwen3.5_9b_w4a8_gptq.safetensors",
    "VAELoader": "flux2-vae.safetensors",
}
LEGACY_FILES = ("minimal_page.json", "panel_redraw.json", "character_swap.json")


def read_workflow(filename: str = FILENAMES[0]) -> dict:
    return json.loads((WORKFLOWS / filename).read_text(encoding="utf-8"))


def schema_for(kind: str, plugin: ModuleType) -> tuple[dict, tuple]:
    if kind in CORE_SCHEMA:
        schema = CORE_SCHEMA[kind]
        return {**schema["inputs"]["required"], **schema["inputs"]["optional"]}, tuple(schema["outputs"])
    cls = plugin.NODE_CLASS_MAPPINGS[kind]
    schema = cls.INPUT_TYPES()
    inputs = {**schema["required"], **schema.get("optional", {})}
    return {
        name: "COMBO" if isinstance(value[0], list) else value[0] for name, value in inputs.items()
    }, cls.RETURN_TYPES


@pytest.mark.parametrize("filename", FILENAMES)
def test_ui_workflow_links(plugin: ModuleType, filename: str) -> None:
    graph = read_workflow(filename)
    assert graph["version"] == 0.4
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert len(nodes) == len(graph["nodes"])
    assert graph["last_node_id"] >= max(nodes)
    # Note is ComfyUI's frontend-only core node; execution nodes have a schema.
    assert {node["type"] for node in nodes.values()} <= (
        CORE_SCHEMA.keys() | plugin.NODE_CLASS_MAPPINGS.keys() | {"Note"}
    )
    links = {link[0]: link for link in graph["links"]}
    assert len(links) == len(graph["links"])
    assert graph["last_link_id"] >= max(links)
    for link_id, source_id, source_slot, dest_id, dest_slot, kind in links.values():
        source, dest = nodes[source_id], nodes[dest_id]
        output, target = source["outputs"][source_slot], dest["inputs"][dest_slot]
        assert output["type"] == target["type"] == kind
        assert link_id in output["links"]
        assert target["link"] == link_id
    for node in nodes.values():
        for slot, output in enumerate(node["outputs"]):
            for link_id in output["links"]:
                assert links[link_id][1:3] == [node["id"], slot]
        if node["type"] == "Note":
            assert not node["inputs"]
            assert not node["outputs"]
            continue
        inputs, outputs = schema_for(node["type"], plugin)
        declared = tuple(output["type"] for output in node["outputs"])
        # Newer core SaveImage adds an IMAGE passthrough. Older saved workflows
        # omit that unused output, which remains valid when loaded by ComfyUI.
        if node["type"] == "SaveImage" and not declared:
            assert outputs in {(), ("IMAGE",)}
        else:
            assert declared == outputs
        assert len({value["name"] for value in node["inputs"]}) == len(node["inputs"])
        for value in node["inputs"]:
            assert value["name"] in inputs
            assert value["type"] == inputs[value["name"]]
            if value["link"] is not None:
                assert links[value["link"]][3:5] == [node["id"], node["inputs"].index(value)]
    pending, visited = set(nodes), set()
    while pending:
        ready = {
            node_id
            for node_id in pending
            if all(
                links[value["link"]][1] in visited
                for value in nodes[node_id]["inputs"]
                if value["link"] is not None
            )
        }
        assert ready, "Workflow contains a cycle"
        pending -= ready
        visited |= ready


def all_strings(value: Any) -> list[str]:  # noqa: ANN401 -- recursively inspect arbitrary JSON
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in all_strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in all_strings(item)]
    return []


@pytest.mark.parametrize("filename", FILENAMES)
def test_workflows_are_portable(filename: str) -> None:
    graph = read_workflow(filename)
    for text in all_strings(graph):
        assert not re.search(r"(?i)(?:\b[a-z]:[\\/]|\\\\|/Users/|/home/)", text), text
        assert not re.search(r"(?i)(?:your[_ -]|placeholder|example\.png|hero\.safetensors)", text), text
    for node in graph["nodes"]:
        kind = node["type"]
        if kind in MODEL_FILES:
            assert node["widgets_values"][0] == MODEL_FILES[kind]
        if kind == "CLIPLoader":
            assert node["widgets_values"][1] == "moss_image"
        if kind in {"SodaLoadStoryboard", "LoadImage"}:
            assert node["widgets_values"][0] == ""


def test_legacy_templates_are_removed() -> None:
    assert sorted(path.name for path in WORKFLOWS.glob("*.json")) == sorted(FILENAMES)
    for filename in LEGACY_FILES:
        assert not (WORKFLOWS / filename).exists()
        for document in (ROOT / "README.md", *ROOT.joinpath("docs").rglob("*.md")):
            text = document.read_text(encoding="utf-8")
            assert f"](example_workflows/{filename})" not in text
            assert f"](../example_workflows/{filename})" not in text


def incoming(graph: dict, node: dict, name: str) -> tuple[dict, int]:
    value = next(value for value in node["inputs"] if value["name"] == name)
    link = next(link for link in graph["links"] if link[0] == value["link"])
    source = next(item for item in graph["nodes"] if item["id"] == link[1])
    return source, link[2]


def test_standard_presets_bypass_and_chinese_instructions() -> None:
    graph = read_workflow()
    samplers = [node for node in graph["nodes"] if node["type"] == "KSampler"]
    full_page = [node for node in samplers if node["widgets_values"][-1] == 1]
    draft = next(node for node in full_page if node["mode"] == 0)
    final = next(node for node in full_page if node["mode"] == 4)
    assert draft["widgets_values"][2:6] == [25, 2.5, "er_sde", "simple"]
    assert final["widgets_values"][2:6] == [50, 3, "euler", "simple"]
    assert incoming(graph, final, "latent_image") == (draft, 0)
    slg, _ = incoming(graph, final, "model")
    assert slg["type"] == "SkipLayerGuidanceDiTSimple"
    assert slg["widgets_values"] == ["", "22", 0, 1]
    assert slg["mode"] == 4
    shifts = [node for node in graph["nodes"] if node["type"] == "ModelSamplingAuraFlow"]
    assert len(shifts) == 1
    assert shifts[0]["widgets_values"] == [5]
    loras = [node for node in graph["nodes"] if "LoRA" in node["type"] or "Lora" in node["type"]]
    assert loras
    assert all(node["mode"] == 4 for node in loras)
    assert all(not any(value["name"] == "lora_name" for value in node["inputs"]) for node in loras)
    details = [node for node in samplers if node not in full_page]
    assert len(details) == 2
    assert all(node["mode"] == 4 and node["widgets_values"][-1] == 0.45 for node in details)
    for group in graph["groups"]:
        x, y, width, height = group["bounding"]
        contents = [
            node
            for node in graph["nodes"]
            if x <= node["pos"][0] < x + width and y <= node["pos"][1] < y + height
        ]
        first = min(contents, key=lambda node: (node["pos"][1], node["pos"][0]))
        assert first["type"] == "Note"
        assert re.search(r"[\u4e00-\u9fff]", first["widgets_values"][0])
        if group["title"].startswith(("5", "6")):
            assert all(node["mode"] == 4 for node in contents if node["type"] != "Note")


def test_detail_sampling_uses_upscaled_original_pixels_and_shrinks_back() -> None:
    graph = read_workflow()
    samplers = [
        node for node in graph["nodes"] if node["type"] == "KSampler" and node["widgets_values"][-1] < 1
    ]
    for sampler in samplers:
        latent, _ = incoming(graph, sampler, "latent_image")
        if latent["type"] == "SetLatentNoiseMask":
            latent, _ = incoming(graph, latent, "samples")
        assert latent["type"] == "VAEEncode"
        crop, _ = incoming(graph, latent, "pixels")
        assert crop["type"] == "SodaCropPanel"
        assert crop["widgets_values"][-1] is True
    pastes = [node for node in graph["nodes"] if node["type"] == "SodaPastePanel"]
    assert len(pastes) == 2
    for paste in pastes:
        patch, _ = incoming(graph, paste, "panel_image")
        if patch["type"] == "ImageCompositeMasked":
            patch, _ = incoming(graph, patch, "source")
        assert patch["type"] == "ImageScale"
        size, width_slot = incoming(graph, patch, "width")
        assert size["type"] == "GetImageSize"
        assert width_slot == 0
        assert incoming(graph, patch, "height") == (size, 1)
        original, _ = incoming(graph, size, "image")
        assert original["type"] == "SodaCropPanel"
        assert original["widgets_values"][-1] is False


def test_local_noise_mask_and_feathered_composite_share_character_mask() -> None:
    graph = read_workflow()
    noise = next(node for node in graph["nodes"] if node["type"] == "SetLatentNoiseMask")
    mask, _ = incoming(graph, noise, "mask")
    assert mask["type"] == "ImageToMask"
    scale, _ = incoming(graph, mask, "image")
    assert scale["type"] == "ImageScale"
    mask_image, _ = incoming(graph, scale, "image")
    assert mask_image["type"] == "MaskToImage"
    character, _ = incoming(graph, mask_image, "mask")
    assert character["type"] == "SodaCharacterMask"
    assert character["widgets_values"][3:5] == [24, 16]
    composite = next(node for node in graph["nodes"] if node["type"] == "ImageCompositeMasked")
    assert incoming(graph, composite, "mask") == (character, 0)
    original, _ = incoming(graph, composite, "destination")
    assert original["type"] == "SodaCropPanel"
    assert original["widgets_values"][-1] is False


def test_stretch_color_retains_tutorial_production_settings() -> None:
    nodes = read_workflow("stretch-color.json")["nodes"]
    sampler = next(node for node in nodes if node["type"] == "KSampler")
    assert sampler["widgets_values"] == [20261022, "fixed", 50, 3, "euler", "simple", 1]
    assert not any("Lora" in node["type"] or "LoRA" in node["type"] for node in nodes)
    slg = next(node for node in nodes if node["type"] == "SkipLayerGuidanceDiTSimple")
    assert slg["widgets_values"] == ["", "22", 0, 1]


def test_example_types_exist_in_comfy_source() -> None:
    source = os.environ.get("COMFYUI_SOURCE")
    if not source:
        pytest.skip("Set COMFYUI_SOURCE to verify the frozen core schema against installed source")
    root = Path(source)
    for kind, schema in CORE_SCHEMA.items():
        source_file = root / (schema["module"].replace(".", "/") + ".py")
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        identifiers = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        assert kind in identifiers, (kind, source_file)
