# Executable Transform Slice

VOX-10 implemented the first executable augmentation path with a deliberately
small transform allowlist. VOX-25 keeps the same end-to-end FiftyOne execution
path, but replaces the normal transform choices with albu-spec catalog-backed
MVP choices.

## Runtime Dependency

The plugin depends on `albumentationsx>=2.3,<3`. AlbumentationsX is installed
from the `albumentationsx` package, but the runtime API remains:

```python
import albumentations as A
```

The current lockfile resolves AlbumentationsX `2.3.7`. The executable path uses
2.3 parameter names from albu-spec, including `RandomBrightnessContrast`
`brightness_range` and `contrast_range`.

## Supported Transforms

Normal executable choices are generated from the albu-spec capability catalog.
The UI includes transforms classified as:

- `supported`
- `supported_with_defaults`

With the current lockfile this exposes `109` normal MVP choices. Transforms
classified as `unsupported_target`, `requires_external_data`,
`blocked_media_target`, `unsupported_output`, `hidden`, or
`requires_manual_schema` are not shown in normal executable choices; they remain
visible in the capability report with concrete exclusion reasons.

## Operator Parameters

- `pipeline_step_count`: number of ordered transform steps, from `1` to `3`;
  defaults to `1`.
- `transform`: step 1 transform, selected from the catalog-backed MVP choices;
  defaults to `HorizontalFlip`.
- `p`: step 1 transform probability, from `0.0` to `1.0`; defaults to
  `1.0` for deterministic manual checks.
- `step_2_transform` / `step_3_transform`: optional additional ordered step
  transforms when `pipeline_step_count` is `2` or `3`.
- `step_2_p` / `step_3_p`: transform probability for later steps.
- `outputs_per_sample`: number of augmented samples to create per source sample,
  from `1` to `3`; defaults to `1`.
- Transform parameters are rendered from albu-spec schemas. For step 1, names
  are unprefixed, such as `brightness_range`, `height`, `width`, and `method`.
- Later-step transform parameters use the same names with the step prefix, such
  as `step_2_brightness_range`, `step_2_height`, and `step_3_method`.
- `dry_run`: validates selection and parameters without writing output files or
  creating samples.

The FiftyOne prompt renders general run settings before transform details, then
shows a dedicated section for each active pipeline stage. Toolbar placement is
context-aware: augmentation is disabled until samples are selected, and run
summary/cleanup actions are disabled until persisted runs exist.

Each stage includes target compatibility guidance generated from the
albu-spec-backed capability catalog. The guidance summarizes image, bbox, mask,
keypoint, and classification-label handling, and switches to a warning when the
active dataset schema contains label targets that the selected transform does
not declare support for. Parameter descriptions include albu-spec constraints
when available.

For `supported_with_defaults` transforms, advanced optional JSON fallback
parameters stay hidden and their albu-spec/Albumentations defaults are used.
Simple parameters remain visible. The executable form also keeps MVP-specific
manual-check defaults: `p` defaults to `1.0`. `RandomCrop` `height` and `width`
default to values derived from selected-sample image metadata when available,
limited to the smallest selected image for mixed dimensions, and otherwise fall
back to `32`.

For compatibility with the original fixed form, the runner also accepts
`brightness_range_min`, `brightness_range_max`, `contrast_range_min`,
`contrast_range_max`, `crop_width`, and `crop_height`.

VOX-13 renders these fields from albu-spec schemas. VOX-14 moved transform
construction and replay execution behind the shared catalog-driven pipeline
factory. VOX-22 lets the FiftyOne execution UI build an ordered chain. VOX-25
generates normal executable choices from the catalog instead of the original
three-transform allowlist.

## Output Behavior

Source samples, source image files, and source annotations are left unchanged.
A successful execution creates new image files under:

```text
~/.fiftyone/albumentationsx-plugin/<dataset-name>/<run-key>/images/
```

Each created FiftyOne sample is tagged with `albumentationsx-output` and
`albumentationsx-run:<run-key>`. It also stores provenance fields for the source
sample ID, run key, output tag, and transform summary.

VOX-26 copies supported classification labels and transforms supported
`Detections`, `Keypoints`, and in-memory `Segmentation` masks through
Albumentations target APIs for the fixed execution path. Unsupported label
fields are excluded from output samples and recorded in run annotation metadata
with a reason.

VOX-15 saves each non-dry execution under the run directory as `manifest.json`
and registers a FiftyOne custom run. The manifest records versions, source IDs,
created sample IDs, relative output paths, replay records, counters, structured
errors, run annotation fields, and per-output dropped target counts when
Albumentations removes boxes, points, or masks. Dry runs still avoid writing
output files or run metadata.

After a successful non-dry run creates samples, the operator asks the FiftyOne
App to reload the dataset so generated outputs are visible without a manual
browser refresh.

Static parameter errors fail before writing output files when possible. Runtime
per-sample errors, such as a `RandomCrop` larger than one selected image, are
reported in the operator summary while allowing other selected samples to
complete.

## Verification

Use the complete local gate in [Verification](verification.md). For manual App
verification, create the demo dataset, launch the App, run
`Augment with AlbumentationsX`, and inspect that new output samples appear while
the original samples keep their original filepaths and tags.
