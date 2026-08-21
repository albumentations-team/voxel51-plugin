# External-Data Transforms

VOX-43 tracks AlbumentationsX transforms that cannot run from a single source
image plus ordinary annotation targets. These transforms need reference images,
donor objects, overlay assets, text metadata, fonts, or other external inputs.

The plugin keeps these transforms out of normal executable choices until each
transform family has an explicit input adapter, validation, provenance, cleanup
safety checks, and focused tests.

## Current Status

The catalog still classifies these transforms as `requires_external_data`:

- `CopyAndPaste`
- `FDA`
- `HistogramMatching`
- `Mosaic`
- `OverlayElements`
- `PixelDistributionAdaptation`
- `TextImage`

VOX-43 adds a host-neutral `ExternalInputRequirement` contract to
`TransformCapability`. Capability entries can now describe the external inputs
they need without making the transform executable.

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

Do not move a transform from `requires_external_data` to a normal executable
status until all of these are true:

- the App can resolve the required inputs from explicit user choices;
- the resolver validates dataset schema, path containment or extension policy,
  and missing data before execution;
- resolved inputs are recorded in manifest metadata or per-output replay;
- cleanup tests prove reference inputs are never deleted;
- focused execution tests cover at least one happy path and one missing-input
  failure for the transform family.

The first practical execution slice should target one reference-image family,
such as `HistogramMatching`, before broadening to donor-object or mosaic-style
transforms.
