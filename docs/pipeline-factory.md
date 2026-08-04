# Pipeline Factory

VOX-14 adds the first catalog-driven AlbumentationsX execution factory. It
replaces handwritten transform construction in the fixed vertical slice with a
shared backend package that resolves transform classes from albu-spec metadata,
coerces parameters from neutral schemas, executes `ReplayCompose`, and returns
JSON-safe replay data.

## Runtime Boundary

The implementation lives in:

- `albumentationsx_plugin/albumentations_backend/pipeline/registry.py`
- `albumentationsx_plugin/albumentations_backend/pipeline/coercion.py`
- `albumentationsx_plugin/albumentations_backend/pipeline/factory.py`
- `albumentationsx_plugin/albumentations_backend/pipeline/runner.py`
- `albumentationsx_plugin/albumentations_backend/pipeline/replay.py`

This package may import `albumentations`, `albu-spec`, NumPy, and core DTOs. It
must not import FiftyOne. Host code should consume it through backend interfaces
or injected services instead of duplicating AlbumentationsX construction logic.

The runner exposes `apply(image, targets=None)`. Without targets it behaves as a
plain image pipeline. When host adapters provide Albumentations-compatible
`bboxes`, `keypoints`, or `masks`, it configures the matching target params,
forwards the targets into `ReplayCompose`, and returns transformed target data
beside the output image and replay. Host-level `PipelineRunner.run(AugmentationInput)`
still belongs above image IO and storage orchestration, because a host adapter
decides how to load media, write outputs, and create host records.

## Safety Rules

- Transform class lookup starts from the albu-spec capability catalog.
- Unknown transforms and excluded transforms raise `UnsupportedTransformError`.
- Runtime modules must be trusted Albumentations modules whose names start with
  `albumentations.`.
- The factory does not call `eval` and does not import modules from unchecked
  user-provided names.
- Parameter names are checked against `FormFieldSchema`; unknown parameters fail
  before constructor calls.
- Required parameters must be provided unless albu-spec defines a default.
- Booleans, numbers, ranges, enums, lists, and JSON fallback values are coerced
  before transform construction.
- Constructor `TypeError` and `ValueError` are wrapped as `InvalidParameterError`
  with structured context.

## Current Scope

The fixed FiftyOne execution path exposes ordered chains of up to three steps
from:

- `HorizontalFlip`
- `RandomBrightnessContrast`
- `RandomCrop`

Internally, those transforms are created by the shared catalog-driven factory.
The factory can construct other MVP image transforms when given a
`PipelineConfig`, but the operator execution UI has not yet been broadened from
the fixed slice to catalog-wide pipelines.

VOX-26 adds the first host-side annotation adapter. The backend runner remains
host-neutral: FiftyOne label serialization and reconstruction live in
`hosts/fiftyone/annotations/`, while this package only receives and returns
Albumentations target arrays.

## Verification

Use the complete local gate in [Verification](verification.md). The focused test
suite for this layer is:

```bash
uv run pytest tests/unit/test_albumentations_pipeline_factory.py tests/unit/test_fixed_image_pipeline.py tests/integration/test_fiftyone_fixed_augmentation_executor.py
```
