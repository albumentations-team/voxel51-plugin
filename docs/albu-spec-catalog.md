# albu-spec Catalog

VOX-11 adds the first version-aware transform capability catalog. It reads
metadata from `albu-spec` and converts it into host-neutral
`TransformCapability` records.

## Runtime Dependencies

The catalog is built from:

- `albumentationsx>=2.3,<3`, currently locked to `2.3.7`;
- `albu-spec>=0.0.6,<1`, currently locked to `0.0.6`.

AlbumentationsX is installed as `albumentationsx`, but its public runtime import
remains:

```python
import albumentations as A
```

`albu-spec` is imported only inside the Albumentations backend catalog package.
Core DTOs and FiftyOne form rendering must not import it directly.

## Capability Statuses

The catalog exposes every transform known to albu-spec with one status:

- `supported`: safe to expose as a normal MVP image transform choice.
- `supported_with_defaults`: safe to expose with simple fields while advanced
  parameters stay hidden or JSON-backed later.
- `hidden`: valid metadata, intentionally not shown in normal UI choices.
- `requires_external_data`: requires metadata/reference inputs not wired into
  the MVP pipeline.
- `requires_manual_schema`: needs explicit schema handling before UI exposure.
- `blocked_media_target`: not a 2D image transform.
- `unsupported_target`: depends on catalog-wide annotation target handling that
  is not wired into the MVP transform picker yet.
- `unsupported_output`: can produce output arrays that are not safe image files
  for the current storage adapter.
- `unsupported_schema`: reserved for schema failures that cannot be represented
  safely.

Normal MVP choices are transforms with `supported` or
`supported_with_defaults`.

## Review Report

Run the report before changing catalog rules or upgrading AlbumentationsX or
albu-spec:

```bash
uv run python scripts/report_transform_capabilities.py
uv run python scripts/report_transform_capabilities.py --format json
```

The report includes the version key, total transform count, status counts,
supported choices, and excluded transform names by status.

## Current Snapshot

The current lockfile produces:

- version key: `albumentationsx-2.3.7__albu-spec-0.0.6`;
- total transforms: `133`;
- normal MVP choices: `109`;
- status counts:
  - `blocked_media_target`: `7`
  - `hidden`: `1`
  - `requires_external_data`: `7`
  - `supported`: `68`
  - `supported_with_defaults`: `41`
  - `unsupported_output`: `2`
  - `unsupported_target`: `7`

Tests intentionally assert this summary so dependency or metadata drift is
visible during review.
