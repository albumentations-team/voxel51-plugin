"""One explicit load action for saved pipelines and run history."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import fiftyone.operators.types as types

from albumentationsx_plugin.hosts.fiftyone.pipeline_loading import (
    AUGMENT_OPERATOR_URI,
    LOAD_BUTTON,
    LOAD_NOTICE,
    LOAD_SOURCE,
    ORIGIN_LABEL,
    ORIGIN_SOURCE,
    load_pipeline_draft,
    pipeline_draft_prompt_params,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import list_pipeline_presets
from albumentationsx_plugin.hosts.fiftyone.presets import list_previous_run_preset_keys, storage_root_from_params

_LOGGER = logging.getLogger(__name__)


def render_pipeline_loader(inputs: types.Object, dataset: Any, params: Mapping[str, object]) -> None:
    """Render a source picker without applying its selection to the current draft."""

    storage_root = storage_root_from_params(params)
    choices = types.AutocompleteView(label="Load pipeline", allow_user_input=False)
    choices.add_choice("", label="Current unsaved draft")
    try:
        for preset in list_pipeline_presets(storage_root=storage_root):
            choices.add_choice(f"saved:{preset.key}", label=f"Saved pipeline: {preset.name} ({preset.key})")
        for run_key in list_previous_run_preset_keys(dataset, storage_root=storage_root):
            choices.add_choice(f"run:{run_key}", label=f"From run history: {run_key}")
    except Exception as error:
        _LOGGER.debug("Could not list pipeline sources", exc_info=True)
        inputs.view(
            "_pipeline_sources_error",
            types.Warning(
                label="Pipeline library unavailable",
                description=f"Current draft is unchanged. Check access to pipeline storage and reopen the form. {type(error).__name__}.",
            ),
        )
    source = params.get(LOAD_SOURCE, "")
    if not isinstance(source, str):
        source = ""
    if source and source not in choices.values():
        choices.add_choice(source, label=source)
    inputs.enum(
        LOAD_SOURCE,
        choices.values(),
        default=source,
        label="Load pipeline",
        view=choices,
        description="Choose a source, then explicitly replace the draft. Selecting a source alone keeps your edits.",
    )
    origin = params.get(ORIGIN_LABEL)
    inputs.view(
        "_pipeline_draft",
        types.Notice(
            label="Editable draft",
            description=(
                f"Loaded from {origin}. " if isinstance(origin, str) and origin else "Current unsaved pipeline. "
            )
            + "Preview, run, and save use the values shown below. Every execution uses fresh randomness; loading from history does not replay an output.",
        ),
    )
    if source:
        render_pipeline_load_button(
            inputs,
            dataset,
            source,
            params,
            label="Reload and replace draft"
            if source == params.get(ORIGIN_SOURCE)
            else "Replace draft with selected pipeline",
        )
    notice = params.get(LOAD_NOTICE)
    if isinstance(notice, str) and notice:
        inputs.view(
            "_pipeline_annotation_mapping", types.Warning(label="Review loaded annotations", description=notice)
        )


def render_pipeline_load_button(
    inputs: types.Object, dataset: Any, source: str, params: Mapping[str, object], *, label: str
) -> None:
    """Open the augmentation editor with a snapshot through FiftyOne's prompt API."""
    try:
        draft = load_pipeline_draft(dataset, source, params, storage_root=storage_root_from_params(params))
        prompt_params = pipeline_draft_prompt_params(draft)
    except Exception as error:
        _LOGGER.debug("Could not load pipeline snapshot", exc_info=True)
        inputs.view(
            "_pipeline_load_error",
            types.Warning(
                label="Pipeline cannot be loaded",
                description=f"Current draft is unchanged. Choose another source or repair the saved pipeline. {type(error).__name__}: {str(error)[:300]}",
            ),
        )
    else:
        inputs.btn(
            LOAD_BUTTON,
            label=label,
            on_click=AUGMENT_OPERATOR_URI,
            prompt=True,
            params=prompt_params,
            description="Replaces stages, their parameters, outputs per sample, and annotation selection. Keeps current scope, run label, and execution mode.",
        )
