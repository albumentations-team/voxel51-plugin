# VOX-72: editable draft continuity

Date: 2026-09-09. Branch: `feature/vox-72-preserve-editor-draft`, based on
`ecea979` (`feature/vox-67-coco-ux-audit`, including VOX-71).

## Implementation

The augmentation editor now exposes one action: Preview, Create augmented
samples, Save pipeline, or Validate without creating samples. The submit label
matches that action. Preview, validation, and saving use immediate execution;
creation retains the immediate/delegated choice. A saved-pipeline name retained
in the draft does not implicitly save during another UI action. The existing
boolean Python API remains available when `_editor_action` is absent.

Every result retains a transient submitted draft, including ordered stages,
parameters, disabled stages, raw invalid JSON, annotation checkboxes, output
count, scope, run label, save settings, and loaded-pipeline context. Back to
editor, Preview again, and Review and create samples restore isolated input
paths, so old form initialization cannot overwrite the restored values.
Creation opens the editor for review before execution. No seed or replay from
a preview is applied: the configuration is preserved, with fresh randomness.

Returned drafts retain an explicit source scope and dataset identity. Empty
selection cannot silently change Selected samples into Current view. A change
in selected IDs after opening the editor, including a different selection of
the same size, is rejected before creation. Reopening refreshes the selected
IDs/counts for review. Loading a pipeline maps annotations to the current
dataset explicitly.

Transforms are above annotation selection and optional reports. Library, save
settings, run options, compatibility, metadata, and result diagnostics use
native details/summary sections via GridView component props; collapsing keeps
controls mounted. Annotated comparisons appear first in preview results.
Known shared validation errors block submission in the editor. Runtime errors
retain the raw draft and offer a correction path; successful retries clear the
previous error notice.

## Host issues found during browser verification

1. The released FiftyOne 1.19 frontend ignores ObjectView's newer `collapsible`
   option. Replaced it with native details/summary sections through supported
   component props. Confirmed their collapsed layout and mouse expansion in the
   real App at 1366×768.
2. A native completed operator prompt retains its execution state when a button
   attempts to replace it with another input prompt. The original Back to editor
   implementation remained on the old result with a loading indicator. Kept this
   observation in `diagnostic-original-result-prompt.json`.
3. The final implementation presents immediate UI results through the public
   `show_output` operation and returns an empty native output schema, allowing
   the completed editor to close before it is reopened. UI detection uses the
   explicit editor action rather than relying on `prompt_id`, which can be
   absent. The output-event payload and empty native schema have regression
   coverage, including a missing prompt ID.

## Verification evidence

- Full suite: **402 passed**, **90.01% coverage** (85% required), 507.18 seconds.
  Local log: `/tmp/vox-72-validation/pytest-final.log`.
- Additional execution after the final App-detection adjustment:
  **14 integration tests passed**, including real preview → returned draft →
  creation, errors/retry, malformed JSON, disabled stages, selection changes,
  dataset boundaries, save/preview separation, action labels, and the independent
  output-modal protocol. Local log:
  `/tmp/vox-72-validation/editor-flow-final.log`.
- `uv sync --frozen --group dev`, `uv lock --check`, pre-commit, Pyrefly, and
  `git diff --check` passed. New files are also checked explicitly.
- Browser observations confirm two configured stages, reordered execution,
  outputs per sample = 2, keypoints unchecked, and a useful comparison displayed
  before diagnostic reports. `preview-1366.png` shows the preview layout at
  1366×768 **before the final output-modal adjustment**; it is not evidence that
  the final continuation worked in the browser.
- An independent Python-operator run on `vox-72-editor-draft-validation` used the
  configuration recorded from the App: VerticalFlip(p=0) then
  HorizontalFlip(p=1), two outputs, detections and segmentations included,
  keypoints omitted. Both outputs match the expected pixels and bounding boxes;
  the source image and source fields are unchanged. See `output-checks.json`.
  This execution was via Python, not a browser materialization claim.

The test dataset contains two copied source samples and two generated outputs.
The original audit dataset was not modified. The local App is on port 5158.

## Remaining manual acceptance check

**The final browser continuation and keyboard-only flow remain unverified.**
The browser connection began timing out on navigation, DOM reads, screenshots,
and attempts to close the test tabs. Reconnecting and opening a fresh tab did
not restore page control. Do not treat the passing Python tests as completion
of this manual gate.

When browser control is available:

1. Open the App and configure two stages, their order and probabilities, output
   count = 2, a run label, and one unchecked annotation field.
2. Preview. Confirm the independent result window opens and the annotated
   comparison is visible before diagnostics.
3. Back to editor: verify all values, check focus, and expand/collapse optional
   sections with Tab and Enter/Space. Preview again and repeat the return.
4. Review and create samples: confirm current selected IDs/counts and scope,
   create outputs, then return from the successful result.
5. Repeat after a runtime error and with an empty/changed source selection.
6. Save a pipeline, return, and preview; the retained name must not trigger a
   save. Check the interaction between the result window and the reopened editor
   when cancelling/closing, including focus and any remaining backdrop.
7. Repeat at 1366×768 and reset any temporary viewport override afterward.

Closing a transient editor/result is not persistent draft storage. Save a
pipeline for later reuse; persistent temporary sessions remain outside VOX-72.
