"""Read portable presets from text or a local JSON file without writing storage."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from albumentationsx_plugin.core import MediaIOError, PipelinePreset
from albumentationsx_plugin.storage.presets import validate_preset_key

MAX_IMPORT_BYTES = 4 * 1024 * 1024


def read_preset_json_file(value: object) -> str:
    """Read a bounded, regular UTF-8 JSON file on the FiftyOne server."""
    if not isinstance(value, str) or not value.strip():
        raise _error("missing_import_path", "Enter an absolute local path to a saved pipeline .json file.")
    raw_path = value.strip()
    if any(ord(char) < 32 for char in raw_path) or "://" in raw_path:
        raise _error("invalid_import_path", "Use a local file path without URLs or control characters.")
    try:
        path = Path(raw_path).expanduser()
        if not path.is_absolute() or ".." in path.parts:
            raise _error("invalid_import_path", "Use an absolute file path without '..' components.")
        if path.suffix.lower() != ".json":
            raise _error("non_json_import_file", "Only .json files can be imported.")
        if path.is_symlink():
            raise _error("unsafe_import_path", "Choose the actual JSON file, not a symbolic link.")
        if not stat.S_ISREG(path.stat().st_mode):
            raise _error("import_not_file", "The import path must be a regular JSON file.")
        # NONBLOCK prevents a concurrently substituted FIFO from blocking open.
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        )
        with os.fdopen(descriptor, "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise _error("import_not_file", "The import path must be a regular JSON file.")
            data = file.read(MAX_IMPORT_BYTES + 1)
        if len(data) > MAX_IMPORT_BYTES:
            raise _error("import_too_large", "Saved pipeline JSON must be at most 4 MiB.")
        return data.decode("utf-8-sig")
    except FileNotFoundError as error:
        raise _error("missing_import_file", "JSON file not found on the FiftyOne server.", raw_path) from error
    except IsADirectoryError as error:
        raise _error("import_not_file", "The import path must be a regular JSON file.", raw_path) from error
    except UnicodeError as error:
        raise _error("invalid_import_encoding", "Saved pipeline files must contain UTF-8 JSON.", raw_path) from error
    except (OSError, ValueError, RuntimeError) as error:
        raise _error("unreadable_import_file", "The local JSON file could not be read.", raw_path) from error


def parse_preset_json(value: object) -> PipelinePreset:
    """Decode the same PipelinePreset schema for either import source."""
    if not isinstance(value, str) or not value.strip():
        raise _error("missing_preset_json", "Paste the full Importable pipeline JSON from Export saved pipeline.")
    try:
        payload = json.loads(value, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as error:
        raise _error(
            "invalid_preset_json", "Saved pipeline JSON could not be parsed. Paste the full JSON object."
        ) from error
    if isinstance(payload, list) or (
        isinstance(payload, dict) and "pipeline" not in payload and {"key", "path", "presets"}.intersection(payload)
    ):
        raise _error(
            "summary_json_not_importable",
            "This is a summary, not a saved pipeline. Copy Importable pipeline JSON from Export saved pipeline.",
        )
    if not isinstance(payload, dict):
        raise _error("invalid_preset_shape", "Saved pipeline JSON must be one complete object.")
    try:
        preset = PipelinePreset.from_dict(payload)
    except (TypeError, ValueError, KeyError) as error:
        raise _error("invalid_preset_schema", f"Invalid saved pipeline: {error}") from error
    validate_preset_key(preset.key)
    return preset


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON value: {value}")


def _error(reason: str, message: str, filepath: str = "") -> MediaIOError:
    return MediaIOError(filepath=filepath, message=message, context={"reason": reason})
