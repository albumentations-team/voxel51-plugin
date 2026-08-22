"""Plugin-owned storage paths for generated augmentation runs."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from os import PathLike
from pathlib import Path
from typing import Final

PLUGIN_STORAGE_DIRNAME: Final[str] = "albumentationsx-plugin"
MAX_RUN_LABEL_SLUG_LENGTH: Final[int] = 48
MAX_PRESET_KEY_LENGTH: Final[int] = 96
_HASH_SUFFIX_LENGTH: Final[int] = 10

_UNSAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")
_UNSAFE_RUN_LABEL = re.compile(r"[^a-z0-9]+")


def build_run_key(
    *,
    now: datetime | None = None,
    suffix: str | None = None,
    run_label: str | None = None,
) -> str:
    """Build a readable unique key for one augmentation run."""

    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix = suffix or uuid.uuid4().hex[:8]
    run_key = f"albumentationsx-{timestamp}-{_safe_component(unique_suffix, default='run')}"
    label_slug = slugify_run_label(run_label)
    return f"{label_slug}-{run_key}" if label_slug else run_key


def slugify_run_label(value: str | None) -> str:
    """Return a bounded, path-safe slug for an optional user-facing run label."""

    if value is None:
        return ""

    normalized = _UNSAFE_RUN_LABEL.sub("-", value.casefold().strip()).strip("-")
    if not normalized:
        return ""
    return normalized[:MAX_RUN_LABEL_SLUG_LENGTH].strip("-")


def build_preset_key(name: str) -> str:
    """Return a stable path-safe key for a user-facing preset name."""

    normalized = _UNSAFE_RUN_LABEL.sub("-", name.casefold().strip()).strip("-")
    return (normalized or "preset")[:MAX_PRESET_KEY_LENGTH].strip("-") or "preset"


def default_storage_root(*, home: str | PathLike[str] | None = None) -> Path:
    """Return the base directory for plugin-owned output files."""

    root_home = Path.home() if home is None else Path(home).expanduser()
    return root_home / ".fiftyone" / PLUGIN_STORAGE_DIRNAME


def build_dataset_run_dir(
    dataset_name: str,
    run_key: str,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> Path:
    """Return the plugin-owned run directory for one dataset and run key."""

    root = default_storage_root() if storage_root is None else Path(storage_root).expanduser()
    dataset_component = _safe_component(dataset_name, default="dataset", include_hash=True)
    return root / dataset_component / _safe_component(run_key, default="run")


def build_preset_dir(*, storage_root: str | PathLike[str] | None = None) -> Path:
    """Return the plugin-owned shared preset directory."""

    root = default_storage_root() if storage_root is None else Path(storage_root).expanduser()
    return root / "presets"


def _safe_component(value: str, *, default: str, include_hash: bool = False) -> str:
    normalized = _UNSAFE_COMPONENT.sub("-", value.strip()).strip("._-")
    if not normalized:
        normalized = default
    if not include_hash:
        return normalized[:96]

    digest = sha256(value.encode("utf-8")).hexdigest()[:_HASH_SUFFIX_LENGTH]
    suffix = f"-{digest}"
    base_length = 96 - len(suffix)
    base = normalized[:base_length].strip("._-") or default
    return f"{base}{suffix}"
