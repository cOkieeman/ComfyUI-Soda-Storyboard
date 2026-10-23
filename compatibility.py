"""Non-fatal dependency version notice for the ComfyUI console."""

from __future__ import annotations

import importlib
import logging
from importlib import metadata

MIN_CORE_VERSION = "0.4.1"
CORE_REQUIREMENT = "soda-storyboard>=0.4.4"
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
            "Soda Storyboard: soda-storyboard %s 需要升级至 >=%s; 在便携版根目录运行 "
            '.\\python_embeded\\python.exe -m pip install --upgrade "%s"; 然后重启 ComfyUI',
            installed,
            MIN_CORE_VERSION,
            CORE_REQUIREMENT,
        )
