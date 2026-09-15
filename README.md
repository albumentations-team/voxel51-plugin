# AlbumentationsX for FiftyOne

[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](LICENSE)

Build augmentation pipelines in the FiftyOne App, preview their effects on
images and annotations, and create new samples while keeping source data intact.

| App action | Use it to |
| --- | --- |
| **AlbumentationsX · Augment images** | Edit transforms, preview, validate, create samples, or save a pipeline. |
| **AlbumentationsX · Saved pipelines** | Reuse, import/export, edit, duplicate, or delete configurations. |
| **AlbumentationsX · Run history** | Inspect results, reuse a run's pipeline, and review output deletion. |

Read the [complete integration guide](docs/albumentationsx-fiftyone-integration.md)
for installation, annotation support, and the full workflow.

## Install

Requirements: Python 3.10–3.14 and FiftyOne `>=1.19,<2`. Install the plugin and
its dependencies in the environment that launches FiftyOne.

```bash
python -m pip install "fiftyone>=1.19,<2"
fiftyone plugins download albumentations-team/voxel51-plugin/<release-tag>
fiftyone plugins requirements @albumentations/albumentationsx --install
fiftyone plugins list --enabled --names-only
```

Replace `<release-tag>` with an existing
[published tag](https://github.com/albumentations-team/voxel51-plugin/releases).
The final command should list `@albumentations/albumentationsx`.
This branch prepares **0.1.2**; a candidate version in the source does not mean
its GitHub Release is published. Follow the matching version's documentation.

For manual ZIP installation, see [Release artifacts](docs/release-artifacts.md).

## First augmentation

1. Open an image dataset and select one sample.
2. Open **Augment images** using the **augment** toolbar button.
3. Choose **Selected samples**, **HorizontalFlip**, and **Probability = 1**.
4. Choose **Action → Preview** and inspect the annotated comparison.
5. Click **Review and create samples**, review the scope, and submit
   **Create augmented samples**.
6. Inspect the generated samples, then open **View in history**.
7. To remove these outputs, use **Review deletion of generated outputs**,
   inspect its scope, and confirm.

Preview creates no samples or files. Created outputs persist until explicitly
deleted. The [quickstart](docs/albumentationsx-fiftyone-integration.md#quickstart)
links to an optional small demo that works without downloading models or datasets.

<a href="https://raw.githubusercontent.com/albumentations-team/voxel51-plugin/2f8aa79c4acad7d5efa41e8554161b15828ec9ee/docs/media/preview.gif"><img src="https://raw.githubusercontent.com/albumentations-team/voxel51-plugin/2f8aa79c4acad7d5efa41e8554161b15828ec9ee/docs/media/preview.gif" width="480" alt="Preview a COCO image with aligned annotations"></a>

*Preview HorizontalFlip on COCO with detections and keypoints. Select the image
to view it at full size.*

## Capabilities and limits

- Up to ten ordered stages and one to three outputs per source.
- Selected samples, current view, or the entire image dataset.
- Preview with annotated comparisons; immediate and delegated creation.
- Classification, detections and instance masks, keypoints, polylines, heatmaps,
  and semantic segmentation, subject to
  [annotation compatibility](docs/annotation-aware-execution.md).
- Shared saved pipelines with editable loading and JSON/file import/export.
- Searchable run history, provenance, and cleanup restricted to recorded outputs.
- The locked AlbumentationsX 2.3.8 / albu-spec 0.0.6 catalog exposes 113 executable
  transforms. Availability depends on the installed versions and selected targets.
- Video, 3D, distributed execution, exact replay of earlier outputs, and unresolved
  external-data transforms are outside the current workflow.
- Preparation reads the chosen source scope before progress/cancellation
  checkpoints. Reference-image transforms load the full pool and build
  per-source reference metadata; use small selections for these workflows.
  See [resource limits](docs/external-data-transforms.md#resource-limits).

## Develop and verify

```bash
git clone https://github.com/albumentations-team/voxel51-plugin.git
cd voxel51-plugin
git switch dev
uv sync --group dev
uv run pre-commit install
export FIFTYONE_PLUGINS_DIR="$PWD"
uv run fiftyone operators list
```

Keep `FIFTYONE_PLUGINS_DIR` scoped to this checkout to avoid scanning unrelated
repositories. Use the repository's
[contributor documentation](https://github.com/albumentations-team/voxel51-plugin/tree/6bbde0947adb07c1fc970671561bc0fdca235ec2/docs)
for architecture, demo scripts, the canonical verification gate, and release
procedures. The installed plugin ZIP contains user documentation; contributor
commands require a checkout.

## License

[GNU Affero General Public License v3.0 only](LICENSE).
