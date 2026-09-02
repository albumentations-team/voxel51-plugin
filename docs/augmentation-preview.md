# Augmentation Preview

VOX-29 adds a non-persistent preview path to `Augment with AlbumentationsX`.
Preview is for judging an augmentation configuration before adding generated
samples to a FiftyOne dataset.

## User Flow

1. Select one to three source samples in the FiftyOne App.
2. Open **Augment with AlbumentationsX**.
3. Configure the same pipeline settings that would be used for a normal run.
4. Enable `Preview only` and execute the operator.
5. Inspect the source image, augmented image, annotated before/after comparison,
   sampled replay parameters, transformed labels, and annotation comparison JSON
   returned in the operator output.
6. Disable `Preview only` and run the same form to create persistent samples.

Preview currently requires selected samples. It ignores broader execution
scopes and runs against the selected sample IDs only, capped at three samples.

## Runtime Contract

Preview uses the same shared runtime setup as materialized execution:

- `hosts/fiftyone/augmentation/runtime.py` builds and validates the fixed
  pipeline config, annotation field selection, source scope, and source inputs.
- `hosts/fiftyone/augmentation/outputs.py` applies the pipeline and transforms
  labels for a single source/output pair.
- `hosts/fiftyone/augmentation/preview.py` encodes the preview images as
  in-memory PNG data URIs and serializes replay/label diagnostics as JSON text.
- `hosts/fiftyone/augmentation/preview_visuals.py` renders annotation-aware
  before/after overlays for detections, keypoints, polylines, heatmaps, and
  masks.

The materialized executor still owns file writes, manifest checkpointing,
FiftyOne sample creation, custom run registration, and progress reporting.

## Persistence Guarantees

Preview must not:

- create output samples;
- create plugin output files;
- create run directories or manifests;
- register FiftyOne custom runs;
- trigger a dataset reload.

Source samples, source files, and source labels remain unchanged. The preview
result is only the operator return payload.

## Preview Output

For each preview slot the operator returns:

- source sample ID and filepath;
- source image as a PNG data URI;
- augmented image as a PNG data URI;
- annotated before/after comparison image as a PNG data URI;
- sampled replay parameters as JSON;
- transformed labels as JSON;
- annotation diagnostics, including dropped target counts where applicable;
- annotation comparison JSON with field-level copied, transformed, dropped, and
  overlay status.

The first implementation renders one preview output per selected source sample.
`outputs_per_sample` still controls the later materialized run, but preview is
bounded to one result per selected sample so the App output remains readable.

## Verification

Focused checks:

```bash
uv run pytest tests/unit/test_fiftyone_augment_operator.py
uv run pytest tests/integration/test_fiftyone_fixed_augmentation_executor.py -k preview
```

Manual App check:

1. Create or open the demo dataset.
2. Select one to three images.
3. Run `Augment with AlbumentationsX` with `Preview only` enabled.
4. Confirm source, augmented, and annotated comparison preview images render.
5. Confirm replay, transformed label JSON, and annotation comparison JSON are
   shown.
6. Refresh the dataset and confirm no generated samples or custom runs were
   created by preview.
7. Disable `Preview only`, run the same configuration, and confirm persistent
   outputs are created normally.
