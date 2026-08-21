# albu-spec Integration Audit

VOX-20 audits how this plugin consumes `albu-spec` and defines when an
integration problem should be fixed upstream instead of papered over locally.

Audit date: 2026-08-15

Current validated snapshot:

- AlbumentationsX: `2.3.8`
- albu-spec: `0.0.6`
- version key: `albumentationsx-2.3.8__albu-spec-0.0.6`
- total transforms: `134`
- normal executable choices: `110`
- `supported`: `69`
- `supported_with_defaults`: `41`

## Integration Contract

The plugin treats `albu-spec` as the source of truth for:

- transform names;
- runtime modules;
- transform targets;
- transform type;
- InitSchema availability;
- constructor parameters;
- parameter defaults;
- parameter descriptions;
- parameter constraints;
- dependency drift snapshots.

The plugin owns host policy and safety decisions:

- which catalog entries are safe for the current image-output workflow;
- which FiftyOne label fields are selected and transformed;
- how host forms render neutral schemas;
- image-size-aware defaults, such as crop dimensions;
- file output safety and cleanup behavior;
- temporary compatibility handling while upstream fixes are pending.

`albu-spec` may be imported only inside the Albumentations backend layer:

- `albumentationsx_plugin/albumentations_backend/catalog/`
- `albumentationsx_plugin/albumentations_backend/parameters/`
- `albumentationsx_plugin/albumentations_backend/pipeline/registry.py`

Core DTOs and FiftyOne host code must consume backend interfaces and neutral
contracts instead of importing `albu-spec` directly.

## Current Touchpoints

| Area | Local code | albu-spec data used |
| --- | --- | --- |
| Capability catalog | `catalog/provider.py`, `catalog/classification.py` | transform metadata, targets, transform type, InitSchema flag, parameter names |
| Parameter schemas | `parameters/provider.py`, `parameters/conversion.py` | parameter type hints, defaults, descriptions, constraints |
| Runtime class lookup | `pipeline/registry.py` | transform name and runtime module |
| Pipeline construction | `pipeline/factory.py`, `pipeline/coercion.py` | generated neutral schemas and defaults |
| Drift checks | `tests/unit/test_albu_spec_catalog.py`, `tests/unit/test_albu_spec_parameter_schema.py` | version key, counts, representative schemas |
| Capability reports | `scripts/report_transform_capabilities.py` | complete classified catalog snapshot |

## Audit Results

### Runtime Metadata

No runtime module or class resolution problems were found in the current
snapshot.

Checks performed:

- every catalog metadata entry with an `albumentations.` module could be
  imported;
- every resolved runtime class exists;
- every resolved runtime class is an `albumentations.BasicTransform`;
- no supported transform had constructor parameters missing from albu-spec
  metadata;
- no supported transform had extra required constructor parameters missing from
  albu-spec metadata.

Decision: no upstream runtime-module issue is needed for `albu-spec 0.0.6`.
Keep the trusted-module check in `pipeline/registry.py` as a plugin safety
boundary.

### Parameter Schema Coverage

The current catalog exposes `110` normal choices. Of those, `41` are
`supported_with_defaults` because optional complex parameters are exposed as
advanced JSON fallback fields until albu-spec can provide richer machine-readable
shapes for first-class controls.

The audit found:

- `76` optional parameters represented as JSON fallback;
- `0` unsupported required parameters;
- `12` supported required parameters without defaults.

Required fields without defaults:

| Transform | Parameters | Owner |
| --- | --- | --- |
| `CenterCrop` | `height`, `width` | Plugin UX should derive image-aware defaults or require explicit input |
| `GridElasticDeform` | `num_grid_xy`, `magnitude` | Plugin UX should provide safe presets or require explicit input |
| `LetterBox` | `size` | Plugin UX should derive image-aware defaults or require explicit input |
| `RandomCrop` | `height`, `width` | Plugin already provides image-aware defaults |
| `RandomResizedCrop` | `size` | Plugin UX should derive image-aware defaults or require explicit input |
| `RandomSizedCrop` | `min_max_height`, `size` | Plugin UX should provide safe presets or require explicit input |
| `Resize` | `height`, `width` | Plugin UX should derive image-aware defaults or require explicit input |

Decision: missing defaults for required constructor parameters are not
automatically upstream bugs. Albumentations intentionally requires those values.
The plugin should add host-aware defaults or clearer validation as UX work.

### Suspected Upstream Issues

#### ASPEC-1: Structured parameter shapes are encoded as non-standard type hints

Impact: many safe advanced parameters cannot be rendered as first-class controls
because the plugin receives strings that are hard to parse safely and
generically.

Examples from `albu-spec 0.0.6`:

| Transform | Parameter | Current type hint |
| --- | --- | --- |
| `CoarseDropout` | `fill` | `float | tuple[float, ...] | random | random_uniform | inpaint_telea | inpaint_ns | grayscale` |
| `Downscale` | `interpolation_pair` | `dict[['downscale', 'upscale'], [0, 1, 2, 3, 4, 5, 6]]` |
| `AnnotationArtifacts` | `element_types` | `tuple[['text', 'rectangle', 'arrow', 'line', 'callout'], ...]` |
| `RandomRotate90` | `group_elements` | `tuple[['e', 'r90', 'r180', 'r270'], ...] | None` |
| `Affine` | `scale` | `tuple[float, float] | dict[str, tuple[float, float]]` |

Expected upstream direction:

- represent string choices as explicit literal/enum metadata instead of bare
  identifiers inside a type-hint string;
- represent fixed-key dictionaries as structured object metadata;
- represent repeated literal tuples as list/tuple item enum metadata;
- keep a machine-readable shape separate from display text.

