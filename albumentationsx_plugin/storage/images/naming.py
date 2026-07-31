"""Deterministic output names for generated image files."""

from __future__ import annotations

import re
from os import PathLike
from pathlib import Path

from albumentationsx_plugin.storage.images.constants import SUPPORTED_OUTPUT_EXTENSIONS

_UNSAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")


def build_output_image_relative_path(
    source_filepath: str | PathLike[str],
    *,
    sample_id: str,
    output_index: int,
    extension: str = ".png",
) -> Path:
    """Build a deterministic run-manifest relative path for one output image."""

    if output_index < 0:
        raise ValueError("output_index must be greater than or equal to zero")

    normalized_extension = _normalize_extension(extension)
    source_stem = _safe_component(Path(source_filepath).stem, default="image")
    sample_component = _safe_component(sample_id, default="sample")
    filename = f"{source_stem}-{sample_component}-{output_index:04d}{normalized_extension}"
    return Path("images") / filename


def _normalize_extension(extension: str) -> str:
    normalized = extension.lower()
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    if normalized not in SUPPORTED_OUTPUT_EXTENSIONS:
        raise ValueError(f"Unsupported output image extension: {extension}")
    return normalized


def _safe_component(value: str, *, default: str) -> str:
    normalized = _UNSAFE_COMPONENT.sub("-", value.strip()).strip("._-")
    if not normalized:
        return default
    return normalized[:64]
