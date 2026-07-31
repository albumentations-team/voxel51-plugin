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
- plugin, AlbumentationsX, albu-spec, and FiftyOne versions;
- output directory, output tag, manifest path, and FiftyOne run key;
- transform summary and serialized pipeline config;
- structured errors serialized as JSON.

The current dataset state is not used to guess counters. The only filesystem
state derived during summary is whether manifest-listed output files still
exist. Missing output files mark the run as `stale`.

Runs cleaned by `delete_albumentationsx_run` may still appear in this operator
because cleanup retains `manifest.json` as an audit trail.

## Failure Modes

The operator must not mutate samples, files, manifests, or FiftyOne custom runs.
It reports clear statuses instead of raising UI-visible exceptions:

- `ok`: manifest loaded and listed output files exist;
- `stale`: manifest loaded, but at least one listed output file is missing;
- `missing_manifest`: FiftyOne custom run exists, but `manifest.json` is gone;
- `invalid_manifest`: manifest exists but cannot be parsed as the expected JSON
  object;
- `not_found`: neither manifest nor matching custom run exists;
- `input_required`: no run key was selected.

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
