# Architecture

This document turns the architecture section of `DESIGN.md` into implementation
guidance for the MVP. The design document remains the product contract; this
page describes the code boundaries we should keep while building it.

## Goals

- Keep the first FiftyOne plugin implementation small and testable.
- Isolate changes in FiftyOne, AlbumentationsX, and albu-spec behind adapters.
- Avoid a second handwritten AlbumentationsX transform catalog.
- Make a future non-FiftyOne host possible without rewriting augmentation
  logic.
- Keep source samples, source media, and source annotations immutable.

## Layers

`core`

Host-neutral data models, validation rules, errors, and orchestration
interfaces. Code in this layer describes what the plugin needs to do without
knowing how FiftyOne renders forms or how AlbumentationsX names runtime classes.

Expected modules:

- `albumentationsx_plugin/core/models.py` for compatibility exports
- `albumentationsx_plugin/core/contracts/pipeline.py`
- `albumentationsx_plugin/core/contracts/catalog.py`
- `albumentationsx_plugin/core/contracts/forms.py`
- `albumentationsx_plugin/core/contracts/augmentation.py`
- `albumentationsx_plugin/core/contracts/runs.py`
- `albumentationsx_plugin/core/contracts/fixed_slice.py` for the temporary
  fixed-transform MVP contract
- `albumentationsx_plugin/core/serialization/`
- `albumentationsx_plugin/core/errors.py`
- `albumentationsx_plugin/core/interfaces/catalog.py`
- `albumentationsx_plugin/core/interfaces/pipeline.py`
- `albumentationsx_plugin/core/interfaces/host.py`
- `albumentationsx_plugin/core/interfaces/storage.py`

`albumentations_backend`

AlbumentationsX and albu-spec integration. This layer loads transform metadata,
classifies capabilities, converts parameter metadata into neutral form schemas,
creates validated AlbumentationsX pipelines, and extracts replay data.

Expected modules:

- `albumentationsx_plugin/albumentations_backend/interfaces.py` for backend
  protocol exports
- `albumentationsx_plugin/albumentations_backend/catalog/`
- `albumentationsx_plugin/albumentations_backend/parameters/`
- `albumentationsx_plugin/albumentations_backend/pipeline/registry.py`
- `albumentationsx_plugin/albumentations_backend/pipeline/coercion.py`
- `albumentationsx_plugin/albumentations_backend/pipeline/factory.py`
- `albumentationsx_plugin/albumentations_backend/pipeline/runner.py`
- `albumentationsx_plugin/albumentations_backend/pipeline/replay.py`
- `albumentationsx_plugin/albumentations_backend/fixed/pipeline.py` for the
  temporary fixed-transform vertical slice

`hosts/fiftyone`

FiftyOne-specific adapter code. This layer registers operators, renders neutral
schemas into `fiftyone.operators.types`, converts selected samples or views into
host-neutral inputs, creates new FiftyOne samples from augmentation results, and
exposes run summary/delete operators.

Expected modules:

- `albumentationsx_plugin/hosts/interfaces.py` for generic host protocol exports
- `albumentationsx_plugin/hosts/fiftyone/operators/augment.py`
- `albumentationsx_plugin/hosts/fiftyone/operators/view_run.py`
- `albumentationsx_plugin/hosts/fiftyone/operators/delete_run.py`
- `albumentationsx_plugin/hosts/fiftyone/augmentation/executor.py`
- `albumentationsx_plugin/hosts/fiftyone/forms/renderer.py`
- `albumentationsx_plugin/hosts/fiftyone/samples/adapter.py`

`storage`

Plugin-owned output paths, image IO, manifests, run metadata, atomic writes, and
safe cleanup. This layer should be usable from FiftyOne operators, but
destructive rules live here so they can be tested without the App.

Expected modules:

- `albumentationsx_plugin/storage/paths.py`
- `albumentationsx_plugin/storage/images/io.py`
- `albumentationsx_plugin/storage/images/naming.py`
- `albumentationsx_plugin/storage/manifest.py`
- `albumentationsx_plugin/storage/cleanup.py`

