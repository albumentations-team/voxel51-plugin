# COCO first-user audit — 2026-09-09

Tracker: https://linear.app/albumentations/issue/VOX-67

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

This attachment contains the audit conclusions already filed in the linked issues. It intentionally excludes machine-local paths, runtime sample IDs, debug bundles and screenshots. Original source hashes remained unchanged in the real operator cleanup checks. Existing tests: 342 passed. Live tests: bbox/mask preview, materialization and run viewing succeeded; valid COCO missing keypoints, pipeline overrides and UX failures require fixes. Large-data performance, other FiftyOne versions and a live delegated worker were not certified.

## Product direction

Three entry points: Augment images, Saved pipelines, Run history. Integrate compatibility and transform discovery in the editor. Move cleanup into run history with a specific preview and confirmation. Use one Load pipeline action to load an editable snapshot from saved pipelines or history; distinguish a pipeline configuration from a run instance and exact replay.

## Task index

* [VOX-68](https://linear.app/albumentations/issue/VOX-68/handle-missing-coco-keypoints-without-aborting-preview-dry-run-or): Handle missing COCO keypoints without aborting preview, dry run, or augmentation
* [VOX-69](https://linear.app/albumentations/issue/VOX-69/preserve-coco-dynamic-label-attributes-and-explain-output-metadata): Preserve COCO dynamic label attributes and explain output metadata policy
* [VOX-70](https://linear.app/albumentations/issue/VOX-70/preserve-aspect-ratio-in-source-augmented-and-comparison-previews): Preserve aspect ratio in source, augmented, and comparison previews
* [VOX-71](https://linear.app/albumentations/issue/VOX-71/unify-pipeline-loading-and-stop-saved-runs-or-presets-from-overriding): Unify pipeline loading and stop saved runs or presets from overriding visible edits
* [VOX-72](https://linear.app/albumentations/issue/VOX-72/keep-an-editable-draft-across-preview-validation-errors-and): Keep an editable draft across preview, validation errors, and materialization
* [VOX-73](https://linear.app/albumentations/issue/VOX-73/block-invalid-submissions-and-make-dry-run-validation-match-real): Block invalid submissions and make dry-run validation match real execution
* [VOX-74](https://linear.app/albumentations/issue/VOX-74/show-actionable-result-summaries-and-distinguish-failed-partial-and): Show actionable result summaries and distinguish failed, partial, and successful runs
* [VOX-75](https://linear.app/albumentations/issue/VOX-75/consolidate-six-operators-into-an-augmentation-editor-saved-pipelines): Consolidate six operators into an augmentation editor, saved pipelines, and run history
* [VOX-76](https://linear.app/albumentations/issue/VOX-76/make-output-destination-and-re-augmentation-of-generated-samples): Make output destination and re-augmentation of generated samples explicit
* [VOX-77](https://linear.app/albumentations/issue/VOX-77/add-a-reproducible-coco-first-user-acceptance-suite-and-setup-guide): Add a reproducible COCO first-user acceptance suite and setup guide

Existing tasks extended: [VOX-49](https://linear.app/albumentations/issue/VOX-49) for explicit overwrite/Unicode identities, [VOX-56](https://linear.app/albumentations/issue/VOX-56) for run-history integration, [VOX-58](https://linear.app/albumentations/issue/VOX-58) for in-editor discovery and actual annotation targets.

## Detailed findings and acceptance criteria

# VOX-68: Handle missing COCO keypoints without aborting preview, dry run, or augmentation

## Problem and evidence

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

Reproduced in the App and through the real augmentation operator: select COCO image 000000048564.jpg (COCO ID 48564), keep all annotation fields selected, and preview HorizontalFlip(p=1). The result is processed=0, created=0, errors=1, empty execution_status, and unexpected_runtime_error. Its debug bundle contains TypeError: "JSON values cannot contain NaN or infinite floats". A dry run over the selection also fails before processing.

FiftyOne represents COCO keypoints with visibility=0 as (NaN, NaN). This is valid missing-point data, not a malformed COCO sample. ID 48564 has 7 missing points; 7 of the 12 audit images contain missing points. Disabling keypoints makes the same bbox/mask preview succeed.

## Required behavior

* Preserve missing keypoint slots and their anatomical indices through conversion, transforms, serialization, preview, and output reconstruction.
* Pass only valid coordinates to transforms, retaining an explicit index/visibility mapping; serialize missingness with a valid JSON representation, then restore FiftyOne's expected representation.
* Preserve per-point visibility and confidence. Cropped-out points must not cause later COCO joints to shift into different anatomical slots.
* One unsupported annotation must produce a field/sample-specific diagnostic rather than aborting an entire selection with an unexplained generic TypeError.
* Keep strict JSON rejection for unrelated invalid values; do not simply enable arbitrary NaN in manifests.

## Implementation pointers

hosts/fiftyone/annotations/conversion.py: _keypoint_payload, target_data_from_annotation_payload, transformed_annotation_payload, _drop_empty_keypoints. core/serialization/__init__.py: normalize_json_value. augmentation/runtime.py eagerly serializes the full source selection before execution.

## Acceptance and verification

1. Preview and materialize HorizontalFlip(p=1) for COCO 48564 with all three fields enabled.
2. Check 17-slot identity and visible/confidence alignment before/after; verify source annotations unchanged.
3. Cover partially missing, entirely missing, boundary, and crop-removed keypoints, multiple people, and a mixed selection with samples without keypoints.
4. Dry run is valid for normal COCO missingness; preview and generated labels agree.
5. Add a real COCO-derived regression fixture in addition to synthetic coordinate tests.

Release priority: fix before inviting users with pose datasets.

# VOX-69: Preserve COCO dynamic label attributes and explain output metadata policy

## Problem and evidence

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

The annotation conversion silently drops native FiftyOne dynamic attributes. On COCO 48564 the first detection is "cell phone", with supercategory="electronic" and iscrowd=0. annotation_payload_from_sample → labels_from_annotation_payload removes both fields while keeping label and bounding_box. The materialization path uses this same conversion. Missing attributes are not included in dropped-annotation diagnostics.

The converter copies Detection.attributes, but FiftyOne's COCO importer stores these values as dynamic fields on Detection itself. Keypoint.visible is another relevant dynamic field and must be coordinated with the missing-keypoints fix. New samples also contain plugin provenance and selected labels but omit source sample tags and scalar fields such as coco_id; the UI does not explain this policy.

## Required behavior

* Preserve safe, serializable label metadata through preview and materialized output, including iscrowd, supercategory, user-defined label attributes, tags, and per-point fields where applicable.
* Define transformation-aware behavior for geometry-derived fields (e.g. area): recompute or clearly exclude them, rather than copying stale values.
* Define and show the source-to-output sample metadata policy. Original IDs must remain distinguishable from generated identities; expose source_coco_id or an explicit mapping if useful, rather than treating generated samples as original COCO entries.
* Explain that unchecked annotation fields are omitted from outputs; users must not infer "leave labels unchanged".
* Warn about unsupported metadata that will be excluded, with field names. Avoid silent label-data loss.

## Implementation pointers

hosts/fiftyone/annotations/conversion.py: _detection_payload, _keypoint_payload, label reconstruction. hosts/fiftyone/samples/adapter.py: create_output_sample. Annotation comparison currently reports geometry counts but not dropped attributes.

## Acceptance and verification

1. Round-trip and HorizontalFlip preserve iscrowd and supercategory on real COCO labels.
2. A mixed metadata fixture covers scalar/list/dict dynamic fields, reserved fields, and fields dependent on geometry.
3. Preview and materialized output have the same metadata policy.
4. The form/result explicitly lists excluded annotation/sample fields and preserved provenance.
5. Source files and source label attributes remain unchanged; regression tests detect removal of iscrowd.

# VOX-70: Preserve aspect ratio in source, augmented, and comparison previews

## Reproduction and measured evidence

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

1. Select COCO 48564, disable keypoints to isolate the current working detection/mask path.
2. Preview HorizontalFlip(p=1), then scroll to images.
3. The portrait becomes visibly wide and flattened even though HorizontalFlip does not change its shape.

Measured from the rendered DOM: source and output PNGs have natural size 427×640, but each is displayed at 320×240 with object-fit: fill. The annotated comparison is naturally 460×370 and displayed at 640×300, also with object-fit: fill. This misrepresents geometric augmentation and makes visual QA unreliable. Screenshot: 05-preview-comparison.png from this audit.

## Implementation

In operators/augment.py, _render_preview_output_fields creates fixed ImageView width/height values (320×240 and 640×300). Preserve intrinsic proportions with responsive bounds and contain/auto sizing. Account for source and output images having different sizes after a crop/resize. Keep the comparison readable, including its before/after labels and overlay legend.

## Acceptance criteria

* Portrait, landscape, square, and crop-resized images retain their intrinsic aspect ratios (within normal pixel rounding).
* Before/after views use a clearly defined scale and padding policy; no stretching, silent crop, or distorted boxes/masks.
* Images fit a typical 1366×768 laptop viewport as well as the audited desktop size without horizontal overflow.
* Only actual preview slots render; absent slots do not reserve image-sized blank regions.
* Add a browser-level assertion of rendered vs natural aspect ratio and manually verify the real COCO portrait. Backend pixel tests alone do not cover this bug.

# VOX-71: Unify pipeline loading and stop saved runs or presets from overriding visible edits

## Reproduction

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

1. Materialize HorizontalFlip(p=1) on a selected COCO sample with detections/segmentations enabled and keypoints disabled.
2. Reopen Augment and select that run in Previous run.
3. Change the visible Probability field to 0, disable keypoints, and preview.
4. The visible form shows p=0, but the image still flips and the output bbox moves from x≈0.22276 to x≈0.67049. Direct resolution confirms p=1.0 overrides the submitted p=0.0.

Both params_with_previous_run_preset and params_with_pipeline_preset overlay saved values on user params on every resolve/execute. Previous-run loading also omits saved target_fields/copy_fields: the original run excluded keypoints, but loading it selects keypoints again and can introduce a new failure. Current UI says "prefill", with no inline warning that edits are overridden. README's instruction to clear Previous run is not a sufficient interaction contract.

## Proposed product behavior

Use one "Load pipeline" entry point with mutually exclusive sources: Saved pipeline / From run history (plus current unsaved draft). Loading copies an editable snapshot once. Show the origin as context, not an active override. Changed values must control execution. Provide an explicit Reload action if needed.

Terminology: pipeline = ordered transform configuration; saved pipeline = reusable named configuration; run = one execution, with dataset/scope/time/status/outputs. "Use pipeline from this run" samples fresh randomness. Do not introduce "previous pipeline" as another almost synonymous entity. Exact replay remains separate VOX-60 work and is not a prerequisite for fixing this bug.

On the same dataset restore the annotation selection consistently. Across datasets map fields safely, explain missing/incompatible fields, and require a conscious replacement rather than silently enabling all annotations. Define which execution options belong to the template.

## Acceptance criteria

* Load → edit p=0 → preview/materialize executes p=0 for both named presets and previous runs; UI and effective config are identical.
* Editing count/order/transform/parameters does not require clearing a hidden source selector.
* Reusing the audited bbox/mask-only run does not unexpectedly enable keypoints.
* Only one load source can be active; no pair of competing selectors or precedence ambiguity.
* Unsaved changes are retained unless explicitly replaced; reloading/replacing a draft is clear.
* UI, docs, run library, and preset manager use the same vocabulary and explain fresh randomness.
* Add browser regression coverage; a schema-default-only test will miss visible-value/execution drift.

# VOX-72: Keep an editable draft across preview, validation errors, and materialization

## Observed problem

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

After a successful preview the output dialog offers only Close. Reopening Augment starts with the defaults: Preview only is false, run label is blank, and all annotation fields are enabled again. In the audit, keypoints had deliberately been disabled to get a working preview; reopening re-enabled them. Returning from an invalid preview similarly gives no direct correction path. A nontrivial pipeline is expensive to reconstruct and users can accidentally create outputs with different settings.

The main transform controls are below general/preset/debug-oriented text, outside the initial 1920×936 viewport. The main action remains "Run augmentation" in preview and save-only modes. Immediate/delegated execution is another separate choice.

## Proposed flow

Maintain one draft containing ordered stages, parameters, annotation selection, source scope, outputs per sample, and relevant preset context. Provide explicit actions: Preview, Create augmented samples, and Save pipeline. Validation failures remain in the editor with the offending field visible. Preview results offer Back to editor / Preview again / Create outputs using this configuration.

Keep transforms and the scope/output summary prominent. Move optional preset description, storage/debug detail, and less common settings into expandable sections. Preserve edits when opening compatibility or browsing transforms.

Clarify that a new stochastic execution can sample fresh randomness; preserving a config is not a promise of exact pixels. If preview parameters are reused, make that a separate supported choice. This task does not require VOX-65's persistent temporary-session architecture.

## Acceptance criteria

* Configure two stages, disable one annotation field, change parameters, preview, return, and materialize: the effective configuration is unchanged.
* Errors do not force re-entry of the draft, and successful previews allow a direct continuation.
* Selected sample IDs/counts are refreshed before creation if the selection changes; no silent scope expansion.
* UI actions are named for their real effect; preset-only saving does not look like creating samples.
* Preview starts with the useful image comparison and renders exactly the available results.
* Keyboard-only operation and a 1366×768 manual flow can reach the primary controls without navigating through long technical reports.

# VOX-73: Block invalid submissions and make dry-run validation match real execution

## Reproductions

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

A. Preview only with no selection: Run augmentation remains enabled. Only after submitting does the user learn that a selection is required.

B. Two enabled stages with Execution order=1: the form shows "Each enabled pipeline stage must have a unique execution order", but Run augmentation is still enabled. The field caption simultaneously says "ties keep stage slot order", contradicting the validator. Validation warnings are informational views, not invalid properties.

C. COCO 48564 (427×640), keypoints excluded, RandomCrop(height=9999,width=9999,p=1): dry run reports processed=1, errors=0, status=dry_run. Preview/materialization reject it: height must be <=640. The current dry run validates the config before image-dependent validation that only runs in FixedImagePipeline.apply.

## Required behavior

* Use the same effective configuration and validation policy for form, preview, dry run, save-only, immediate, and delegated paths.
* Block impossible submissions at the relevant fields; keep server-side validation for programmatic calls.
* Replace conflicting mode toggles with valid explicit actions/modes, or enforce exclusivity inline.
* Dry run must detect deterministic scope/media/annotation/dimension failures it claims to validate. If validation is intentionally incomplete, name and show that limit rather than implying the pipeline will execute successfully.
* Show field-level errors with sample/stage/parameter context and an actionable fix; focus or scroll to the first invalid field.
* Correct the duplicate-order caption and list the conflicting stage numbers. Prefer moving stages with up/down controls over manual numeric collisions.

## Acceptance criteria

* No-selection preview, duplicate order, contradictory modes, and missing preset name cannot be submitted in the App.
* Oversized crop fails preflight/dry run before files or runs are created; a valid crop succeeds.
* Valid configurations recover immediately after editing; disabled stages do not block execution.
* Test all execution modes against a shared invalid-input matrix and verify no side effects.
* Add real App checks of disabled submission and displayed field errors, not just warning text presence.

# VOX-74: Show actionable result summaries and distinguish failed, partial, and successful runs

## Observed failures

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

The output schema is effectively the same for failures, previews, dry runs, preset-only saves, and materialized runs. Empty fields dominate the dialog: run keys, directories, replay/preset values, blank JSON editors, and all three preview slots. For a successful preview or run, Errors displays "No errors added yet / Click the Add errors button to add an item" — editing-form copy inside a result. Error objects use an empty Object schema and the useful explanation is only in Errors JSON. Preview note is blank even when the backend supplies text.

An oversized RandomCrop on COCO creates zero outputs and one error, yet the materialized result and manifest report execution_status=completed. Generic preflight failures have an empty execution_status. Successful materialization also omits some schema fields, yielding "No value provided". The result has only Close; opening outputs requires finding another operator and reselecting a long run key.

## Required behavior

* Lead with a concise, read-only outcome: created X from Y, failed/skipped Z, or a concrete validation failure.
* Define completed / partial / failed / cancelled / preview / dry-run / preset-saved consistently in returned data, manifests, history, and diagnostics. A 0-of-N run with errors cannot be presented as successful completion.
* Render fields conditionally for the outcome; remove empty list-editing controls and unused preview slots.
* Show readable errors with stage, field, sample, cause and next action. Put JSON/config/replay/debug bundle under optional technical details with copy/download controls.
* Successful runs provide Open generated samples and View in history; preview/errors provide Return to editor with draft preserved.
* Clearly label run identity vs saved pipeline identity; do not show two opaque differently formatted run keys as equal primary concepts.

## Acceptance criteria

* Cover successful single preview, three previews, no-selection error, missing keypoints error, dry run, preset-only save, all-failed crop, partial failure and cancellation.
* A fully failed run stores failed; mixed results store partial; history and results agree.
* No "Add errors", blank image panels, missing-value noise, or empty status in these states.
* The main cause and recovery action are visible without reading JSON or scrolling through unrelated metadata.
* Keep structured diagnostic payloads available for developers and preserve existing cleanup guarantees.

# VOX-75: Consolidate six operators into an augmentation editor, saved pipelines, and run history

## Audit finding and recommendation

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

The plugin registers six sample-grid actions. Long repeated AlbumentationsX labels consume toolbar width; run viewing/cleanup/preset actions move into overflow. Users must leave their task to run Analyze Compatibility or Show Capabilities, interpret a technical report, reopen Augment and recreate settings. Compatibility already appears in Augment, so the standalone action partly duplicates that work. View Run and Delete Run operate on the same run but require separate discovery and selection.

Recommended information architecture: three user entry points under the AlbumentationsX plugin identity.

| Entry | Responsibilities |
| --- | --- |
| Augment images | Scope → editable pipeline → inline compatibility and transform discovery → preview/create |
| Saved pipelines | Load, save as, rename, duplicate, import/export, and explicitly replace/delete reusable configuration |
| Run history | Execution status/counts, generated samples, failed samples, use pipeline from a run, diagnostics, cleanup preview/confirmation |

Embed the compatibility report as expandable detail in the editor. Integrate capability search/filter/help into the stage selector. Put run cleanup in Run history with a concrete deletion preview, keeping destructive actions distinct from reuse or read-only viewing. Existing Python operators can remain implementation/API entry points; simplifying navigation does not require merging backend responsibilities or breaking operator URIs.

## Scope and coordination

Implement or validate a composed panel/workflow suitable for FiftyOne; a single long modal with every control is not the target. Reuse VOX-56 for the active run-library implementation, VOX-58 for discovery, VOX-49 for pipeline management, and VOX-35 for cleanup preview. This task owns navigation, action naming and state transfer, avoiding duplicated implementations.

## Acceptance criteria

* At most three primary plugin entry points; normal users do not need six independent operator concepts.
* Browse compatibility or choose a transform without losing the active draft.
* A successful run opens outputs/history directly; history can seed an editable pipeline in one action.
* Only Run history deals with execution instances; Saved pipelines clearly holds reusable configs.
* Cleanup shows the selected run label, date, output counts and file scope, then requires explicit confirmation.
* Existing external operator callers remain compatible or get documented aliases/migration.
* Validate the complete first-run and repeat-run flows at desktop and laptop sizes with COCO.

# VOX-76: Make output destination and re-augmentation of generated samples explicit

## Evidence

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

Outputs are appended to the same dataset. After creating two audit outputs from a 12-source COCO dataset, an Entire dataset dry run reports processed_count=14: generated samples are silently eligible as new sources. Repeating whole-dataset augmentation therefore changes its input population and can grow the dataset rapidly. The form does not show an original/generated breakdown, an explicit include-generated choice, or planned output count. The output location is only revealed afterwards; users may expect a new dataset or in-place augmentation.

## Proposed behavior

* Show the actual source count, scope, generated-source count, outputs per source, planned total, and destination before creation.
* Default broad-scope runs to original samples with an explicit "Include previously generated samples" choice. If the product deliberately retains include-all by default, require a prominent explanation and confirmation of the planned total. A user who explicitly selects generated samples must be told what will be processed, not silently filtered.
* State that new samples are added to the current dataset and original files remain unchanged; show the output storage root and make failure to write it actionable.
* In Preview mode show the actual selected subset (up to three) and clarify ignored execution-scope/output-count options, rather than showing Current view/Entire dataset as if preview used the same source pool.
* Preserve lineage if re-augmentation is intentional and avoid ambiguity around source vs root source.

## Acceptance criteria

* 12 originals → 2 generated → next broad-scope form visibly distinguishes 12 and 2 and shows the exact planned output count.
* Repeat runs follow the explicit generated-source policy in immediate and delegated execution.
* A filtered current view and an explicit selected subset report correct counts and destination.
* Preview states its bounded source policy; materialization revalidates scope if the dataset/selection changed.
* Add tests for source filtering, lineage and repeated-run counts. Do not change/delete original samples or silently move outputs to another dataset.

# VOX-77: Add a reproducible COCO first-user acceptance suite and setup guide

## Why this is needed

Audit baseline: checkout `31df1b9`, plugin 0.1.0, Python 3.12.13, FiftyOne 1.19.0, AlbumentationsX 2.3.8, albu-spec 0.0.6; macOS/Chrome, 1920×936 viewport. COCO 2017 validation subset (12 images, seed 51), detections + instance masks; person keypoints imported from the official keypoint annotations for the same image IDs. Audit date: 2026-09-09.

All 342 existing tests pass (pytest --no-cov -q; 185.58s, 954 warnings), while the live COCO audit exposes missing-keypoint failures, distorted previews, form-state loss, preset overrides, discarded label attributes, and misleading failure status. Existing headless synthetic contexts do not verify browser layout or displayed-vs-executed values.

COCO instance masks also require pycocotools, absent from the initial project environment. Installing pycocotools 2.0.11 enabled mask import. Passing multiple label_types to the installed zoo loader did not populate person keypoints from instances annotations; the audit explicitly imported official person_keypoints_val2017.json for the same COCO IDs. Setup instructions must verify the resulting schema and nonempty data rather than claiming all label families are loaded.

## Deliverable

Add a small reproducible acceptance dataset/workflow based on fixed COCO validation IDs (include 48564) covering portrait/landscape, small/large objects, instance masks, missing keypoints, multiple people and mixed dimensions. Document download size/cache, optional COCO dependencies, paths and dataset naming. Do not bundle the entire dataset or claim support from a bbox-only import.

The suite should exercise UI and real backend together: first open without selection, invalid preview, edit/preview/create, saved-pipeline loading/editing, previous-run reuse, current-view/dataset scope, partial/all-failed runs, view outputs, and cleanup. Include screenshot checks for proportions/layout and equality of visible parameters with effective execution.

## Acceptance criteria

* A documented command creates a dedicated nonempty COCO acceptance dataset and verifies label types, masks and missing keypoints.
* Exact IDs/seed, versions, environment, commands, screenshots and expected outcomes are recorded.
* Fast offline regression fixtures cover correctness; larger downloads remain an explicit acceptance step.
* UI checks catch the audited p=0 override and image stretching, not merely schema defaults.
* Source-file hashes and source-annotation values are checked before/after run and cleanup.
* Cleanup removes only fixture-owned generated artifacts; an existing user's dataset is never overwritten.
* Release evidence names the FiftyOne versions actually exercised. This audit covered installed 1.19.0 only, not the entire declared >=1.19,<2 range or a full COCO training split.
