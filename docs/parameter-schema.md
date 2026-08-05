# Parameter Schema

VOX-12 adds host-neutral parameter schema generation for transforms exposed by
the albu-spec capability catalog.

## Boundary

The schema generator lives in:

- `albumentationsx_plugin/albumentations_backend/parameters/conversion.py`
- `albumentationsx_plugin/albumentations_backend/parameters/provider.py`

It may import `albu-spec` and core DTOs. It must not import FiftyOne. Host
adapters receive `FormFieldSchema` objects and decide how to render them.

## Generated Fields

Each albu-spec parameter is converted into a `FormFieldSchema` with:

- field name and label;
- field kind;
- default value;
- required flag;
- min/max bounds when albu-spec exposes constraints;
- enum choices for literal lists;
- help text from the parameter description;
- metadata with the original type hint and schema reason code.

Supported field shapes:

- `boolean`
- `integer`
- `float`
- `string`
- `enum`
- `number_range`
- `list`
- `json`

`json` is used as a safe fallback for optional complex values. Required complex
values are marked with `schema_status=unsupported_required` and
`reason_code=unsupported_required_parameter` so hosts can block or explain them
instead of rendering a broken input.

## Provider

Use `AlbuSpecParameterSchemaProvider` when a host or pipeline builder needs
fields for one transform:

```python
from albumentationsx_plugin.albumentations_backend.parameters import (
    AlbuSpecParameterSchemaProvider,
)

provider = AlbuSpecParameterSchemaProvider()
fields = provider.get_parameter_schema("RandomBrightnessContrast")
```

The provider only returns schemas for transforms that the capability catalog
marks as normal MVP choices. Excluded transforms raise `UnsupportedTransformError`
with the catalog reason.

## Snapshot Review

Tests snapshot representative transforms against the current lockfile:

- `HorizontalFlip`
- `RandomBrightnessContrast`
- `RandomCrop`
- `ToGray`
- `D4`

The current version key is
`albumentationsx-2.3.8__albu-spec-0.0.6`.
