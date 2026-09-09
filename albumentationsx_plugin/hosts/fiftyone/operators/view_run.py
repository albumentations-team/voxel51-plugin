"""Read-only FiftyOne operator for inspecting persisted augmentation runs."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from os import PathLike
from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.hosts.fiftyone.branding import ALBUMENTATIONS_ICON
from albumentationsx_plugin.hosts.fiftyone.editor_draft import RESULT_DETAILS
from albumentationsx_plugin.hosts.fiftyone.forms.pipeline_loading import render_pipeline_load_button
from albumentationsx_plugin.hosts.fiftyone.forms.sections import add_collapsible_section
from albumentationsx_plugin.hosts.fiftyone.result_presentation import add_json_output, add_outcome, has_display_value
from albumentationsx_plugin.hosts.fiftyone.run_library import RunLibraryEntry, list_run_library
from albumentationsx_plugin.hosts.fiftyone.run_summary import build_run_summary

OPERATOR_NAME = "view_albumentationsx_run"
OPERATOR_LABEL = "AlbumentationsX · Run history"
RUN_KEY_FIELD_NAME = "run_key"
OUTPUT_KEY_FIELD_NAME = "output_key"
OPEN_GENERATED_SAMPLES_FIELD_NAME = "open_generated_samples"
STORAGE_ROOT_PARAM_NAME = "_storage_root"
_LOGGER = logging.getLogger(__name__)


class ViewAlbumentationsXRun(foo.Operator):
    """FiftyOne App operator that reports manifest-backed run metadata."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            icon=ALBUMENTATIONS_ICON,
            description="Browse AlbumentationsX run history, open outputs, reuse pipelines, and review cleanup.",
            dynamic=True,
            allow_immediate_execution=True,
            allow_delegated_execution=False,
            allow_distributed_execution=False,
            risk_level=RiskLevel.LOW,
        )

    # pyrefly: ignore[bad-override]
    def resolve_input(self, ctx: Any):
        params = _ctx_params(ctx)
        storage_root = _storage_root(params)
        dataset = getattr(ctx, "dataset", None)
        entries = list_run_library(dataset, storage_root=storage_root) if dataset is not None else ()
        query = _optional_str_param(params.get("run_query"))
        show_cleaned = params.get("show_cleaned", True) is not False
        entries = tuple(
            entry
            for entry in entries
            if (show_cleaned or entry.status != "cleaned")
            and (
                not query
                or query.casefold() in f"{entry.choice_label} {entry.run_key} {entry.pipeline_summary}".casefold()
            )
        )
        run_keys = tuple(entry.run_key for entry in entries)
        requested_run = _optional_str_param(params.get(RUN_KEY_FIELD_NAME))
        stale_selection = RUN_KEY_FIELD_NAME in params and requested_run not in run_keys
        selected_run_key = "" if stale_selection or not entries else _selected_run_key(requested_run, run_keys)

        inputs = types.Object()
        inputs.str("run_query", label="Search runs", default=query, required=False)
        inputs.bool("show_cleaned", label="Include cleaned runs", default=show_cleaned)
        inputs.message(
            "run_history",
            label=f"Run history: {len(entries)} run(s)",
            description="Newest first. Search by label, date, status, or transform. Runs are execution records; reusable configurations live in Saved pipelines.",
        )
        if entries:
            choices = types.AutocompleteView(
                label="Run",
                allow_user_input=False,
                componentsProps={"autocomplete": {"value": None}} if stale_selection else {},
            )
            for entry in entries:
                choices.add_choice(entry.run_key, label=entry.choice_label)
            inputs.enum(
                RUN_KEY_FIELD_NAME,
                run_keys,
                label="Run",
                default=selected_run_key,
                required=True,
                view=choices,
                invalid=stale_selection,
                error_message="The selected run is outside this search. Choose a run from the filtered results."
                if stale_selection
                else "",
            )
        else:
            inputs.str(
                RUN_KEY_FIELD_NAME,
                label="Run",
                description="No persisted AlbumentationsX runs match this search for this dataset.",
                invalid=True,
                error_message="Create a run or change the search filters.",
            )

        if dataset is not None and selected_run_key:
            summary = build_run_summary(
                dataset,
                selected_run_key,
                storage_root=storage_root,
                selected_output_key=_optional_str_param(params.get(OUTPUT_KEY_FIELD_NAME)),
            )
            add_outcome(inputs, summary.to_dict())
            entry = next(entry for entry in entries if entry.run_key == selected_run_key)
            _add_library_details(inputs, entry)
            _add_generated_output_controls(inputs, summary)
            action_params = {"run_key": selected_run_key, "reset_source_view": True}
            if storage_root is not None:
                action_params[STORAGE_ROOT_PARAM_NAME] = str(storage_root)
            for name, label, available in (
                ("open_generated_samples", "Open generated samples", summary.available_generated_sample_ids),
                ("open_failed_samples", "Open failed source samples", _failed_sample_ids(summary.errors_json)),
            ):
                if available:
                    inputs.btn(
                        f"_{name}",
                        label=label,
                        prompt=False,
                        on_click="@albumentations/albumentationsx/view_albumentationsx_run",
                        params={**action_params, name: True},
                    )
            inputs.view(
                "_run_pipeline_help",
                types.Notice(
                    label="Pipeline from run history",
                    description="A run records an execution, its source samples, status and outputs. Its pipeline can be edited and run again with fresh randomness; this does not replay a generated output.",
                ),
            )
            render_pipeline_load_button(
                inputs, dataset, f"run:{selected_run_key}", params, label="Use pipeline from this run"
            )
            _add_cleanup_action(inputs, entry, storage_root=storage_root)

        return types.Property(
            inputs,
            view=types.PromptView(label=OPERATOR_LABEL, submit_button_label="Inspect run", cancel_button_label="Close"),
        )

    # pyrefly: ignore[bad-override]
    def resolve_output(self, ctx: Any):
        outputs = types.Object()
        outputs.str("run_key", label="Run key")
        outputs.str("created_at", label="Created at (UTC)")
        outputs.str("execution_scope", label="Execution scope")
        outputs.str("library_status", label="Run outcome")
        outputs.str("manifest_json", label="Detailed manifest")
        outputs.str("status", label="Manifest availability")
        outputs.str("message", label="Message")
        outputs.str("manifest_path", label="Manifest path")
        outputs.str("fiftyone_run_key", label="FiftyOne run key")
        outputs.str("cleanup_status", label="Cleanup status")
        outputs.str("cleaned_at", label="Cleaned at")
        outputs.str("execution_status", label="Execution status")
        outputs.str("cancelled_at", label="Cancelled at")
        outputs.str("run_label", label="Run label")
        outputs.str("run_label_slug", label="Run label slug")
        outputs.int("source_count", label="Sources")
        outputs.int("created_count", label="Created samples")
        outputs.int("skipped_count", label="Skipped sources")
        outputs.int("output_count", label="Manifest outputs")
        outputs.int("available_output_count", label="Available outputs")
        outputs.int("missing_output_count", label="Missing outputs")
        outputs.int("error_count", label="Errors")
        outputs.int("replay_count", label="Replay records")
        outputs.bool("replay_available", label="Replay available")
        outputs.str("output_tag", label="Output tag")
        outputs.str("output_dir", label="Output directory")
        outputs.str("generated_sample_ids_json", label="Generated sample IDs")
        outputs.str("available_generated_sample_ids_json", label="Available generated sample IDs")
        outputs.str("generated_outputs_json", label="Generated outputs")
        outputs.str("selected_output_key", label="Selected output key")
        outputs.str("selected_output_status", label="Selected output status")
        outputs.str("selected_source_sample_id", label="Selected source sample ID")
        outputs.str("selected_generated_sample_id", label="Selected generated sample ID")
        outputs.int("selected_output_index", label="Selected output index")
        outputs.str("selected_output_path", label="Selected output path")
        outputs.bool("selected_output_available", label="Selected output available")
        outputs.str("selected_replay_json", label="Selected replay")
        outputs.str("plugin_version", label="Plugin version")
        outputs.str("dependency_versions_json", label="Dependency versions")
        outputs.str("pipeline_summary", label="Transform summary")
        outputs.str("pipeline_config_json", label="Transform config")
        outputs.str("errors_json", label="Errors")
        results = getattr(ctx, "results", None)
        if isinstance(results, Mapping):
            visible = types.Object()
            add_outcome(visible, results)
            for name in ("run_label", "created_at", "message", "pipeline_summary"):
                if has_display_value(results.get(name)):
                    visible.add_property(name, outputs.properties[name])
            details = types.Object()
            for name, prop in outputs.properties.items():
                if name not in visible.properties and has_display_value(results.get(name)):
                    if name.endswith("_json"):
                        add_json_output(details, name, label=prop.view.label, value=results[name])
                    else:
                        details.add_property(name, prop)
            if details.properties:
                add_collapsible_section(visible, RESULT_DETAILS, "Technical details", details)
            return types.Property(visible)
        return types.Property(outputs)

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        # The bundled App component provides the logo-and-caption placement.
        return None

    def execute(self, ctx: Any) -> JSONDict:
        params = _ctx_params(ctx)
        summary = build_run_summary(
            ctx.dataset,
            _selected_run_key(params.get(RUN_KEY_FIELD_NAME), ()),
            storage_root=_storage_root(params),
            selected_output_key=_optional_str_param(params.get(OUTPUT_KEY_FIELD_NAME)),
        )
        if _bool_param(params.get("open_failed_samples")):
            from fiftyone.operators.operations import Operations

            ids = _failed_sample_ids(summary.errors_json)
            if ids:
                Operations(ctx).set_view(view=ctx.dataset.select(list(ids)))
        if _bool_param(params.get(OPEN_GENERATED_SAMPLES_FIELD_NAME)):
            if _bool_param(params.get("reset_source_view")) and summary.available_generated_sample_ids:
                # Build from the dataset so source filters cannot exclude outputs.
                from fiftyone.operators.operations import Operations

                Operations(ctx).set_view(view=ctx.dataset.select(list(summary.available_generated_sample_ids)))
            else:
                _trigger_generated_samples_view(ctx, summary.available_generated_sample_ids)
        result = summary.to_dict()
        result[RESULT_DETAILS] = dict(result)
        return result


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    if not isinstance(params, Mapping):
        return {}
    nested = params.get("_output_inspection")
    return {**params, **nested} if isinstance(nested, Mapping) else params


