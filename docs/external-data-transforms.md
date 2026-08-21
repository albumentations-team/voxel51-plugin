# External-Data Transforms

VOX-43 tracks AlbumentationsX transforms that cannot run from a single source
image plus ordinary annotation targets. These transforms need reference images,
donor objects, overlay assets, text metadata, fonts, or other external inputs.

The plugin keeps unresolved transform families out of normal executable choices
until each family has an explicit input adapter, validation, provenance, cleanup
safety checks, and focused tests.

## Current Status

These reference-image transforms are executable through the FiftyOne adapter:

- `FDA`
- `HistogramMatching`
- `PixelDistributionAdaptation`

They use the current execution scope as a deterministic reference pool. Each
source sample receives all other source samples as preloaded reference images
under the transform's `metadata_key`; per-output replay metadata records the
reference source ids. The run is rejected before any files are written when the
scope contains fewer than two source samples.

The catalog still classifies these unresolved transforms as
`requires_external_data`:

- `CopyAndPaste`
- `Mosaic`
- `OverlayElements`
- `TextImage`

VOX-43 adds a host-neutral `ExternalInputRequirement` contract to
`TransformCapability`. Capability entries can describe the external inputs they
need whether the transform is already executable or still blocked behind a
future adapter.

## Requirement Inventory

| Transform | Requirement | Kind | Metadata key | Resolver hint |
|---|---|---|---|---|
| `CopyAndPaste` | `donor_objects` | `metadata_sequence` | `copy_paste_metadata` | `copy_paste_donor_pool` |
| `FDA` | `reference_images` | `metadata_sequence` | `fda_metadata` | `reference_image_pool` |
| `HistogramMatching` | `reference_images` | `metadata_sequence` | `hm_metadata` | `reference_image_pool` |
| `Mosaic` | `mosaic_items` | `metadata_sequence` | `mosaic_metadata` | `mosaic_sample_pool` |
| `OverlayElements` | `overlay_elements` | `metadata_sequence` | `overlay_metadata` | `overlay_element_pool` |
| `PixelDistributionAdaptation` | `reference_images` | `metadata_sequence` | `pda_metadata` | `reference_image_pool` |
| `TextImage` | `text_regions` | `metadata_sequence` | `textimage_metadata` | `text_region_metadata` |
| `TextImage` | `font_file` | `file_path` | n/a | `font_file_path` |

`metadata_sequence` means the AlbumentationsX transform expects a sequence of
preloaded data objects under the configured `metadata_key` in the Compose call.
`file_path` means the transform accepts an explicit user or environment resource
path and must validate that path before execution.

## Execution Policy

Do not move another transform from `requires_external_data` to a normal
executable status until all of these are true:

- the App can resolve the required inputs from explicit user choices;
- the resolver validates dataset schema, path containment or extension policy,
  and missing data before execution;
- resolved inputs are recorded in manifest metadata or per-output replay;
- cleanup tests prove reference inputs are never deleted;
- focused execution tests cover at least one happy path and one missing-input
  failure for the transform family.

The first execution slice supports the shared reference-image family:
`FDA`, `HistogramMatching`, and `PixelDistributionAdaptation`. Next slices
should handle donor-object, mosaic, overlay, and text/font data separately
because their metadata shapes and cleanup risks differ from simple reference
image pools.
