# Release preparation: 0.1.2

Release candidate audit and verification record.
All documentation, release text, captions, and PR content are in English.

## Candidate and baseline

- Baseline: `dev` at
  `ca5507b5df3df8c816b16a0f5230b9bc235d0826` after fetching `origin/dev`.
- Recorded runtime and documentation content: `2f8aa79c4acad7d5efa41e8554161b15828ec9ee`.
- Latest published release checked: `0.1.1`. Existing candidate version: `0.1.2`.
- Version sources: `pyproject.toml`, `fiftyone.yml`, runtime `_version.py`, and
  the root package entry in `uv.lock`. No speculative version bump.
- Upstream docs base: `voxel51/fiftyone` at
  `35e5f1c2f33f7c1eec6f94ea9583c0d9bd200f3f`.
- Local environment: macOS arm64, Python 3.12.13, FiftyOne 1.19.0,
  AlbumentationsX 2.3.8, albu-spec 0.0.6. Browser acceptance uses Chromium 151.
  Optional COCO decoder: pycocotools 2.0.11.

## Documentation audit and file disposition

The initial audit covered 34 Markdown/RST files and 5,376 lines. Decisions below
describe the complete original documentation inventory. Historical material is
preserved in Git; useful runtime compatibility code remains in place.

| Original file | Decision and reason |
| --- | --- |
| `README.md` | Rewrite as installation, first workflow, capabilities, and navigation. |
| `DESIGN.md` | Retain for contributors; correct release baseline, toolbar design, and current gate. Exclude from ZIP. |
| `docs/README.md` | Maintain a clear index for installed users and source contributors. |
| `docs/albumentationsx-fiftyone-integration.md` | Rewrite against the current operators; standalone quickstart and current limits. |
| `docs/voxel51-albumentationsx-integration-template.rst` | Replace with `docs/fiftyone-integration.rst`; remove obsolete placeholders. |
| `docs/first-run-onboarding.md` | Merge into the integration quickstart; remove duplicate workflow. |
| `docs/fixed-transform-slice.md` | Retire the early implementation narrative; preserve the Python contract in `docs/operator-api.md`. |
| `docs/albu-spec-integration-audit.md` | Remove dated working audit; pin its historical Git URL and move durable policy into architecture. |
| `sample_data/README.md` | Remove duplicate demo setup; canonical instructions remain in `docs/demo-dataset.md`. |
| `docs/albu-spec-catalog.md` | Retain metadata ownership/selector policy; link archived audit by commit. Source only. |
| `docs/annotation-aware-execution.md` | Retain detailed label and metadata policy; clarify contributor checks. |
| `docs/architecture.md` | Retain and update implementation policy and checks. Source only. |
| `docs/augmentation-preview.md` | Replace old checkbox language with Action and continuation controls. |
| `docs/cancellation.md` | Retain; explain preparation before cancellation checkpoints and current labels. |
| `docs/capability-browser.md` | Retain the detailed catalog/report contract. |
| `docs/capability-report-v0.1.0.md` | Retain the original 110-transform historical snapshot, clearly labeled. Source only. |
| `docs/dataset-compatibility-report.md` | Retain; update preview/action wording. |
| `docs/demo-dataset.md` | Retain contributor fixture recipes; distinguish checkout from installed-plugin quickstart. Source only. |
| `docs/dynamic-fiftyone-forms.md` | Retain; correct rendered advanced JSON and current editor controls. Source only. |
| `docs/external-data-transforms.md` | Retain; document full reference pool and quadratic metadata growth. |
| `docs/fiftyone-operator-debugging.md` | Retain; correct action names and explicit pipeline loading. Source only. |
| `docs/gitflow.md` | Retain contribution/release process. Source only. |
| `docs/parameter-schema.md` | Retain parameter metadata contract. Source only. |
| `docs/pipeline-factory.md` | Retain compiler/runtime boundary. Source only. |
| `docs/pipeline-presets.md` | Retain complete identity, load, save, import/export, and overwrite rules. |
| `docs/plugin-navigation.md` | Retain current toolbar, history, and URI navigation. |
| `docs/pr-checklist.md` | Retain and link the existing canonical verification page. Source only. |
| `docs/release-artifacts.md` | Retain; correct bare versus v-prefixed tags, checksums, and ZIP inventory. |
| `docs/release-v0.1.0.md` | Retain historical release notes without presenting old acceptance as current. Source only. |
| `docs/release-v0.1.2.md` | Rewrite release description from published 0.1.1 to this candidate. Source only. |
| `docs/run-cleanup-operator.md` | Retain manifest-bound deletion and source preservation contract. |
| `docs/run-manifest.md` | Retain durable storage contract; update current behavior. Source only. |
| `docs/run-summary-operator.md` | Retain history/report behavior; correct Action wording. |
| `docs/verification.md` | Canonical gate plus fresh App/COCO acceptance checklist. Source only. |

The user ZIP contains the root README plus 13 selected documents. Tests verify
the reviewed input list, excluded contributor/history files, and relative link
closure. Demo recordings and upstream RST are documentation deliverables, not
runtime dependencies. Large original recordings and COCO downloads stay outside
the repository. No runtime module was removed without evidence that it is unused.

## Corrected behavior

- Run tags use `albumentationsx-run:<run-key>`, including the colon.
- Preview, create, save, and validation are mutually exclusive Action choices.
- Loading a saved pipeline/run explicitly replaces the draft; picking a source
  alone does not. New preset IDs are independent of display names.
- The plugin registers six Python operator URIs and exposes three primary actions.
- Optional advanced JSON inputs are rendered in the editor.
- Image-only color transforms copy heatmaps; mixed geometry/color pipelines
  with selected heatmaps can be blocked.
