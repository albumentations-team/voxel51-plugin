"""Storage helpers for plugin-owned files and manifests."""

from albumentationsx_plugin.storage.cleanup import FileCleanupResult, delete_manifest_output_files
from albumentationsx_plugin.storage.manifest import (
    MANIFEST_FILENAME,
    FileRunStore,
    resolve_manifest_output_path,
)
from albumentationsx_plugin.storage.paths import (
    MAX_RUN_LABEL_SLUG_LENGTH,
    PLUGIN_STORAGE_DIRNAME,
    build_dataset_run_dir,
    build_preset_dir,
    build_preset_key,
    build_run_key,
    default_storage_root,
    slugify_run_label,
)
from albumentationsx_plugin.storage.presets import PRESET_FILE_SUFFIX, FilePipelinePresetStore

__all__ = [
    "FileCleanupResult",
    "FilePipelinePresetStore",
    "FileRunStore",
    "MANIFEST_FILENAME",
    "MAX_RUN_LABEL_SLUG_LENGTH",
    "PRESET_FILE_SUFFIX",
    "PLUGIN_STORAGE_DIRNAME",
    "build_dataset_run_dir",
    "build_preset_dir",
    "build_preset_key",
    "build_run_key",
    "delete_manifest_output_files",
    "default_storage_root",
    "resolve_manifest_output_path",
    "slugify_run_label",
]
