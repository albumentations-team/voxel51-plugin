# Cancellation Semantics

VOX-47 defines the safe behavior for interrupted or cancelled materialized
augmentation runs.

## Host Signal

Supported FiftyOne versions expose progress reporting for delegated operators,
but the current public execution context does not provide a stable cancellation
flag that the plugin can rely on. The plugin therefore uses a best-effort
`FiftyOneCancellationChecker` that watches cancellation-like context attributes
or methods if a host version exposes them later.

The executor also treats `KeyboardInterrupt` as a controlled cancellation.
Abrupt process termination, such as a hard kill while Python or native image IO
is executing, may stop the process before the plugin can write a final
`cancelled` manifest state.

## Runtime Policy

For non-dry materialized runs, the executor writes an initial manifest before it
starts processing samples. During execution it checks for cancellation before
each source, before each output, and after each output file is checkpointed.

When cancellation is observed:

- source samples and source files are never modified or deleted;
- generated output files and samples already registered in the manifest are
  retained instead of being silently removed;
- the final manifest stores `metadata.execution_status = "cancelled"`;
- the final manifest stores `metadata.cancelled_at` as an ISO UTC timestamp;
- the manifest includes an `augmentation_cancelled` structured error;
- the FiftyOne custom run is registered so `View AlbumentationsX Run` can
  inspect the partial run;
- the progress reporter receives a final `cancelled` snapshot.

Retaining partial outputs makes the state auditable and lets users decide
whether to inspect or delete generated data.

## Cleanup

`Delete AlbumentationsX Run` uses the same manifest allowlist for cancelled runs
as it does for completed runs. It removes only:

- `manifest.created_sample_ids`;
- files listed in `manifest.output_paths`;
- the matching FiftyOne custom run.

The original source samples and source files remain outside the cleanup
allowlist.

## Verification

Focused checks:

```bash
uv run pytest tests/unit/test_fiftyone_cancellation.py tests/integration/test_fiftyone_fixed_augmentation_executor.py
```

Manual App checks:

1. Start a delegated augmentation on a dataset with multiple samples.
2. Interrupt the execution if the host exposes a supported cancellation path.
3. Run `View AlbumentationsX Run` and confirm the run is marked `cancelled`.
4. Run `Delete AlbumentationsX Run` and confirm retained generated outputs are
   removed while source samples remain unchanged.
