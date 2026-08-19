# Run Summary Operator

VOX-16 adds `view_albumentationsx_run`, a read-only FiftyOne operator for
inspecting previous AlbumentationsX plugin runs.

## Behavior

The operator lists run keys known for the active dataset from two sources:

- plugin-owned run manifests under the local storage directory;
- FiftyOne custom runs registered with `method="albumentationsx_plugin"`.

When a run key is selected, the operator returns values from the persisted
manifest:

- source, created sample, output, error, and replay counts;
- generated sample IDs that are still present in the active dataset;
- per-output availability for generated samples and output files;
- plugin, AlbumentationsX, albu-spec, and FiftyOne versions;
- output directory, output tag, manifest path, and FiftyOne run key;
- transform summary and serialized pipeline config;
- selected output source sample ID, output index, output path, generated sample
  ID, availability status, and replay JSON;
- structured errors serialized as JSON.

The current dataset state is not used to guess counters. The only filesystem
state derived during summary is whether manifest-listed output files still
exist. The operator also checks whether manifest-listed generated sample IDs
still exist so users can distinguish available outputs from stale or cleaned
audit records. Missing output files mark the run as `stale`.

Runs cleaned by `delete_albumentationsx_run` may still appear in this operator
because cleanup retains `manifest.json` as an audit trail.

The input form also exposes an `Output replay` selector when the selected run
has manifest-listed outputs. The selector defaults to the first output and lets
users inspect one JSON-safe replay record without opening `manifest.json`
manually.

When `Open generated samples` is enabled, executing the operator asks the
FiftyOne App to show the generated samples from the selected run that still
exist in the dataset. This is read-only App navigation; it does not modify the
dataset, manifest, output files, or custom run metadata.

## Failure Modes

The operator must not mutate samples, files, manifests, or FiftyOne custom runs.
It reports clear statuses instead of raising UI-visible exceptions:

- `ok`: manifest loaded and listed output files exist;
- `cancelled`: manifest loaded, execution was cancelled, and retained outputs
  remain inspectable;
- `stale`: manifest loaded, but at least one listed output file is missing;
- `missing_manifest`: FiftyOne custom run exists, but `manifest.json` is gone;
- `invalid_manifest`: manifest exists but cannot be parsed as the expected JSON
  object;
- `not_found`: neither manifest nor matching custom run exists;
- `input_required`: no run key was selected.

Per-output status values are separate from the aggregate run status:

- `available`: output file exists and the generated sample exists when a sample
  ID was recorded;
- `missing_output_file`: manifest lists an output path that no longer exists;
- `missing_sample`: manifest lists a generated sample ID that is no longer in
  the dataset;
- `cleaned`: cleanup was completed and the manifest is retained only for audit;
- `missing`: the manifest output entry does not include enough data to prove
  file or sample availability.

## Implementation Notes

`albumentationsx_plugin.hosts.fiftyone.run_summary` owns the read-only summary service.
`albumentationsx_plugin.hosts.fiftyone.operators.view_run` stays as a thin
FiftyOne host layer that renders the selector/output fields and delegates to the
summary service.

The operator accepts an internal `_storage_root` parameter for tests and
programmatic checks. The FiftyOne App form does not expose it.

## Verification

Use the complete local gate in [Verification](verification.md). Focused checks:

```bash
uv run pytest tests/unit/test_fiftyone_run_summary.py tests/unit/test_fiftyone_view_run_operator.py tests/integration/test_fiftyone_view_run_operator_integration.py
```

Manual inspection:

```bash
uv run python scripts/create_demo_dataset.py create --overwrite
uv run fiftyone app launch albumentationsx-demo
```

Run `Augment with AlbumentationsX` with a non-dry configuration, then run
`View AlbumentationsX Run` and select the created run key.
