# Python operator parameters

The [integration guide](albumentationsx-fiftyone-integration.md#python-operator-reference)
lists the six registered Python URIs. These parameters are for programmatic
callers; the App uses the Action picker and nested draft groups.

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
`crop_width`, and `crop_height`. The old fixed-pipeline import facade remains;
new host code uses `hosts.fiftyone.pipeline_compiler`, and runtime code uses
`albumentations_backend.image_pipeline`.

## Modes and persistence

When `_editor_action` is absent, legacy Python callers can supply
`preview_only`, `dry_run`, and `save_preset_only`; conflicting modes are
rejected. Explicit API save-and-materialize behavior remains available.
App actions are exclusive and never save merely because a name remains in a draft.

Preview uses up to three selected sources and writes nothing. Dry run validates
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
manifest allowlist. `_storage_root` is an internal override for isolated tests.

Use the [manifest reference](run-manifest.md) for persisted contracts and
[operator debugging](fiftyone-operator-debugging.md) for diagnostics.
