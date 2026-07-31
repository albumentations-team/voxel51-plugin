# Pipeline Factory

VOX-14 adds the first catalog-driven AlbumentationsX execution factory. It
replaces handwritten transform construction in the fixed vertical slice with a
shared backend package that resolves transform classes from albu-spec metadata,
coerces parameters from neutral schemas, executes image-only `ReplayCompose`, and
returns JSON-safe replay data.

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

The current runner is intentionally image-only and exposes `apply(image)`. The
host-level `PipelineRunner.run(AugmentationInput)` contract still belongs above
image IO and storage orchestration, because a host adapter decides how to load
media, write outputs, and create host records.

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
The factory can construct other image-only MVP transforms when given a
`PipelineConfig`, but the operator execution UI has not yet been broadened from
the fixed slice to catalog-wide pipelines.

Annotation targets remain outside VOX-14. Bounding boxes, masks, and keypoints
should be added through separate adapter modules with geometry tests.

## Verification

Use the complete local gate in [Verification](verification.md). The focused test
suite for this layer is:

```bash
uv run pytest tests/unit/test_albumentations_pipeline_factory.py tests/unit/test_fixed_image_pipeline.py tests/integration/test_fiftyone_fixed_augmentation_executor.py
```
