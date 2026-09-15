# Reference images and external inputs

Some AlbumentationsX transforms cannot run from a single source
image plus ordinary annotation targets. These transforms need reference images,
donor objects, overlay assets, text metadata, fonts, or other external inputs.

Only transforms whose required inputs can be supplied by the plugin appear
in the executable selector.

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

These excluded transforms are visible in the detailed capability report with
an explanation. They cannot be enabled by supplying arbitrary metadata or paths
in advanced JSON. See the [catalog API](operator-api.md#catalog-filters-and-statuses).

## Resource limits

The current implementation reads the complete reference pool and constructs a
list of other sources for each input. Image memory scales with the full pool;
reference lists and provenance grow quadratically with source count. Preparation
precedes output progress/cancellation checkpoints. Use small selected scopes
and do not assume delegated execution bounds memory or makes preparation
immediately cancellable.
