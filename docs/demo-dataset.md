# Demo Dataset

Use the local demo dataset when a pull request needs a repeatable FiftyOne App
check. The workflow generates tiny PNG files locally and creates a persistent
FiftyOne dataset. It does not download external data.

## Create

These commands require a repository checkout and its development environment.
For an installed-plugin demo, use the standalone
[integration quickstart](albumentationsx-fiftyone-integration.md#quickstart).

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

## Operator smoke check

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

1. **Augment images → Create augmented samples** with a geometry transform.
2. **Run history** for the created run.
3. **Review deletion of generated outputs**, inspect the scope, and confirm.

After cleanup, generated samples/files should be gone, and the three source demo
samples/files should remain.

Use the focused [annotation acceptance](verification.md#annotation-acceptance)
checklist when validating broadened label support in the App.

## COCO acceptance

Use a source checkout for the optional real-image acceptance suite. It is
separate from the three-image quickstart and does not replace visual App checks.
Download the official COCO 2017 annotation archive once (about 241 MiB); the
helper downloads only the selected JPEGs, about a few MiB, and reuses cached
images. It never downloads the full image split or overwrites an existing dataset.

```bash
mkdir -p sample_data/generated/coco
curl -fL https://s3.us-east-1.amazonaws.com/images.cocodataset.org/annotations/annotations_trainval2017.zip \
  -o sample_data/generated/coco/annotations_trainval2017.zip
uv run --with pycocotools==2.0.11 python scripts/create_coco_acceptance.py \
  --annotations sample_data/generated/coco/annotations_trainval2017.zip \
  --data-dir sample_data/generated/coco/images
```

Launch the unique dataset name printed by the helper with
`fiftyone app launch <printed-dataset-name>`. The fixed IDs are
`138979, 130586, 260106, 448076, 81988, 119445, 261888, 231508, 570756, 378116,
350148, 48564`. The first eleven are a seed-51 selection from CC BY images with
person keypoints; 48564 is an additional portrait regression case. This is a
documented selection, not an attempt to reconstruct an older unpublished sample.

The helper explicitly imports instance masks from `instances_val2017.json` and
person keypoints from `person_keypoints_val2017.json`. It requires nonempty masks,
actual poses, and missing joints before persisting the dataset. The recorded
12-image import contains 131 nonempty masks, 33 person poses, and 142 missing
joints. Bbox-only loading does not establish this coverage.

Use `--recording-only` with a new `--name` for the three-photograph studio:
130586, 261888, and 378116. Preserve the original image URLs and licenses in the
printed baseline manifest when sharing recordings. The private regression image
48564 has a different license and is excluded from this studio.

The baseline manifest records source-file SHA-256 values and complete serialized
labels. Compare them after preview, creation, and run cleanup. Also verify that
the original source sample count is unchanged and that only generated outputs
were removed. Keep the manifest outside the plugin's run directory.

Delete an acceptance dataset by its printed unique name after verification.
Cached source images and the baseline remain separate; generated-output cleanup
must never remove them. See [Release acceptance](verification.md#release-app-acceptance)
for the UI scenarios and [media capture](media/README.md) for the recording recipe.

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
