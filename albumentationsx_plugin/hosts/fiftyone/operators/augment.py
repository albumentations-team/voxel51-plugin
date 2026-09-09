"""Augmentation operator lifecycle and action dispatch."""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

from albumentationsx_plugin.core import JSONDict, PluginError
from albumentationsx_plugin.hosts.fiftyone.augment_validation import (
    validate_augment_template_sources,
    validate_effective_augment_params,
)
from albumentationsx_plugin.hosts.fiftyone.branding import ALBUMENTATIONS_ICON
from albumentationsx_plugin.hosts.fiftyone.cancellation import FiftyOneCancellationChecker
from albumentationsx_plugin.hosts.fiftyone.diagnostics import (
    DEBUG_BUNDLE_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.editor_draft import (
    ACTION_LABELS,
    DRAFT_DATASET,
    EDITOR_ACTION,
    EDITOR_DRAFT,
    RESULT_DETAILS,
    RETURN_ERRORS,
    REVIEWED_SELECTION,
    editor_action,
    snapshot_editor,
)
from albumentationsx_plugin.hosts.fiftyone.editor_draft import (
    execution_params as effective_editor_params,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    selected_execution_scope,
    selected_sample_ids_from_context,
    source_selected_sample_ids,
    source_view_from_context,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import (
    DRAFT_ID,
    draft_parameter_group_name,
)
from albumentationsx_plugin.hosts.fiftyone.operators.augment_contract import _LOGGER, OPERATOR_LABEL, OPERATOR_NAME
from albumentationsx_plugin.hosts.fiftyone.operators.augment_errors import (
    _augment_validation_error_result,
    _diagnostic_fields,
    _error_result,
    _invalid_execution_scope_result,
    _missing_dependency_inputs,
    _missing_dependency_result,
    _no_selected_samples_result,
    _pipeline_preset_error_result,
    _plugin_error_result,
    _preview_requires_selected_samples_result,
    _unexpected_runtime_error_result,
)
from albumentationsx_plugin.hosts.fiftyone.operators.augment_navigation import (
    _open_created_outputs,
    _trigger_dataset_reload,
)
from albumentationsx_plugin.hosts.fiftyone.operators.augment_results import build_result_schema
from albumentationsx_plugin.hosts.fiftyone.operators.augment_values import (
    _ctx_params,
    _dry_run_param,
    _is_missing_runtime_dependency,
    _json_dump,
    _preview_only_param,
    _save_preset_only_param,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    pipeline_preset_save_requested,
    save_pipeline_preset_from_params,
)
from albumentationsx_plugin.hosts.fiftyone.presets import (
    storage_root_from_params,
)
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    MAX_PREVIEW_SAMPLES,
    PREVIEW_ONLY_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.progress import FiftyOneProgressReporter


class AugmentWithAlbumentationsX(foo.Operator):
    """FiftyOne App operator that creates augmented image samples."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            icon=ALBUMENTATIONS_ICON,
            description="Build and apply AlbumentationsX augmentation pipelines to samples, views, or datasets.",
            dynamic=True,
            allow_immediate_execution=True,
            allow_delegated_execution=True,
            default_choice_to_delegated=False,
            allow_distributed_execution=False,
            risk_level=RiskLevel.LOW,
        )

    # pyrefly: ignore[bad-override]
    def resolve_input(self, ctx: Any):
        try:
            inputs = _build_dynamic_augment_form(ctx)
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            inputs = _missing_dependency_inputs(error)
        draft_id = _ctx_params(ctx).get(DRAFT_ID)
        if isinstance(draft_id, str):
            wrapper = types.Object()
            wrapper.define_property(draft_parameter_group_name(draft_id), inputs, view=types.View())
            inputs = wrapper
        return types.Property(
            inputs,
            view=types.PromptView(
                label=OPERATOR_LABEL,
                submit_button_label=ACTION_LABELS[editor_action(_ctx_params(ctx))],
                cancel_button_label="Close",
                # Remount uncontrolled FiftyOne inputs only when a snapshot is explicitly loaded.
                componentsProps={"container": {"key": str(_ctx_params(ctx).get(DRAFT_ID, "unsaved"))}},
            ),
        )

    # pyrefly: ignore[bad-override]
    def resolve_output(self, ctx: Any):
        results = getattr(ctx, "results", None)
        if isinstance(results, Mapping) and results.get("_displayed_in_app") is True:
            return types.Property(types.Object())
        return self._result_schema(ctx)

    def _result_schema(self, ctx: Any):
        return build_result_schema(ctx)

    # pyrefly: ignore[bad-override]
    def resolve_delegation(self, ctx: Any):
        if editor_action(_ctx_params(ctx)) in {"preview", "save", "validate"}:
            return False
        return None

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        # The bundled App component provides the logo-and-caption placement.
        return None

    def execute(self, ctx: Any) -> JSONDict:
        draft = snapshot_editor(ctx, _ctx_params(ctx))
        result = self._execute(ctx)
        errors = result.get("errors")
        if isinstance(errors, list) and errors:
            draft[RETURN_ERRORS] = "\n".join(
                str(error.get("message", "")) for error in errors if isinstance(error, Mapping)
            )
        if isinstance(errors, list) and errors and DEBUG_BUNDLE_FIELD_NAME not in result:
            result.update(
                _diagnostic_fields(
                    effective_editor_params(_ctx_params(ctx)),
                    cast(list[JSONDict], errors),
                    ctx=ctx,
                    source_scope=str(result.get("source_scope", "")),
                    selected_sample_ids=selected_sample_ids_from_context(ctx),
                    dry_run=result.get("dry_run") is True,
                    preview_only=result.get(PREVIEW_ONLY_FIELD_NAME) is True,
                )
            )
        bundle = result.get(DEBUG_BUNDLE_FIELD_NAME)
        if isinstance(bundle, str):
            diagnostic = json.loads(bundle)
            diagnostic["execution"]["execution_status"] = result.get("execution_status")
            result[DEBUG_BUNDLE_FIELD_NAME] = _json_dump(diagnostic)
        result[EDITOR_DRAFT] = cast(Any, draft)
        # Keep the flat execution API; nested values serve only the collapsed App report.
        result[RESULT_DETAILS] = dict(result)
        cast(dict, result[RESULT_DETAILS]).pop(EDITOR_DRAFT, None)
        if (
            EDITOR_ACTION in _ctx_params(ctx)
            and not getattr(ctx, "delegated", False)
            and callable(getattr(ctx, "trigger", None))
        ):
            # The 1.19 prompt retains hasExecuted when another prompt replaces
            # its output. Show results through the public independent output
            # modal so the completed editor can close and a fresh one can open.
            output_ctx = SimpleNamespace(params=_ctx_params(ctx), results=result)
            schema = self._result_schema(output_ctx).to_json()
            if result.get("created_count") and result.get("manifest_path"):
                try:
                    _open_created_outputs(ctx, result)
                except Exception:
                    # Result navigation must not discard a successfully created run.
                    _LOGGER.warning("Could not open generated samples; use the result's history link", exc_info=True)
            ctx.trigger("show_output", params={"outputs": schema, "results": dict(result)})
            result["_displayed_in_app"] = True
        return result

    def _execute(self, ctx: Any) -> JSONDict:
        raw_params = _ctx_params(ctx)
        params = effective_editor_params(raw_params)
        if EDITOR_ACTION in raw_params and (
            not isinstance(raw_params[EDITOR_ACTION], str) or raw_params[EDITOR_ACTION] not in ACTION_LABELS
        ):
            return _error_result(
                params,
                errors=[
                    {
                        "code": "invalid_editor_action",
                        "message": "Choose Preview, Create augmented samples, Save pipeline, or Validate without creating samples.",
                        "context": {},
                    }
                ],
                ctx=ctx,
            )
        dataset_name = getattr(getattr(ctx, "dataset", None), "name", None)
        if raw_params.get(DRAFT_DATASET) and raw_params[DRAFT_DATASET] != dataset_name:
            return _error_result(
                params,
                errors=[
                    {
                        "code": "draft_dataset_changed",
                        "message": "This draft belongs to another dataset. Open its original dataset or load a saved pipeline to map annotations to this dataset.",
                        "context": {},
                    }
                ],
                ctx=ctx,
            )
        reviewed = raw_params.get(REVIEWED_SELECTION)
        selected_now = selected_sample_ids_from_context(ctx)
        if (
            editor_action(params) == "create"
            and params.get("execution_scope") == EXECUTION_SCOPE_SELECTED_SAMPLES
            and isinstance(reviewed, list)
            and set(reviewed) != set(selected_now)
        ):
            return _error_result(
                params,
                errors=[
                    {
                        "code": "selection_changed",
                        "message": "The selected samples changed after this editor was opened. Return to the editor to review the current selection before creating samples.",
                        "context": {"reviewed_count": len(reviewed), "selected_count": len(selected_now)},
                    }
                ],
                ctx=ctx,
            )
        selected_sample_ids = selected_sample_ids_from_context(ctx)
        storage_root = storage_root_from_params(params)
        template_source_issues = validate_augment_template_sources(params)
        if template_source_issues:
            return _augment_validation_error_result(
                params,
                template_source_issues,
                ctx=ctx,
            )
        if _save_preset_only_param(params):
            try:
                preset_params = dict(params)
                validation_issues = validate_effective_augment_params(preset_params)
                if validation_issues:
                    return _augment_validation_error_result(
                        preset_params,
                        validation_issues,
                        ctx=ctx,
                    )
                return save_pipeline_preset_from_params(
                    preset_params, dataset=ctx.dataset, storage_root=storage_root
                ).to_dict()
            except Exception as error:
                return _pipeline_preset_error_result(params, error, ctx=ctx)
        preview_only = _preview_only_param(params)
        try:
            source_scope = selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
        except ValueError as error:
            return _invalid_execution_scope_result(params, error, ctx=ctx)
        if preview_only and not selected_sample_ids:
            return _preview_requires_selected_samples_result(params, ctx=ctx)
        if source_scope == EXECUTION_SCOPE_SELECTED_SAMPLES and not selected_sample_ids:
            return _no_selected_samples_result(params, source_scope=source_scope, ctx=ctx)
        execution_params = dict(params)
        validation_issues = validate_effective_augment_params(execution_params)
        if validation_issues:
            return _augment_validation_error_result(
                execution_params,
                validation_issues,
                source_scope=source_scope,
                ctx=ctx,
            )
        execution_params[EXECUTION_SCOPE_FIELD_NAME] = source_scope
        if preview_only:
            preview_params = dict(execution_params)
            preview_params[EXECUTION_SCOPE_FIELD_NAME] = EXECUTION_SCOPE_SELECTED_SAMPLES
            preview_params["dry_run"] = False
            try:
                result = _execute_fixed_augmentation_preview(
                    dataset=ctx.dataset,
                    view=source_view_from_context(ctx, EXECUTION_SCOPE_SELECTED_SAMPLES),
                    selected_sample_ids=selected_sample_ids[:MAX_PREVIEW_SAMPLES],
                    params=preview_params,
                )
            except ModuleNotFoundError as error:
                if not _is_missing_runtime_dependency(error):
                    raise
                return _missing_dependency_result(
                    error,
                    params=preview_params,
                    source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
                    ctx=ctx,
                )
            except PluginError as error:
                return _plugin_error_result(
                    preview_params,
                    error,
                    source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
                    ctx=ctx,
                )
            except Exception as error:
                return _unexpected_runtime_error_result(
                    preview_params,
                    error,
                    source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
                    ctx=ctx,
                )
            return result.to_dict()
        saved_preset = None
        if pipeline_preset_save_requested(execution_params) and not _dry_run_param(execution_params):
            try:
                # Legacy callers can save and create in one request. Preflight
                # before persisting the preset as well as before run creation.
                from albumentationsx_plugin.hosts.fiftyone.augmentation.runtime import build_fixed_augmentation_runtime

                build_fixed_augmentation_runtime(
                    dataset=ctx.dataset,
                    view=source_view_from_context(ctx, source_scope),
                    selected_sample_ids=source_selected_sample_ids(selected_sample_ids, source_scope),
                    params=execution_params,
                )
                saved_preset = save_pipeline_preset_from_params(
                    execution_params, dataset=ctx.dataset, storage_root=storage_root
                )
            except Exception as error:
                return _pipeline_preset_error_result(
                    params,
                    error,
                    source_scope=source_scope,
                    ctx=ctx,
                )
        try:
            result = _execute_fixed_augmentation(
                dataset=ctx.dataset,
                view=source_view_from_context(ctx, source_scope),
                selected_sample_ids=source_selected_sample_ids(selected_sample_ids, source_scope),
                params=execution_params,
                storage_root=storage_root,
                cancellation_checker=FiftyOneCancellationChecker(ctx),
                progress_reporter=FiftyOneProgressReporter(ctx),
            )
        except ModuleNotFoundError as error:
            if not _is_missing_runtime_dependency(error):
                raise
            return _missing_dependency_result(
                error,
                params=execution_params,
                source_scope=source_scope,
                ctx=ctx,
            )
        except PluginError as error:
            return _plugin_error_result(
                execution_params,
                error,
                source_scope=source_scope,
                ctx=ctx,
            )
        except Exception as error:
            return _unexpected_runtime_error_result(
                execution_params,
                error,
                source_scope=source_scope,
                ctx=ctx,
            )
        try:
            _trigger_dataset_reload(ctx, result)
        except Exception as error:
            return _unexpected_runtime_error_result(
                execution_params,
                error,
                source_scope=source_scope,
                ctx=ctx,
                phase="dataset_reload",
                extra=_successful_result_output_fields(result),
            )
        output = result.to_dict()
        if saved_preset is not None:
            output.update(_pipeline_preset_output_fields(saved_preset))
        return output


def _build_dynamic_augment_form(ctx: Any):
    from albumentationsx_plugin.hosts.fiftyone.forms import build_dynamic_augment_form

    return build_dynamic_augment_form(ctx)


def _execute_fixed_augmentation(**kwargs: Any):
    from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation

    return execute_fixed_augmentation(**kwargs)


def _execute_fixed_augmentation_preview(**kwargs: Any):
    from albumentationsx_plugin.hosts.fiftyone.augmentation import execute_fixed_augmentation_preview

    return execute_fixed_augmentation_preview(**kwargs)


def _pipeline_preset_output_fields(save_result: Any) -> JSONDict:
    preset_result = save_result.to_dict()
    return {
        "preset_key": preset_result["preset_key"],
        "preset_name": preset_result["preset_name"],
        "preset_path": preset_result["preset_path"],
    }


def _successful_result_output_fields(result: Any) -> Mapping[str, object]:
    return {
        "run_key": getattr(result, "run_key", ""),
        "processed_count": getattr(result, "processed_count", 0),
        "created_count": getattr(result, "created_count", 0),
        "skipped_count": getattr(result, "skipped_count", 0),
        "dry_run": getattr(result, "dry_run", False),
        "execution_status": getattr(result, "execution_status", ""),
        "output_tag": getattr(result, "output_tag", ""),
        "output_dir": getattr(result, "output_dir", ""),
        "manifest_path": getattr(result, "manifest_path", ""),
        "fiftyone_run_key": getattr(result, "fiftyone_run_key", ""),
    }
