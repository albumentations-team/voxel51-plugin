# VOX-74: result summaries and execution outcomes

Based on `7f3099e` (VOX-73). Branch: `feature/vox-74-result-summaries`.
Date: 2026-09-09.

## Changes

- A finished materialization stores `completed` only when it has no errors.
  Zero created samples with errors is `failed`; mixed results are `partial`.
  Controlled cancellation remains `cancelled`. The returned result, final
  manifest, FiftyOne custom run, progress and run history agree.
- Preview failures use `failed` or `partial` while retaining `preview_only`.
  Successful preview, validation and saving use `preview`, `dry_run` and
  `preset_saved`. Preflight errors have a nonempty status and no stored run.
- History interprets legacy incorrectly completed manifests from their counters
  without rewriting their contents. Manifest availability and execution status
  remain distinct. Skipped source counts are included in history.
- Results start with an outcome and counts, followed by readable error causes,
  available stage/transform/field/sample context and a recovery action. The
  first five errors are visible; the complete structured list remains available.
- Empty fields, empty editable lists and unused preview slots are omitted.
  Preview notes are displayed as text. Technical details are collapsed and offer
  native read-only JSON trees with clipboard controls and JSON download links.
- Runtime per-output errors now have the same debug bundle as preflight errors,
  including execution status. The flat API payload and draft continuation are
  retained.
- Results link to the selected run in history. Open generated samples builds a
  view from the dataset and manifest-listed existing IDs so source filters do
  not exclude outputs. In FiftyOne 1.19 this changes the grid behind the result
  modal; close the result with Done to see it.

## Verification

The new integration matrix covers single/three-image preview, validation,
save-only, creation, missing selection, oversized crop, invalid keypoints,
all-failed and partially successful execution, controlled cancellation,
preview runtime failures, legacy history and generated-sample navigation.
Immediate and delegated contexts share the same executor; a live worker is
not claimed. It checks status agreement, source bytes, cleanup boundaries,
conditional schemas and complete structured diagnostics.

Real App: FiftyOne 1.19.0, Chrome, isolated `vox-74-result-app` on port 5160.
Three test samples reference local COCO 2017 image 48564 with the checked-in
cell-phone detection copied onto them. HorizontalFlip(p=1) preview displayed
one comparison with a leading outcome, no empty error list and collapsed
technical details. JSON trees displayed source/replay/annotation data and
copy/download controls. Review and create samples restored the draft and
created one output. View in history preselected its run and showed the same
completed outcome. Open generated samples loaded a Select view with exactly
that generated sample after closing the result modal. Repeating creation with
an active sidebar `source` tag filter also opened exactly the new generated
sample and cleared the filter. During setup, switching away from the first
Select view and immediately reopening the editor hit a transient App
`Cannot read properties of undefined (reading id)` error. Reloading recovered
the App; the complete filtered scenario then passed. The stack was in the
FiftyOne frontend; its root cause was not established as a plugin defect.

Cleanup removed exactly two generated samples and two generated images through
the manifest-backed cleanup service. Three source samples and the COCO media
were retained, with zero custom runs; the source hash was unchanged by cleanup.
The test App and tab were then closed and its temporary dataset removed.
Cleaned manifests remain as audit records. User datasets were not modified.

Final verification:

- Complete suite: **453 passed**, **88.34% coverage** (85% required), 913.00s.
- Final schema/history refinements: **104 passed**, including all 17 new
  integration scenarios; unexpected/reload error cause display: **2 passed**.
- Lockfile check, pre-commit for tracked and new files, Ruff, Pyrefly and
  `git diff --check` passed.
- Cleanup verification confirmed the temporary dataset is absent and port 5160
  is closed.

Logs are in `/tmp/vox-74-validation/`: `full.log`, `final-delta.log`,
`causes.log`, `pre-commit-final.log`, `pre-commit-new-final.log`, `cleanup.log`.
The implementation is uncommitted for review on the VOX-74 feature branch.
