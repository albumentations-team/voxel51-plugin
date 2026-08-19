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

## MVP Smoke Check

Run the headless smoke workflow without opening the App:

```bash
uv run pytest -m smoke
```

The smoke workflow verifies local plugin discovery, creates the demo dataset,
augments one image sample, inspects the saved run, deletes the generated run,
and confirms the source samples and source files remain.

For manual App verification, create the dataset, launch the App, then run:

1. `Augment with AlbumentationsX` with a non-dry fixed transform.
2. `View AlbumentationsX Run` for the created run key.
3. `Delete AlbumentationsX Run` with confirmation checked.

After cleanup, generated samples/files should be gone, and the three source demo
samples/files should remain.

## Delete

Delete only the FiftyOne dataset:

```bash
uv run python scripts/create_demo_dataset.py delete
```

Delete the FiftyOne dataset and generated image files:

```bash
uv run python scripts/create_demo_dataset.py delete --delete-files
```

The file cleanup command refuses to delete a directory unless it contains the
marker written by the demo dataset script.
