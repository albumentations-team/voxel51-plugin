"""Storage helpers for plugin-owned files and manifests."""

from albumentationsx_plugin.storage.cleanup import FileCleanupResult, delete_manifest_output_files
from albumentationsx_plugin.storage.manifest import (
    MANIFEST_FILENAME,
    FileRunStore,
    resolve_manifest_output_path,
)
from albumentationsx_plugin.storage.paths import (
    PLUGIN_STORAGE_DIRNAME,
    build_dataset_run_dir,
    build_run_key,
    default_storage_root,
)

__all__ = [
    "FileCleanupResult",
    "FileRunStore",
    "MANIFEST_FILENAME",
    "PLUGIN_STORAGE_DIRNAME",
    "build_dataset_run_dir",
    "build_run_key",
    "delete_manifest_output_files",
    "default_storage_root",
    "resolve_manifest_output_path",
]
