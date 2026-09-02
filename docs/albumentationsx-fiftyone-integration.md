# AlbumentationsX and FiftyOne Integration

AlbumentationsX for FiftyOne lets you build augmentation pipelines in the
FiftyOne App, apply them to image datasets, inspect the generated samples, and
clean up plugin-created outputs without touching source samples or source
files.

This guide documents the AlbumentationsX plugin in this repository:

```text
@albumentations/albumentationsx
```

It is not the same plugin as the older Voxel51 Albumentations integration page.
That page describes the historical `jacobmarks/fiftyone-albumentations-plugin`
workflow, including temporary batches, "last run" shortcuts, and
dataset-bound saved transforms. The current plugin uses explicit run manifests,
run-key based inspection, named pipeline presets, and allowlist-based cleanup.

## What You Can Do

- Build a pipeline of AlbumentationsX transforms from the FiftyOne App.
- Apply the pipeline to selected samples, the current view, or the whole image
  dataset.
- Generate one or more output samples per source sample.
- Preview selected-sample outputs in memory before writing files.
- Run a dry-run validation without creating samples, files, manifests, or
  FiftyOne custom runs.
- Keep supported labels aligned with compatible geometry transforms.
- Store run manifests with pipeline config, dependency versions, output paths,
  structured errors, and replay metadata.
- Reuse a previous run as a same-dataset pipeline template with fresh
  randomness.
- Save named presets that can be reused across datasets in the same plugin
  storage root.
- Inspect, export, import, rename, and delete named presets.
- Delete only the generated samples, files, and FiftyOne custom run for a
  selected augmentation run.

## Install

Install the plugin into the same Python environment that runs FiftyOne. For a
published release, prefer a tag instead of an unreviewed branch tip:

```bash
python -m pip install "fiftyone>=1.19,<2"
fiftyone plugins download albumentations-team/voxel51-plugin/<release-tag>
fiftyone plugins requirements @albumentations/albumentationsx --install
fiftyone plugins list --enabled --names-only
```

The plugin list should include:

```text
@albumentations/albumentationsx
```

Published releases also include a checksummed plugin zip for environments that
cannot use `fiftyone plugins download`. See
[Release artifacts](release-artifacts.md) for the zip install and verification
flow.

For local development:

```bash
git clone https://github.com/albumentations-team/voxel51-plugin.git
cd voxel51-plugin
uv sync --group dev
export FIFTYONE_PLUGINS_DIR="$PWD"
uv run fiftyone operators list
```

`FIFTYONE_PLUGINS_DIR` should point at this checkout, not a broad parent
directory. FiftyOne recursively scans plugin paths, so broad workspace roots
can make unrelated repositories look like broken plugins.

## Registered Operators

The plugin registers five App operators:

| Operator | Purpose |
| --- | --- |
| `Augment with AlbumentationsX` | Configure and execute an augmentation pipeline. |
| `Show AlbumentationsX Capabilities` | Search the current transform catalog and see support reasons. |
| `Manage AlbumentationsX Presets` | Inspect, export, import, rename, or delete named presets. |
| `View AlbumentationsX Run` | Inspect a saved run manifest and generated sample availability. |
| `Delete AlbumentationsX Run` | Remove generated outputs for one selected run after confirmation. |

The full operator URIs are listed in the root [README](../README.md).

## First Run

For the shortest click-by-click path, follow
[First-run onboarding](first-run-onboarding.md). The summary below shows the
same flow inline.

Create the deterministic demo dataset:

```bash
uv run python scripts/create_demo_dataset.py create --overwrite
uv run fiftyone app launch albumentationsx-demo
```

In the App:

1. Select one or more source samples.
2. Open `Augment with AlbumentationsX` from the actions menu.
3. Set `Execution scope` to `Selected samples`.
4. Enable `Preview only` for the first pass.
5. Set `Pipeline stages` to `1`.
6. Choose `HorizontalFlip`.
7. Keep `p` at `1.0`.
8. Keep `Outputs per sample` at `1`.
9. Run the operator and inspect the preview output.
10. Disable `Preview only`, optionally set a readable `Run label`, and run the
    same configuration again.

The plugin creates new output samples tagged with `albumentationsx-output` and
a run-specific tag. Source samples and source image files remain unchanged.

To inspect and clean up the result:

