"""FiftyOne operator for managing shared AlbumentationsX saved pipelines."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import PipelinePreset
from albumentationsx_plugin.hosts.fiftyone.branding import ALBUMENTATIONS_ICON
from albumentationsx_plugin.hosts.fiftyone.forms.pipeline_loading import render_pipeline_load_button
from albumentationsx_plugin.hosts.fiftyone.preset_management import (
    ACTION_DELETE,
    ACTION_DUPLICATE,
    ACTION_EDIT,
    ACTION_EXPORT,
    ACTION_FIELD_NAME,
    ACTION_IMPORT,
    ACTION_INSPECT,
    ACTION_RENAME,
    CONFIRM_DELETE_FIELD_NAME,
    IMPORT_MODE_FIELD_NAME,
    IMPORT_PATH_FIELD_NAME,
    NEW_PRESET_NAME_FIELD_NAME,
    OVERWRITE_FIELD_NAME,
    PRESET_ACTIONS_REQUIRING_PRESET,
    PRESET_JSON_FIELD_NAME,
    PRESET_KEY_FIELD_NAME,
    PRESET_MANAGEMENT_ACTIONS,
    STORAGE_ROOT_PARAM_NAME,
    bool_param,
    execute_preset_management_action,
    json_dump,
    preset_edit_group,
    selected_management_action,
    selected_preset_key,
    storage_root_from_params,
    string_param,
)
from albumentationsx_plugin.storage import FilePipelinePresetStore

OPERATOR_NAME = "manage_albumentationsx_presets"
OPERATOR_LABEL = "AlbumentationsX · Saved pipelines"
PRESET_STORAGE_WARNING_FIELD_NAME = "_preset_storage_warning"
_LOGGER = logging.getLogger(__name__)


class ManageAlbumentationsXPresets(foo.Operator):
    """FiftyOne App operator that manages saved augmentation pipelines."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            icon=ALBUMENTATIONS_ICON,
            description="Inspect, export, import, edit, duplicate, and delete AlbumentationsX saved pipelines.",
            dynamic=True,
            allow_immediate_execution=True,
            allow_delegated_execution=False,
            allow_distributed_execution=False,
            risk_level=RiskLevel.HIGH,
        )

    # pyrefly: ignore[bad-override]
    def resolve_input(self, ctx: Any):
        params = _ctx_params(ctx)
        action = selected_management_action(params.get(ACTION_FIELD_NAME))
        store = FilePipelinePresetStore(storage_root=storage_root_from_params(params))
        presets, storage_warning = _safe_list_presets(store)

        inputs = types.Object()
        if storage_warning:
            inputs.message(
                PRESET_STORAGE_WARNING_FIELD_NAME,
                label="Saved pipeline storage",
                description=storage_warning,
            )
        inputs.enum(
            ACTION_FIELD_NAME,
            list(PRESET_MANAGEMENT_ACTIONS),
            label="Action",
            default=action,
            required=True,
            view=_action_view(),
        )

        if action in PRESET_ACTIONS_REQUIRING_PRESET:
            _add_preset_selector(inputs, params=params, presets=presets)
        if action in {ACTION_INSPECT, ACTION_EXPORT} and presets and getattr(ctx, "dataset", None) is not None:
            key = selected_preset_key(params.get(PRESET_KEY_FIELD_NAME), presets)
            render_pipeline_load_button(
                inputs, ctx.dataset, f"saved:{key}", params, label="Edit a copy of this pipeline"
            )
        if action == ACTION_IMPORT:
            _add_import_controls(inputs, params)
        if action in {ACTION_RENAME, ACTION_DUPLICATE}:
            _add_rename_controls(inputs, params)
        if action == ACTION_EDIT:
            key = selected_preset_key(params.get(PRESET_KEY_FIELD_NAME), presets)
            preset = next((preset for preset in presets if preset.key == key), None)
            if preset is not None:
                _add_edit_controls(inputs, params, preset)
        if action == ACTION_DELETE:
            _add_delete_controls(inputs, params)

        return types.Property(
            inputs,
            view=types.PromptView(
                label=OPERATOR_LABEL,
                submit_button_label=_submit_label(action),
                cancel_button_label="Close",
            ),
        )

    # pyrefly: ignore[bad-override]
    def resolve_output(self, ctx: Any):
        preset_row = types.Object()
        preset_row.str("key", label="Key")
        preset_row.str("name", label="Name")
        preset_row.str("description", label="Description")
        preset_row.int("transform_count", label="Transforms")
        preset_row.int("outputs_per_sample", label="Outputs per sample")
        preset_row.str("pipeline_summary", label="Pipeline")
        preset_row.str("plugin_version", label="Plugin version")
        preset_row.str("created_at", label="Created at")
        preset_row.str("updated_at", label="Updated at")
        preset_row.str("path", label="Path")

        outputs = types.Object()
        outputs.str("status", label="Status")
        outputs.str("message", label="Message")
        outputs.str("action", label="Action")
        outputs.str("preset_key", label="Saved pipeline key")
        outputs.str("preset_name", label="Saved pipeline name")
        outputs.str("preset_path", label="Local JSON file on the FiftyOne server")
        outputs.int("preset_count", label="Saved pipeline count")
        table = types.TableView()
        for key, label in (
            ("name", "Name"),
            ("description", "Description"),
            ("pipeline_summary", "Pipeline"),
            ("key", "ID"),
        ):
            table.add_column(key, label=label)
        outputs.list("presets", preset_row, label="Saved pipelines overview", view=table)
        outputs.str(
            "importable_preset_json",
            label="Importable pipeline JSON",
            description="Copy this entire JSON object into Import → Paste full JSON, or save it as a .json file.",
            view=types.CodeView(language="json", read_only=True),
        )
        outputs.str("errors_json", label="Error details", view=types.CodeView(language="json", read_only=True))
        return types.Property(outputs)

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        # The bundled App component provides the logo-and-caption placement.
        return None

    def execute(self, ctx: Any):
        return execute_preset_management_action(_ctx_params(ctx)).to_dict()


