"""Safe deletion helpers for manifest-listed output files."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.storage.manifest import resolve_manifest_output_path


@dataclass(frozen=True, slots=True)
class FileCleanupResult:
    """Summary of deleting manifest-listed files."""

    deleted_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: tuple[JSONDict, ...] = ()


def delete_manifest_output_files(
    run_dir: str | PathLike[str],
    output_paths: Sequence[str],
) -> FileCleanupResult:
    """Delete only files listed by relative manifest paths under one run directory."""

    resolved_outputs = tuple(
        resolve_manifest_output_path(run_dir, output_path) for output_path in tuple(dict.fromkeys(output_paths))
    )
    return _delete_resolved_files(resolved_outputs)


def _delete_resolved_files(output_paths: tuple[Path, ...]) -> FileCleanupResult:
    deleted_count = 0
    skipped_count = 0
    failed_count = 0
    errors: list[JSONDict] = []
    for output_path in output_paths:
        if not output_path.exists():
            skipped_count += 1
            continue
        if not output_path.is_file():
            failed_count += 1
            errors.append(_file_error(output_path, "not_a_file", "Manifest output path exists but is not a file."))
            continue
        try:
            output_path.unlink()
        except OSError as error:
            failed_count += 1
            errors.append(
                _file_error(
                    output_path,
                    "file_delete_failed",
                    "Manifest output file could not be deleted.",
                    exception_type=type(error).__name__,
                )
            )
        else:
            deleted_count += 1

    return FileCleanupResult(
        deleted_count=deleted_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        errors=tuple(errors),
    )


def _file_error(output_path: Path, reason: str, message: str, **context: str) -> JSONDict:
    return {
        "filepath": str(output_path),
        "reason": reason,
        "message": message,
        **context,
    }