def _selected_run_key(raw_value: object, run_keys: tuple[str, ...]) -> str:
    if isinstance(raw_value, str) and raw_value.strip():
        value = raw_value.strip()
        if not run_keys or value in run_keys:
            return value
    return run_keys[0] if run_keys else ""


def _optional_str_param(raw_value: object) -> str:
    return raw_value.strip() if isinstance(raw_value, str) else ""


def _bool_param(raw_value: object) -> bool:
    return raw_value if isinstance(raw_value, bool) else False


def _add_library_details(
    inputs: types.Object,
    entry: RunLibraryEntry,
) -> None:
    inputs.message(
        "run_details",
        label=entry.display_name,
        description=(
            f"Created: {entry.created_at or 'unknown'} | Scope: {entry.execution_scope or 'unknown'} | "
            f"Sources: {entry.source_count} | Outputs: {entry.output_count} | Errors: {entry.error_count}\n"
            f"Pipeline: {entry.pipeline_summary or 'unavailable'}"
        ),
    )


def _add_generated_output_controls(inputs: types.Object, summary: Any) -> None:
    details = types.Object()
    if summary.generated_outputs:
        choices = types.AutocompleteView(label="Output replay", allow_user_input=False)
        output_keys: list[str] = []
        for output in summary.generated_outputs:
            output_keys.append(output.key)
            choices.add_choice(output.key, label=f"Output {output.position + 1} · {output.status}")
        selected_output = summary.selected_output
        details.enum(
            OUTPUT_KEY_FIELD_NAME,
            output_keys,
            label="Output replay",
            default=selected_output.key if selected_output is not None else output_keys[0],
            required=False,
            view=choices,
        )
    details.bool(
        OPEN_GENERATED_SAMPLES_FIELD_NAME,
        label="Open generated samples when inspecting",
        default=False,
        description="Open the generated samples for this run when submitting Inspect run.",
        view=types.CheckboxView(),
    )
    add_collapsible_section(inputs, "_output_inspection", "Output replay details", details)