Local decision: expose optional complex parameters as JSON fallback fields, but
do not add ad hoc string parsers for these type hints in the plugin. First-class
typed controls should come from richer albu-spec metadata.

#### ASPEC-2: External runtime data requirements are inferred locally

Impact: the plugin currently classifies external-data transforms through local
policy, including `metadata_key` and transform-name rules.

Affected transforms in the current report:

- `CopyAndPaste`
- `FDA`
- `HistogramMatching`
- `Mosaic`
- `OverlayElements`
- `PixelDistributionAdaptation`
- `TextImage`

Expected upstream direction:

- expose whether a transform requires extra sample data, reference images,
  metadata arrays, callbacks, masks, or non-image payloads;
- expose which parameter or target supplies that data;
- distinguish optional advanced data hooks from required execution inputs.

Local decision: keep these transforms excluded until the plugin has explicit
host UI and storage flows for reference data. VOX-43 records the current local
contract as `ExternalInputRequirement` entries on each affected
`TransformCapability`; see [External-data transforms](external-data-transforms.md).
Name-based classification should remain documented and narrow.

#### ASPEC-3: Output safety is not machine-readable

Impact: `Normalize` and `ToFloat` are excluded with plugin-side name rules
because they can produce model-input arrays that are unsafe for the current
uint8 image-output writer.

Expected upstream direction:

- expose output dtype/range/media-shape effects when a transform changes image
  storage safety;
- distinguish visualization-safe transforms from model-preprocessing
  transforms.

Local decision: keep local output safety policy because the storage adapter owns
file output constraints. If albu-spec later exposes output contracts, replace
name-based checks with metadata-driven checks.

### Plugin-Owned Work

The following are not upstream bugs:

- deriving convenient size defaults for `CenterCrop`, `Resize`, `LetterBox`,
  `RandomResizedCrop`, and similar transforms;
- selecting which FiftyOne label fields should be transformed;
- blocking pipelines that require labels absent from the active dataset/view;
- exposing advanced controls progressively in the FiftyOne form;
- previewing outputs before creating samples;
- deciding whether generated arrays can be written as plugin-owned image files.

Related plugin tasks:

- `VOX-40`: annotation field selection and incompatible pipeline blocking;
- `VOX-41`: broader annotation support;
- `VOX-42`: advanced transform parameters with safe schema controls;
- `VOX-43`: reference/external data transforms.

## Temporary Workaround Policy

Plugin-side workarounds for upstream metadata problems must be:

- temporary and documented in this file or the related architecture doc;
- scoped to the backend integration layer when they concern albu-spec metadata;
- covered by focused tests;
- linked to an upstream issue, PR, or draft in the PR description;
- removed or re-evaluated when the `version_key` changes;
- expressed as reason-coded classification or schema metadata, not broad silent
  exception handling.

Avoid adding parsers for arbitrary albu-spec type-hint strings. Prefer upstream
metadata fixes or small explicit mappings with tests and an upstream link.

## Upstream Issue Draft

Title:

```text
Expose structured parameter shapes for literal unions, repeated literals, and fixed-key dicts
```

Body:

````markdown
## Context

The AlbumentationsX FiftyOne plugin consumes `albu-spec` metadata to generate
safe host-neutral parameter schemas. With `albumentationsx 2.3.8` and
`albu-spec 0.0.6`, runtime module metadata looks healthy, but many optional
parameters cannot be rendered as first-class UI controls because their
`type_hint` values encode structured shapes as non-standard strings.

## Examples

- `CoarseDropout.fill`:
  `float | tuple[float, ...] | random | random_uniform | inpaint_telea | inpaint_ns | grayscale`
- `Downscale.interpolation_pair`:
  `dict[['downscale', 'upscale'], [0, 1, 2, 3, 4, 5, 6]]`
- `AnnotationArtifacts.element_types`:
  `tuple[['text', 'rectangle', 'arrow', 'line', 'callout'], ...]`
- `RandomRotate90.group_elements`:
  `tuple[['e', 'r90', 'r180', 'r270'], ...] | None`
- `Affine.scale`:
  `tuple[float, float] | dict[str, tuple[float, float]]`

## Impact

Downstream UI generators must either hide these parameters, fall back to raw
JSON, or implement fragile string parsers. The FiftyOne plugin uses raw JSON
fallback fields for optional complex parameters in normal App flows, which keeps
the plugin maintainable but is less ergonomic than first-class typed controls.

## Request

Please expose a machine-readable parameter shape in addition to the display
type hint. Useful shapes would include:

- primitive scalar;
- numeric range;
- enum/literal;
- list/tuple with item shape and optional length;
- object/dict with fixed keys and per-key value shape;
- union with explicit variants;
- external data or callback marker.

This would let downstream consumers render controls safely without hard-coded
transform-specific parsers.

## Minimal repro

```python
from albu_spec import get_all_transforms_metadata

metadata = {item.name: item for item in get_all_transforms_metadata().get_all()}
for transform, parameter in [
    ("CoarseDropout", "fill"),
    ("Downscale", "interpolation_pair"),
    ("AnnotationArtifacts", "element_types"),
    ("RandomRotate90", "group_elements"),
]:
    field = metadata[transform].parameters[parameter]
    print(transform, parameter, field.type_hint, field.default)
```

## Verification

Focused local plugin checks for this integration layer:

```bash
uv run pytest tests/unit/test_albu_spec_catalog.py tests/unit/test_albu_spec_parameter_schema.py tests/unit/test_albumentations_pipeline_factory.py
uv run pyrefly check
uv run ruff check albumentationsx_plugin scripts tests
uv run ruff format --check albumentationsx_plugin scripts tests
```
````
