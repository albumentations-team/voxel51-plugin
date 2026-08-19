# Annotation-Aware Execution

VOX-26 adds the first annotation-aware execution path for the fixed FiftyOne
augmentation slice. Geometry is delegated to Albumentations target handling; the
plugin only converts FiftyOne labels into target data and reconstructs FiftyOne
labels from the transformed targets.

## Supported Labels

The current FiftyOne adapter supports these dataset label fields:

- `Classification`: copied to the output sample unchanged.
- `Detections`: `Detection.bounding_box` values are converted from FiftyOne
  relative coordinates to Albumentations `pascal_voc`, transformed, and written
  back as relative FiftyOne bounding boxes. `Detection(mask=...)` and
  `Detection(mask_path=...)` instance masks are expanded to full-image mask
  targets, transformed with the image, and cropped back to each transformed
  bounding box. Detection mask outputs are stored as in-memory
  `Detection.mask` values.
- `Keypoints`: `Keypoint.points` are converted from relative FiftyOne
  coordinates to Albumentations `xy`, transformed, and written back as relative
  points.
- `Polylines`: each `Polyline.points` contour vertex is converted from relative
  FiftyOne coordinates to Albumentations `xy` keypoints, transformed, grouped
  back into its source contour, and written as relative points. Labels,
  confidences, tags, JSON-safe attributes, indices, `closed`, and `filled` are
  preserved.
- `Heatmap`: the 2D heatmap map is converted to a batched image-like target,
  transformed with geometric stages, and written to output samples as an
  in-memory `Heatmap.map`. File-backed source `map_path` values are preserved
  in copied heatmaps and recorded as `source_map_path` in transformed payloads,
  but transformed heatmap outputs are not materialized as separate files yet.
- `Segmentation`: `Segmentation(mask=...)` masks are passed through
  Albumentations `masks` and written to the output sample in memory.
  `Segmentation(mask_path=...)` masks are read from disk, transformed through the
  same target path, and written as plugin-owned output mask PNGs under the run
  directory.

Supported label attributes, tags, labels, confidences, and indices are preserved
where they can be represented as JSON-safe values.

`Polylines` use vertex-based semantics. Albumentations keypoint handling can
remove vertices that become invisible after transforms such as crops. The plugin
drops open contours with fewer than two remaining points and closed/filled
contours with fewer than three remaining points; it does not perform full
polygon clipping.

`Heatmap` support is intended for geometry-only target synchronization.
AlbumentationsX 2.3.8 does not expose a dedicated heatmap target parameter, so
the plugin maps heatmaps through image-like additional targets. To avoid
silently applying color/intensity transforms to heatmap values, the compatibility
check rejects pipelines that combine selected heatmaps, a geometric image target,
and image-only stages. Pure image-only pipelines copy selected heatmaps
unchanged.

## Unsupported Scope

The current slice does not claim full annotation coverage. Unsupported label
classes, custom embedded documents, video labels, 3D labels, and
transform-specific target requirements should be added in follow-up tasks with
focused tests.

Unsupported label fields are excluded from generated output samples. The run
manifest stores excluded fields and reason codes under `metadata.annotations` so
the behavior is inspectable instead of silent.

## Runtime Flow

The FiftyOne sample adapter resolves supported label fields from the dataset
schema and serializes labels into `AugmentationInput.metadata`. The fixed
executor converts that payload into Albumentations target arrays before calling
the backend runner:

```text
FiftyOne labels -> annotation payload -> Albumentations targets
Albumentations targets -> transformed payload -> FiftyOne output labels
```

The backend runner remains host-neutral. It only receives target names such as
`bboxes`, `keypoints`, `masks`, and `heatmaps`, configures `ReplayCompose`, and
returns the transformed target values. FiftyOne-specific reconstruction stays
in `hosts/fiftyone/annotations/`. File-backed semantic mask results are
materialized under the plugin-owned run directory and listed in the manifest
cleanup allowlist.

Compatibility checks run in two passes. The first pass uses the dataset schema
to reject selected label fields whose declared target type is incompatible with
the requested transform chain. The second pass uses the serialized source
annotation payloads. This catches value-dependent requirements, such as a
`Detections` field that normally needs `bboxes` targets but also needs `mask`
targets when any selected detection carries an instance mask. Runtime target
requirements are stored in run annotation metadata for inspection.

## Verification

Use the complete local gate in [Verification](verification.md). The focused
annotation check is:

```bash
uv run pytest tests/integration/test_fiftyone_fixed_augmentation_executor.py::test_fixed_augmentation_executor_transforms_supported_annotations
uv run pytest tests/integration/test_fiftyone_fixed_augmentation_executor.py::test_fixed_augmentation_executor_materializes_file_backed_segmentation_masks
uv run pytest tests/unit/test_fiftyone_annotation_conversion.py
```
