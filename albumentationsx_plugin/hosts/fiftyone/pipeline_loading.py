"""Copy saved pipelines into independent, editable FiftyOne form drafts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from typing import Any, Final
from uuid import uuid4

from albumentationsx_plugin.albumentations_backend.image_pipeline import validate_fixed_pipeline_config
from albumentationsx_plugin.albumentations_backend.parameters import AlbuSpecParameterSchemaProvider
from albumentationsx_plugin.core import (
    MAX_PIPELINE_STEPS,
    FieldKind,
    PipelineConfig,
    UnsupportedTransformError,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.fields import (
    ANNOTATION_FIELD_PARAM_PREFIX,
    annotation_field_param_name,
    list_supported_annotation_fields,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import (
    ANNOTATION_FIELD_GROUP_NAME,
    DRAFT_ID,
    EDITOR_SECTION_FIELDS,
    draft_parameter_group_name,
    flatten_fiftyone_form_groups,
    stage_parameter_group_name,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import validate_pipeline_preset
from albumentationsx_plugin.hosts.fiftyone.presets import operator_params_from_pipeline
from albumentationsx_plugin.storage import FilePipelinePresetStore, FileRunStore

LOAD_SOURCE: Final[str] = "pipeline_load_source"
LOAD_BUTTON: Final[str] = "_load_pipeline"
ORIGIN_SOURCE: Final[str] = "_pipeline_origin_source"
ORIGIN_LABEL: Final[str] = "_pipeline_origin_label"
LOAD_NOTICE: Final[str] = "_pipeline_load_notice"
AUGMENT_OPERATOR_URI: Final[str] = "@albumentations/albumentationsx/augment_with_albumentationsx"
ANNOTATION_SELECTION: Final[str] = "annotation_selection"

# These belong to the current execution, not the reusable pipeline. An allowlist
# also removes every old stage parameter, including stage 1's unprefixed keys.
_EXECUTION_FIELDS: Final[tuple[str, ...]] = (
    "_editor_action",
    "_reviewed_selection",
    "execution_scope",
    "run_label",
    "dry_run",
    "preview_only",
    "save_preset_only",
    "save_preset_name",
    "save_preset_description",
    "save_preset_mode",
    "save_preset_target",
    "_storage_root",
)


def pipeline_draft_prompt_params(draft: Mapping[str, object]) -> dict[str, object]:
    """Populate nested controls, including checkbox values, in the actual App.

    Schema defaults do not populate nested groups when the prompt already has
    initial params. Match the editor's data paths instead of relying on defaults.
    """
    params = dict(draft)
    schema_provider = AlbuSpecParameterSchemaProvider()
    for step in range(1, MAX_PIPELINE_STEPS + 1):
        transform = params.get(pipeline_step_field_name(step, "transform"))
        if not isinstance(transform, str):
            continue
        group: dict[str, object] = {}
        for name in (pipeline_stage_enabled_field_name(step), pipeline_stage_order_field_name(step)):
            if name in params:
                group[name] = params.pop(name)
        try:
            fields = schema_provider.get_parameter_schema(transform)
        except (UnsupportedTransformError, ModuleNotFoundError):
            # Returning from a failed execution must also work for invalid
            # transforms or unavailable runtime dependencies.
            fields = ()
        for field in fields:
            name = pipeline_step_field_name(step, field.name)
            if name in params:
                value = params.pop(name)
                group[name] = (
                    json.dumps(value) if field.kind is FieldKind.JSON and not isinstance(value, str) else value
                )
        params[stage_parameter_group_name(step)] = group
    annotations = {name: params.pop(name) for name in tuple(params) if name.startswith(ANNOTATION_FIELD_PARAM_PREFIX)}
    if annotations:
        params[ANNOTATION_FIELD_GROUP_NAME] = annotations
    for section, names in EDITOR_SECTION_FIELDS.items():
        group = {name: params.pop(name) for name in names if name in params}
        if group:
            params[section] = group
    draft_id = str(params[DRAFT_ID])
    return {DRAFT_ID: draft_id, draft_parameter_group_name(draft_id): params}


def load_pipeline_draft(
    dataset: Any,
    source: str,
    current_params: Mapping[str, object],
    *,
    storage_root: str | PathLike[str] | None = None,
) -> dict[str, object]:
    """Build a replacement snapshot; callers must explicitly apply it once.

    No run seed, replay, sample scope, or output identity is carried forward.
    The returned annotation checkboxes remain the only selection authority.
    """

    kind, separator, key = source.partition(":")
    if not separator or not key:
        raise ValueError("Choose a saved pipeline or a run from history.")
    if kind == "saved":
        preset = FilePipelinePresetStore(storage_root=storage_root).load_preset(key)
        validate_pipeline_preset(preset)
        pipeline = preset.pipeline
        selection = preset.metadata.get(ANNOTATION_SELECTION)
        label = f"Saved pipeline: {preset.name}"
        same_dataset = isinstance(selection, Mapping) and selection.get("source_dataset") == getattr(
            dataset, "name", None
        )
    elif kind == "run":
        manifest = FileRunStore(dataset.name, storage_root=storage_root).load_manifest(key)
        pipeline = manifest.pipeline
        selection = manifest.metadata.get("annotations")
        label = f"Run history: {key}"
        same_dataset = True
    else:
        raise ValueError("Unknown pipeline source. Choose a saved pipeline or a run from history.")

    validate_fixed_pipeline_config(pipeline)
    if len(pipeline.transforms) > MAX_PIPELINE_STEPS:
        raise ValueError(
            f"This pipeline has more than {MAX_PIPELINE_STEPS} stages and cannot be loaded without losing stages."
        )
    flat_params = flatten_fiftyone_form_groups(current_params)
    draft = {name: flat_params[name] for name in _EXECUTION_FIELDS if name in flat_params}
    if storage_root is not None:
        draft["_storage_root"] = str(storage_root)
    draft.update(operator_params_from_pipeline(pipeline))
    annotation_params, notice = _map_annotations(
        dataset, pipeline, selection, same_dataset=same_dataset, from_run=kind == "run"
    )
    draft.update(annotation_params)
    draft.update(
        {LOAD_SOURCE: source, ORIGIN_SOURCE: source, ORIGIN_LABEL: label, LOAD_NOTICE: notice, DRAFT_ID: uuid4().hex}
    )
    draft["_draft_dataset"] = getattr(dataset, "name", None)
    return draft


def _map_annotations(
    dataset: Any,
    pipeline: PipelineConfig,
    selection: object,
    *,
    same_dataset: bool,
    from_run: bool,
) -> tuple[dict[str, object], str]:
    fields = list_supported_annotation_fields(dataset)
    current = {field.name: field for field in fields}
    saved_types: dict[str, str] = {}
    saved_names = set((*pipeline.target_fields, *pipeline.copy_fields))
    known = from_run or bool(saved_names)
    if isinstance(selection, Mapping):
        raw_fields = selection.get("selected_fields")
        if isinstance(raw_fields, list | tuple):
            known = True
            saved_names = set()
            for field in raw_fields:
                if isinstance(field, Mapping) and isinstance(field.get("field_name"), str):
                    name = str(field["field_name"])
                    saved_names.add(name)
                    if isinstance(field.get("label_type"), str):
                        saved_types[name] = str(field["label_type"])

    matched: set[str] = set()
    unresolved: list[str] = []
    for name in sorted(saved_names):
        if name not in current:
            unresolved.append(f"{name} (missing or unsupported)")
        elif name in saved_types and current[name].label_type != saved_types[name]:
            unresolved.append(f"{name} (type changed: {saved_types[name]} → {current[name].label_type})")
        elif name not in saved_types and not same_dataset:
            unresolved.append(f"{name} (saved field type unknown)")
        else:
            matched.add(name)

    messages = []
    if not known:
        messages.append(
            "This older saved pipeline has no annotation selection. All annotation fields were unchecked at load time; choose the fields to include below."
        )
    if unresolved:
        messages.append(
            "Not restored at load time: "
            + "; ".join(unresolved)
            + ". Choose replacement fields below, or leave them unchecked to omit them."
        )
    if not same_dataset and known:
        messages.append(
            "Annotations were matched by field name and label type. Other fields were left unchecked; review the selection below."
        )
    return {annotation_field_param_name(field.name): field.name in matched for field in fields}, " ".join(messages)
