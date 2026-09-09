# VOX-71: editable pipeline loading

Issue: [VOX-71](https://linear.app/albumentations/issue/VOX-71).
Branch: `feature/vox-71-editable-pipeline-loading`, based on
`feature/vox-67-coco-ux-audit` at `2c69fcd`, including VOX-68–70.

Validated on 2026-09-09 with FiftyOne 1.19.0, AlbumentationsX 2.3.8,
albu-spec 0.0.6 and Python 3.12.13. The App used an isolated dataset
`vox-71-pipeline-loading-validation`, with a copy of COCO validation image
48564 (427 × 640), detections, instance masks and keypoints. A baseline
HorizontalFlip run and a named saved pipeline both used `p=1`, selected
detections/segmentations, and excluded keypoints.

## Implementation

- One Load pipeline picker replaces the competing Named preset / Previous run
  selectors. Selecting a source keeps the draft. Explicit Replace / Reload
  copies stages, output count and annotation selection once.
- The current draft is used by preview, materialization, dry run and save.
  Removing or renaming the saved source does not alter an already loaded draft.
- Saved pipelines record annotation names/types and source dataset; loading
  restores transformed/copied fields and safely maps compatible fields.
  Missing or changed fields are explained and remain unchecked.
- Run history and saved pipeline management open the same editable snapshot.
  UI vocabulary explains pipeline, saved pipeline, run, and fresh randomness.
- The old live-selector API is rejected with migration instructions. Serialized
  storage schema and preset result keys remain compatible.

The App uses the public [Button/prompt API](https://docs.voxel51.com/api/fiftyone.operators.types.html#fiftyone.operators.types.Object.btn)
with actual nested group values. Browser testing caught an additional FiftyOne
behavior: uncontrolled inputs could retain their old state across a new prompt,
even though the server schema already described the loaded snapshot. Each snapshot therefore has its own form data paths and container identity.
Late initialization of the replaced prompt cannot write into the active draft.
The identity stays stable while editing and changes only on explicit load/reload.
This restores both checked and unchecked values without resetting user edits
during ordinary dynamic resolution. The intermediate failing observation is
retained in [diagnostic-before-draft-isolation.json](diagnostic-before-draft-isolation.json).

## Browser regression scenarios

1. Set Probability to 0 in the unsaved draft. Choose the saved `p=1` pipeline:
   Probability stays 0 until Replace is clicked.
2. Replace the draft: Probability becomes 1, the stage is enabled, detections
   and segmentations are checked, and keypoints are unchecked.
3. Change Probability to 0 and preview. The source and augmented image data URLs
   are identical. Sampled replay reports `applied: false`; the first bbox keeps
   its x coordinate around 0.22276348, rather than moving to 0.67049.
4. Repeat from run history. Edit to 0, then Reload: Probability returns to 1 and
   Preview remains enabled. Edit back to 0 and preview: images are identical.
5. Load the saved pipeline, change Probability to 0, and materialize one output
   with run label `vox71-saved-p0`.
6. Load from run history, set stage count to 2, add VerticalFlip, set both
   probabilities to 0, and change order to VerticalFlip → HorizontalFlip.
   Materialize one output with run label `vox71-run-p0`.
7. Load the saved pipeline in `vox-71-cross-dataset-mapping`, whose detections
   field has changed type and whose segmentation field was renamed. Verify
   explicit missing/type warnings and unchecked replacement fields; choose a
   replacement checkbox manually.
8. Open the manager’s **Edit a copy of this pipeline** and the run viewer’s
   **Use pipeline from this run**. Verify both open the same editable draft and
   restore annotations safely. Repeat preview through the run viewer and
   materialization through the loaded editor after the form data isolation fix.
   The final materialized check uses run label `vox71-final-p0`.

Evidence is captured from the rendered DOM in
[browser-observations.json](browser-observations.json). These are actual
control values, not `resolve_input()` defaults. Preview screenshots:
[saved pipeline](saved-pipeline-p0-preview.png),
[run history](run-history-p0-preview.png). The modified editor is shown in
[edited-run-stages.png](edited-run-stages.png). Cross-dataset guidance is shown
in [cross-dataset-mapping.png](cross-dataset-mapping.png).

Materialized output checks are in [output-checks.json](output-checks.json):
persisted pipeline parameters/order, pixel equality, bbox comparison, excluded
keypoints, and hashes of the original sample/file before and after the UI runs.
Run `node docs/audits/vox-71-pipeline-loading-validation/assert-observations.mjs`
to verify the recorded controls, preview identity and materialized checks.

Generated samples and the test baseline are confined to the validation dataset;
the original audit dataset remains unchanged. The fixtures are retained for
review; this change does not alter run cleanup.

## Automated regression coverage

The loading tests cover both sources, nested browser edits, preview and
materialization dispatch, real `p=0` pixel identity, order/count/transform edits,
reload, source deletion before execution, typed cross-dataset mapping, legacy
annotation selections, explicitly empty selections, editable JSON parameters,
stable-versus-replaced form identity, and rejection of delayed updates to old
form groups. Existing smoke scenarios now load
explicit snapshots before reusing saved configurations and runs.

Final complete gate passed:

- `uv sync --group dev` and `uv lock --check`.
- `pre-commit run --all-files`, plus explicit checks for new files.
- `pyrefly check`: 0 errors.
- Full pytest suite: **388 passed**, **89.67% coverage** (85% required), 435.24 s.

The full suite includes the headless demo operator smoke scenarios. The local
App checks above additionally exercise actual nested values, false checkboxes,
explicit reloads, cross-dataset replacement, and generated samples.
