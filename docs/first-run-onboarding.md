# First-Run Onboarding

Use this guide after installing the plugin when you want the shortest path from
a fresh checkout to one visible augmented sample in the FiftyOne App.

The guided starter workflow intentionally uses one deterministic, annotation-safe
transform:

```text
HorizontalFlip(p=1.0)
```

This keeps the first run focused on learning the plugin flow instead of
debugging transform compatibility.

## Create The Demo Dataset

From the repository root:

```bash
uv run python scripts/create_demo_dataset.py create --overwrite
uv run fiftyone app launch albumentationsx-demo
```

The demo dataset contains three generated image samples with stable `demo_id`
values and supported label fields for repeatable checks.

## Preview The Starter Pipeline

In the FiftyOne App:

1. Select one sample.
2. Open `Augment with AlbumentationsX` from the actions menu.
3. Set `Execution scope` to `Selected samples`.
4. Enable `Preview only`.
5. Keep `Pipeline stages` at `1`.
6. Keep the transform as `HorizontalFlip`.
7. Keep `p` at `1.0`.
8. Keep `Outputs per sample` at `1`.
9. Run the operator.

Preview returns image and label diagnostics in the operator output. It does not
create samples, files, manifests, presets, or FiftyOne custom runs.

## Create The First Output

Open `Augment with AlbumentationsX` again with the same selected sample:

1. Set `Execution scope` to `Selected samples`.
2. Disable `Preview only`.
3. Set `Run label` to `First run demo`.
4. Keep `Pipeline stages` at `1`.
5. Keep the transform as `HorizontalFlip`.
6. Keep `p` at `1.0`.
7. Keep `Outputs per sample` at `1`.
8. Run the operator.

The new output sample appears in the App after the dataset reload trigger. It is
tagged with `albumentationsx-output` and a run-specific tag whose key starts
with:

```text
first-run-demo-albumentationsx-
```

Source samples and source image files are left unchanged.

## Inspect The Run

Run `View AlbumentationsX Run` and choose the generated run key. Check:

- processed and created counts;
- dependency versions;
- transform summary and pipeline config;
- generated sample IDs;
- replay metadata for the output.

This is the recommended place to copy diagnostics when a run behaves
unexpectedly.

## Clean Up

Run `Delete AlbumentationsX Run`:

1. Choose the same run key.
2. Check `Confirm deletion`.
3. Run the operator.

Only the generated sample, generated output file, and matching FiftyOne custom
run are deleted. The original three demo samples and generated source image
files remain available.

To delete the demo dataset and local source images when you are finished:

```bash
uv run python scripts/create_demo_dataset.py delete --delete-files
```

## Headless Check

The same first-run path is covered by the MVP smoke test:

```bash
uv run pytest tests/smoke/test_mvp_demo_workflow.py
```

That test creates the demo dataset, applies the starter pipeline to one selected
sample, verifies generated labels and files, inspects the run, deletes the
generated output, and confirms source data safety.

## Starter Defaults

The shared starter defaults live in
`albumentationsx_plugin.hosts.fiftyone.onboarding` so tests and future UI
onboarding can reuse the same configuration.

Current defaults:

| Setting | Value |
| --- | --- |
| Execution scope | `Selected samples` |
| Run label | `First run demo` |
| Pipeline stages | `1` |
| Transform | `HorizontalFlip` |
| `p` | `1.0` |
| Outputs per sample | `1` |

Keep the first-run path intentionally small. Broader preset galleries,
recommended pipelines, temporary sessions, and richer run-library UX should
live in their own focused tasks.
