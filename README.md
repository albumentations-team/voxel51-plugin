# AlbumentationsX plugin for FiftyOne

[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](LICENSE)

This repository contains a [FiftyOne](https://docs.voxel51.com/plugins/index.html) plugin for building and previewing [AlbumentationsX](https://albumentations.ai/docs/) augmentation pipelines on FiftyOne datasets.

> [!IMPORTANT]
> The project is in the early implementation phase. The plugin renders catalog-driven transform forms, can create augmented outputs with an ordered catalog-backed MVP transform pipeline, transforms supported FiftyOne annotations for the executable slice, can inspect saved run manifests, and can clean up generated runs; broader UX polish and target coverage are still upcoming.

## What the plugin will do

The plugin will let a FiftyOne user:

- choose AlbumentationsX transforms and configure their parameters in the FiftyOne App;
- build an ordered augmentation pipeline;
- apply the pipeline to a dataset, filtered view, or sample selection;
- create new samples without changing the source images or annotations;
- keep bounding boxes, segmentation masks, and keypoints aligned with transformed images;
- record the sampled parameters so each result can be inspected and reproduced;
- remove only the samples and files created by a specific plugin run.

Transform names, parameter types, default values, constraints, and descriptions will come from [albu-spec](https://github.com/albumentations-team/albu-spec). The repository will not maintain a second handwritten catalog of AlbumentationsX transforms.

## Current status

The implementation has started with the plugin scaffold, host-neutral contracts,
image IO helpers, a FiftyOne sample adapter, and a fixed-transform augmentation
operator. The repository currently contains:

- the [design document](DESIGN.md), written in Russian for the project owner and coding agents;
- the `AGPL-3.0-only` license text;
- a `pyproject.toml` that defines the development tools and the test groups;
- a `pre-commit` configuration that runs file checks, Ruff, and Pyrefly;
- `fiftyone.yml`, a Python package skeleton, and a registered operator that can
  create augmented image samples from selected FiftyOne samples or views;
- direct dependencies on `albumentationsx>=2.3,<3` and `albu-spec>=0.0.6,<1`;
  AlbumentationsX is installed as `albumentationsx` and imported at runtime as
  `albumentations`;
- a version-aware albu-spec capability catalog that classifies supported and
  excluded transforms before dynamic form generation;
- host-neutral albu-spec parameter schemas for transforms exposed by the MVP
  catalog;
- a dynamic FiftyOne operator form that renders catalog-backed transform
  parameters;
- a catalog-driven AlbumentationsX image pipeline factory that validates
  transform parameters, constructs runtime transforms, and records JSON-safe
  replay data;
- executable augmentation choices generated from the albu-spec capability
  catalog for transforms classified as `supported` or
  `supported_with_defaults`;
- annotation-aware execution for supported FiftyOne `Classification`,
  `Detections`, `Keypoints`, and in-memory `Segmentation` mask fields in the
  current fixed execution path;
- saved run manifests, FiftyOne custom run records, a read-only run summary
  operator, and a confirmed cleanup operator for non-dry executions.

## MVP limitations

- Annotation-aware execution covers supported FiftyOne classification,
  detection, keypoint, and in-memory segmentation mask fields in the executable
  fixed slice. Unsupported label classes, external mask-path variants, and
  broader target requirements still need follow-up work.
- The executable App flow currently applies an ordered chain of up to three transforms from the catalog-backed normal MVP choices.
- Transforms classified as `unsupported_target`, `requires_external_data`, `blocked_media_target`, `unsupported_output`, `hidden`, or `requires_manual_schema` stay out of normal executable choices but remain visible in the capability report with exclusion reasons.
- Dynamic forms hide advanced optional JSON fallback parameters for `supported_with_defaults` transforms and use documented defaults until richer controls are implemented.
- Cleanup deletes generated output samples, manifest-listed output files, and the FiftyOne custom run; it intentionally retains `manifest.json` as an audit trail.

The next implementation pull requests will improve the augmentation UX and
broaden target-aware transform coverage. See the [design document](DESIGN.md#план-работы-небольшими-pull-request)
for the complete sequence and acceptance criteria.

## Implementation rules

- Write the plugin from scratch against the current public APIs of FiftyOne, AlbumentationsX, and albu-spec.
- Do not copy files, functions, classes, or code fragments from the previous community plugin.
- Keep source samples, image files, and annotations unchanged.
- Make every supported transform visible in a capability report. Give every excluded transform a concrete reason.
- Add tests and reproducible verification commands in the same pull request as each feature.
- Keep pull requests small enough for a separate review agent to test independently.

The [design document](DESIGN.md) is the implementation contract when this summary and the detailed requirements differ.

## Project documentation

Additional development documentation lives in [`docs/`](docs/README.md):

- [Gitflow](docs/gitflow.md) describes the `feature/* -> dev -> main -> release/*` workflow;
- [Architecture](docs/architecture.md) describes the layered code boundaries and extension points;
- [Fixed transform slice](docs/fixed-transform-slice.md) describes the executable catalog-backed path;
- [Annotation-aware execution](docs/annotation-aware-execution.md) describes supported FiftyOne label conversion;
- [albu-spec catalog](docs/albu-spec-catalog.md) describes transform capability classification;
- [Parameter schema](docs/parameter-schema.md) describes host-neutral parameter fields generated from albu-spec metadata;
- [Dynamic FiftyOne forms](docs/dynamic-fiftyone-forms.md) describes catalog-backed operator rendering;
- [Pipeline factory](docs/pipeline-factory.md) describes catalog-driven transform construction and replay execution;
- [Run manifest](docs/run-manifest.md) describes saved run metadata, replay records, and custom run registration;
- [Run summary operator](docs/run-summary-operator.md) describes read-only run inspection in FiftyOne;
- [Run cleanup operator](docs/run-cleanup-operator.md) describes confirmed deletion of generated outputs;
- [PR checklist](docs/pr-checklist.md) lists required scope, safety, documentation, and verification checks;
- [Verification](docs/verification.md) centralizes local gate commands, targeted tests, and manual checks.

## Prepare a development checkout

Contributors need Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Git. The upper bound matches [FiftyOne's current Python support](https://docs.voxel51.com/installation/index.html).

```bash
git clone https://github.com/albumentations-team/voxel51-plugin.git
cd voxel51-plugin

uv sync --group dev
uv run pre-commit install
```

`uv` creates and manages the local `.venv`; manual activation is optional.
Run the complete local gate from [Verification](docs/verification.md) before
opening a pull request.

For local FiftyOne plugin discovery from this checkout, point FiftyOne at the parent directory that contains this repository:

```bash
export FIFTYONE_PLUGINS_DIR="$(dirname "$PWD")"
uv run fiftyone operators list
```

The operator list should include:

```text
@albumentations/albumentationsx/augment_with_albumentationsx
@albumentations/albumentationsx/view_albumentationsx_run
@albumentations/albumentationsx/delete_albumentationsx_run
```

Execution currently supports up to three ordered steps selected from the
catalog-backed normal MVP transform choices. With the current lockfile this is
`109` choices classified as `supported` or `supported_with_defaults`.

Review the catalog-backed MVP transform capabilities with:

```bash
uv run python scripts/report_transform_capabilities.py
```

## Create the local demo dataset

Use the deterministic demo dataset for manual App checks and smoke tests:

```bash
uv run python scripts/create_demo_dataset.py create --overwrite
uv run python scripts/create_demo_dataset.py list
uv run fiftyone app launch albumentationsx-demo
```

The workflow generates three tiny PNG images under `sample_data/generated/` and
creates a persistent FiftyOne dataset named `albumentationsx-demo`. The dataset
uses stable `demo_id` values for repeatable checks; FiftyOne internal sample IDs
are database-generated.

In the App, select one or more samples, run `Augment with AlbumentationsX`, set
`Pipeline steps`, and choose the fixed transforms for each ordered step. New output samples are written under the
plugin-owned storage directory and tagged with the run key; source samples and
source files remain unchanged. Non-dry runs also save `manifest.json` under the
run output directory and register the manifest in FiftyOne's custom run store.
Then run `View AlbumentationsX Run` to inspect persisted counts, versions,
transform config, replay availability, and stale/missing manifest state. Run
`Delete AlbumentationsX Run` with confirmation checked to remove generated
samples/files and the FiftyOne custom run; source samples and source files
remain unchanged.

Clean up the dataset and generated images with:

```bash
uv run python scripts/create_demo_dataset.py delete --delete-files
```

More details live in [the demo dataset workflow](docs/demo-dataset.md).

## What the automated tests cover

The test contract lives in [`pyproject.toml`](pyproject.toml). Every pytest test must belong to one of these groups:

- `unit` checks one isolated rule, such as converting albu-spec metadata into a form field or validating a cleanup path;
- `integration` uses real temporary image files and a temporary FiftyOne dataset to test operator execution, provenance, custom runs, and cleanup;
- `geometry` uses synthetic images with known coordinates to verify that boxes, masks, and keypoints stay aligned with transformed images;
- `smoke` verifies local plugin discovery and the headless MVP workflow from demo dataset creation through augmentation, run inspection, and cleanup.

Run the complete local quality gate from [Verification](docs/verification.md)
before handing a pull request to the review agent. That page also lists targeted
commands for `unit`, `integration`, `geometry`, and `smoke` pytest groups.

Ruff and Pyrefly read their settings from `pyproject.toml`. Pytest measures
branch coverage for the `albumentationsx_plugin` package and writes
`coverage.xml`.

## How changes are accepted

By default, one implementation agent handles one bounded pull request. The project owner may write any part of the change, revise the agent's implementation, or implement the whole pull request. A separate review agent inspects the diff, reruns the checks, and compares the observable result with the design document.

A pull request is ready for the project owner when:

- all automated checks pass;
- the README contains commands that reproduce the result;
- the FiftyOne App demonstration works when the pull request changes user-visible behavior;
- the review agent reports no blocking problems;
- source samples and files remain unchanged.

The project owner also reviews the code at the depth appropriate for the change and may modify it directly. The workflow does not require the project owner to implement the entire plugin from scratch.

## License

This repository is available under the [GNU Affero General Public License v3.0 only](LICENSE), identified by the SPDX expression `AGPL-3.0-only`.
