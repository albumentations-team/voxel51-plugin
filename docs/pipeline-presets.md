# Pipeline Presets

VOX-28 adds named, shared augmentation pipeline presets for repeated work across
datasets. A preset stores the reusable pipeline configuration only: transform
names, parameter values, output count, plugin version, dependency versions, and
optional user-facing description.

Presets do not store source sample IDs, generated sample IDs, output paths,
custom run keys, or per-output replay records. Loading a preset produces a
fresh augmentation run with fresh randomness.

## Storage Layout

Named presets are saved outside dataset-specific run directories:

```text
~/.fiftyone/albumentationsx-plugin/presets/<preset-key>.json
```

The key is derived from the preset name with a path-safe slug. Saving another
preset with the same name updates that preset while preserving its original
`created_at` timestamp and writing a new `updated_at` timestamp.

## Form Behavior

The `Augment with AlbumentationsX` general section can show two template
sources:

- `Named preset`: shared pipeline templates available across datasets in the
  same plugin storage root.
- `Previous run`: pipeline templates loaded from a saved run manifest in the
  active dataset.

If both fields are selected, the previous run is applied after the named preset
and therefore takes precedence for overlapping pipeline values.

To save a reusable preset:

1. Configure the pipeline stages and output count.
2. Fill `Preset name`.
3. Optionally fill `Preset description`.
4. Run the operator normally to both save the preset and create outputs, or
   enable `Save preset only` to validate and save the preset without running
   augmentation.

`Preview only` and `Dry run` remain non-persistent for presets unless `Save
preset only` is explicitly enabled.

## Contract

Preset JSON uses `PipelinePreset` schema version `1`:

- `schema_version`;
- `key`;
- `name`;
- `description`;
- `tags`;
- `plugin_version`;
- `dependency_versions`;
- `pipeline`;
- `created_at`;
- `updated_at`;
- `metadata`.

The saved `pipeline` is validated with the current catalog-backed pipeline
factory before it is persisted and again before it is loaded into the form.
This keeps old presets from silently running if future AlbumentationsX or
albu-spec changes make the pipeline invalid.

## Current Scope

VOX-28 provides shared storage, form loading, preset save/update, and unit
coverage for loading a preset into the form and saving one from operator
params.

VOX-48 adds **Manage AlbumentationsX Presets**, a dedicated FiftyOne operator
for preset lifecycle actions:

- `Inspect presets`: list stored presets and show selected preset JSON.
- `Export preset`: return one preset as formatted JSON.
- `Import preset`: parse JSON, require schema version compatibility, require
  the key to match the normalized preset name, validate the pipeline against the
  current executable catalog, and save only after passing validation.
- `Rename preset`: write the renamed preset first, preserve the reusable
  pipeline and `created_at` timestamp, update `updated_at`, then remove the old
  preset file.
- `Delete preset`: remove only the selected preset JSON file after explicit
  confirmation.

Import and rename reject accidental collisions unless `Overwrite existing
preset` is enabled. Preset deletion is deliberately separate from
`Delete AlbumentationsX Run`: it never removes run manifests, generated
samples, generated files, FiftyOne custom runs, source samples, or source files.

## Verification

Focused checks:

```bash
uv run pytest tests/unit/test_core_contracts.py tests/unit/test_pipeline_preset_store.py tests/unit/test_fiftyone_augment_operator.py tests/unit/test_fiftyone_manage_presets_operator.py
```
