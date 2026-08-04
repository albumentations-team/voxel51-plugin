# Run Cleanup Operator

VOX-17 adds `delete_albumentationsx_run`, a destructive but narrow FiftyOne
operator for cleaning up generated outputs from one AlbumentationsX plugin run.

## Behavior

The operator requires an explicit `confirm_delete` boolean before it mutates
anything. Without confirmation it returns `confirmation_required`.

After confirmation, cleanup loads the trusted `manifest.json` for the selected
run and deletes only:

- sample IDs listed in `manifest.created_sample_ids`;
- files listed in `manifest.output_paths`, after resolving each relative path
  under the plugin-owned run directory;
- the matching FiftyOne custom run record.

It does not delete source samples, source files, source annotations, broad
directories, or files found by globbing.

The manifest is intentionally retained as the cleanup allowlist and audit trail.
Keeping it also makes repeated cleanup idempotent: already-deleted samples and
missing files are counted as skipped no-op results.

After an `ok` or `partial` cleanup result, the operator asks the FiftyOne App to
reload the dataset so removed generated samples disappear from the grid without
a manual browser refresh.

## Safety Rules

Cleanup uses the same manifest path validation as manifest persistence:

- absolute output paths are rejected;
- parent traversal such as `../outside.png` is rejected;
- paths must resolve inside the selected run directory;
- existing non-file paths are reported as failures and are not removed.

If a manifest is malformed or contains unsafe paths, cleanup returns
`invalid_manifest` before deleting samples, files, or the custom run.

## Result Fields

The operator reports:

- deleted and skipped sample counts;
- deleted, skipped, and failed file counts;
- whether the FiftyOne custom run was deleted or already missing;
- status and message;
- structured cleanup errors serialized as JSON.

Statuses:

- `ok`: cleanup reached the desired final state;
- `partial`: some files could not be deleted, so the custom run is retained;
- `confirmation_required`: `confirm_delete` was not checked;
- `missing_manifest`: custom run exists, but `manifest.json` is gone;
- `invalid_manifest`: manifest exists but is malformed or unsafe;
- `not_found`: neither manifest nor matching custom run exists;
- `input_required`: no run key was selected.

## Verification

Use the complete local gate in [Verification](verification.md). Focused checks:

```bash
uv run pytest tests/unit/test_fiftyone_run_cleanup.py tests/unit/test_fiftyone_delete_run_operator.py tests/integration/test_fiftyone_delete_run_operator_integration.py
```

Manual inspection:

```bash
uv run python scripts/create_demo_dataset.py create --overwrite
uv run fiftyone app launch albumentationsx-demo
```

Run `Augment with AlbumentationsX` with a non-dry configuration, then run
`Delete AlbumentationsX Run` with `confirm_delete` checked. Confirm that source
samples/files remain and generated output samples/files are gone.
