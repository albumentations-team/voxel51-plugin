"""File-backed storage for reusable pipeline presets."""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any

from albumentationsx_plugin.core import MediaIOError, PipelinePreset
from albumentationsx_plugin.storage.paths import build_preset_dir, build_preset_key

PRESET_FILE_SUFFIX = ".json"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FilePipelinePresetStore:
    """Persist named presets under the shared plugin-owned preset directory."""

    storage_root: str | PathLike[str] | None = None

    @property
    def preset_dir(self) -> Path:
        """Return the shared preset directory."""

        return build_preset_dir(storage_root=self.storage_root)

    def preset_path(self, preset_key: str) -> Path:
        """Return the JSON file path for one preset key."""

        safe_key = _safe_preset_key(preset_key)
        return self.preset_dir / f"{safe_key}{PRESET_FILE_SUFFIX}"

    def save_preset(self, preset: PipelinePreset) -> None:
        """Atomically write a preset JSON file."""

        preset_path = self.preset_path(preset.key)
        preset_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = _write_temporary_preset(preset_path, preset)
        try:
            temporary_path.replace(preset_path)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise _preset_error(
                preset_path,
                "Pipeline preset could not be moved into place.",
                reason="preset_write_failed",
                exception_type=type(error).__name__,
            ) from error

    def load_preset(self, preset_key: str) -> PipelinePreset:
        """Load one preset by exact key."""

        preset_path = self.preset_path(preset_key)
        if not preset_path.exists():
            raise _preset_error(preset_path, "Pipeline preset does not exist.", reason="missing_preset")
        if not preset_path.is_file():
            raise _preset_error(preset_path, "Pipeline preset path is not a file.", reason="preset_not_file")

        try:
            with preset_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise _preset_error(
                preset_path,
                "Pipeline preset could not be read as valid JSON.",
                reason="invalid_preset_json",
                exception_type=type(error).__name__,
            ) from error

        if not isinstance(payload, dict):
            raise _preset_error(preset_path, "Pipeline preset must be a JSON object.", reason="invalid_preset_shape")
        preset = PipelinePreset.from_dict(payload)
        expected_key = _safe_preset_key(preset_key)
        if preset.key != expected_key:
            raise _preset_error(
                preset_path,
                "Pipeline preset key does not match its file name.",
                reason="preset_key_mismatch",
                preset_key=preset.key,
                expected_key=expected_key,
            )
        return preset

    def list_presets(self) -> tuple[PipelinePreset, ...]:
        """Return all readable presets sorted by display name then key."""

        if not self.preset_dir.exists():
            return ()

        presets: list[PipelinePreset] = []
        for preset_path in sorted(self.preset_dir.glob(f"*{PRESET_FILE_SUFFIX}")):
            try:
                presets.append(self.load_preset(preset_path.stem))
            except Exception as error:
                _LOGGER.debug("Skipping unreadable pipeline preset %s", preset_path, exc_info=error)
                continue
        return tuple(sorted(presets, key=lambda preset: (preset.name.casefold(), preset.key)))

    def list_preset_keys(self) -> tuple[str, ...]:
        """Return all readable preset keys."""

        return tuple(preset.key for preset in self.list_presets())

    def delete_preset(self, preset_key: str) -> None:
        """Delete a preset JSON file if it exists."""

        self.preset_path(preset_key).unlink(missing_ok=True)


def _safe_preset_key(value: str) -> str:
    return build_preset_key(value)


def _write_temporary_preset(preset_path: Path, preset: PipelinePreset) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".preset.",
            suffix=".tmp",
            dir=preset_path.parent,
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(preset.to_dict(), file, indent=2, sort_keys=True)
            file.write("\n")
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise _preset_error(
            preset_path,
            "Pipeline preset could not be written.",
            reason="preset_write_failed",
            exception_type=type(error).__name__,
        ) from error

    return temporary_path


def _preset_error(filepath: str | PathLike[str], message: str, *, reason: str, **context: Any) -> MediaIOError:
    return MediaIOError(
        filepath=str(filepath),
        message=message,
        context={"reason": reason, **context},
    )


__all__ = [
    "PRESET_FILE_SUFFIX",
    "FilePipelinePresetStore",
]
