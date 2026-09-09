# VOX-69: annotation metadata validation

Issue: [VOX-69](https://linear.app/albumentations/issue/VOX-69).
Branch: `feature/vox-69-preserve-annotation-metadata`, based on
`feature/vox-67-coco-ux-audit` at `2848d14`, including the merged VOX-68 fix.

Validated on 2026-09-09 with Python 3.12.13, FiftyOne 1.19.0 and
AlbumentationsX 2.3.8. The original [COCO audit](../coco-ux-2026-09-09/README.md)
records the lost `iscrowd` and `supercategory` attributes.

## Change

Dynamic and legacy label attributes, nested JSON values, label/container tags
and per-point metadata are preserved across the supported annotation families.
Legacy attribute types and their metadata are retained, and user field names
cannot overwrite the annotation payload structure. Unsupported values are
reported instead of stringified. Known geometry-derived attributes are
explicitly excluded on transformed labels; copied annotation fields retain them.

The form, preview, dry run and materialization results explain included and
omitted annotations, source sample fields, new output identities, source lookup
and attribute exclusions. The same structured policy is stored in the run
manifest. See the complete [output metadata policy](../../annotation-aware-execution.md#output-metadata-policy),
including the conservative handling of geometry-derived values.

## Manual App scenario

The App runs at `http://localhost:5153` with a separate clone named
`vox-69-label-metadata-validation`, initially containing the 12 original COCO audit
samples. The original audit dataset is unchanged.

1. Select image 48564, `000000048564.jpg` (427 × 640).
2. Open **Augment with AlbumentationsX**. Keep `detections` and `keypoints`
   selected and uncheck `segmentations`. Confirm **Output metadata** updates to
   list `segmentations` as omitted, and `coco_id`/source tags as omitted sample
   fields.
3. Use **HorizontalFlip**, probability 1, one output per sample, selected-sample
   scope, and **Preview only**. Result: processed=1, preview=1, created=0, errors=0.
   The result identifies `keypoints.keypoints[0].num_keypoints` as an excluded
   derived attribute; transformed labels retain the detection custom attributes.
4. Reopen with the same transform and annotation selection, disable preview and
   use run label `VOX-69 verification`. Result: processed=1, created=1, errors=0.
   The App refreshes to 13 samples and displays the same metadata policy.

The saved output retains `iscrowd=0` and `supercategory=electronic` on the cell
phone detection, with new label/sample IDs. The unchecked segmentation field,
source sample `coco_id` and source sample tags are omitted. Source provenance
resolves to the original sample. Output pixels equal the horizontal flip of the
original image; the keypoint pose retains 17 slots and seven missing points.

A separate readback compares materialized label attributes and manifest policy
with a deterministic preview. A dry run over all 12 originals with all three
annotation fields passes. Original annotations, tags and import IDs match the
untouched audit dataset. The clone and its output remain available for review.
Cleanup is verified in the automated integration scenario.

Existing result-form verbosity and preview sizing remain covered by VOX-74 and
VOX-70. Custom output tags and tag inheritance remain covered by VOX-78.

## Regression coverage

- Round trips for all six supported label families, dynamic/container tags,
  nested objects, lists, NumPy arrays, user field names that overlap payload
  keys, and per-point values.
- Legacy attribute values and types, categorical confidence/logits, and a
  same-named dynamic field and legacy attribute.
- Derived attribute exclusions on transformed labels, retention on copied
  labels, and exact warnings for unsupported dynamic and legacy values.
- A small real COCO detection annotation fixture uses the official FiftyOne
  importer with deterministic local media, without downloading a dataset.
  The operator integration scenario checks the input form, preview, dry run,
  materialization, manifest, source immutability, omitted fields and cleanup.

## Checks

- `uv sync --group dev` and `uv lock --check`: passed.
- Complete `uv run pytest --cov-fail-under=85 -q --disable-warnings`:
  **367 passed**, coverage **89.47%**, 345.51 seconds. This includes the headless
  user-scenario smoke suite and the VOX-68 keypoint regression checks.
- `uv run pre-commit run --all-files`, plus explicit checks of the new Python,
  fixture and evidence files: passed, including Ruff and Pyrefly.
- Separate `uv run pyrefly check` and `git diff --check`: passed.

## Evidence

- [Updated form after unchecking segmentations](01-output-policy-form.png)
- [Preview result and attribute exclusions](02-preview-metadata.png)
- [Materialization result](03-materialized-metadata.png)
- [COCO readback checks](real-coco-results.json)