def _failed_sample_ids(errors_json: str) -> tuple[str, ...]:
    errors = json.loads(errors_json or "[]")
    return tuple(
        dict.fromkeys(
            str(error["context"].get("source_sample_id") or error["context"].get("sample_id"))
            for error in errors
            if isinstance(error, dict)
            and isinstance(error.get("context"), dict)
            and (error["context"].get("source_sample_id") or error["context"].get("sample_id"))
        )
    )


def _trigger_generated_samples_view(ctx: Any, sample_ids: tuple[str, ...]) -> None:
    if not sample_ids:
        return

    ops = getattr(ctx, "ops", None)
    show_samples = getattr(ops, "show_samples", None)
    if callable(show_samples):
        try:
            show_samples(list(sample_ids))
            return
        except Exception:
            _LOGGER.debug("Error while opening generated samples through ctx.ops.show_samples", exc_info=True)

    trigger = getattr(ctx, "trigger", None)
    if not callable(trigger):
        return

    params = {"samples": list(sample_ids), "use_extended_selection": False}
    try:
        trigger("show_samples", params=params)
    except TypeError:
        try:
            trigger("show_samples", params)
        except Exception:
            _LOGGER.debug("Error while triggering generated sample view", exc_info=True)
            return
    except Exception:
        _LOGGER.debug("Error while triggering generated sample view", exc_info=True)
        return


def _storage_root(params: Mapping[str, object]) -> str | PathLike[str] | None:
    value = params.get(STORAGE_ROOT_PARAM_NAME)
    if isinstance(value, str):
        return value
    return value if isinstance(value, PathLike) else None


def _add_cleanup_action(
    inputs: types.Object, entry: RunLibraryEntry, *, storage_root: str | PathLike[str] | None
) -> None:
    action_params: dict[str, object] = {"run_key": entry.run_key}
    if storage_root is not None:
        action_params[STORAGE_ROOT_PARAM_NAME] = str(storage_root)
    if entry.manifest_available and entry.status != "cleaned":
        inputs.btn(
            "delete_run_outputs",
            label="Review deletion of generated outputs",
            icon="delete",
            prompt=True,
            on_click="@albumentations/albumentationsx/delete_albumentationsx_run",
            params={**action_params, "_history_run": True, "confirm_delete": False},
        )
