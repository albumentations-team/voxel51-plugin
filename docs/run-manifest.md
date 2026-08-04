# Run Manifest

VOX-15 persists each non-dry augmentation execution as a plugin-owned run
manifest and registers the same data in FiftyOne's generic custom run store.

## Filesystem Layout

For local MVP runs, generated data lives under:

```text
~/.fiftyone/albumentationsx-plugin/<dataset-name>/<run-key>/
```

The run directory contains:

- `manifest.json`: JSON-serializable run metadata and cleanup allowlist;
- `images/`: generated image outputs listed by relative path in the manifest.

The public plugin `run_key` is used for the run directory, sample tags, sample
provenance fields, and manifest lookups.

## Manifest Contract

`manifest.json` stores a serialized `RunManifest` with:

- plugin version;
- `albumentationsx`, `albu-spec`, and `fiftyone` package versions;
- pipeline config;
- source sample IDs;
- created sample IDs;
- relative output file paths;
- per-output replay records;
- counters for processed, created, skipped, errors, and outputs;
- structured per-sample errors;
- metadata with output directory, output tag, and FiftyOne run key.

Output paths must be relative to the run directory. Absolute paths and parent
traversal are rejected before the manifest is saved. This makes the manifest the
future cleanup allowlist.

Manifest writes use a temporary file in the same run directory followed by
replace, so interrupted writes should not leave a partially written
`manifest.json`.

## FiftyOne Custom Run

FiftyOne generic run keys must be Python identifiers, while the public plugin
`run_key` contains hyphens. The host adapter stores a separate
`fiftyone_run_key`, derived by replacing unsafe characters with underscores.

The custom run stores:

- `plugin_run_key`: the public plugin run key;
- `manifest_path`: path to the saved `manifest.json`;
- `manifest`: the same serialized manifest payload;
- plugin and dependency versions;
- pipeline config.

Dry runs do not create output files, run directories, manifests, or custom runs.

## Run Summary

VOX-16 adds the read-only `view_albumentationsx_run` operator. It lists run keys
for the active dataset and displays counters, versions, transform config, replay
availability, output fields, and errors from `manifest.json`. If the manifest is
missing or malformed, the operator returns a clear status instead of mutating the
dataset or crashing. Details live in [Run summary operator](run-summary-operator.md).

## Run Cleanup

VOX-17 adds the confirmed `delete_albumentationsx_run` operator. Cleanup uses
the manifest as its allowlist, deletes only `created_sample_ids` and
manifest-listed `output_paths`, and removes the matching FiftyOne custom run.
The manifest file is retained for auditability and idempotent repeated cleanup.
Details live in [Run cleanup operator](run-cleanup-operator.md).

## Verification

Use the complete local gate in [Verification](verification.md). Focused checks:

```bash
uv run pytest tests/unit/test_manifest_store.py tests/integration/test_fiftyone_fixed_augmentation_executor.py
```

Manual inspection after running the demo operator:

```bash
cat ~/.fiftyone/albumentationsx-plugin/<dataset-name>/<run-key>/manifest.json
```
