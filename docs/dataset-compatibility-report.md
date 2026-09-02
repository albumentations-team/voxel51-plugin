# Dataset Compatibility Report

VOX-61 adds the read-only `Analyze AlbumentationsX Compatibility` operator. It
answers a dataset-specific question before users build a pipeline: which
annotation fields can the plugin safely copy or transform, and which
AlbumentationsX target families are available in the current catalog.

The operator does not create samples, files, manifests, presets, or custom runs.
It reads the active dataset schema, selected sample IDs, current view metadata
where available, and the same albu-spec capability catalog used by the
augmentation form and capability browser.

## Scope

The form exposes the shared `Source scope` selector:

- `Selected samples`: reports the current selected-sample count.
- `Current view`: reports the active view count when FiftyOne exposes it.
- `Entire dataset`: reports the dataset count when available.

The report keeps both `source_count` and `source_count_available` so callers can
distinguish an empty source from a source that could not be counted.

## Annotation Fields

Each detected label field is returned in both table and JSON form:

- field name and FiftyOne label type;
- support status: `copy_supported`, `transform_supported`, `conditional`, or
  `unsupported`;
- plugin role: `copied`, `transformed`, or `excluded`;
- required Albumentations target, when applicable;
- compatible transform count and representative transform names;
- recommended capability filter and important limitations.

The report uses the same annotation field resolver as execution validation, so
unsupported label classes appear as excluded diagnostics instead of being
silently ignored. Schema-reading failures are downgraded to a warning because
the report is advisory and should not break App rendering.

## Target Families

Target family rows summarize the current albu-spec catalog by target:

- target name;
- whether the target has executable MVP transforms;
- executable and excluded transform counts;
- image-only and geometry transform counts;
- representative executable transform names;
- how the FiftyOne adapter uses the target;
- current limitations.

The primary MVP target families are:

- `image`: source images and heatmap geometry maps;
- `bboxes`: `Detections` bounding boxes;
- `keypoints`: `Keypoints` plus `Polylines` vertices;
- `mask`: semantic `Segmentation` masks and runtime detection masks.

Catalog targets that are not wired into the FiftyOne adapter are still shown as
`not_available` when they appear in albu-spec.

## Recommendations

The operator emits short recommendations that point users toward safer next
steps, such as:

- using `Preview only` on a small selection before materializing outputs;
- filtering transform capabilities by the required target for spatial labels;
- keeping heatmap pipelines geometry-only or disabling heatmap fields;
- handling unsupported labels outside the plugin.

The complete `report_json` field is intended for issue reports, release notes,
and debugging conversations because it bundles source scope, package versions,
schema warnings, field rows, target rows, and recommendations.

## Inline Augment Form Preview

`Augment with AlbumentationsX` reuses the same report backend for a compact
inline preflight section. The inline view is intentionally smaller than the
standalone operator output: it summarizes the selected source scope, available
source count, schema availability, selected annotation fields, and the current
pipeline's transform/copy behavior.

Use the inline section while configuring a run. It updates with the form values
and surfaces critical pipeline conflicts before submit, for example a selected
heatmap field combined with mixed geometry and image-only stages. Use the
standalone `Analyze AlbumentationsX Compatibility` operator when you need the
full table output, target-family breakdown, package versions, or copyable JSON
for bug reports.
