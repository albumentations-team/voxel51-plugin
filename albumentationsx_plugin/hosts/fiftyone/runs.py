"""FiftyOne custom run helpers for AlbumentationsX executions."""

from __future__ import annotations

import re
from os import PathLike
from pathlib import Path

import fiftyone as fo
from fiftyone.core.runs import RunConfig, RunResults

from albumentationsx_plugin.core import RUN_LABEL_FIELD_NAME, RUN_LABEL_SLUG_METADATA_KEY, RunManifest

FIFTYONE_RUN_METHOD = "albumentationsx_plugin"

_UNSAFE_RUN_KEY_CHAR = re.compile(r"\W+")


def build_fiftyone_run_key(run_key: str) -> str:
    """Convert the public plugin run key into a FiftyOne-compatible identifier."""

    candidate = _UNSAFE_RUN_KEY_CHAR.sub("_", run_key).strip("_")
    if not candidate or candidate[0].isdigit():
        candidate = f"albumentationsx_{candidate}"
    return candidate


def register_fiftyone_run(
    dataset: fo.Dataset,
    manifest: RunManifest,
    *,
    manifest_path: str | PathLike[str],
    overwrite: bool = False,
) -> str:
    """Register manifest metadata in FiftyOne's generic custom run store."""

    manifest_file = Path(manifest_path)
    fiftyone_run_key = build_fiftyone_run_key(manifest.run_key)
    run_label = _metadata_str(manifest, RUN_LABEL_FIELD_NAME)
    run_label_slug = _metadata_str(manifest, RUN_LABEL_SLUG_METADATA_KEY)
    config = RunConfig(
        method=FIFTYONE_RUN_METHOD,
        plugin_run_key=manifest.run_key,
        run_label=run_label,
        run_label_slug=run_label_slug,
        plugin_version=manifest.plugin_version,
        dependency_versions=dict(manifest.dependency_versions),
        pipeline=manifest.pipeline.to_dict(),
        manifest_path=str(manifest_file),
        output_dir=str(manifest_file.parent),
    )
    results = RunResults(
        dataset,
        config,
        fiftyone_run_key,
        manifest=manifest.to_dict(),
        manifest_path=str(manifest_file),
        plugin_run_key=manifest.run_key,
        run_label=run_label,
        run_label_slug=run_label_slug,
    )
    dataset.register_run(
        fiftyone_run_key,
        config,
        results=results,
        overwrite=overwrite,
        cleanup=False,
        cache=True,
    )
    return fiftyone_run_key


def _metadata_str(manifest: RunManifest, name: str) -> str:
    value = manifest.metadata.get(name, "")
    return value if isinstance(value, str) else ""
