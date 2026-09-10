"""Read-only outcome summaries shared by augmentation and run inspection."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping

import fiftyone.operators.types as types


def result_errors(result: Mapping[str, object]) -> list[Mapping[str, object]]:
    errors = result.get("errors")
    if not isinstance(errors, list):
        try:
            errors = json.loads(str(result.get("errors_json", "[]")))
        except (ValueError, TypeError):
            errors = []
    return [error for error in errors if isinstance(error, Mapping)] if isinstance(errors, list) else []


def outcome_summary(result: Mapping[str, object]) -> tuple[str, str]:
    """Keep execution outcome distinct from manifest availability and mode."""
    status = str(result.get("execution_status", ""))
    created = result.get("created_count", 0)
    processed = result.get("processed_count", result.get("source_count", 0))
    errors = result.get("error_count", len(result_errors(result)))
    skipped = result.get("skipped_count", 0)
    if not status:
        return "Result unavailable", str(result.get("message") or "No execution result is available.")
    if status == "preset_saved":
        if result.get("preset_save_action") == "updated":
            return (
                "Pipeline updated",
                f"Updated saved pipeline: {result.get('preset_name', '')}. No augmented samples were created.",
            )
        return "Pipeline saved", f"Saved pipeline: {result.get('preset_name', '')}. No augmented samples were created."
    if status == "dry_run":
        return "Validation passed", (
            f"Validated {processed} source sample(s). No samples or files were created. "
            "Only sampled random branches were checked; output write permissions were not tested."
        )
    if result.get("preview_only") is True or status == "preview":
        title = {"failed": "Preview failed", "partial": "Preview partially succeeded"}.get(status, "Preview ready")
        return title, (
            f"Generated {result.get('preview_count', 0)} preview(s) from {processed} source sample(s); "
            f"{errors} error(s), {skipped} skipped source(s). No samples or files were created."
        )
    title = {
        "completed": "Augmentation completed",
        "partial": "Augmentation partially succeeded",
        "failed": "Augmentation failed",
        "cancelled": "Augmentation cancelled",
        "running": "Augmentation running",
    }.get(status, status.replace("_", " ").capitalize())
    if status == "failed" and not result.get("run_key"):
        title = "Validation failed" if result.get("dry_run") else "Unable to run augmentation"
        return title, "No augmented samples were created. Correct the error below and return to the editor."
    return title, (
        f"Created {created} sample(s) from {processed} processed source sample(s); "
        f"{errors} error(s), {skipped} skipped source(s)."
    )


def error_recovery(error: Mapping[str, object]) -> str:
    context = error.get("context")
    context = context if isinstance(context, Mapping) else {}
    code = str(error.get("code", ""))
    reason = str(context.get("reason", ""))
    if "selection" in reason or code in {"no_selected_samples", "preview_requires_selected_samples"}:
        return "Select source samples, then return to the editor and preview again."
    if code == "augmentation_cancelled":
        return "Inspect retained outputs in history; return to the editor to start a new run if needed."
    if reason == "invalid_annotation_data" or "keypoint" in str(error.get("message", "")).lower():
        return "Correct the reported annotation or deselect that annotation field, then validate again."
    if code == "missing_runtime_dependency":
        return "Install the plugin requirements in the environment that launches FiftyOne, then reload the App."
    if code == "pipeline_preset_unavailable":
        return "Check the saved pipeline name, configuration and storage access, then save again."
    if code == "unexpected_runtime_error":
        return (
            "Return to the editor and validate. If this persists, copy or download the debug bundle for a bug report."
        )
    if context.get("parameter_name") or context.get("stage_number") or "parameter" in code or "order" in code:
        return "Correct the reported stage or parameter in the editor, then validate before creating samples."
    if context.get("field_name") or "annotation" in reason:
        return "Check the reported annotation field and pipeline compatibility, then validate again."
    if "media" in code or "file" in reason:
        return "Check that the reported media exists and can be read, and that output storage is writable."
    return "Review the reported sample and pipeline in the editor, then validate before retrying."


def add_outcome(outputs: types.Object, result: Mapping[str, object]) -> None:
    title, description = outcome_summary(result)
    view_type = types.Warning if result.get("execution_status") in {"failed", "partial", "cancelled"} else types.Notice
    outputs.view("_outcome", view_type(label=title, description=description))
    errors = result_errors(result)
    for index, error in enumerate(errors[:5]):
        context = error.get("context")
        context = context if isinstance(context, Mapping) else {}
        location = "; ".join(
            f"{label}: {context[key]}"
            for key, label in (
                ("stage_number", "Stage"),
                ("transform_name", "Transform"),
                ("field_name", "Field"),
                ("parameter_name", "Parameter"),
                ("sample_id", "Sample"),
                ("output_index", "Output index"),
            )
            if context.get(key) is not None and context.get(key) != ""
        )
        cause = context.get("cause") or context.get("error_message") or context.get("error")
        description = "\n".join(filter(None, (location, str(cause) if cause else "", "Next: " + error_recovery(error))))
        outputs.view(
            f"_error_{index + 1}",
            types.Warning(
                label=str(error.get("message") or error.get("code") or "Execution error"), description=description
            ),
        )
    if len(errors) > 5:
        outputs.view("_more_errors", types.Notice(label=f"{len(errors) - 5} more errors in Technical details"))


def has_display_value(value: object) -> bool:
    return value is not None and value != "" and value != [] and value != {} and value not in ("[]", "{}", "null")


def add_json_output(outputs: types.Object, name: str, *, label: str, value: object = None) -> None:
    """Use the native read-only JSON tree with clipboard controls and a download."""
    outputs.str(
        name,
        label=label,
        view=types.JSONView(
            read_only=True,
            componentsProps={
                "jsonViewer": {
                    "jsonViewerProps": {
                        "enableClipboard": True,
                        "editable": False,
                        "style": {"maxHeight": "50vh", "overflow": "auto"},
                    }
                }
            },
        ),
    )
    if isinstance(value, str) and has_display_value(value):
        encoded = base64.b64encode(value.encode()).decode("ascii")
        outputs.view(
            f"_download_{name}",
            types.LinkView(
                label=f"Download {label.lower()}",
                href=f"data:application/json;base64,{encoded}",
                componentsProps={"link": {"download": f"albumentationsx-{name}.json"}},
            ),
        )
