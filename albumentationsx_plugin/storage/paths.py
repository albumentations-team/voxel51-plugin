"""Plugin-owned storage paths for generated augmentation runs."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from os import PathLike
from pathlib import Path

PLUGIN_STORAGE_DIRNAME = "albumentationsx-plugin"

_UNSAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")


def build_run_key(*, now: datetime | None = None, suffix: str | None = None) -> str:
    """Build a readable unique key for one augmentation run."""

    timestamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix = suffix or uuid.uuid4().hex[:8]
    return f"albumentationsx-{timestamp}-{_safe_component(unique_suffix, default='run')}"


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
    return root / _safe_component(dataset_name, default="dataset") / _safe_component(run_key, default="run")


def _safe_component(value: str, *, default: str) -> str:
    normalized = _UNSAFE_COMPONENT.sub("-", value.strip()).strip("._-")
    if not normalized:
        return default
    return normalized[:96]
