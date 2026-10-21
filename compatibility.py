"""Non-fatal dependency version notice for the ComfyUI console."""

from __future__ import annotations

import importlib
import logging
from importlib import metadata

MIN_CORE_VERSION = "0.3.1"
LOGGER = logging.getLogger(__name__)


def check_core_version() -> None:
    try:
        installed = metadata.version("soda-storyboard")
    except metadata.PackageNotFoundError:
        # Nodes remain registered; execution supplies the installation message.
        return
    try:
        versions = importlib.import_module("packaging.version")
        outdated = versions.Version(installed) < versions.Version(MIN_CORE_VERSION)
    except (ImportError, ValueError):
        # Missing optional version parser or invalid metadata must not block load.
        outdated = True
    if outdated:
        LOGGER.warning(
            "Soda Storyboard: soda-storyboard %s 需要升级至 >=%s; 请在节点包目录用 ComfyUI Python "
            "运行 python -m pip install --upgrade -r requirements.txt",
            installed,
            MIN_CORE_VERSION,
        )
