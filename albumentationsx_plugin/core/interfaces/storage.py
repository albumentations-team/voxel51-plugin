"""Run persistence and output storage interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from albumentationsx_plugin.core.contracts import RunManifest
from albumentationsx_plugin.core.serialization import JSONDict


@runtime_checkable
class RunStore(Protocol):
    """Persistence boundary for augmentation run manifests."""

    def save_manifest(self, manifest: RunManifest) -> None:
        """Persist or replace a run manifest atomically enough for the backend."""
        ...

    def load_manifest(self, run_key: str) -> RunManifest:
        """Load one manifest by exact run key."""
        ...

    def list_run_keys(self) -> tuple[str, ...]:
        """Return available run keys for the active dataset or workspace."""
        ...

    def delete_manifest(self, run_key: str) -> None:
        """Delete manifest metadata after cleanup has succeeded."""
        ...


@runtime_checkable
class OutputStorageBackend(Protocol):
    """Storage boundary for plugin-created output media files."""

    def prepare_run(self, run_key: str) -> None:
        """Create or verify the plugin-owned directory for a run."""
        ...

    def write_output(self, run_key: str, relative_path: str, data: bytes) -> str:
        """Write output bytes and return the manifest-safe relative path."""
        ...

    def delete_outputs(self, manifest: RunManifest) -> JSONDict:
        """Delete files listed in the manifest and return a JSON cleanup report."""
        ...