1. Run `View AlbumentationsX Run` and choose the generated run key.
2. Review the pipeline config, counters, dependency versions, generated sample
   IDs, and replay metadata.
3. Run `Delete AlbumentationsX Run`, choose the same run key, and check the
   confirmation box.

Cleanup removes the generated samples, generated files, and FiftyOne custom run
for that plugin run. The retained manifest remains useful for audit and stale
run diagnostics.

## Build A Pipeline

The augmentation form starts with general settings, then renders one section per
pipeline stage.

General settings include:

- `Named preset`: load a reusable pipeline template from shared plugin storage.
- `Previous run`: load a saved run's pipeline config from the active dataset.
- `Execution scope`: selected samples, current view, or entire dataset.
- `Preview only`: render bounded selected-sample previews without persistence.
- `Run label`: add a readable prefix to generated run keys.
- `Outputs per sample`: generate multiple outputs for each source sample.
- `Preset name` and `Preset description`: save the resolved pipeline as a named
  preset.
- `Save preset only`: validate and save a preset without running augmentation.
- `Pipeline stages`: choose how many stage slots are visible.

`Named preset` and `Previous run` are mutually exclusive template sources. If
both are selected, the form shows a validation message and blocks execution
until one source is cleared. This avoids silently applying one saved pipeline
over another.

Each stage has its own transform selector, `Enabled` switch, `Execution order`,
and catalog-backed parameter fields. Disabled stages are ignored without
clearing their saved values. Lower execution-order values run earlier.

The form derives defaults from the selected dataset when it can. For example,
crop-like transforms can use image dimensions from selected samples or dataset
metadata instead of forcing users to start from zero.

The form also includes a compact compatibility section. It summarizes the
selected source scope, estimated source count, schema availability, selected
annotation fields, and whether the current pipeline will transform or copy those
fields. Critical conflicts are shown before execution with a corrective action.
Run `Analyze AlbumentationsX Compatibility` when you need the full report with
field tables, target-family details, package versions, and copyable JSON.

## Preview, Dry Run, And Execution

Use `Preview only` when you want to see a small selected-sample result before
writing anything. Preview returns source images, output images, sampled replay
metadata, and transformed label JSON through the operator output.

Use `Dry run` when you want validation and scope resolution without creating
samples or files. Dry runs do not create run directories, manifests, custom
runs, or presets.

Use materialized execution when you want real generated samples in the dataset.
For small selections, immediate execution is fine. For larger views or whole
datasets, choose delegated execution in FiftyOne so the App stays responsive
while progress is reported.

## Supported Annotations

The plugin processes image samples and can keep these FiftyOne label types
aligned when the selected pipeline is compatible:

| Label type | Behavior |
| --- | --- |
| `Classification` | Copied as static labels. |
| `Detections` | Bounding boxes use Albumentations bbox targets. |
| `Detection.mask` | In-memory instance masks follow their detections. |
| `Detection.mask_path` | File-backed instance masks are loaded and returned as in-memory masks. |
| `Keypoints` | Points use Albumentations keypoint targets. |
| `Polylines` | Vertices use keypoint-style geometry semantics. |
| `Heatmap` | Maps use image-like synchronization for geometry-only pipelines. |
| `Segmentation` | Semantic masks are transformed; file-backed mask outputs are written to plugin-owned storage. |

If selected annotations cannot be transformed safely, the operator fails before
writing outputs and returns structured diagnostics. A common example is mixing a
selected heatmap with an image-only color transform such as
`RandomBrightnessContrast`; the image can change color, but the heatmap should
not receive that intensity operation.

Unsupported label classes, video media, 3D media, unsafe output-only transforms,
and unresolved external-data transforms are excluded from the normal executable
flow.

## Transform Coverage

The transform list is version-aware and comes from the current
AlbumentationsX/albu-spec catalog. For the current locked dependency snapshot:

- capability version key:
  `albumentationsx-2.3.8__albu-spec-0.0.6`
- total catalog transforms: `134`
- normal executable choices: `113`
- directly supported: `72`
- supported with default-backed advanced parameters: `41`

Use `Show AlbumentationsX Capabilities` in the App to search transforms by
name, support status, targets, external input requirements, and exclusion
reason. To regenerate the command-line report:

```bash
uv run python scripts/report_transform_capabilities.py
```

Avoid assuming that a transform count from another Albumentations release still
applies. The supported list changes when AlbumentationsX, albu-spec, or plugin
capability rules change.

