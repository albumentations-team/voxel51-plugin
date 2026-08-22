# AlbumentationsX plugin for FiftyOne

[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](LICENSE)

Build and apply AlbumentationsX augmentation pipelines directly in the
[FiftyOne](https://docs.voxel51.com/plugins/index.html) App. The plugin writes
new output samples, keeps supported annotations aligned with geometric changes,
and leaves the selected source samples and files unchanged.

## Install a published release

Install the plugin into the same Python environment as FiftyOne. Replace
`<release-tag>` with a published GitHub tag, rather than installing an
unreviewed branch tip.

```bash
python -m pip install "fiftyone>=1.19,<2"
fiftyone plugins download albumentations-team/voxel51-plugin/<release-tag>
fiftyone plugins requirements @albumentations/albumentationsx --install
fiftyone plugins list --enabled --names-only
```

The final command should list `@albumentations/albumentationsx`.

Published tags also attach a checksummed FiftyOne plugin zip for workflows that
cannot use the GitHub download helper. See
[Release artifacts](docs/release-artifacts.md) for the zip install path and
artifact verification commands.

FiftyOne registers these operators:

```text
@albumentations/albumentationsx/augment_with_albumentationsx
@albumentations/albumentationsx/show_albumentationsx_capabilities
@albumentations/albumentationsx/manage_albumentationsx_presets
@albumentations/albumentationsx/view_albumentationsx_run
@albumentations/albumentationsx/delete_albumentationsx_run
```

## Run your first augmentation

1. Open a FiftyOne image dataset or view. Optionally select samples if you want
   to process only a subset.
2. Run **Augment with AlbumentationsX** from the App actions menu.
3. Choose the execution scope, ordered pipeline stages, and transform
   parameters. Optionally enable `Preview only` to inspect up to three selected
   samples in memory, then disable it and run the same configuration to create
   outputs. Optionally choose a named preset or save the current pipeline as a
   reusable preset.
4. Inspect the resulting samples tagged by the run key. Use **Manage
   AlbumentationsX Presets** for shared preset import/export/rename/delete,
   **View AlbumentationsX Run** to inspect the saved pipeline, and **Delete
   AlbumentationsX Run** to remove only that run's generated outputs.

`Execution scope` controls whether the operator processes selected samples, the
active current view, or the entire dataset. `Preview only` renders source and
augmented images, sampled replay parameters, and transformed label JSON for a
bounded selected-sample preview without creating samples, files, manifests, or
custom runs. `Dry run` validates a configuration and reports the resolved source
scope without creating samples or files. Use immediate execution for small
bounded selections; use delegated execution for larger views or datasets to keep
the App responsive while progress is reported.

> [!NOTE]
> Selecting `Previous run` loads its saved pipeline as a reusable template and
> samples fresh randomness. Clear that field before editing the loaded pipeline.
> `Named preset` loads a shared pipeline template that can be reused across
> datasets in the same plugin storage root.

## Current capabilities

- The form exposes 113 catalog-backed image transforms from the current locked
  dependency set. [albu-spec Catalog](docs/albu-spec-catalog.md) records the
  current transform-by-transform snapshot and exclusion reasons.
- **Show AlbumentationsX Capabilities** exposes the same catalog in the App with
  search, status filtering, target filtering, dependency versions, supported
  targets, advanced-parameter status, and exclusion reasons.
- Form controls use compact captions, readable enum labels, and responsive
  parameter groups instead of repeating defaults and constraints as prose.
- A pipeline can contain up to ten stage slots. Each slot can be enabled or
  disabled, and lower `Execution order` values run earlier.
- Runs can target selected samples, the active current view, or the entire
  dataset.
- Selected samples can be previewed in memory before creating persistent output
  samples.
- Augmentation supports both immediate execution and delegated execution.
  Progress reports processed sources, planned outputs, created outputs, skipped
  sources, and errors.
- Interrupted or cancelled materialized runs keep source data unchanged, mark
  the run as `cancelled`, and retain manifest-listed partial outputs for
  inspection and cleanup.
- The executable path keeps FiftyOne `Classification`, `Detections`,
  `Keypoints`, `Polylines`, `Heatmap`, and semantic `Segmentation`
  annotations aligned with supported transforms. `Detection(mask=...)` and
  `Detection(mask_path=...)` instance masks follow their bounding boxes;
  detection mask outputs are stored as in-memory `Detection.mask` values.
  `Polylines` vertices use Albumentations keypoint targets. `Heatmap` maps
  use image-like targets for geometry and write transformed output maps in
  memory.
  `Segmentation(mask_path=...)` outputs write plugin-owned mask PNGs that are
  listed in the run manifest for cleanup.
- Reference-image transforms `FDA`, `HistogramMatching`, and
  `PixelDistributionAdaptation` use the current execution scope as a reference
  pool. For each source sample, the plugin passes the other source samples as
  preloaded reference images and records the reference source ids in replay
  metadata.
- Every non-dry run stores its pipeline configuration and sampled replay
  metadata. Generated samples and files can be inspected and cleaned up by run.
- Named pipeline presets can be saved from the augmentation form and loaded
  across datasets. They persist only the reusable pipeline config and dependency
  versions, not sample IDs, output paths, or replay records.
- **Manage AlbumentationsX Presets** can inspect, export, import, rename, and
  delete named presets. Import validates the preset schema and pipeline against
  the current executable catalog before saving. Deleting a preset removes only
  the preset JSON file, not runs, generated samples, output files, or sources.

## Current limits

- The plugin currently processes image samples. Video, 3D media, distributed
  execution, non-image outputs, unresolved donor-object/mosaic/overlay/text
  external-data transforms, and unsafe output types are excluded from the normal
  selector.
- FiftyOne `>=1.19,<2` does not expose a stable public cancellation flag to
  operators, so cancellation detection is best-effort; abrupt process
  termination can still stop before a final `cancelled` checkpoint is written.
- Unsupported FiftyOne label classes are not part of the annotation-aware
  execution path.
- `Polylines` use vertex-based transform semantics. Crops do not perform full
  polygon clipping; vertices outside the output image can be removed, and
  contours with too few remaining points are dropped.
- Heatmap support is intended for geometry-only target synchronization. When a
  selected heatmap would be transformed by a geometric stage, the plugin blocks
  mixed image-only color/intensity stages until per-target replay can keep
  heatmap values untouched by those effects.
- `supported_with_defaults` transforms expose simple typed controls plus an
  advanced JSON section for optional complex parameters.
- `Previous run` restores pipeline configuration; it does not reproduce each
  earlier sample's random parameters.
- `Named preset` restores reusable pipeline configuration across datasets; it
  does not store source samples, generated outputs, or sampled replay values.

## Develop locally

Contributors need Python 3.10 through 3.14,
[uv](https://docs.astral.sh/uv/getting-started/installation/), and Git.

```bash
git clone https://github.com/albumentations-team/voxel51-plugin.git
cd voxel51-plugin
uv sync --group dev
uv run pre-commit install
```

For local development, point FiftyOne only at this checkout. A broad workspace
directory makes FiftyOne recursively scan unrelated repositories for plugins.

```bash
export FIFTYONE_PLUGINS_DIR="$PWD"
uv run fiftyone operators list
```

Create the deterministic demo dataset and open it in the App:

```bash
uv run python scripts/create_demo_dataset.py create --overwrite
uv run fiftyone app launch albumentationsx-demo
```

The workflow generates three tiny PNG images under `sample_data/generated/` and
creates a persistent FiftyOne dataset named `albumentationsx-demo`. The dataset
uses stable `demo_id` values plus `Classification`, `Detections`, `Keypoints`,
`Polylines`, `Heatmap`, and `Segmentation` labels for repeatable checks;
FiftyOne internal sample IDs are database-generated.

In the App, run `Augment with AlbumentationsX`, choose `Execution scope`
(`Selected samples`, `Current view`, or `Entire dataset`), set `Pipeline stages`,
optionally choose `Named preset` to prefill the form from a shared pipeline
template, optionally choose `Previous run` to prefill the form from a saved run
in this dataset, optionally set `Run label` and `Outputs per sample`, and choose
a catalog-backed transform for each visible stage slot. Each stage slot can be
skipped with `Enabled` or moved by changing `Execution order`. Fill `Preset
name` to save the current pipeline as a reusable named preset; enable `Save
preset only` to save it without running augmentation. Select one to three source
samples and enable `Preview only` to render source/augmented image previews,
sampled replay parameters, and transformed label JSON without writing files,
creating samples, or registering a run. `Dry run` validates the
configuration and reports the resolved source scope without writing files or
creating samples. Run small selections immediately. For larger views or full
datasets, choose delegated execution in FiftyOne's execution dialog so the App
can remain responsive and report live progress. Previous-run settings are used
as a reusable pipeline template with fresh randomness, including all saved
stages up to the current ten-slot editor limit, not as an exact replay of
earlier sampled parameters. Clear `Previous run` after loading if you want to
keep editing the form without reapplying the saved pipeline. New output samples
are written under the plugin-owned storage directory and tagged with the run
key; source samples and source files remain unchanged. Non-dry runs also save
`manifest.json` under the run output directory and register the manifest in
FiftyOne's custom run store. If a materialized run is cancelled or interrupted
after outputs have been created, retained partial outputs are recorded in the
manifest so they can be inspected and deleted by run.
Then run `View AlbumentationsX Run` to inspect persisted counts, generated
sample availability, versions, transform config, per-output replay records, and
stale/missing manifest state. The viewer can also open the generated samples
that still exist in the active dataset. Run `Manage AlbumentationsX Presets` to
inspect shared presets, export one as JSON, import validated preset JSON, rename
presets, or delete only a preset JSON file. Run
`Delete AlbumentationsX Run` with confirmation checked to remove generated
samples/files and the FiftyOne custom run; source samples and source files
remain unchanged. Cleaned runs remain inspectable through the retained manifest
audit trail, but they are hidden from cleanup run-key suggestions.

Clean up the dataset and generated images with:

```bash
uv run python scripts/create_demo_dataset.py delete --delete-files
```

## Verify changes

```bash
uv sync --group dev
uv lock --check
uv run pre-commit run --all-files
uv run pytest --cov-fail-under=85
uv run pyrefly check
```

Targeted checks and the manual App release checklist are in
[Verification](docs/verification.md). Implementation and architecture notes are
listed in [Project documentation](docs/README.md).

## License

This plugin is available under the [GNU Affero General Public License v3.0 only](LICENSE).
