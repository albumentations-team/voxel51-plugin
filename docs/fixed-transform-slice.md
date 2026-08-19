# Executable Transform Slice

VOX-10 implemented the first executable augmentation path with a deliberately
small transform allowlist. VOX-25 keeps the same end-to-end FiftyOne execution
path, but replaces the normal transform choices with albu-spec catalog-backed
MVP choices.

## Runtime Dependency

The plugin depends on `albumentationsx>=2.3.8,<3`. AlbumentationsX is installed
from the `albumentationsx` package, but the runtime API remains:

```python
import albumentations as A
```

The current lockfile resolves AlbumentationsX `2.3.8`. The executable path uses
2.3 parameter names from albu-spec, including `RandomBrightnessContrast`
`brightness_range` and `contrast_range`.

## Supported Transforms

Normal executable choices are generated from the albu-spec capability catalog.
The UI includes transforms classified as:

- `supported`
- `supported_with_defaults`

With the current lockfile this exposes `110` normal MVP choices. Transforms
classified as `unsupported_target`, `requires_external_data`,
`blocked_media_target`, `unsupported_output`, `hidden`, or
`requires_manual_schema` are not shown in normal executable choices; they remain
visible in the capability report with concrete exclusion reasons.

The original three names from VOX-10, `HorizontalFlip`,
`RandomBrightnessContrast`, and `RandomCrop`, remain only as default stage
presets for a fresh form. They do not limit the transform selector after
VOX-25.

## Operator Parameters

- `pipeline_step_count`: number of visible transform stage slots, from `1` to
  `10`; defaults to `1`.
- `transform`: slot 1 transform, selected from the catalog-backed MVP choices;
  defaults to `HorizontalFlip`.
- `pipeline_stage_enabled`: slot 1 enabled flag; defaults to `true`.
- `pipeline_stage_order`: slot 1 execution order, from `1` to `10`; defaults
  to `1`.
- `p`: slot 1 transform probability, from `0.0` to `1.0`; defaults to
  `1.0` for deterministic manual checks.
- `step_N_transform`: later-slot transforms when `pipeline_step_count` is at
  least `N`, for `2 <= N <= 10`.
- `step_N_pipeline_stage_enabled` and `step_N_pipeline_stage_order`: later-slot
  enable and execution-order controls.
- `step_N_p`: transform probability for later slots.
- `outputs_per_sample`: number of augmented samples to create per source sample,
  from `1` to `3`; defaults to `1`.
- Transform parameters are rendered from albu-spec schemas. For slot 1, names
  are unprefixed, such as `brightness_range`, `height`, `width`, and `method`.
- Later-slot transform parameters use the same names with the step prefix, such
  as `step_2_brightness_range`, `step_2_height`, and `step_10_method`.
- `dry_run`: validates selection and parameters without writing output files or
  creating samples.
- `preview_only`: renders up to three selected source samples in memory without
  writing output files, creating samples, saving manifests, or registering
  custom runs.
- `run_label`: optional short prefix added to generated run keys so users can
  find related runs more easily.

The FiftyOne prompt renders general run settings before transform details, then
shows a dedicated section for each visible pipeline stage slot. Disabled slots
are skipped without clearing their transform settings. Enabled slots are sorted
by `pipeline_stage_order`, with slot number as the tie-breaker. Toolbar
placement is context-aware: augmentation is disabled until samples are selected
or an image dataset/view is open, and run summary/cleanup actions are disabled
until persisted runs exist. The augmentation operator supports immediate and
delegated execution; immediate execution remains the default, and the form
recommends delegated execution for larger views or datasets.

Each stage heading identifies the stable slot, while `Execution order` controls
the pipeline order, so transform and parameter labels do not repeat the step
number. Parameters use short captions, readable enum labels, and switches for
booleans. Parameter controls use two columns on desktop and one column on
narrower screens. Defaults remain visible in the controls, while numeric bounds
remain part of field validation rather than repeated prose.

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
three-transform allowlist. VOX-39 replaces the hard three-stage limit with a
bounded ten-slot editor that supports add/remove/reorder semantics through
stage count, enabled flags, and execution-order values.

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

VOX-29 adds a non-persistent preview path. Preview requires selected source
samples and returns source/augmented PNG data URIs plus JSON replay and label
diagnostics in the operator output. It reuses the same runtime setup and
per-source image/annotation transformation code as materialized execution, but
it does not create output samples, files, manifests, custom runs, or dataset
reloads.

The executor accepts a small progress reporter interface. FiftyOne delegated
contexts receive updates for processed sources, planned outputs, created
outputs, skipped sources, and errors. The reporter is non-critical: progress
backend failures do not fail the augmentation run, and partial failures remain
inspectable through the run manifest.

Static parameter errors fail before writing output files when possible. Runtime
per-sample errors, such as a `RandomCrop` larger than one selected image, are
reported in the operator summary while allowing other selected samples to
complete.

## Verification

Use the complete local gate in [Verification](verification.md). For manual App
verification, create the demo dataset, launch the App, run
`Augment with AlbumentationsX`, and inspect that new output samples appear while
the original samples keep their original filepaths and tags.
