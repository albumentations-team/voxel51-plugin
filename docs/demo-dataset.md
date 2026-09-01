# Demo Dataset

Use the local demo dataset when a pull request needs a repeatable FiftyOne App
check. The workflow generates tiny PNG files locally and creates a persistent
FiftyOne dataset. It does not download external data.

## Create

```bash
uv run python scripts/create_demo_dataset.py create --overwrite
```

The default dataset name is `albumentationsx-demo`. Generated images are written
under `sample_data/generated/albumentationsx-demo/`, which is ignored by Git.
The default `basic` suite is intentionally stable for smoke tests and keeps the
original three samples.

Create a focused suite instead:

```bash
uv run python scripts/create_demo_dataset.py create --suite annotations --overwrite
uv run python scripts/create_demo_dataset.py create --suite masks --overwrite
uv run python scripts/create_demo_dataset.py create --suite validation --overwrite
```

Create every suite at once:

```bash
uv run python scripts/create_demo_dataset.py create --suite all --overwrite
```

Named suites use these dataset names:

| Suite | Dataset | Purpose |
| --- | --- | --- |
| `basic` | `albumentationsx-demo` | Stable three-sample smoke workflow. |
| `annotations` | `albumentationsx-demo-annotations` | Supported label families, multiple labels, empty containers, and boundary geometry. |
| `masks` | `albumentationsx-demo-masks` | Memory-backed and file-backed segmentation, detection mask, and heatmap assets. |
| `validation` | `albumentationsx-demo-validation` | Intentional edge cases for validation and error UX checks. |

## Inspect

```bash
uv run python scripts/create_demo_dataset.py list
uv run fiftyone datasets list
uv run fiftyone datasets info albumentationsx-demo
uv run fiftyone app launch albumentationsx-demo
```

The dataset contains three samples with stable `demo_id` values:
`demo-001`, `demo-002`, and `demo-003`. FiftyOne's internal sample IDs are
created by the database and should not be used as stable test fixtures.
Each sample includes `Classification`, `Detections`, `Keypoints`, `Polylines`,
`Heatmap`, and `Segmentation` labels so annotation-aware execution can be
checked from the App.

List all generated demo suites:

```bash
uv run python scripts/create_demo_dataset.py list --suite all
```

The `validation` suite adds a `validation_case` field and matching tags so App
checks can filter the exact edge case. Current cases are:

| Case | Intended check |
| --- | --- |
| `heatmap_with_image_only_transform` | A selected `Heatmap` should reject mixed geometry plus image-only pipelines. |
| `missing_source_image` | Missing source files should produce a clear media input error. |
| `missing_segmentation_mask_file` | File-backed segmentation with a missing mask path should fail clearly. |
| `invalid_segmentation_mask_shape` | Unexpected mask dimensions are available for adapter robustness checks. |
| `missing_heatmap_map_file` | File-backed heatmap with a missing map path should fail clearly. |
| `unsupported_label_field` | Unsupported FiftyOne label containers remain visible for validation checks. |
| `crop_larger_than_image` | Small images are available for crop-size validation. |

## Coverage Boundaries

The demo suites cover generated data fixtures, not every operator state by
themselves. Use them together with the operator tests and the full transform
smoke helper:

```bash
uv run python scripts/smoke_supported_transforms.py
```

That helper constructs and executes every transform exposed by the normal
catalog selector against deterministic synthetic inputs. It is intended for
release/full-smoke checks rather than every small documentation-only pull
request.

## MVP Smoke Check

Run the headless smoke workflow without opening the App:

```bash
uv run pytest -m smoke
```

The smoke workflow verifies local plugin discovery, creates deterministic demo
datasets, exercises the augmentation operator with preview, materialized runs,
current-view and whole-dataset scopes, named presets, previous-run reuse, run
inspection, cleanup, automatic reload triggers, and confirms the source samples
and source files remain unchanged.

For manual App verification, create the dataset, launch the App, then run:

1. `Augment with AlbumentationsX` with a non-dry fixed transform.
2. `View AlbumentationsX Run` for the created run key.
3. `Delete AlbumentationsX Run` with confirmation checked.

After cleanup, generated samples/files should be gone, and the three source demo
samples/files should remain.

Use the focused [VOX-41 annotation acceptance](verification.md#vox-41-annotation-acceptance)
checklist when validating broadened label support in the App.

## Delete

Delete only the FiftyOne dataset:

```bash
uv run python scripts/create_demo_dataset.py delete
```

Delete the FiftyOne dataset and generated image files:

```bash
uv run python scripts/create_demo_dataset.py delete --delete-files
```

Delete all generated demo suites and their files:

```bash
uv run python scripts/create_demo_dataset.py delete --suite all --delete-files
```

The file cleanup command refuses to delete a directory unless it contains the
marker written by the demo dataset script.