The root `__init__.py` stays short and only exposes plugin registration hooks
required by FiftyOne.

## Dependency Rules

Allowed dependencies:

- `core` may import only the Python standard library and lightweight typing or
  serialization helpers already accepted by the project.
- `albumentations_backend` may import `core`, NumPy array helpers,
  `albumentations`, and `albu-spec`. The runtime package is
  `albumentationsx`, imported as `albumentations`.
- `storage` may import `core`, standard filesystem/JSON helpers, NumPy, and
  Pillow for image IO.
- `hosts/fiftyone` may import `core`, `storage`,
  `albumentations_backend.interfaces`, and `fiftyone`.
- Operator modules may compose services, but should not own catalog parsing,
  pipeline construction, or cleanup path validation.

Forbidden dependencies:

- `core` must not import `fiftyone`, `albumentations`, or `albu-spec`.
- `albumentations_backend` must not import `fiftyone`.
- `storage` must not import `fiftyone` UI/operator modules.
- Form rendering must not instantiate AlbumentationsX transform classes.
- Pipeline creation must not call `eval` or instantiate classes from unchecked
  user-provided names.
- Cleanup must not use broad globs or delete files outside the plugin-owned run
  directory.

## Boundary Enforcement

Dependency rules should be checked as soon as the corresponding packages exist.
Start with small unit tests that import modules and assert forbidden dependencies
are not loaded by neutral layers:

- importing `albumentationsx_plugin.core` must not import `fiftyone`,
  `albumentations`, or `albu-spec`;
- importing `albumentationsx_plugin.albumentations_backend.interfaces` must not
  import `fiftyone`;
- importing `albumentationsx_plugin.storage` must not import FiftyOne operator
  modules.

When the package layout stabilizes, add an import-boundary tool such as
`import-linter` to encode the same rules in configuration. That check should run
inside the complete local gate documented in `docs/verification.md`.

## Core Contracts

The MVP should introduce explicit DTOs before adding heavier behavior. The exact
implementation can use dataclasses, typed dictionaries, or another local pattern,
but the objects should remain JSON-serializable.

Planned contracts:

- `PipelineConfig`: ordered transform list, output count, selected targets, and
  execution options.
- `TransformConfig`: transform name plus user-supplied parameters.
- `TransformCapability`: catalog status, supported targets, unsupported reason,
  and optional advanced-parameter notes.
- `FormFieldSchema`: host-neutral field kind, default, bounds, choices,
  required flag, and help text.
- `AugmentationInput`: source sample identity, filepath, dimensions, selected
  label fields, and host metadata needed for output mapping.
- `AugmentationResult`: created media path, copied/transformed labels, replay
  data, source sample ID, and per-sample errors.
- `RunManifest`: run key, versions, pipeline config, source IDs, created IDs,
  relative output paths, replay records, counters, and errors.

Structured errors should include a stable reason code, a user-facing message,
and optional context such as transform name, parameter name, sample ID, or path.

## Interface Contracts

Protocols live under `albumentationsx_plugin/core/interfaces/` and use only core
DTOs plus standard-library types. They are grouped by boundary:

- `catalog.py`: `TransformCatalogProvider` and `ParameterSchemaProvider`;
- `pipeline.py`: `PipelineFactory` and `PipelineRunner`;
- `host.py`: `HostSampleAdapter`;
- `storage.py`: `RunStore` and `OutputStorageBackend`.

`albumentationsx_plugin/albumentations_backend/interfaces.py` re-exports the
backend-facing protocols that concrete albu-spec and AlbumentationsX modules
will implement. Host adapters may import this module when they need a backend
service, but they should not import concrete backend modules directly.

Concrete implementations should live in their owning packages:

- albu-spec catalog and schema logic in `albumentations_backend`;
- AlbumentationsX pipeline construction and replay extraction in
  `albumentations_backend`;
