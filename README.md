# AlbumentationsX plugin for FiftyOne

[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](LICENSE)

This repository will contain a [FiftyOne](https://docs.voxel51.com/plugins/index.html) plugin for building and previewing [AlbumentationsX](https://albumentations.ai/docs/) augmentation pipelines on FiftyOne datasets.

> [!IMPORTANT]
> The project is in the design and repository-setup phase. There is no installable plugin yet.

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

The implementation has not started. The repository currently contains:

- the [design document](DESIGN.md), written in Russian for the project owner and coding agents;
- the `AGPL-3.0-only` license text;
- a `pyproject.toml` that defines the development tools and the test groups;
- a `pre-commit` configuration that runs file checks, Ruff, and Pyrefly.

The first implementation pull request will create the FiftyOne plugin structure and register one empty operator. See the [design document](DESIGN.md#план-работы-небольшими-pull-request) for the complete sequence and acceptance criteria.

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
- [PR checklist](docs/pr-checklist.md) lists required scope, safety, documentation, and verification checks.

## Prepare a development checkout

The runtime dependencies will be added with the first implementation pull request. Today, contributors need Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Git. The upper bound matches [FiftyOne's current Python support](https://docs.voxel51.com/installation/index.html).

```bash
git clone https://github.com/albumentations-team/voxel51-plugin.git
cd voxel51-plugin

uv sync --group dev
uv run pre-commit install
uv run pre-commit run --all-files
```

`uv` creates and manages the local `.venv`; manual activation is optional.

## What the automated tests cover

The test contract lives in [`pyproject.toml`](pyproject.toml). Every pytest test must belong to one of these groups:

- `unit` checks one isolated rule, such as converting albu-spec metadata into a form field or validating a cleanup path;
- `integration` uses real temporary image files and a temporary FiftyOne dataset to test operator execution, provenance, custom runs, and cleanup;
- `geometry` uses synthetic images with known coordinates to verify that boxes, masks, and keypoints stay aligned with transformed images;
- `smoke` constructs every transform marked as supported and applies it to the target types claimed by the capability registry.

The first implementation pull request will add the `tests/` directory. Until then, pytest has no tests to collect. Once the suite exists, run all tests with:

```bash
uv run pytest
```

Run one group with `uv run pytest -m unit`, replacing `unit` with `integration`, `geometry`, or `smoke`. Pytest also measures branch coverage for the `albumentationsx_plugin` package and writes `coverage.xml`.

Pyrefly performs static type checking: it compares annotations with the values passed through the code and reports mismatches before the plugin runs. After the first Python files are added, run it directly with:

```bash
uv run pyrefly check
```

Run the complete local quality gate before handing a pull request to the review agent:

```bash
uv run pre-commit run --all-files
```

Ruff and Pyrefly read their settings from `pyproject.toml`. The Pyrefly pre-commit hook checks the whole Python project whenever a Python file is part of a commit.

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
