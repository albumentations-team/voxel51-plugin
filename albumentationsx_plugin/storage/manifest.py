"""File-backed run manifest persistence."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any

from albumentationsx_plugin.core import MediaIOError, RunManifest
from albumentationsx_plugin.storage.paths import build_dataset_run_dir, default_storage_root

MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True, slots=True)
class FileRunStore:
    """Persist run manifests under the plugin-owned dataset storage directory."""

    dataset_name: str
    storage_root: str | PathLike[str] | None = None

    @property
    def dataset_dir(self) -> Path:
        """Return the plugin-owned directory for all runs in this dataset."""

        root = default_storage_root() if self.storage_root is None else Path(self.storage_root).expanduser()
        return build_dataset_run_dir(self.dataset_name, "_placeholder_", storage_root=root).parent

    def run_dir(self, run_key: str) -> Path:
        """Return the plugin-owned directory for one run key."""

        return build_dataset_run_dir(self.dataset_name, run_key, storage_root=self.storage_root)

    def manifest_path(self, run_key: str) -> Path:
        """Return the manifest path for one run key."""

        return self.run_dir(run_key) / MANIFEST_FILENAME

    def save_manifest(self, manifest: RunManifest) -> None:
        """Atomically write a manifest JSON file for one run."""

        run_dir = self.run_dir(manifest.run_key)
        _validate_manifest_paths(run_dir, manifest)
        manifest_path = run_dir / MANIFEST_FILENAME
        run_dir.mkdir(parents=True, exist_ok=True)

        temporary_path = _write_temporary_manifest(manifest_path, manifest)
        try:
            temporary_path.replace(manifest_path)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise _manifest_error(
                manifest_path,
                "Run manifest could not be moved into place.",
                reason="manifest_write_failed",
                exception_type=type(error).__name__,
            ) from error

    def load_manifest(self, run_key: str) -> RunManifest:
        """Load one manifest by exact run key."""

        manifest_path = self.manifest_path(run_key)
        if not manifest_path.exists():
            raise _manifest_error(manifest_path, "Run manifest does not exist.", reason="missing_manifest")
        if not manifest_path.is_file():
            raise _manifest_error(manifest_path, "Run manifest path is not a file.", reason="manifest_not_file")

        try:
            with manifest_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise _manifest_error(
                manifest_path,
                "Run manifest could not be read as valid JSON.",
                reason="invalid_manifest_json",
                exception_type=type(error).__name__,
            ) from error

        if not isinstance(payload, dict):
            raise _manifest_error(manifest_path, "Run manifest must be a JSON object.", reason="invalid_manifest_shape")
        manifest = RunManifest.from_dict(payload)
        _validate_manifest_paths(self.run_dir(manifest.run_key), manifest)
        return manifest

    def list_run_keys(self) -> tuple[str, ...]:
        """Return persisted run keys for this dataset."""

        if not self.dataset_dir.exists():
            return ()

        run_keys: list[str] = []
        for manifest_path in sorted(self.dataset_dir.glob(f"*/{MANIFEST_FILENAME}")):
            run_keys.append(self.load_manifest(manifest_path.parent.name).run_key)
        return tuple(run_keys)

    def delete_manifest(self, run_key: str) -> None:
        """Delete one manifest file if it exists."""

        self.manifest_path(run_key).unlink(missing_ok=True)


def resolve_manifest_output_path(run_dir: str | PathLike[str], relative_path: str | PathLike[str]) -> Path:
    """Resolve a manifest output path and prove that it stays inside the run directory."""

    root = Path(run_dir).expanduser().resolve()
    raw_relative_path = Path(relative_path)
    if raw_relative_path.is_absolute():
        raise _manifest_error(
            raw_relative_path,
            "Manifest output path must be relative to the run directory.",
            reason="absolute_manifest_output_path",
        )
    if not raw_relative_path.parts or ".." in raw_relative_path.parts:
        raise _manifest_error(
            root / raw_relative_path,
            "Manifest output path must not contain parent traversal.",
            reason="unsafe_manifest_output_path",
            relative_path=str(relative_path),
        )

    output_path = (root / raw_relative_path).resolve()
    try:
        output_path.relative_to(root)
    except ValueError as error:
        raise _manifest_error(
            output_path,
            "Manifest output path escapes the run directory.",
            reason="unsafe_manifest_output_path",
            relative_path=str(relative_path),
        ) from error

    return output_path


def _validate_manifest_paths(run_dir: Path, manifest: RunManifest) -> None:
    for relative_path in manifest.output_paths:
        resolve_manifest_output_path(run_dir, relative_path)


def _write_temporary_manifest(manifest_path: Path, manifest: RunManifest) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".manifest.",
            suffix=".tmp",
            dir=manifest_path.parent,
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(manifest.to_dict(), file, indent=2, sort_keys=True)
            file.write("\n")
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise _manifest_error(
            manifest_path,
            "Run manifest could not be written.",
            reason="manifest_write_failed",
            exception_type=type(error).__name__,
        ) from error

    return temporary_path


def _manifest_error(filepath: str | PathLike[str], message: str, *, reason: str, **context: Any) -> MediaIOError:
    return MediaIOError(
        filepath=str(filepath),
        message=message,
        context={"reason": reason, **context},
    )
