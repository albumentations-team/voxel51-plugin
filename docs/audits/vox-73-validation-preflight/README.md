# VOX-73: validation and dry-run preflight

Date: 2026-09-09. Based on `6185f53` (VOX-72 merged into the VOX-67 audit
branch). Implementation branch: `feature/vox-73-validation-preflight`.

## Behavior

- The form and operator share configuration validation, including constructor
  parameters, malformed JSON, enabled stages, output count and unique order.
  Errors mark the corresponding properties invalid; the form disables submit.
  Duplicate orders name the conflicting stage slots and mark both order fields.
- Preview without a selection, empty execution scope and saving without a name
  are blocked in the form. The exclusive actions introduced in VOX-72 remain;
  contradictory legacy API modes still fail server validation.
- Disabled stages keep their raw draft values and hide inactive controls. Their
  invalid parameters and duplicate orders do not block an otherwise valid draft.
- Error-containing sections expand. Text/number errors remount their field
  wrapper and use the released App's `componentsProps.field.autoFocus` support.
  This preserves the draft while bringing the invalid control into view.
- Inline dimension checks resolve the App's `selected_samples` ID descriptors
  to sample metadata. The server independently reads actual images and selected
  annotation assets for **every** source before creating a manifest or output.
  A valid first image followed by an oversized-crop failure creates no partial run.
- Known shape inference follows execution order through flips, brightness/
  contrast, crop and resize, and ignores zero-probability stages. Unknown geometry
  ends static inference; it is not evaluated against an incorrectly assumed
  original image size.
- Dry run additionally executes every planned output through the same in-memory
  image/annotation path used by preview and creation. Errors retain sample,
  transform, stage/parameter context where available. No images, annotation
  assets, samples, manifests or custom runs are written by dry run.
- Save-only checks configuration and annotation compatibility; image-dependent
  validation is a separate explicit action. The legacy save-and-create API
  preflights source data before saving the named pipeline as well.

## Validation limits shown in the editor

Dry run evaluates sampled stochastic branches, not every possible future random
outcome. It does not check output write permissions or promise that source data
will remain unchanged before a later execution. Saving a reusable pipeline does
not claim image-dependent validation. These limits appear next to the relevant
editor action and are documented in the execution guide.

## Automated coverage

Final complete suite: **436 passed**, **90.10% coverage** (85% required),
857.10 seconds. Log: `/tmp/vox-73-validation/pytest-final-full.log`.
Lockfile validation, pre-commit for tracked and new files, Ruff, Pyrefly and
`git diff --check` pass. Changes are uncommitted and ready for review.

The regression matrix exercises preview, validation, save, immediate creation
and a delegated operator context against duplicate order, invalid probability,
malformed JSON and no enabled stages. It asserts field invalidity, server errors,
unchanged source bytes and absence of files/custom runs. Additional scenarios
cover oversized crop/recovery, corrupt media without metadata, empty selection,
missing name, disabled invalid stages, legacy mode conflicts, all-source preflight,
actual execution after geometry outside static inference, and App selection ID
descriptors. Delegated tests exercise the shared worker entry point; no live
worker endurance run is claimed.

COCO 2017 image 48564 (427 x 640), with a detection from the checked-in annotation
fixture, was also checked independently. Crop 9999 x 9999 failed in preview,
validation and creation before writes. Dry run with height 320 / width 200
processed one source successfully. Source SHA-256 was unchanged, dataset count
stayed one, custom-run count stayed zero, and the output root did not exist.

## Real App checks

FiftyOne 1.19.0 / Chrome, isolated `vox-73-validation-app`, 1920 x 936 viewport.
The test dataset uses the existing local COCO image and a copied annotation;
no original audit dataset is modified.

- No selection + Preview: inline selection error; Preview button disabled.
- Save pipeline + blank name: save section expands, name error is visible,
  Save pipeline button disabled. Entering a name clears the error and enables it.
- Two stages with order 1: both order fields display the conflicting stage
  numbers, submit is disabled. Changing stage 2 to order 2 clears the errors and
  enables submit.
- COCO 48564 + RandomCrop(height=9999): Height shows the sample/stage error
  and the 640-pixel bound, and Create is disabled. After tabbing to Width while
  validation resolves, focus returns automatically to Height.
- Correcting the crop to height 320 / width 200 clears the error. The explicit
  validation action shows its limits, enables submit and completes in the App
  with Processed = 1, Created = 0, Errors = 0.
- Back to editor after dry run restores RandomCrop, height 320 / width 200,
  annotation selection, source scope and the validation action.
- Stage 2 probability = 2: its field error blocks validation and receives focus.
  Disabling that stage hides its inactive parameters and enables validation.
  Re-enabling restores probability = 2 and the error, proving the value survives.

The first real-App crop check exposed that selection descriptors omit metadata;
that observation drove the descriptor-resolution fix and its regression test.
Autofocus verification also exposed that FiftyOne View serialization merges
constructor kwargs last. Reconstructing the FieldView with the final props fixes
this; the test asserts the serialized field props, and the App check confirms
actual focus movement.
Local logs and independent COCO checks are in `/tmp/vox-73-validation/`.

After the App checks, the dataset still contained one source and zero custom
runs. The task-owned test dataset, server and browser tab were removed; the
original COCO media and user datasets were retained.
