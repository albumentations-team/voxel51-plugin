"""Previous-run preset helpers for FiftyOne augmentation forms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import PathLike
from typing import Final

from albumentationsx_plugin.core import (
    MAX_PIPELINE_STEPS,
    PIPELINE_STEP_COUNT_FIELD_NAME,
    PipelineConfig,
    pipeline_step_field_name,
)
from albumentationsx_plugin.storage import MANIFEST_FILENAME, FileRunStore

PREVIOUS_RUN_KEY_FIELD_NAME: Final[str] = "previous_run_key"
STORAGE_ROOT_PARAM_NAME: Final[str] = "_storage_root"


@dataclass(frozen=True, slots=True)
class PreviousRunPreset:
    """Operator params derived from a saved run manifest."""

    run_key: str
    operator_params: Mapping[str, object]
    manifest_path: str


def selected_previous_run_key(params: Mapping[str, object]) -> str:
    """Return the selected previous run key, if any."""

    value = params.get(PREVIOUS_RUN_KEY_FIELD_NAME)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def storage_root_from_params(params: Mapping[str, object]) -> str | PathLike[str] | None:
    """Return the test-only storage root override from operator params."""

    value = params.get(STORAGE_ROOT_PARAM_NAME)
    if isinstance(value, str):
        return value
    return value if isinstance(value, PathLike) else None


def list_previous_run_preset_keys(
    dataset: object | None,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> tuple[str, ...]:
    """Return manifest-backed run keys that can be reused as form presets."""

    dataset_name = _dataset_name(dataset)
    if not dataset_name:
        return ()

    store = FileRunStore(dataset_name, storage_root=storage_root)
    if not store.dataset_dir.exists():
        return ()

    run_keys: list[str] = []
    for manifest_path in sorted(store.dataset_dir.glob(f"*/{MANIFEST_FILENAME}")):
        try:
            manifest = store.load_manifest(manifest_path.parent.name)
        except Exception:
            continue
        run_keys.append(manifest.run_key)
    return tuple(run_keys)


def load_previous_run_preset(
    dataset: object | None,
    run_key: str,
    *,
    storage_root: str | PathLike[str] | None = None,
) -> PreviousRunPreset:
    """Load one previous run and convert its pipeline config into operator params."""

    dataset_name = _required_dataset_name(dataset)
    store = FileRunStore(dataset_name, storage_root=storage_root)
    manifest = store.load_manifest(run_key)
    return PreviousRunPreset(
        run_key=manifest.run_key,
        operator_params=operator_params_from_pipeline(manifest.pipeline),
        manifest_path=str(store.manifest_path(manifest.run_key)),
    )


def params_with_previous_run_preset(
    dataset: object | None,
    params: Mapping[str, object],
    *,
    storage_root: str | PathLike[str] | None = None,
) -> dict[str, object]:
    """Overlay saved pipeline params under user-provided operator params."""

    run_key = selected_previous_run_key(params)
    if not run_key:
        return dict(params)

    preset = load_previous_run_preset(dataset, run_key, storage_root=storage_root)
    return {**preset.operator_params, **params}


def operator_params_from_pipeline(pipeline: PipelineConfig) -> dict[str, object]:
    """Convert a persisted pipeline config back into FiftyOne operator params."""

    transforms = pipeline.transforms[:MAX_PIPELINE_STEPS]
    params: dict[str, object] = {
        PIPELINE_STEP_COUNT_FIELD_NAME: len(transforms),
        "outputs_per_sample": pipeline.outputs_per_sample,
    }
    for step_index, transform in enumerate(transforms, start=1):
        params[pipeline_step_field_name(step_index, "transform")] = transform.name
        for parameter_name, value in transform.params.items():
            params[pipeline_step_field_name(step_index, parameter_name)] = value
    return params


def _dataset_name(dataset: object | None) -> str:
    name = getattr(dataset, "name", "") if dataset is not None else ""
    return name.strip() if isinstance(name, str) and name.strip() else ""


def _required_dataset_name(dataset: object | None) -> str:
    dataset_name = _dataset_name(dataset)
    if not dataset_name:
        raise ValueError("A dataset with a name is required to load previous run settings.")
    return dataset_name


__all__ = [
    "PREVIOUS_RUN_KEY_FIELD_NAME",
    "STORAGE_ROOT_PARAM_NAME",
    "PreviousRunPreset",
    "list_previous_run_preset_keys",
    "load_previous_run_preset",
    "operator_params_from_pipeline",
    "params_with_previous_run_preset",
    "selected_previous_run_key",
    "storage_root_from_params",
]
