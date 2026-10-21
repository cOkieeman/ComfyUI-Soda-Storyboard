"""Stable node names used by saved workflows."""

from .storyboard import (
    SodaCharacterMask,
    SodaCropPanel,
    SodaCutQuads,
    SodaExtractLayout,
    SodaLetterPage,
    SodaLoadMossJSON,
    SodaLoadStoryboardPage,
    SodaPastePanel,
    SodaStoryboardPreview,
)

NODE_CLASS_MAPPINGS = {
    cls.__name__: cls
    for cls in (
        SodaLoadStoryboardPage,
        SodaLoadMossJSON,
        SodaStoryboardPreview,
        SodaCropPanel,
        SodaCharacterMask,
        SodaPastePanel,
        SodaCutQuads,
        SodaLetterPage,
        SodaExtractLayout,
    )
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "SodaLoadStoryboardPage": "载入分镜页 · Load Storyboard Page",
    "SodaLoadMossJSON": "载入 MOSS JSON · Load MOSS JSON",
    "SodaStoryboardPreview": "分镜草稿图 · Storyboard Preview",
    "SodaCropPanel": "切格 · Crop Panel",
    "SodaCharacterMask": "人物遮罩 · Character Mask",
    "SodaPastePanel": "贴回格子 · Paste Panel",
    "SodaCutQuads": "斜切裁剪 · Cut Quads",
    "SodaLetterPage": "排字 · Letter Page",
    "SodaExtractLayout": "参考图生成版式 · Extract Layout",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
