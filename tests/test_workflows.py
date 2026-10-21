from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

WORKFLOWS = Path(__file__).resolve().parents[1] / "example_workflows"
CORE_TYPES = {
    "UNETLoader",
    "ModelSamplingAuraFlow",
    "CLIPLoader",
    "VAELoader",
    "EmptyFlux2LatentImage",
    "CLIPTextEncode",
    "KSampler",
    "VAEDecode",
    "SaveImage",
    "LoadImage",
    "VAEEncode",
    "SetLatentNoiseMask",
    "ImageCompositeMasked",
}


@pytest.mark.parametrize("filename", ["minimal_page.json", "panel_redraw.json", "character_swap.json"])
def test_ui_workflow_links(plugin: ModuleType, filename: str) -> None:
    graph = json.loads((WORKFLOWS / filename).read_text(encoding="utf-8"))
    assert graph["version"] == 0.4
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert len(nodes) == len(graph["nodes"])
    assert {n["type"] for n in nodes.values()} <= CORE_TYPES | plugin.NODE_CLASS_MAPPINGS.keys()
    links = {link[0]: link for link in graph["links"]}
    assert len(links) == len(graph["links"])
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
        cls = plugin.NODE_CLASS_MAPPINGS.get(node["type"])
        if cls:
            assert tuple(o["type"] for o in node["outputs"]) == cls.RETURN_TYPES
            schema = cls.INPUT_TYPES()
            all_inputs = {**schema["required"], **schema.get("optional", {})}
            assert {i["name"] for i in node["inputs"]} <= all_inputs.keys()
    # Acyclic, with every producer scheduled before its consumers.
    pending = set(nodes)
    visited = set()
    while pending:
        ready = {
            node_id
            for node_id in pending
            if all(links[i["link"]][1] in visited for i in nodes[node_id]["inputs"] if i["link"] is not None)
        }
        assert ready, "Workflow contains a cycle"
        pending -= ready
        visited |= ready
    sampler = next(n for n in nodes.values() if n["type"] == "KSampler")
    assert sampler["widgets_values"][2:6] == [25, 2.5, "er_sde", "simple"]
    expected_denoise = {"minimal_page.json": 1, "panel_redraw.json": 0.45, "character_swap.json": 0.85}
    assert sampler["widgets_values"][-1] == expected_denoise[filename]
    if filename == "character_swap.json":
        assert sum(n["type"] == "SodaLoadStoryboardLoRA" for n in nodes.values()) == 1
        assert any(n["type"] == "ImageCompositeMasked" for n in nodes.values())


def test_example_types_exist_in_comfy_source() -> None:
    source = os.environ.get("COMFYUI_SOURCE")
    if not source:
        pytest.skip("Set COMFYUI_SOURCE to check node identifiers against local ComfyUI source")
    root = Path(source)
    identifiers = set()
    for relative in (
        "nodes.py",
        "comfy_extras/nodes_flux.py",
        "comfy_extras/nodes_model_advanced.py",
        "comfy_extras/nodes_mask.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        identifiers.update(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    assert identifiers >= CORE_TYPES
