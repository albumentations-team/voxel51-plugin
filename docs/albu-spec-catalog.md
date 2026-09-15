# albu-spec Catalog

The version-aware transform capability catalog reads
metadata from `albu-spec` and converts it into host-neutral
`TransformCapability` records.

## Runtime Dependencies

The catalog is built from:

- `albumentationsx>=2.3.8,<3`, currently locked to `2.3.8`;
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

- `supported`: safe to expose as a normal image transform choice.
- `supported_with_defaults`: safe to expose with simple fields while advanced
  parameters use optional JSON inputs.
- `hidden`: valid metadata, intentionally not shown in normal UI choices.
- `requires_external_data`: requires metadata/reference inputs not yet wired
  into the current pipeline. Entries with supported adapters may still carry
  `ExternalInputRequirement` metadata while remaining normal executable choices.
- `requires_manual_schema`: needs explicit schema handling before UI exposure.
- `blocked_media_target`: not a 2D image transform.
- `unsupported_target`: depends on catalog-wide annotation target handling that
  is not wired into the current transform picker yet.
- `unsupported_output`: can produce output arrays that are not safe image files
  for the current storage adapter.
- `unsupported_schema`: reserved for schema failures that cannot be represented
  safely.

Executable choices are transforms with `supported` or
`supported_with_defaults`; these choices appear in the executable
FiftyOne augmentation UI.

## Review Report

Run the report before changing catalog rules or upgrading AlbumentationsX or
albu-spec:

```bash
uv run python scripts/report_transform_capabilities.py
uv run python scripts/report_transform_capabilities.py --format json
```

The report includes the version key, total transform count, status counts,
supported choices, advanced parameter editability, external input requirements,
and excluded transform names by status.

## Current Snapshot

The current lockfile produces:

- version key: `albumentationsx-2.3.8__albu-spec-0.0.6`;
- total transforms: `134`;
- executable choices: `113`;
- status counts:
  - `blocked_media_target`: `7`
  - `hidden`: `1`
  - `requires_external_data`: `4`
  - `supported`: `72`
  - `supported_with_defaults`: `41`
  - `unsupported_output`: `2`
  - `unsupported_target`: `7`

Tests intentionally assert this summary so dependency or metadata drift is
visible during review. The release-specific snapshot for the first public release is
[Capability Report v0.1.0](capability-report-v0.1.0.md).

For ownership and workaround rules, see [Architecture](architecture.md#metadata-ownership-and-upstream-work).
The dated [integration audit](https://github.com/albumentations-team/voxel51-plugin/blob/ca5507b5df3df8c816b16a0f5230b9bc235d0826/docs/albu-spec-integration-audit.md)
retains version-specific observations and the upstream issue draft.
For input-adapter policy, see
[External-data transforms](external-data-transforms.md).
