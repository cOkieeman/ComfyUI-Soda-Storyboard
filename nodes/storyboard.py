"""Storyboard ComfyUI nodes, callable without a running PromptServer."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PIL import Image

from .core import (
    NEGATIVE,
    content_hash,
    core,
    dumps,
    info,
    inside,
    load,
    parse_info,
    project_root,
    relative_lora,
    resolution,
)
from .images import (
    character_mask,
    check_size,
    crop_panel,
    cut_quads,
    images_tensor,
    map_images,
    paste_edit_mask,
    paste_panel,
    tensor_images,
)


def string(default: str = "", *, multiline: bool = False) -> tuple:
    return ("STRING", {"default": default, "multiline": multiline})


def page_inputs() -> dict:
    return {"project_dir": string(), "page_id": string()}


def image_inputs() -> dict:
    return {"image": ("IMAGE",), "page_info": string(multiline=True)}


class SodaNode:
    CATEGORY = "Soda Storyboard"
    FUNCTION = "execute"


class SodaLoadStoryboardLoRA(SodaNode):
    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    DESCRIPTION = "接收分镜页的 LoRA 相对路径和强度；名称为空时原样返回模型。一次只加载一个人物 LoRA。"

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "model": ("MODEL",),
                "lora_name": string(),
                "strength": ("FLOAT", {"default": 1.0, "min": -100.0, "max": 100.0, "step": 0.01}),
            }
        }

    def execute(self, model: Any, lora_name: str, strength: float = 1.0) -> tuple:
        name = lora_name.strip()
        if not name:
            return (model,)
        name = relative_lora(name)
        folders = importlib.import_module("folder_paths")
        path = folders.get_full_path("loras", name)
        if not path or not Path(path).is_file():
            msg = f"找不到 LoRA 文件：{name}，请检查 ComfyUI models/loras 及角色卡 lora.path"
            raise ValueError(msg)
        utils = importlib.import_module("comfy.utils")
        sd = importlib.import_module("comfy.sd")
        weights = utils.load_torch_file(path, safe_load=True)
        patched, _ = sd.load_lora_for_models(model, None, weights, strength, 0.0)
        return (patched,)


class SodaLoadStoryboardPage(SodaNode):
    RETURN_TYPES = ("STRING", "INT", "INT", "STRING", "STRING", "FLOAT", "STRING", "STRING")
    RETURN_NAMES = (
        "moss_json",
        "width",
        "height",
        "resolution_json",
        "lora_name",
        "lora_strength",
        "negative",
        "page_info",
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                **page_inputs(),
                "dialogue_mode": (["跟随页面", "MOSS 画字", "程序排字"],),
                "slant_mode": (["cut", "hint"],),
            }
        }

    @classmethod
    def IS_CHANGED(
        cls, project_dir: str, page_id: str, dialogue_mode: str = "跟随页面", slant_mode: str = "cut"
    ) -> str:
        return content_hash(project_dir, page_id, dialogue_mode, slant_mode)

    def execute(
        self, project_dir: str, page_id: str, dialogue_mode: str = "跟随页面", slant_mode: str = "cut"
    ) -> tuple:
        page, characters = load(project_dir, page_id, dialogue_mode)
        compiled = core("compiler").compile_page(page, characters, slant_mode=slant_mode)
        lora = core("production.api").select_lora(page, characters) or {}
        width, height = page.canvas_size
        return (
            dumps(compiled),
            width,
            height,
            resolution(width, height),
            relative_lora(lora.get("path", "")),
            float(lora.get("strength", 0.0)),
            NEGATIVE,
            info(page, characters),
        )


class SodaLoadMossJSON(SodaNode):
    RETURN_TYPES = ("STRING", "INT", "INT", "STRING")
    RETURN_NAMES = ("moss_json", "width", "height", "resolution_json")

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "source": string(multiline=True),
                "width": ("INT", {"default": 1024, "min": 16, "step": 16}),
                "height": ("INT", {"default": 1536, "min": 16, "step": 16}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, source: str, width: int, height: int) -> str:
        payload = source.strip().encode()
        if not source.lstrip().startswith("{"):
            payload = Path(source).expanduser().read_bytes()
        return hashlib.sha256(payload + dumps([width, height]).encode()).hexdigest()

    def execute(self, source: str, width: int = 1024, height: int = 1536) -> tuple:
        core("models")
        payload = (
            source
            if source.lstrip().startswith("{")
            else Path(source).expanduser().read_text(encoding="utf-8-sig")
        )
        value = json.loads(payload)
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("summary"), dict)
            or not isinstance(value.get("items"), list)
        ):
            msg = "MOSS JSON 必须包含 summary 对象和 items 数组"
            raise TypeError(msg)
        return dumps(value), width, height, resolution(width, height)


class SodaStoryboardPreview(SodaNode):
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("draft",)

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {"required": page_inputs(), "optional": {"page_info": string(multiline=True)}}

    @classmethod
    def IS_CHANGED(cls, project_dir: str, page_id: str, page_info: str = "") -> str:
        return (
            hashlib.sha256(page_info.encode()).hexdigest()
            if page_info
            else content_hash(project_dir, page_id)
        )

    def execute(self, project_dir: str = "", page_id: str = "", page_info: str = "") -> tuple:
        page, characters = parse_info(page_info) if page_info else load(project_dir, page_id)
        with TemporaryDirectory(prefix="soda-sketch-") as directory:
            path = Path(directory) / "sketch.png"
            core("preview").render_preview(page, path, characters, style="sketch")
            with Image.open(path) as image:
                return (images_tensor([image.convert("RGB")]),)


class SodaCropPanel(SodaNode):
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING")
    RETURN_NAMES = ("panel", "mask", "panel_prompt", "panel_box")

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                **image_inputs(),
                "panel": string("1"),
                "resize_to_1024": ("BOOLEAN", {"default": True}),
            }
        }

    def execute(self, image: Any, page_info: str, panel: str = "1", resize_to_1024: bool = True) -> tuple:
        results = [crop_panel(im, page_info, panel, resize=resize_to_1024) for im in tensor_images(image)]
        return (
            images_tensor([r[0] for r in results]),
            images_tensor([r[1] for r in results], mask=True),
            results[0][2],
            results[0][3],
        )


class SodaCharacterMask(SodaNode):
    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)
    DESCRIPTION = "格子：输入切出的单格，遮罩缩放到单格尺寸。整页：输入完整页面，遮罩按页面坐标放置。"

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                **image_inputs(),
                "panel": string("1"),
                "character_id": string(),
                "margin": ("INT", {"default": 24, "min": 0, "max": 512}),
                "feather": ("INT", {"default": 16, "min": 0, "max": 256}),
                "scope": (["格子", "整页"], {"default": "格子", "tooltip": cls.DESCRIPTION}),
            }
        }

    def execute(
        self,
        image: Any,
        page_info: str,
        panel: str,
        character_id: str,
        margin: int = 24,
        feather: int = 16,
        scope: str = "格子",
    ) -> tuple:
        masks = [
            character_mask(im, page_info, panel, character_id, margin, feather, scope)
            for im in tensor_images(image)
        ]
        return (images_tensor(masks, mask=True),)


class SodaPastePanel(SodaNode):
    RETURN_TYPES = ("IMAGE",)

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "image": ("IMAGE",),
                "panel_image": ("IMAGE",),
                "panel_box": string(),
                "protect_text": ("BOOLEAN", {"default": True}),
            }
        }

    def execute(self, image: Any, panel_image: Any, panel_box: str, protect_text: bool = True) -> tuple:
        originals, patches = tensor_images(image), tensor_images(panel_image)
        if len(originals) != len(patches) and min(len(originals), len(patches)) != 1:
            msg = "整页和重画格子的 batch 数必须相同，或其中一个为 1（广播）"
            raise ValueError(msg)
        metadata = json.loads(panel_box)
        processed = images_tensor(
            [
                paste_panel(
                    originals[i % len(originals)],
                    patches[i % len(patches)],
                    metadata,
                    protect_text=protect_text,
                )
                for i in range(max(len(originals), len(patches)))
            ]
        )
        # Preserve unedited float pixels exactly; a PIL round trip quantizes them.
        page, _ = parse_info(metadata["page_info"])
        panel = next(p for p in page.panels if p.id == metadata["panel_id"])
        area = paste_edit_mask(page, panel, protect_text=protect_text)
        editable = images_tensor([area], mask=True).unsqueeze(-1).to(image.device)
        original = image.expand(len(processed), -1, -1, -1)[..., :3]
        torch = __import__("torch")
        return (torch.where(editable > 0, processed.to(image.device), original),)


class SodaCutQuads(SodaNode):
    RETURN_TYPES = ("IMAGE",)

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                **image_inputs(),
                "inset": ("INT", {"default": 12, "min": 0, "max": 512}),
                "border": ("INT", {"default": 3, "min": 1, "max": 64}),
            }
        }

    def execute(self, image: Any, page_info: str, inset: int = 12, border: int = 3) -> tuple:
        return map_images(image, lambda im: cut_quads(im, page_info, inset, border))


class SodaLetterPage(SodaNode):
    RETURN_TYPES = ("IMAGE",)

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {"required": image_inputs(), "optional": {"font": string()}}

    def execute(self, image: Any, page_info: str, font: str = "") -> tuple:
        page, _ = parse_info(page_info)

        def letter(im: Image.Image) -> Image.Image:
            check_size(im, page)
            return core("production.lettering").letter_image(im, page, font=font or None)

        return map_images(image, letter)


class SodaExtractLayout(SodaNode):
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("layout_json", "preview")
    # Saving a template is an explicit file side effect; execute on each queued run.
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "image": ("IMAGE",),
                "direction": (["rtl", "ltr"],),
                "save_template": ("BOOLEAN", {"default": False}),
            },
            "optional": {"project_dir": string(), "template_name": string("Reference layout")},
        }

    def execute(
        self,
        image: Any,
        direction: str = "rtl",
        save_template: bool = False,
        project_dir: str = "",
        template_name: str = "Reference layout",
    ) -> tuple:
        extractor = core("extract")
        layouts, previews = [], []
        for index, im in enumerate(tensor_images(image)):
            # extract_image is the public PIL equivalent of extract_layout(path).
            result = extractor.extract_image(im, direction=direction)
            if save_template:
                directory = inside(project_root(project_dir), "templates")
                extractor.save_template(result, directory, name=f"{template_name}-{index + 1}")
            with TemporaryDirectory(prefix="soda-layout-") as directory:
                path = Path(directory) / "preview.png"
                extractor.draw_extraction_preview(im, result, path)
                with Image.open(path) as preview:
                    previews.append(preview.convert("RGB"))
            layouts.append(result)
        return dumps(layouts[0] if len(layouts) == 1 else layouts), images_tensor(previews)
