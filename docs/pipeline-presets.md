# Saved pipelines and run history

A **pipeline** is an ordered list of transforms and their parameters. A **saved
pipeline** is a named, reusable configuration. A **run** records one execution:
its dataset, source scope, status, generated outputs, and sampled replay data.
The current **draft** is the editable configuration in the Augment form.

## Load an editable copy

In **Augment images**, use the single **Load pipeline** picker:

- **Current unsaved draft** keeps the current configuration.
- **Saved pipeline: …** selects a named configuration from shared storage.
- **From run history: …** selects a run from the active dataset.

Selecting a source does not change the draft. Click **Replace draft with
selected pipeline** to replace it. The editor then shows its origin and offers
**Reload and replace draft** to explicitly discard subsequent edits and load
that source again. Changing or clearing the picker keeps your existing edits.
The origin is context, not an active override.

Preview, materialization, dry run, and saving all use the visible draft. For
example, load `HorizontalFlip(p=1)`, change Probability to `0`, and preview or
run: the image will not flip. Stage count, order, Enabled, transform selection,
and all parameters remain editable. The loaded copy still executes if its
source is later renamed or deleted, including when execution is delegated.

**Run history → Use pipeline from this run** and **Saved pipelines → Edit a copy of this pipeline** open the same
editor with an independent snapshot. Every execution uses fresh randomness;
loading a pipeline does not reproduce an earlier output's replay or seed.

## What loading replaces

| Setting | Load behavior |
| --- | --- |
| Transforms and parameters | Replace with saved enabled transforms in execution order; old stage parameters are removed. |
| Outputs per sample | Restore the saved count; editable afterward. |
| Annotation selection | Restore compatible saved fields as described below. |
| Scope, current sample selection/view | Keep the current execution context. |
| Run label and chosen action | Keep current form settings. |
| Save name, description, mode and target | Keep current form settings; loading does not enable saving. Replacement confirmation is cleared. |
| Seed, replay, source IDs, output paths | Do not restore. |

Only executable stages are saved, as before. Loading rejects pipelines above
the ten-stage editor limit rather than silently truncating them.

## Annotation mapping

New saved pipelines record the selected field names and label types in
`metadata.annotation_selection`, with the source dataset name. Loading restores
both transformed and copied annotations, including an explicitly empty
selection. Fields omitted by a run remain unchecked; adding new annotation
fields to the dataset does not enable them in the loaded copy.

Across datasets, only matching names **and** label types are checked. Missing,
unsupported, changed, or unknown types are listed in **Review loaded
annotations**. Choose replacement fields explicitly using the annotation
checkboxes, or leave them unchecked to omit them. No approximate mapping or
automatic inclusion of every supported field takes place.

Older runs without typed metadata restore `pipeline.target_fields` and
`pipeline.copy_fields` by name within the same dataset. Older saved pipelines
with no annotation selection load with all fields unchecked and an explanation.
Review those fields before executing. Checkboxes remain editable after loading.

## Save and manage

Choose **Action → Save pipeline**. The **Save pipeline settings** section opens;
choose a save mode, fill **Saved pipeline name** and optionally **Saved pipeline description**.
**Save as new pipeline** always creates a separate configuration, including when
the exact display name already exists. **Update existing pipeline** requires
selecting **Pipeline to replace** and checking **Confirm replacement**. The load
picker never chooses a replacement target. Returning to the editor or loading
another pipeline clears replacement confirmation.
Saving creates no dataset samples. The result lets you return to the editor,
preview, or review the scope before creating samples. Names and descriptions
remain in the draft, but other UI actions do not implicitly save a pipeline.

The Python API continues to support `preview_only`, `dry_run`, and
`save_preset_only` when `_editor_action` is absent, including its validation of
conflicting modes and its explicit save-and-materialize behavior.

Shared storage remains `~/.fiftyone/albumentationsx-plugin/presets/<preset-key>.json`.
New pipelines use `pipeline-<uuid>` IDs independent of their display names.
Unicode, punctuation, case, whitespace and long names cannot select an existing
file for replacement. Names may repeat; selectors include IDs to distinguish
them. Updates and renames keep the ID and `created_at`, and update `updated_at`.
Updates also retain existing tags and custom metadata.