## Runs And Reproducibility

Every materialized run receives a public plugin run key such as:

```text
training-flips-albumentationsx-20260901T120000Z-a1b2c3d4
```

The optional `Run label` becomes the readable prefix. The run key is used for
generated sample tags, output directories, manifest lookup, and run cleanup.

The manifest is stored under:

```text
~/.fiftyone/albumentationsx-plugin/<dataset-name>/<run-key>/manifest.json
```

It records:

- plugin and dependency versions;
- resolved pipeline config;
- source sample IDs and generated sample IDs;
- relative output paths;
- per-output replay metadata;
- counters and structured errors;
- execution scope and execution status;
- the matching FiftyOne custom run key.

`Previous run` uses the saved pipeline config as a template for a new run in the
same dataset. It samples fresh randomness. It does not exact-replay each earlier
sample's random parameters.

## Named Presets

Named presets are reusable pipeline templates stored outside dataset-specific
run directories:

```text
~/.fiftyone/albumentationsx-plugin/presets/<preset-key>.json
```

A named preset stores transform names, parameter values, output count, plugin
version, dependency versions, and optional description. It does not store source
sample IDs, generated sample IDs, output paths, custom run keys, or replay
records.

Use presets when you want a portable training recipe. Use previous runs when
you want to reuse a pipeline that was already executed on the active dataset.

`Manage AlbumentationsX Presets` supports:

- inspecting stored presets;
- exporting one preset as JSON;
- importing validated preset JSON;
- renaming a preset without changing its pipeline;
- deleting only the preset JSON file.

Preset deletion never removes generated samples, run manifests, output files,
FiftyOne custom runs, source samples, or source files.

## Data Safety

The plugin follows a conservative data model:

- source samples are not mutated;
- source image files are not overwritten;
- generated images are written under plugin-owned storage;
- generated samples carry plugin tags and provenance fields;
- cleanup deletes only manifest-listed generated samples and files;
- retained manifests make repeated cleanup and stale-run inspection possible.

The main generated fields and tags are:

| Name | Meaning |
| --- | --- |
| `albumentationsx-output` | Tag applied to generated output samples. |
| `albumentationsx-run-<run-key>` | Run-specific tag applied to generated output samples. |
| `albumentationsx_source_sample_id` | Source sample ID copied onto each generated sample. |
| `albumentationsx_run_key` | Public plugin run key copied onto each generated sample. |
| `albumentationsx_transform_summary` | Compact transform pipeline summary. |
| `albumentationsx_output_tag` | Output tag used for the generated sample. |

## Demo Data

The default stable demo command creates `albumentationsx-demo`, a small local
image dataset with `Classification`, `Detections`, `Keypoints`, `Polylines`,
`Heatmap`, and `Segmentation` labels. This `basic` suite is intentionally kept
to three samples so smoke checks stay fast and predictable.

```bash
uv run python scripts/create_demo_dataset.py list
uv run fiftyone datasets info albumentationsx-demo
uv run fiftyone app launch albumentationsx-demo
```

The repository also includes focused suites for broader manual and automated
checks:

| Suite | Dataset | Purpose |
| --- | --- | --- |
| `basic` | `albumentationsx-demo` | Stable three-sample first-run and smoke workflow. |
| `annotations` | `albumentationsx-demo-annotations` | Supported label families, multiple labels, empty containers, and boundary geometry. |
| `masks` | `albumentationsx-demo-masks` | Memory-backed and file-backed segmentation, detection masks, and heatmap assets. |
| `validation` | `albumentationsx-demo-validation` | Intentional edge cases for validation and error UX checks. |

Create focused suites individually:

```bash
uv run python scripts/create_demo_dataset.py create --suite annotations --overwrite
uv run python scripts/create_demo_dataset.py create --suite masks --overwrite
uv run python scripts/create_demo_dataset.py create --suite validation --overwrite
```

Create or inspect every suite at once:

```bash
uv run python scripts/create_demo_dataset.py create --suite all --overwrite
uv run python scripts/create_demo_dataset.py list --suite all
```

Use `annotations` when checking geometry-aware label handling, `masks` when
checking file-backed and in-memory mask assets, and `validation` when checking
structured failures such as missing media, missing mask files, unsupported label
fields, heatmap/image-only conflicts, or crops larger than the source image.

