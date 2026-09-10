"""Present augmentation summaries and preview image results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import fiftyone.operators.types as types

from albumentationsx_plugin.hosts.fiftyone.diagnostics import (
    DEBUG_BUNDLE_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.editor_draft import (
    EDITOR_DRAFT,
    RESULT_DETAILS,
    continuation_draft,
)
from albumentationsx_plugin.hosts.fiftyone.forms.sections import add_collapsible_section
from albumentationsx_plugin.hosts.fiftyone.operators.augment_values import _ctx_params, _preview_only_from_ctx
from albumentationsx_plugin.hosts.fiftyone.pipeline_loading import AUGMENT_OPERATOR_URI, pipeline_draft_prompt_params
from albumentationsx_plugin.hosts.fiftyone.preview_contract import (
    MAX_PREVIEW_SAMPLES,
    PREVIEW_FIELD_ANNOTATION_COMPARISON_JSON,
    PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON,
    PREVIEW_FIELD_COMPARISON_IMAGE,
    PREVIEW_FIELD_LABELS_JSON,
    PREVIEW_FIELD_OUTPUT_IMAGE,
    PREVIEW_FIELD_REPLAY_JSON,
    PREVIEW_FIELD_SOURCE_FILEPATH,
    PREVIEW_FIELD_SOURCE_IMAGE,
    PREVIEW_FIELD_SOURCE_SAMPLE_ID,
    PREVIEW_ONLY_FIELD_NAME,
    preview_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.result_presentation import add_json_output, add_outcome, has_display_value


def _arrange_output(fields: types.Object, ctx: Any) -> types.Object:
    results = getattr(ctx, "results", None)
    results = results if isinstance(results, Mapping) else {}
    outputs = types.Object()
    add_outcome(outputs, results)
    # Causes and recovery precede previews, which can be taller than the viewport.
    for slot in range(1, MAX_PREVIEW_SAMPLES + 1):
        name = preview_field_name(slot, PREVIEW_FIELD_COMPARISON_IMAGE)
        if name in fields.properties:
            outputs.add_property(name, fields.properties[name])
    for name in ("preview_note", "preset_name"):
        if name in fields.properties:
            outputs.add_property(name, fields.properties[name])
    if results.get("manifest_path") and results.get("run_key"):
        navigation_params = {"run_key": results["run_key"]}
        storage_root = _ctx_params(ctx).get("_storage_root")
        if storage_root:
            navigation_params["_storage_root"] = storage_root
        if results.get("created_count"):
            outputs.btn(
                "_open_generated_samples",
                label="Open generated samples",
                on_click="@albumentations/albumentationsx/view_albumentationsx_run",
                prompt=False,
                params={**navigation_params, "open_generated_samples": True, "reset_source_view": True},
            )
        outputs.btn(
            "_view_in_history",
            label="View in history",
            on_click="@albumentations/albumentationsx/view_albumentationsx_run",
            prompt=True,
            params=navigation_params,
        )
    draft = results.get(EDITOR_DRAFT)
    if isinstance(draft, Mapping):
        for name, label, action in (
            ("_back_to_editor", "Back to editor", None),
            ("_preview_again", "Preview again", "preview"),
            ("_create_from_draft", "Review and create samples", "create"),
        ):
            restored = continuation_draft(draft, action=action)
            outputs.btn(
                name,
                label=label,
                on_click=AUGMENT_OPERATOR_URI,
                prompt=True,
                params=pipeline_draft_prompt_params(restored),
                description="Restores your configuration. Review the current source selection and submit the chosen action.",
            )
        outputs.view(
            "_draft_continuation_note",
            types.Notice(
                label="Continue editing",
                description="Your configuration is preserved. Each preview or creation samples fresh randomness, so its pixels may differ. Closing this result ends this draft; use Back to editor or save the pipeline to keep it.",
            ),
        )
    details = types.Object()
    for name, prop in fields.properties.items():
        if name not in outputs.properties:
            details.add_property(name, prop)
    if details.properties:
        add_collapsible_section(outputs, RESULT_DETAILS, "Technical details", details)
    return outputs


def _render_preview_output_fields(outputs: types.Object, results: Mapping[str, object]) -> None:
    outputs.str(
        "preview_note",
        label="Preview note",
        view=types.MarkdownView(read_only=True),
    )
    populated_slots = [
        slot
        for slot in range(1, MAX_PREVIEW_SAMPLES + 1)
        if all(
            isinstance(results.get(preview_field_name(slot, field)), str) and results[preview_field_name(slot, field)]
            for field in (PREVIEW_FIELD_SOURCE_IMAGE, PREVIEW_FIELD_OUTPUT_IMAGE, PREVIEW_FIELD_COMPARISON_IMAGE)
        )
    ]
    if populated_slots:
        outputs.view(
            "preview_display_policy",
            types.Notice(
                label="Image display",
                description=(
                    "Images keep their proportions and fit the available space without cropping or enlargement. "
                    "Before/after panels are fitted independently, with blank padding when sizes differ. "
                    "Their displayed sizes do not indicate the same pixel scale."
                ),
            ),
        )
    for slot_number in populated_slots:
        label_prefix = f"Preview {slot_number}"
        outputs.str(preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_SAMPLE_ID), label=f"{label_prefix} source ID")
        outputs.str(
            preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_FILEPATH),
            label=f"{label_prefix} source file",
        )
        outputs.define_property(
            preview_field_name(slot_number, PREVIEW_FIELD_SOURCE_IMAGE),
            types.String(),
            label=f"{label_prefix} source image",
            view=_preview_image_view(alt=f"{label_prefix} source image"),
        )
        outputs.define_property(
            preview_field_name(slot_number, PREVIEW_FIELD_OUTPUT_IMAGE),
            types.String(),
            label=f"{label_prefix} augmented image",
            view=_preview_image_view(alt=f"{label_prefix} augmented image"),
        )
        outputs.define_property(
            preview_field_name(slot_number, PREVIEW_FIELD_COMPARISON_IMAGE),
            types.String(),
            label=f"{label_prefix} annotated comparison",
            view=_preview_image_view(alt=f"{label_prefix} annotated before and after comparison"),
        )
        _render_preview_json_field(
            outputs,
            preview_field_name(slot_number, PREVIEW_FIELD_REPLAY_JSON),
            label=f"{label_prefix} sampled parameters",
        )
        _render_preview_json_field(
            outputs,
            preview_field_name(slot_number, PREVIEW_FIELD_LABELS_JSON),
            label=f"{label_prefix} transformed labels",
        )
        _render_preview_json_field(
            outputs,
            preview_field_name(slot_number, PREVIEW_FIELD_ANNOTATION_SUMMARY_JSON),
            label=f"{label_prefix} annotation summary",
        )
        _render_preview_json_field(
            outputs,
            preview_field_name(slot_number, PREVIEW_FIELD_ANNOTATION_COMPARISON_JSON),
            label=f"{label_prefix} annotation comparison",
        )


def _preview_image_view(*, alt: str) -> types.ImageView:
    return types.ImageView(
        width="auto",
        height="auto",
        alt=alt,
        read_only=True,
        componentsProps={
            "image": {
                "style": {
                    "display": "block",
                    "maxWidth": "100%",
                    "maxHeight": "min(360px, 50vh)",
                    "objectFit": "contain",
                    "objectPosition": "left top",
                },
            },
            "container": {"sx": {"minWidth": 0, "maxWidth": "100%"}},
        },
    )


def _render_preview_json_field(outputs: types.Object, name: str, *, label: str) -> None:
    _render_json_output_field(outputs, name, label=label)


def _render_json_output_field(outputs: types.Object, name: str, *, label: str) -> None:
    add_json_output(outputs, name, label=label)


def build_result_schema(ctx: Any):
    outputs = types.Object()
    outputs.str("run_key", label="Run key")
    outputs.str("source_scope", label="Source scope")
    outputs.int("processed_count", label="Processed")
    outputs.int("created_count", label="Created")
    outputs.int("skipped_count", label="Skipped")
    outputs.int("error_count", label="Errors")
    outputs.bool("dry_run", label="Dry run")
    outputs.str("execution_status", label="Execution status")
    outputs.str("metadata_policy_summary", label="Output metadata", view=types.MarkdownView())
    outputs.bool(PREVIEW_ONLY_FIELD_NAME, label="Preview only")
    outputs.str("output_tag", label="Output tag")
    outputs.str("output_dir", label="Output directory")
    outputs.str("manifest_path", label="Manifest path")
    outputs.str("fiftyone_run_key", label="FiftyOne run key")
    _render_json_output_field(outputs, "errors_json", label="Errors JSON")
    _render_json_output_field(outputs, "pipeline_config_json", label="Pipeline config")
    _render_json_output_field(outputs, "operator_params_json", label="Operator params")
    _render_json_output_field(outputs, DEBUG_BUNDLE_FIELD_NAME, label="Debug bundle")
    outputs.int("preview_count", label="Preview results")
    outputs.str("preset_key", label="Saved pipeline key")
    outputs.str("preset_name", label="Saved pipeline name")
    outputs.str("preset_path", label="Saved pipeline path")
    results = getattr(ctx, "results", {})
    if _preview_only_from_ctx(ctx) or (isinstance(results, Mapping) and results.get(PREVIEW_ONLY_FIELD_NAME)):
        _render_preview_output_fields(outputs, results if isinstance(results, Mapping) else {})
    results = getattr(ctx, "results", None)
    if isinstance(results, Mapping):
        if results.get("dry_run") or results.get(PREVIEW_ONLY_FIELD_NAME):
            for name in ("run_key", "fiftyone_run_key", "output_dir", "output_tag", "manifest_path"):
                outputs.properties.pop(name, None)
        for name in list(outputs.properties):
            if name not in {"preview_display_policy"} and not has_display_value(results.get(name)):
                del outputs.properties[name]
        for name in list(outputs.properties):
            if name.endswith("_json"):
                add_json_output(outputs, name, label=outputs.properties[name].view.label, value=results.get(name))
    return types.Property(_arrange_output(outputs, ctx))