def _add_preset_selector(
    inputs: types.Object,
    *,
    params: Mapping[str, object],
    presets: tuple[PipelinePreset, ...],
) -> None:
    if not presets:
        inputs.str(
            PRESET_KEY_FIELD_NAME,
            label="Saved pipeline",
            description="No saved AlbumentationsX pipelines were found.",
        )
        return

    preset_keys = tuple(preset.key for preset in presets)
    choices = types.AutocompleteView(label="Saved pipeline", allow_user_input=False)
    for preset in presets:
        choices.add_choice(preset.key, label=f"{preset.name} ({preset.key})")
    inputs.enum(
        PRESET_KEY_FIELD_NAME,
        preset_keys,
        label="Saved pipeline",
        default=selected_preset_key(params.get(PRESET_KEY_FIELD_NAME), presets),
        required=True,
        view=choices,
    )


def _add_import_controls(inputs: types.Object, params: Mapping[str, object]) -> None:
    mode = params.get(IMPORT_MODE_FIELD_NAME, "json")
    choices = types.RadioGroup()
    choices.add_choice("json", label="Paste full JSON")
    choices.add_choice("file", label="Local JSON file")
    inputs.enum(
        IMPORT_MODE_FIELD_NAME,
        ["json", "file"],
        label="Import from",
        default=mode,
        required=True,
        view=choices,
    )
    if mode == "file":
        inputs.str(
            IMPORT_PATH_FIELD_NAME,
            label="Local JSON file path",
            required=True,
            default=string_param(params.get(IMPORT_PATH_FIELD_NAME)),
            description="Absolute path on the FiftyOne server (or ~/…). Choose a regular UTF-8 .json file, not a URL or symbolic link.",
        )
    else:
        inputs.str(
            PRESET_JSON_FIELD_NAME,
            label="Importable pipeline JSON",
            required=True,
            allow_empty=False,
            default=string_param(params.get(PRESET_JSON_FIELD_NAME)),
            description="Paste the complete Importable pipeline JSON from Export saved pipeline. Overview rows and paths are not import payloads.",
            view=types.CodeView(language="json"),
        )
    inputs.bool(
        OVERWRITE_FIELD_NAME,
        label="Overwrite existing saved pipeline",
        description="Replace only the saved pipeline with the same ID as the imported JSON. Matching names alone never replace another pipeline.",
        default=bool_param(params.get(OVERWRITE_FIELD_NAME)),
        required=False,
        view=types.CheckboxView(),
    )


