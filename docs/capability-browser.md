# Capability Browser Operator

VOX-44 adds the read-only `Show AlbumentationsX Capabilities` operator. It uses
the same `AlbuSpecCatalogProvider` and capability classification rules as the
augmentation form and `scripts/report_transform_capabilities.py`.

The operator is available without selected samples. It shows:

- plugin, FiftyOne, AlbumentationsX, and albu-spec versions;
- the capability version key;
- total, supported, excluded, and matching transform counts;
- status counts for the full catalog and the current filter result;
- one row per matching transform with supported targets, advanced-parameter
  status, external input requirements, reason code, and explanation.

## Filters

- `Search`: case-insensitive transform-name substring search.
- `Capability status`: filters by catalog status, including `supported`,
  `supported_with_defaults`, and excluded statuses.
- `Target`: filters transforms by albu-spec target, such as `image`, `mask`,
  `bboxes`, or `keypoints`.

The output includes both structured `transforms` rows and `transforms_json` for
copying into issue reports or release notes. `json_editable` in the
advanced-parameter status means optional complex parameters are available in the
augmentation form as JSON-backed advanced fields.
For `requires_external_data` transforms, `External inputs` lists the declared
input requirement names that future VOX-43 adapters must resolve before the
transform can become executable.

## Dependency Behavior

The plugin entrypoint does not import `albu-spec` while registering operators.
The capability catalog is loaded only when the operator form or execution
payload is resolved. If `albu-spec` or AlbumentationsX is missing from the active
FiftyOne environment, the operator shows a dependency installation message
instead of breaking plugin registration.
