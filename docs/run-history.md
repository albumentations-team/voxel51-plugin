# Run history, storage, and cleanup

Open **Run history** to search executions by label, date, outcome, or transform.
Runs appear newest first. Select a run to inspect its scope, counters, pipeline,
dependency versions, output availability, errors, and sampled replay data.

## Inspect and reuse a run

- **Open generated samples** shows the run's available outputs and clears source
  filters that could hide them.
- **Open failed source samples** helps identify the inputs mentioned in errors.
- **Use pipeline from this run** opens an editable configuration with fresh
  randomness. It does not restore the old source selection or replay old outputs.
- **Inspect run** exposes full details; **Output replay details** lets you
  inspect the sampled parameters for an individual output.
- **Include cleaned runs** shows retained audit records and defaults to enabled.

Run history combines local manifests with matching FiftyOne custom runs. A run
may remain visible after output deletion because its audit manifest is retained.
Preview, validation, saved-pipeline creation, and failures rejected before
persistence do not create history entries.

## Outcomes and availability

| Outcome | Meaning |
| --- | --- |
| `running` | Output processing has started; the last checkpoint is still in progress |
| `completed` | Output attempts finished without errors |
| `partial` | Outputs were created and errors occurred |
| `failed` | Errors occurred without created samples |
| `cancelled` | Controlled interruption; already recorded outputs remain |
| `cleaned` | Cleanup completed; the manifest remains for inspection |

Processed/skipped counters count source samples; created counts generated
samples; errors counts error records. Multiple outputs or failures per source
mean these numbers need not sum to the source count.

Availability is separate from execution outcome. A completed run can later lose
an output file or sample. The detailed report uses these statuses:

| Status | Meaning |
| --- | --- |
| `ok` | The manifest loaded and listed output files exist |
| `cancelled` | The manifest records cancellation; retained outputs remain inspectable |
| `stale` | At least one listed output file is missing |
| `missing_manifest` | A custom run exists, but its manifest is missing |
| `invalid_manifest` | The manifest cannot be parsed as a valid run record |
| `not_found` | Neither the manifest nor a matching custom run exists |
| `input_required` | No run was selected |

Each output is also marked `available`, `missing_output_file`, `missing_sample`,
`cleaned`, or `missing` when its record lacks enough information to establish
availability. Read those details before reusing or deleting a run. Missing or
invalid manifests block pipeline reuse and cleanup.

Errors identify the available sample, field, stage, transform, and cause. The
App expands up to five errors; the complete structured list remains in
**Technical details**. For recovery and source-level retry behavior, follow
[Recover from errors](albumentationsx-fiftyone-integration.md#recover-from-errors).

## Storage and provenance

Generated data is stored under:

```text
~/.fiftyone/albumentationsx-plugin/<normalized-dataset-name>-<hash>/<run-key>/
```

The suffix is the first ten characters of the SHA256 hash of the original
dataset name. Copy the exact path from Run history instead of constructing it.

`manifest.json` records the pipeline, package versions, source/created sample
IDs, relative output paths, sampled replay records, counters, and errors.
Metadata includes execution scope/status, output directory/tag, annotation
policy, and the matching FiftyOne run key. Controlled cancellation also records
`cancelled_at`. The public plugin run key can contain hyphens; the separate
FiftyOne custom-run key uses a Python-identifier-compatible form.

Generated samples have `albumentationsx-output` and
`albumentationsx-run:<run-key>` tags. Their provenance includes
`albumentationsx_source_sample_id`, `albumentationsx_run_key`,
`albumentationsx_transform_summary`, and `albumentationsx_output_tag`.
See [output metadata policy](annotation-aware-execution.md#output-metadata-policy)
for copied and omitted fields.

Saved pipelines are stored separately under
`~/.fiftyone/albumentationsx-plugin/presets/`. They contain reusable configuration,
not generated outputs or cleanup records. Deleting a saved pipeline does not
delete outputs, and cleaning a run does not delete saved pipelines.

## Cancellation

Cancellation is best-effort. The supported FiftyOne execution context does not
provide a stable cancellation flag that the plugin can always use. When a host
exposes a detectable signal, or execution receives `KeyboardInterrupt`, the
plugin treats it as controlled cancellation. A hard process kill can prevent a
final checkpoint and leave the last recorded state as `running`.

Source collection, validation, and reference-image setup happen before output
progress and cancellation checkpoints. This preparation is not yet cancellable.
Use small source scopes, especially with reference-image transforms.

Once output processing starts, cancellation is checked between sources and
outputs. Already recorded files and samples are retained, with a cancelled run
record and an `augmentation_cancelled` error. Inspect them through history and
clean them only after execution has stopped. Closing an App dialog is not a
reliable way to stop a background worker.

## Cleanup

Wait for the run to finish or confirm that its worker has stopped. Cleanup does
not cancel or lock an active execution against later writes.

1. Select the run and choose **Review deletion of generated outputs**.
2. Review its label/date, generated sample/file counts, directory, and listed paths.
3. Confirm deletion for that run and inspect the result.

Cleanup deletes only `created_sample_ids` and `output_paths` recorded in the
manifest, including generated mask files, then removes the matching FiftyOne
custom run when cleanup succeeds. Paths must resolve inside this run directory;
absolute paths, parent traversal, and unsafe manifests are rejected before
deletion. Directories and unrelated files are not removed.

Source samples, images, annotations, and the audit manifest are retained.
Already missing outputs count as skipped, so repeated cleanup is safe. A partial
cleanup retains the custom run and reports file failures for inspection.

| Cleanup status | Meaning |
| --- | --- |
| `ok` | Cleanup reached the desired final state |
| `partial` | Some files could not be deleted; inspect the errors |
| `confirmation_required` | Deletion was not confirmed |
| `missing_manifest` | A custom run exists, but the allowlist is missing |
| `invalid_manifest` | The allowlist is malformed or unsafe |
| `not_found` | Neither manifest nor matching custom run exists |
| `input_required` | No run was selected |

The result reports deleted/skipped samples, deleted/skipped/failed files, custom
run removal, and structured errors. The App reloads after `ok` or `partial`.
If the grid still shows only the former outputs, remove its output-only
**Select** view stage to return to the sources.

Programmatic deletion uses `run_key` and explicit `confirm_delete=True`; see
the [operator API](operator-api.md#cleanup-and-diagnostics).