def _add_rename_controls(inputs: types.Object, params: Mapping[str, object]) -> None:
    inputs.str(
        NEW_PRESET_NAME_FIELD_NAME,
        label="New saved pipeline name",
        default=string_param(params.get(NEW_PRESET_NAME_FIELD_NAME)),
        allow_empty=False,
        required=True,
    )


def _add_edit_controls(inputs: types.Object, params: Mapping[str, object], preset: PipelinePreset) -> None:
    group_name = preset_edit_group(preset.key)
    values = params.get(group_name, {})
    values = values if isinstance(values, Mapping) else {}
    edits = types.Object()
    edits.str("name", label="Saved pipeline name", default=values.get("name", preset.name), required=True)
    edits.str("description", label="Description", default=values.get("description", preset.description))
    edits.list(
        "tags", types.String(), label="Tags", default=values.get("tags", list(preset.tags)), view=types.ListView()
    )
    edits.str(
        "metadata_json",
        label="Metadata JSON (advanced)",
        description="Keep annotation_selection to preserve saved annotation mapping when loading this pipeline.",
        default=values.get("metadata_json", json_dump(preset.metadata)),
        view=types.CodeView(language="json"),
    )
    inputs.define_property(group_name, edits, view=types.ObjectView(label=f"Details for {preset.name}"))


def _add_delete_controls(inputs: types.Object, params: Mapping[str, object]) -> None:
    inputs.bool(
        CONFIRM_DELETE_FIELD_NAME,
        label="Confirm deletion",
        default=bool_param(params.get(CONFIRM_DELETE_FIELD_NAME)),
        required=True,
        description="Delete only the selected saved pipeline JSON file.",
        view=types.CheckboxView(),
    )


def _action_view() -> types.DropdownView:
    view = types.DropdownView()
    labels = {
        ACTION_INSPECT: "Inspect saved pipelines",
        ACTION_EXPORT: "Export saved pipeline",
        ACTION_IMPORT: "Import saved pipeline",
        ACTION_RENAME: "Rename saved pipeline",
        ACTION_EDIT: "Edit saved pipeline details",
        ACTION_DUPLICATE: "Duplicate saved pipeline",
        ACTION_DELETE: "Delete saved pipeline",
    }
    for action in PRESET_MANAGEMENT_ACTIONS:
        view.add_choice(action, label=labels[action])
    return view


def _submit_label(action: str) -> str:
    return {
        ACTION_INSPECT: "Inspect saved pipelines",
        ACTION_EXPORT: "Export saved pipeline",
        ACTION_IMPORT: "Import saved pipeline",
        ACTION_RENAME: "Rename saved pipeline",
        ACTION_EDIT: "Save pipeline details",
        ACTION_DUPLICATE: "Duplicate saved pipeline",
        ACTION_DELETE: "Delete saved pipeline",
    }.get(action, "Run")


def _safe_list_presets(store: FilePipelinePresetStore) -> tuple[tuple[PipelinePreset, ...], str]:
    try:
        return store.list_presets(), ""
    except Exception as error:
        _LOGGER.debug("Error while listing saved pipelines", exc_info=True)
        return (), f"Saved pipeline storage could not be listed: {type(error).__name__}: {error}"


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return params if isinstance(params, Mapping) else {}


__all__ = [
    "ACTION_DELETE",
    "ACTION_EXPORT",
    "ACTION_FIELD_NAME",
    "ACTION_IMPORT",
    "ACTION_INSPECT",
    "ACTION_RENAME",
    "CONFIRM_DELETE_FIELD_NAME",
    "ManageAlbumentationsXPresets",
    "NEW_PRESET_NAME_FIELD_NAME",
    "OPERATOR_LABEL",
    "OPERATOR_NAME",
    "OVERWRITE_FIELD_NAME",
    "PRESET_JSON_FIELD_NAME",
    "PRESET_KEY_FIELD_NAME",
    "PRESET_STORAGE_WARNING_FIELD_NAME",
    "STORAGE_ROOT_PARAM_NAME",
]