- FiftyOne sample/view conversion and output sample creation in
  `hosts/fiftyone`;
- manifest persistence, output writes, and cleanup in `storage`.

The VOX-10 fixed-transform slice is documented in
`docs/fixed-transform-slice.md`. It is intentionally small and should be
replaced by catalog-driven backend services rather than expanded as a handwritten
catalog.

For VOX-10, `hosts/fiftyone/augmentation/executor.py` is the temporary
composition point that wires the FiftyOne sample adapter, storage helpers, and
fixed AlbumentationsX backend together. Later catalog work should replace this
with explicit backend service injection so host operators depend on backend
interfaces instead of concrete fixed-slice modules.

The VOX-11 albu-spec catalog is documented in `docs/albu-spec-catalog.md`. It
is the source for normal transform choices, capability reports, and version
drift checks.

The VOX-12 parameter schema generator is documented in
`docs/parameter-schema.md`. It converts albu-spec parameter metadata into
host-neutral `FormFieldSchema` records without importing FiftyOne.

The VOX-13 dynamic form layer is documented in
`docs/dynamic-fiftyone-forms.md`. It keeps FiftyOne-specific rendering under
`hosts/fiftyone/forms/` while consuming backend catalog and schema interfaces.

The VOX-14 pipeline factory is documented in `docs/pipeline-factory.md`. It
resolves transform classes from albu-spec metadata, validates parameters through
neutral schemas, and provides an image-only replay runner. Host-level media IO,
output sample creation, and storage orchestration remain outside that runner.

The VOX-15 run manifest layer is documented in `docs/run-manifest.md`. It stores
`manifest.json` in the plugin-owned run directory and registers the same payload
in FiftyOne's generic custom run store. The filesystem manifest remains the
cleanup allowlist because it contains relative output paths that can be resolved
and validated later.

## Extension Points

### New transform source

A new transform metadata source should implement the same catalog and schema
interfaces used by `albumentations_backend`. The host layer should keep asking
for `TransformCapability` and `FormFieldSchema` objects instead of reaching into
source-specific metadata.

### New host integration

A non-FiftyOne host should add a new package under `albumentationsx_plugin/hosts/`
and implement host adapters for:

- rendering `FormFieldSchema` into that host's UI;
- converting host media records into `AugmentationInput`;
- converting `AugmentationResult` into host-owned output records;
- exposing run summaries and cleanup confirmation.

The host should not need to reimplement catalog loading, schema generation,
pipeline validation, replay extraction, or manifest safety rules.

### Future annotation targets

Detections, segmentation masks, and keypoints should be added as separate
adapter modules with round-trip tests. Spatial labels must not be copied across
geometric transforms unless the transform chain is proven compatible with that
target type.

## Storage and Safety

Generated files belong under a plugin-owned directory:

```text
~/.fiftyone/albumentationsx-plugin/<dataset-name>/<run-key>/
```

Each run stores a manifest with relative paths. Cleanup resolves each path,
checks that it remains inside the run directory, and deletes only files listed
in the manifest. Missing files and already-deleted samples should be reported as
idempotent cleanup results, not broad failures.

Source media paths, source annotations, and source sample IDs are never modified
by augmentation execution or cleanup.

## Decision Record

Decision: keep the reusable core inside this repository for the MVP.

Reason: there is one concrete host integration today, FiftyOne. Extracting a
separate shared package before a second consumer exists would add release and
dependency overhead without proving the boundary. The code should still be
written as if another host could appear: neutral DTOs, small interfaces, and no
FiftyOne imports in `core`.

Revisit when:

- another service wants to use the augmentation core;
- the core becomes useful outside the plugin release cadence;
- host adapters start sharing only a thin dependency on the rest of the package.

## Verification

Use `docs/verification.md` as the single source of truth for local gates and
manual checks. Architecture-only changes usually need the documentation gate and
manual review against `DESIGN.md`; code changes should use the complete local
gate described there.
