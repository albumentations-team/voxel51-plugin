# VOX-75: plugin navigation

Date: 2026-09-09. Branch: `feature/vox-75-plugin-navigation`, created from
`feature/vox-67-coco-ux-audit` at `c6e69ec` (VOX-74). The user subsequently
requested VOX-56 from `dev`; its merged revision `8ce5e21` was integrated in
`2716ca4`, preserving the VOX-71–74 loading, draft and outcome behavior.

## Changes

- Three primary App entries: AlbumentationsX · Augment images,
  AlbumentationsX · Saved pipelines and AlbumentationsX · Run history.
  Compact toolbar logo buttons have one-word captions and named tooltips.
  Narrow grids use FiftyOne's More items menu. Existing six operator URIs remain
  registered; compatibility, capability reporting and deletion are unlisted
  implementation/API entries.
- Transform search, target filtering and help live beside each stage. The
  current transform and parameters survive filter changes. Compatibility stays
  in an expandable editor section; preview and results keep the existing draft.
- Immediate creation opens manifest-listed generated samples from the dataset,
  clearing source filters. A navigation failure cannot discard a successful
  result. Delegated execution retains its existing result flow.
- History reuses VOX-56's metadata listing. It shows label/date/outcome, opens
  outputs or failed source samples, loads an editable snapshot, and hands the
  selected run to cleanup. The legacy previous-run reuse button was removed in
  favor of the VOX-71 snapshot loader. History and inspector share the VOX-74
  execution status calculation.
- Search cannot leave an old selection paired with another run's actions.
  Excluded or cleared selections require choosing a matching run.
- Cleanup previews label/date, existing and missing sample/file counts, the run
  directory and manifest-listed paths. The history handoff fixes the run and
  binds confirmation to it. Invalid/missing/unsafe manifests block the form.
  The existing deletion allowlist and source preservation policy are retained.

## Automated verification

The new integration scenarios cover three primary operators with six callable
Python URIs, discovery without pipeline changes, automatic output navigation, editable
history reuse, confirmation boundaries, safe file paths, cleanup audit records,
failed-source navigation and recovery from a navigation failure. Existing tests
cover saved-pipeline loading, per-output replay, metadata and annotation handling.

- Full suite: **478 passed**, **87.51% coverage** (85% required), 941.01s.
  The targeted runs below cover subsequent history/cleanup refinements.
- Final navigation/history/cleanup/status/doc delta: 59 passed.
- Final filtered/cleared run selection checks: 18 passed.
- Lockfile, dependency sync, Ruff, Pyrefly and pre-commit passed. Dependency sync
  used `--inexact` to preserve the existing audit-only pycocotools installation.

## Real App verification

FiftyOne 1.19.0, Chrome, isolated `vox-75-navigation-app` on port 5161. Three
source samples reference COCO 2017 validation image 48564 with the fixture's
cell-phone detection. Desktop viewport: 1920×936; laptop: 1366×768.

At desktop size, changing probability to zero, opening Compatibility details,
and filtering by bboxes preserved the current HorizontalFlip draft. Preview
succeeded; Review and create samples restored p=0 and produced one output.
The grid switched to a Select view containing that output. View in history
preselected the named run and displayed matching counts and p=0.

At laptop size, the history-to-cleanup transition showed one generated sample
and one file, a concrete run directory, and a disabled destructive submit until
confirmation. Returning to history and loading its pipeline restored p=0;
changing it to p=1 and naming the repeat run produced a new output. Manifest
inspection confirmed both executions retain their respective probabilities.
Save pipeline then created a reusable p=1 configuration without more samples.
The UI clears sample selection on output navigation; returning to the editor
correctly asks the user to review the new selection before another creation.

The search test found a stale selector/detail mismatch, now fixed and covered
by tests for missing, empty and null selections. A seeded run with a manifest
under a different test storage root also exercised the missing-manifest display.

The final three compact toolbar actions fit at 1366×768. Saved pipelines
opened the newly saved configuration, and Edit a copy of this pipeline restored
its p=1 value and displayed the correct saved-pipeline origin in the editor.

Cleanup removed exactly three generated samples and three images across the
seeded run and two UI runs. Both task-created presets were deleted. Source sample
IDs, complete sample dictionaries and the COCO file hash stayed unchanged during
cleanup. The temporary dataset was then removed; cleaned manifests remain as
audit records. The browser tab was closed and its viewport override reset. The
port-5161 App process was stopped.
Test datasets had separate names; the App used the existing local MongoDB
service (localhost:57585), rather than a separate server instance.

### Branding follow-up

The three primary labels and their prompt headings now include `AlbumentationsX`.
Toolbar buttons display a locally bundled official Albumentations mark, with a
white variant for the orange action background and the red variant in operator
configuration. All six operator configurations have a logo; cleanup also has a
branded prompt heading. Action tooltips contain the full operator label.
The user requested distinct one-word captions alongside the logos; a small
directly shipped `ComponentView` now displays `augment`, `pipelines` and `history`
using FiftyOne's shared React/MUI runtime. No frontend build step is required.

Final label/schema/documentation/release checks: 30 passed. Six Node tests cover
the App launchers, native component types, captions, local asset paths, correct
Python prompt targets, disabled states, keyboard activation and overflow handoff; CI runs them with
`node --test tests/frontend/test_toolbar.cjs`. The three-primary-entry integration
check also passed. ZIP/wheel verification includes both SVG files and toolbar
script. Ruff, Pyrefly and pre-commit passed.
The branding App pass uses a separate one-source `vox-75-branding-app` fixture;
it opens forms without executing augmentation or changing saved pipelines.
At 1920×936 all three logo-and-caption buttons are visible. At 1366×768 the
native More items menu contains the overflowing pipelines/history buttons;
opening pipelines from it shows the correct saved-pipeline prompt. Clicking
augment opens the editor, and pressing Enter on history opens the run-history
prompt. The temporary dataset was removed, the test App stopped, and the browser
tab and viewport override were cleaned up.

This is a focused COCO navigation check, not a full COCO dataset or long-running
worker certification. Actual deletion is verified through the real operator
classes in isolated integration tests; the browser pass inspects its preview
and confirmation boundary. Broader saved-pipeline lifecycle and discovery work
remain VOX-49 and VOX-58 scope.

Logs: `/tmp/vox-75-validation/` (`full.log`, `delta.log`, `selection.log`,
`pre-commit.log`, `pre-commit-new.log`, and App validation logs).

VOX-75 implementation changes remain uncommitted for review; only the `dev`
integration is committed.
