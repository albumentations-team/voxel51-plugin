"""Arrange augmentation editor sections and action controls."""

from __future__ import annotations

from collections.abc import Mapping

import fiftyone.operators.types as types

from albumentationsx_plugin.core import (
    PIPELINE_STEP_COUNT_FIELD_NAME,
    RUN_LABEL_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.editor_draft import (
    ACTION_LABELS,
    EDITOR_ACTION,
    PREVIOUS_SELECTION,
    RETURN_ERRORS,
    REVIEWED_SELECTION,
    editor_action,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import (
    ANNOTATION_FIELD_GROUP_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.forms.editor_fields import (
    ANNOTATION_COMPATIBILITY_WARNING_FIELD_NAME,
    ANNOTATION_SECTION_FIELD_NAME,
    AUGMENT_VALIDATION_WARNING_FIELD_NAME,
    EXECUTION_MODE_GUIDANCE_FIELD_NAME,
    OUTPUTS_PER_SAMPLE_FIELD_NAME,
    STAGE_SECTION_FIELD_PREFIX,
)
from albumentationsx_plugin.hosts.fiftyone.forms.editor_values import _selected_outputs_per_sample
from albumentationsx_plugin.hosts.fiftyone.forms.sections import add_collapsible_section
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    SAVE_PRESET_NAME_FIELD_NAME,
)


def _arrange_editor(
    inputs: types.Object,
    params: Mapping[str, object],
    *,
    selected_sample_ids: tuple[str, ...],
    source_count: int | None,
) -> types.Object:
    arranged = types.Object()
    action = editor_action(params)
    choices = types.DropdownView()
    for value, label in ACTION_LABELS.items():
        choices.add_choice(value, label=label)
    arranged.enum(EDITOR_ACTION, choices.values(), default=action, required=True, label="Action", view=choices)
    if params.get(RETURN_ERRORS):
        arranged.view(
            "_previous_execution_error",
            types.Warning(
                label="Previous attempt needs attention",
                description=str(params[RETURN_ERRORS]) + " Your settings are preserved below.",
            ),
        )
    if AUGMENT_VALIDATION_WARNING_FIELD_NAME in inputs.properties:
        arranged.add_property(
            AUGMENT_VALIDATION_WARNING_FIELD_NAME, inputs.properties[AUGMENT_VALIDATION_WARNING_FIELD_NAME]
        )
    arranged.add_property(EXECUTION_SCOPE_FIELD_NAME, inputs.properties[EXECUTION_SCOPE_FIELD_NAME])
    summary = (
        f"Source samples in this scope: {source_count if source_count is not None else 'unknown'}. "
        f"Selected now: {len(selected_sample_ids)}. "
        f"Outputs per source: {_selected_outputs_per_sample(params.get(OUTPUTS_PER_SAMPLE_FIELD_NAME))}. "
        "Creation uses the scope shown above. Preview uses up to 3 selected samples and creates no dataset samples."
    )
    arranged.view("_source_summary", types.Notice(label="Source and outputs", description=summary))
    if action == "validate":
        arranged.view(
            "_validation_scope",
            types.Notice(
                label="Validation scope",
                description="Reads every source image and selected annotation, checks known crop dimensions, and executes every planned output in memory. Creates no files or runs. Stochastic branches can differ on a later run; output write permissions and future input changes are not checked.",
            ),
        )
    if action == "save":
        arranged.view(
            "_save_validation_scope",
            types.Notice(
                label="Pipeline validation",
                description="Saving checks configuration and annotation compatibility. Use Validate without creating samples to check this pipeline against source images before creation.",
            ),
        )
    previous = params.get(PREVIOUS_SELECTION)
    if isinstance(previous, list) and set(previous) != set(selected_sample_ids):
        arranged.view(
            "_selection_changed",
            types.Warning(
                label="Selection changed",
                description=f"The previous draft used {len(previous)} selected sample(s); now {len(selected_sample_ids)} are selected. Review this scope before creating samples.",
            ),
        )
    arranged.list(REVIEWED_SELECTION, types.String(), default=list(selected_sample_ids), view=types.HiddenView())
    for name in (PIPELINE_STEP_COUNT_FIELD_NAME, OUTPUTS_PER_SAMPLE_FIELD_NAME):
        prop = inputs.properties[name]
        prop.view.space = 6
        arranged.add_property(name, prop)
    for name, prop in inputs.properties.items():
        if (
            name.startswith((STAGE_SECTION_FIELD_PREFIX + "_", "_stage_parameters_", "_stage_target_", "_stage_help_"))
            or name == "transform"
            or (name.startswith("step_") and name.endswith("_transform"))
        ):
            arranged.add_property(name, prop)
    for name in (
        ANNOTATION_SECTION_FIELD_NAME,
        ANNOTATION_COMPATIBILITY_WARNING_FIELD_NAME,
        ANNOTATION_FIELD_GROUP_NAME,
    ):
        if name in inputs.properties:
            arranged.add_property(name, inputs.properties[name])
    groups = (
        (
            "_pipeline_library",
            "Load a saved pipeline or run",
            lambda n: n.startswith("_pipeline_") or n == "pipeline_load_source" or n == "_load_pipeline",
        ),
        ("_save_options", "Save pipeline settings", lambda n: n.startswith("save_preset_")),
        ("_run_options", "Run options", lambda n: n in (RUN_LABEL_FIELD_NAME, EXECUTION_MODE_GUIDANCE_FIELD_NAME)),
        ("_compatibility_details", "Compatibility details", lambda n: n.startswith("_dataset_compatibility")),
        ("_metadata_details", "Output metadata details", lambda n: n == "_output_metadata_policy"),
    )
    for key, label, matches in groups:
        group = types.Object()
        for name, prop in inputs.properties.items():
            if name not in arranged.properties and matches(name):
                group.add_property(name, prop)
        if key == "_save_options" and action == "save":
            group.properties[SAVE_PRESET_NAME_FIELD_NAME].required = True
        add_collapsible_section(arranged, key, label, group, expanded=key == "_save_options" and action == "save")
    return arranged
