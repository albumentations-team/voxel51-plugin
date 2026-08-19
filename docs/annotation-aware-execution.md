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
  back as relative FiftyOne bounding boxes.
- `Keypoints`: `Keypoint.points` are converted from relative FiftyOne
  coordinates to Albumentations `xy`, transformed, and written back as relative
  points.
- `Segmentation`: `Segmentation(mask=...)` masks are passed through
  Albumentations `masks` and written to the output sample in memory.
  `Segmentation(mask_path=...)` masks are read from disk, transformed through the
  same target path, and written as plugin-owned output mask PNGs under the run
  directory.

Supported label attributes, tags, labels, confidences, and indices are preserved
where they can be represented as JSON-safe values.

## Unsupported Scope

The first slice does not claim full annotation coverage. Unsupported label
classes, detection instance masks, polylines, heatmaps, custom embedded
documents, video labels, 3D labels, and transform-specific target requirements
should be added in follow-up tasks with focused tests.

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
`bboxes`, `keypoints`, and `masks`, configures `ReplayCompose`, and returns the
transformed target values. FiftyOne-specific reconstruction stays in
`hosts/fiftyone/annotations/`. File-backed semantic mask results are
materialized under the plugin-owned run directory and listed in the manifest
cleanup allowlist.

## Verification

Use the complete local gate in [Verification](verification.md). The focused
annotation check is:

```bash
uv run pytest tests/integration/test_fiftyone_fixed_augmentation_executor.py::test_fixed_augmentation_executor_transforms_supported_annotations
uv run pytest tests/integration/test_fiftyone_fixed_augmentation_executor.py::test_fixed_augmentation_executor_materializes_file_backed_segmentation_masks
```
