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

FiftyOne registers these operators:

```text
@albumentations/albumentationsx/augment_with_albumentationsx
@albumentations/albumentationsx/view_albumentationsx_run
@albumentations/albumentationsx/delete_albumentationsx_run
```

## Run your first augmentation

1. Open a FiftyOne dataset and select one or more image samples.
2. Run **Augment with AlbumentationsX** from the App actions menu.
3. Choose the ordered pipeline stages and their parameters, then run the
   operator.
4. Inspect the resulting samples tagged by the run key. Use **View
   AlbumentationsX Run** to inspect the saved pipeline and **Delete
   AlbumentationsX Run** to remove only that run's generated outputs.

`Dry run` validates a configuration without creating samples or files.

> [!NOTE]
> Selecting `Previous run` loads its saved pipeline as a reusable template and
> samples fresh randomness. Clear that field before editing the loaded pipeline.

## Current capabilities

- The form exposes 110 catalog-backed image transforms from the current locked
  dependency set. The [capability report](docs/capability-report-v0.1.0.md)
  records the complete transform-by-transform snapshot and exclusion reasons.
- A pipeline can contain up to three ordered stages.
- The executable path keeps FiftyOne `Classification`, `Detections`,
  `Keypoints`, and in-memory `Segmentation` annotations aligned with supported
  transforms.
- Every non-dry run stores its pipeline configuration and sampled replay
  metadata. Generated samples and files can be inspected and cleaned up by run.

## Current limits

- The plugin currently processes image samples. Video, 3D media, non-image
  outputs, transforms that need external reference data, and unsafe output
  types are excluded from the normal selector.
- External mask-path variants and unsupported FiftyOne label classes are not
  part of the annotation-aware execution path.
- Some `supported_with_defaults` transforms use documented defaults until their
  advanced controls are available in the form.
- `Previous run` restores pipeline configuration; it does not reproduce each
  earlier sample's random parameters.

## Develop locally

Contributors need Python 3.10, 3.11, or 3.12,
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

Clean up the demo dataset and its generated images when finished:

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