Existing files migrate in place: legacy slug IDs and filenames remain valid,
including `preset.json`. No files are bulk-renamed and existing `saved:<key>`
references continue to work after a rename or update. `build_preset_key(name)`
remains a legacy compatibility helper, not the allocator for new pipelines.
Previously overwritten configurations cannot be recovered by this change.
The `PipelinePreset` JSON
schema remains version `1`; annotation selection is backward-compatible
metadata. Imported and loaded pipelines are validated against the current
transform catalog. Saved pipelines exclude source IDs, output IDs and paths,
run cleanup allowlists, and per-output replay records.

**Saved pipelines** provides inspect, export, import, edit details, duplicate,
rename, and delete actions. The recommended workflow is:

1. **Export saved pipeline**: choose a pipeline and copy the entire
   **Importable pipeline JSON** object. The overview table is only a summary.
   The separately labelled local path points to the JSON file on the server.
2. **Import saved pipeline → Paste full JSON**: paste that object. Alternatively,
   select **Local JSON file** and enter its absolute path (or `~/…`) on the
   machine running FiftyOne. A path on a remote browser's computer is not a
   server path. Files must be regular UTF-8 `.json` files, at most 4 MiB; URLs,
   relative paths, `..`, control characters and symbolic links are rejected.
3. Import validates the same portable schema and executable pipeline for both
   modes before writing. The imported ID is retained, independent of the name.
   To replace that exact ID, check **Overwrite existing saved pipeline**.
   Matching names with different IDs remain separate configurations.
4. **Edit saved pipeline details** updates name, description, tags and optional
   metadata JSON. Keep `annotation_selection` metadata to retain annotation
   mapping. **Rename saved pipeline** changes only its display name.
   **Duplicate saved pipeline** creates a new ID and keeps the source unchanged.
   Use **Edit a copy of this pipeline** to edit transforms in the augmentation
   editor, then choose a save mode explicitly.

Errors for malformed JSON, summary JSON, unsafe paths, missing/non-JSON files,
invalid schemas and unsupported pipelines include a stable `reason` in
`errors` / `errors_json`. Validation errors and unconfirmed updates preserve
the original file bytes. New saves publish atomically without replacing an
existing ID, even when writers race; confirmed updates replace files atomically.

Deletion requires confirmation and removes
only the selected configuration file. **Run history → Review deletion of generated outputs** remains
the action for generated outputs and run cleanup.

## Python callers and older form parameters

The legacy `pipeline_preset_key` and `previous_run_key` live selectors are no
longer accepted by execution. They return `pipeline_load_required`, or
`preset_source_conflict` when both are supplied, with migration guidance.
Internal storage names and serialized output keys such as `preset_key` remain
compatible. Management results expose `importable_preset_json` as the canonical
copyable payload. `presets_json`, `selected_preset_json` and
`exported_preset_json` remain response aliases for older callers but are not
rendered as competing JSON fields in the App.

For import, use `action="import"`, `import_mode="json"` (the default) with
`preset_json`, or `import_mode="file"` with `import_path`. Set `overwrite=True`
only to replace the imported ID. New editor/API saves default to
`save_preset_mode="new"`; updates require `save_preset_mode="update"`,
`save_preset_target=<existing ID>` and `save_preset_confirm_update={<existing ID>: True}`.
Confirmation is bound to the target ID; switching targets requires a new check.
The low-level file store also defaults to `overwrite=False`.
Metadata edits use `action="edit"`, `preset_key=<ID>` and the object returned by
`preset_edit_group(<ID>)` as the parameter key, containing optional `name`,
`description`, `tags` (list of strings), and `metadata_json` (JSON object text).

Python callers can explicitly copy a configuration with
`hosts.fiftyone.pipeline_loading.load_pipeline_draft(dataset, source, params,
storage_root=...)`, where `source` is `saved:<key>` or `run:<key>`. Edit the
returned flat params and pass them to the augmentation operator. The App packs
that snapshot into its own nested form group before opening the editor. This
isolates it from delayed updates to a replaced prompt, so actual checkbox/input
values match the configuration rather than relying on schema defaults. See [verification](verification.md) for the complete gate and smoke
scenarios.