- Whole-scope preparation can reject all inputs before materialization. Dry-run
  validation executes every planned transformation in memory.
- Installation asset names normalize the version while release URLs retain
  the exact tag. Installed documentation does not assume bundled test/scripts.

## Live App fixes

Release acceptance found two FiftyOne 1.19 integration defects. Returning from
preview could lose a nested draft when delayed empty-text initialization replaced
its parameters. Returned drafts now include mounted text values. Completed
editors no longer return an empty output schema that leaves an invisible dialog
blocking toolbar actions. Regression coverage checks both host contracts; the
COCO recording verifies continued editing, saving, and toolbar navigation.

## Capability evidence map

| Capability | Implementation / verification | Guide section | Recording |
| --- | --- | --- | --- |
| Annotated preview | `operators/augment.py`; preview and geometry tests; COCO App | Quickstart | `preview.gif` |
| Ordered editable stages | `pipeline_loading.py`; editor-draft integration tests; App return with p=0 | Build a pipeline | `edit-pipeline.gif` |
| Persisted outputs | Augmentation orchestrator; source-integrity smoke; COCO creation | Preview and create | `create-outputs.gif` |
| Reusable configurations | `operators/manage_presets.py`; preset-management tests; App save/load | Save and reuse pipelines | `save-reuse.gif` |
| History and provenance | `operators/view_run.py`; run-library tests; App inspect/reuse | Inspect runs and outputs | `inspect-run.gif` |
| Scoped cleanup | `operators/delete_run.py`; cleanup tests; COCO source hashes | Delete generated outputs | `cleanup.gif` |

Implementation paths above are relative to
`albumentationsx_plugin/hosts/fiftyone`. The media manifest records exact capture
parameters, versions, attribution, and export settings.

## Validation record

Results below are local evidence, not a claim that release CI or publication ran.

| Check | Result |
| --- | --- |
| Complete pytest gate | 532 passed; 91.18% coverage against required 85%. |
| Focused documentation/artifact tests | 7 passed again after final media embedding. |
| `uv lock --check` | Passed. |
| Pyrefly | 0 errors; existing suppressions/warnings reported. |
| Toolbar Node tests | Passed. |
| Supported transform smoke | 113 passed, 0 failed, 0 skipped. |
| Wheel, sdist, plugin ZIP | Built in fresh `dist/release-0.1.2/`; six candidate files in SHA256SUMS, all verified. |
| FiftyOne page preview | Official preview plus `sphinx-build -W`; all eight images loaded. Desktop 1440 px and mobile 390 px checked; no horizontal overflow. |
| COCO acceptance | 12 sources; 131 masks and 33 poses, including 142 missing joints. Validation, 12 created outputs, and cleanup passed; source SHA256 and full labels unchanged. |
| Final App recording | Six clips, 11–24 seconds each, all below 4 MiB; save/load/edit, completed run, history, cleanup, and three unchanged COCO sources verified. |
| Media reproduction | Documented exporter reproduced all six GIF SHA256 hashes exactly. |
| Clean artifact installation | Fresh venv outside checkout; wheel imported from site-packages, then uninstalled; ZIP alone registered six operators. Both passed preview/create/cleanup with unchanged source data. |
| Clean App quickstart | ZIP-only environment: preview 1, create 1, inspect history, delete 1, close result dialogs, remove the output-only view stage, and return to 3 sources. |
| GitHub download | Documented CLI successfully installed available candidate commit `2c04dac`; no editable checkout required. |

The complete suite emitted existing dependency/deprecation warnings; none failed
the gate. The declared Python/FiftyOne compatibility range still requires the
release workflow's OS/Python matrix. See [Verification](verification.md) for
commands and the full App checklist.

## Distribution inventory

The GitHub download intentionally contains the complete tracked source tree:
251 files, about 19.21 MiB at `2c04dac`, including contributor docs, tests,
scripts, and finished media. No raw recordings, generated datasets, caches,
or logs were present. The small runtime artifacts are separate:

| Distribution | Entries | Documentation and assets |
| --- | --- | --- |
| Plugin ZIP | 145 | Root README plus 13 selected guides; registration, manifest, version, toolbar, and logos included. |
| Wheel | 132 | Runtime Python package, version, toolbar/logo package data, metadata, and license; no media or contributor docs. |
| sdist | 159 | Python build sources, README, metadata, and license; no demo media, caches, or downloaded data. |

Build in an empty staging directory before checksum generation. Existing files
from older releases in a developer's `dist/` must not enter an upload set.
Only the six current candidate assets and their SHA256SUMS belong in the draft.

## Upstream documentation handoff

Copy `docs/fiftyone-integration.rst` to
`voxel51/fiftyone/docs/source/integrations/albumentations.rst`.
Keep the old `albumentations-*` section anchors: external links must continue
to resolve. The replacement uses responsive list tables, an executable
standalone quickstart, current workflow semantics, migration guidance, and
explicit limits. It does not inherit the older plugin's availability claim.

The upstream draft must be reviewed against the published plugin release and
include its final media paths. Build it with the upstream preview script and
review desktop and narrow layouts before merging. Release publication and
upstream merge remain separate from this preparation branch.

## Review links and external gates

- [Plugin preparation PR](https://github.com/albumentations-team/voxel51-plugin/pull/75), targeting `dev`.
- [FiftyOne integration PR](https://github.com/voxel51/fiftyone/pull/8471), targeting `main`, with eight public media assets.
- Both PRs must remain drafts until the maintainer finishes their own detailed
  review and changes the status. Required CI runs and release publication remain external
  gates; local acceptance is not a claim that the OS/Python matrix has passed.
- Publish the matching release before merging the upstream integration page,
  then verify the final public tag/download links. No tag was created or pushed
  by the preparation workflow.