Delete generated demo datasets and local files with:

```bash
uv run python scripts/create_demo_dataset.py delete --delete-files
uv run python scripts/create_demo_dataset.py delete --suite all --delete-files
```

The complete suite reference lives in [Demo dataset](demo-dataset.md).

## Troubleshooting

### Operators Are Not Visible

Check that the plugin is installed and enabled:

```bash
fiftyone plugins list --enabled --names-only
```

For local development, confirm `FIFTYONE_PLUGINS_DIR` points at the repository
root that contains `fiftyone.yml`.

### Missing Runtime Dependencies

Install requirements into the same environment that launches FiftyOne:

```bash
fiftyone plugins requirements @albumentations/albumentationsx --install
```

If you run the App through `uv`, launch FiftyOne from the same project
environment:

```bash
uv run fiftyone app launch albumentationsx-demo
```

### Annotation Compatibility Error

Open the operator output and inspect:

- `errors_json`;
- `pipeline_config_json`;
- `operator_params_json`.

Those fields are designed to be copied into bug reports. The structured error
usually names the field, label type, transform, stage, target, and reason.

### Preset Or Previous Run Does Not Match The Form

`Named preset` and `Previous run` are both template sources. They cannot be used
at the same time. Clear one source, reload the form, and then edit or execute
the resolved pipeline.

## How This Differs From The Older Voxel51 Page

| Older page concept | Current plugin behavior |
| --- | --- |
| Install `jacobmarks/fiftyone-albumentations-plugin`. | Install `albumentations-team/voxel51-plugin/<release-tag>`. |
| Apply mostly classic Albumentations transforms. | Expose catalog-backed AlbumentationsX choices from albu-spec. |
| Temporary generated batches by default. | Materialized runs are persistent until explicitly deleted by run key. |
| Separate save-generated-augmentations operator. | Generated samples are already saved and tracked by manifest. |
| View or inspect the last augmentation run. | Inspect any available run by run key with `View AlbumentationsX Run`. |
| Dataset-bound saved transform pipelines. | Shared named presets live in plugin storage and can be reused across datasets. |
| Quickstart dataset plus optional model inference examples. | Repository-owned deterministic demo suites avoid external downloads and cover first-run, annotation, mask, and validation checks. |
| Claim broad support for all target label classes. | Supported labels are explicit and safety-checked before execution. |

## Parity And Follow-Up Roadmap

The current plugin is already stricter and more reproducible than the older
page's flow in several important ways: it uses explicit run keys instead of
"last run" state, keeps manifest-listed outputs available for audit, validates
annotation compatibility before writing data, exposes a catalog capability
browser, and separates reusable named presets from dataset-specific runs.

There are also old-page conveniences that should return as explicit follow-up
features rather than implicit behavior:

- Temporary augmentation sessions with a promote-or-discard workflow should be
  added separately from persistent runs.
- A first-class run library should make previous runs easier to browse than a
  raw run-key dropdown.
- A recommended preset gallery should help users start from safe pipelines
  without knowing AlbumentationsX transform names up front.
- Portable preset or run bundles should replace copy/paste workflows for
  sharing reusable augmentation recipes.
- Side-by-side previews with annotation overlays should make visual validation
  stronger than JSON/image preview output alone.
- Optional examples using the FiftyOne zoo or external model integrations can
  be added after the deterministic demo flow remains stable.

## Visual Asset Checklist

The first version of this guide is text-only. Before using it as a polished
public docs page, capture screenshots or short GIFs for:

- the operator list or actions menu;
- general augmentation settings;
- multi-stage pipeline configuration;
- selected-sample preview output;
- generated samples filtered by plugin output tag or run tag;
- run summary inspection;
- preset management;
- delete confirmation;
- capability browser filters.

## More References

- [Root README](../README.md)
- [First-run onboarding](first-run-onboarding.md)
- [Demo dataset](demo-dataset.md)
- [Verification](verification.md)
- [Capability browser](capability-browser.md)
- [albu-spec catalog](albu-spec-catalog.md)
- [Pipeline presets](pipeline-presets.md)
- [Run manifest](run-manifest.md)
- [Run cleanup operator](run-cleanup-operator.md)
- [FiftyOne operator debugging](fiftyone-operator-debugging.md)
- [Older Voxel51 Albumentations page](https://docs.voxel51.com/integrations/albumentations.html)
