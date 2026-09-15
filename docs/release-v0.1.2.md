# AlbumentationsX for FiftyOne 0.1.2

**Status: release candidate.** This document describes preparation for 0.1.2.
It is not a publication or final acceptance announcement.

Changes are measured from the published **0.1.1** release to the candidate.
Use the [verification record](release-preparation.md) for current evidence and
remaining publication gates.

[Watch the COCO workflow demos](https://github.com/albumentations-team/voxel51-plugin/tree/2f8aa79c4acad7d5efa41e8554161b15828ec9ee/docs/media).

## Highlights

- Build and inspect pipelines through three focused actions: **Augment images**,
  **Saved pipelines**, and **Run history**, with branded toolbar buttons.
- Preview selected images and annotations side by side before creating samples.
  Previews preserve image proportions and omit empty result slots.
- Keep editable settings across preview, validation errors, and result navigation.
  Returning to the editor preserves the configuration, and closing results
  leaves the toolbar usable for the next action.
  Loading a pipeline explicitly replaces the draft; subsequent edits control execution.
- Save reusable pipelines across datasets, import/export full JSON, edit metadata,
  duplicate configurations, and explicitly create or update a saved pipeline.
- Search run history, open outputs or failed sources, inspect replay/provenance,
  reuse configurations, and review the exact deletion scope.

## Features and fixes since 0.1.1

### Pipelines and execution

- Up to ten enabled/ordered stage slots, selected/current-view/entire-dataset
  scopes, in-memory validation, and delegated creation with progress.
- Advanced JSON controls for optional complex transform parameters.
- Inline dataset/annotation compatibility feedback and detailed diagnostic APIs.
- Reference-image adapters for FDA, HistogramMatching, and
  PixelDistributionAdaptation using the other sources in the selected scope.
- Accepted transform settings, including crop padding and additional brightness
  options, survive pipeline loading, editing, and compilation.
- Prepared pipelines reuse their runner; selected-sample preparation queries
  the selected subset before decoding inputs.
- Accurate completed/partial/failed/cancelled outcomes and actionable error summaries.

### Annotation and output integrity

- Support for detection instance masks, file-backed semantic masks, polylines,
  and heatmaps, with explicit target compatibility.
- COCO-style missing keypoints retain joint indices and aligned per-point metadata.
- Label tags and JSON-safe attributes are preserved; omitted derived geometry and
  unsupported metadata are explained. Generated sample provenance links to sources.
- Source images, samples, and annotations remain intact through execution and cleanup.
- Controlled cancellation retains recorded partial outputs for inspection/removal.

### Installation and maintenance

- Checksummed plugin ZIP, wheel, source distribution, capability report, and
  installation notes.
- Runtime version metadata is included in isolated plugin installations.
- Explicit ZIP input inventory excludes accidental local files and generated data.
- Documentation follows current UI actions, correct run tags, and tag-aware asset names.
- Contributor contracts and historical evidence are separated from installed user docs.

## Compatibility and upgrade

- Python 3.10–3.14; FiftyOne `>=1.19,<2`.
- AlbumentationsX `>=2.3.8,<3`; albu-spec `>=0.0.6,<1`.
- Locked catalog: AlbumentationsX 2.3.8, albu-spec 0.0.6; 113 executable
  transforms from 134 catalog entries.
- CI targets and allowed dependency ranges are distinct from the environments
  actually exercised in the verification record.

Install the eventual published tag through the
[integration guide](albumentationsx-fiftyone-integration.md#installation-and-upgrade).
Existing plugin operator URIs remain registered. Legacy Python callers that
supply live `pipeline_preset_key` / `previous_run_key` must migrate to explicit
draft loading; see [Python API migration](operator-api.md#loading-and-saving).

Existing preset IDs remain valid. New presets use IDs independent of display
names; repeated names do not implicitly overwrite data. Review loaded annotations
when reusing a pipeline across datasets.

The older `jacobmarks/fiftyone-albumentations-plugin` is a separate integration.
There is no automatic migration of its saved transforms or runs.

## Known limitations

- Image samples only; no video, 3D, distributed execution, or exact replay mode.
- Preview shows one result for each of up to three selected sources.
- Generated samples remain eligible as inputs; filter them out or select only
  originals when repeating an augmentation.
- Polylines use vertex-based clipping; transformed heatmaps cannot safely share
  mixed geometric and image-only color/intensity pipelines.
- Source preparation reads and validates the complete scope before output
  progress/cancellation checkpoints. Validation executes planned outputs in memory.
- Reference-image transforms load the complete source pool; per-source reference
  lists/provenance grow quadratically. Use small selected scopes; bounded resources and cancellable preflight
  remain future work.
- Host cancellation detection is best-effort; hard termination may interrupt
  checkpoint persistence. Cleanup requires a finished or stopped execution.
- Saved-pipeline reuse samples fresh randomness, including after preview.

## Release handoff

Attach the final capability report, install notes, and `SHA256SUMS` produced by
the [artifact process](release-artifacts.md). Link the reviewed demos and upstream
FiftyOne documentation PR. Publication follows fresh App/COCO acceptance,
artifact installation, and required CI for the final candidate.
