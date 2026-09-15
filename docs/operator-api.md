# Python operator API

The [integration guide](albumentationsx-fiftyone-integration.md#python-operator-reference)
lists the six registered Python URIs. These parameters are for programmatic
callers; the App uses the Action picker and nested draft groups.

## Execute a read-only catalog query

Run this in the Python environment where the plugin is installed and enabled.
Replace the dataset name with an existing image dataset in that environment:

```python
import fiftyone.operators as foo

execution = foo.execute_operator(
    "@albumentations/albumentationsx/show_albumentationsx_capabilities",
    ctx={
        "dataset": "your-image-dataset",
        "params": {
            "query": "HorizontalFlip",
            "status_filter": "all",
            "target_filter": "all",
        },
    },
)
execution.raise_exceptions()
print(execution.result["transforms"])
```

The result includes `status`, `query`, `matching_count`, and `transforms`.
This query creates no samples or run. With an active event loop, such as in a
notebook, `execute_operator` returns a task: use
`execution = await foo.execute_operator(...)` before inspecting its result.

For a read-only compatibility report, use
`@albumentations/albumentationsx/analyze_albumentationsx_dataset_compatibility`
with `params={"execution_scope": "current_view"}` and pass the intended view
in the execution context. A dataset-only context uses its full view.

## Catalog filters and statuses

`show_albumentationsx_capabilities` uses the same catalog as the editor.
It has no toolbar button and is unlisted in the general operator picker.
No sample selection is required for the report.

- `query`: case-insensitive transform-name substring.
- `status_filter`: a capability status below, or `"all"`.
- `target_filter`: a declared target such as `image`, `mask`, `bboxes`, or
  `keypoints`, or `"all"`.

Supply both filters explicitly; SDK calls do not inherit App form defaults.
The report includes package versions, the capability version key, total/matching
counts, status counts, and transform rows with targets and exclusion reasons.
`transforms_json` contains the rows as copyable JSON.

| Capability status | Meaning |
| --- | --- |
| `supported` | Available in the executable selector |
| `supported_with_defaults` | Available; complex optional parameters use advanced JSON controls |
| `hidden` | Intentionally omitted from normal choices |
| `requires_external_data` | Required inputs do not yet have an executable adapter |
| `requires_manual_schema` | Requires explicit parameter-schema handling |
| `blocked_media_target` | Outside the 2D image workflow |
| `unsupported_target` | Requires target handling unavailable in the selector |
| `unsupported_output` | Can produce outputs incompatible with image storage |
| `unsupported_schema` | Cannot be represented safely by the available schema |

The installed dependency versions determine the catalog. Target filters describe
transform metadata; they do not prove compatibility with every annotation value
in a selected dataset. Supported reference-image transforms may still report
external input requirements because the plugin supplies their inputs. See
[reference-image behavior](external-data-transforms.md).

## Dataset compatibility report

`analyze_albumentationsx_dataset_compatibility` is also unlisted. The editor uses
the same reporting logic for its inline compatibility details. For a full report:

```python
import fiftyone as fo
import fiftyone.operators as foo

dataset = fo.load_dataset("your-image-dataset")
execution = foo.execute_operator(
    "@albumentations/albumentationsx/analyze_albumentationsx_dataset_compatibility",
    ctx={
        "view": dataset.view(),
        "params": {"execution_scope": "current_view"},
    },
)
execution.raise_exceptions()
print(execution.result["report_json"])
```

Use the intended filtered view in place of `dataset.view()`. Scope values match
the augmentation operator: `selected_samples`, `current_view`, or `entire_dataset`.
The context must include a nonempty sample selection for `selected_samples`.

The report contains source scope/count, package versions, schema warnings,
annotation fields, target families, and recommendations. Field statuses are
`copy_supported`, `transform_supported`, `conditional`, or `unsupported`; roles
are `copied`, `transformed`, or `excluded`. `source_count_available` distinguishes
an unknown count from a known empty scope. `report_json` is useful for bug reports.

This report is advisory. Use **Validate without creating samples** to check
actual images and selected annotation values against the intended pipeline.

## Pipeline fields

| Parameter | Contract |
| --- | --- |
| `pipeline_step_count` | Visible stage count, 1–10; default 1 |
| `transform` | First-stage transform; default HorizontalFlip |
| `pipeline_stage_enabled` | First-stage enable flag; default true |
| `pipeline_stage_order` | First-stage order, 1–10; unique among enabled stages |
| `p` | First-stage probability, 0–1; default 1 |
| `step_N_transform`, `step_N_p` | Later-stage transform/probability, N = 2–10 |
| `step_N_pipeline_stage_enabled`, `step_N_pipeline_stage_order` | Later-stage enable/order |
| `outputs_per_sample` | 1–3; default 1 |
| `execution_scope` | `selected_samples`, `current_view`, or `entire_dataset` |
| `run_label` | Optional readable run-key prefix |

Other parameters come from the selected transform's schema. First-stage names
are unprefixed; later stages use `step_N_`. Optional JSON fallback strings are
parsed before persistence. Disabled stages retain draft values but do not enter
the executable pipeline. Duplicate enabled orders are rejected.

Compatibility aliases include `brightness_range_min`,
`brightness_range_max`, `contrast_range_min`, `contrast_range_max`,
`crop_width`, and `crop_height`.

## Modes and persistence

When `_editor_action` is absent, legacy Python callers can supply
`preview_only`, `dry_run`, and `save_preset_only`; conflicting modes are
rejected. Explicit API save-and-materialize behavior remains available.
App actions are exclusive and never save merely because a name remains in a draft.

Preview uses up to three selected sources and writes nothing. It returns one
output per source regardless of `outputs_per_sample`, with source/output images,
an annotated comparison, replay JSON, transformed labels, and annotation
diagnostics. Images are PNG data URIs. Empty slots remain in the flat response
for compatibility but are omitted from the App display.

Dry run validates
the source scope and executes planned outputs in memory. Preparation can reject
the entire scope before a manifest is created. Materialized execution may
retain partial results when later output attempts fail.
See [scope and validation](albumentationsx-fiftyone-integration.md#scope-validation-and-execution).

## Loading and saving

Legacy `pipeline_preset_key` and `previous_run_key` live selectors are rejected
with migration guidance. Use
`hosts.fiftyone.pipeline_loading.load_pipeline_draft(dataset, source, params, storage_root=...)`
with `saved:<key>` or `run:<key>`, edit the returned flat parameters, and submit
that snapshot. It is independent of later changes to the saved source.

The [preset reference](pipeline-presets.md#python-callers-and-older-form-parameters)
defines import, explicit new/update saving, ID-bound confirmation, and metadata
editing. Loading restores compatible annotation names and types, not source IDs,
scope, or replay values.

## Cleanup and diagnostics

Direct cleanup callers use `run_key` and `confirm_delete=True`.
The App instead binds confirmation to the inspected run. Both paths use the
manifest allowlist. Finish execution or stop its worker before deleting outputs.

Use [Run history, storage, and cleanup](run-history.md) for run outcome,
availability, cleanup statuses, persisted metadata, and cancellation behavior.
Include dependency versions and structured errors when reporting a problem.
