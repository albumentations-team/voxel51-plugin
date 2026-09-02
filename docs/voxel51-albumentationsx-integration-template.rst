.. _albumentationsx-integration:

AlbumentationsX Integration
===========================

.. default-role:: code

..
    TODO: Uncomment and fill this directive if Voxel51 docs need an
    availability banner for the final published page.

    .. customavailablein::
        :oss_version: TBD
        :enterprise_version: TBD

The `AlbumentationsX <https://github.com/albumentations-team/albumentationsx>`_
library provides modern image augmentation transforms for computer vision
workflows. The AlbumentationsX FiftyOne plugin lets you build augmentation
pipelines directly in the FiftyOne App, preview their effects, apply them to
image datasets, inspect generated samples, and delete plugin-created outputs
without touching source samples or source files.

This integration takes the form of a
:ref:`FiftyOne plugin <using-plugins>` that can be installed from the
`Albumentations Team repository <https://github.com/albumentations-team/voxel51-plugin>`_.
It is separate from the older
`jacobmarks/fiftyone-albumentations-plugin <https://github.com/jacobmarks/fiftyone-albumentations-plugin>`_
integration.

With the AlbumentationsX plugin, you can augment images and keep supported
|Classification|, |Detections|, |Keypoints|, |Polylines|, |Heatmap|, and
|Segmentation| labels aligned when the selected pipeline is compatible.

This guide focuses on setup and App functionality. For deeper implementation
details, see the plugin repository documentation.

.. _albumentationsx-plugin-overview:

Overview
________

Before we get started, let's take a look at what the AlbumentationsX FiftyOne
integration provides and when to use each workflow.

.. _albumentationsx-workflows-at-a-glance:

Workflows at a glance
---------------------

.. list-table::
    :header-rows: 1

    * - Goal
      - Use
      - Result
    * - Try a transform without writing data
      - `Preview only`
      - Source/output image previews, transformed label JSON, and sampled
        replay metadata in the operator output
    * - Validate a configuration
      - `Dry run`
      - Scope and config validation without samples, files, manifests, presets,
        or custom runs
    * - Create augmented dataset samples
      - Materialized augmentation run
      - Generated samples, plugin-owned output files, run tags, run manifest,
        and FiftyOne custom run metadata
    * - Reuse a known recipe
      - `Named preset`
      - A shared pipeline template that can be loaded across datasets in the
        same plugin storage root
    * - Repeat a same-dataset setup
      - `Previous run`
      - The saved pipeline config from an earlier run on the active dataset,
        with fresh randomness
    * - Remove generated data
      - `Delete AlbumentationsX Run`
      - Only the generated samples, generated files, and custom run for the
        selected run are removed

.. _albumentationsx-supported-transformations:

Supported transformations
-------------------------

AlbumentationsX exposes a version-aware transform catalog. The plugin reads the
current AlbumentationsX/albu-spec metadata and shows the transforms that can be
executed safely through the current image-focused FiftyOne flow.

For the current validated dependency snapshot:

- capability version key:
  `albumentationsx-2.3.8__albu-spec-0.0.6`
- total catalog transforms: `134`
- normal executable choices: `113`
- directly supported choices: `72`
- supported choices with default-backed advanced parameters: `41`

Use the `Show AlbumentationsX Capabilities` operator to search the catalog by
name, support status, target type, dependency version, and exclusion reason.
This is the recommended way to understand why a transform is available,
hidden, or blocked in the normal App flow.

.. note::

    Transform counts are dependency-specific. Recheck the capability report
    after updating AlbumentationsX, albu-spec, or the plugin's safety policy.

.. _albumentationsx-plugin-functionality:

Functionality
-------------

The AlbumentationsX FiftyOne plugin provides the following functionality:

- Apply AlbumentationsX pipelines to selected samples, the current view, or the
  entire image dataset
- Compose ordered multi-stage pipelines in the FiftyOne App
- Preview selected-sample outputs before writing files
- Validate a configuration with a dry run
- Generate one or more output samples per source sample
- Keep supported annotations aligned with compatible transforms
- Inspect saved run manifests and sampled replay metadata
- Reuse a previous run as a same-dataset pipeline template with fresh
  randomness
- Save, inspect, export, import, rename, and delete named pipeline presets
- Delete only the samples, files, and custom run created by a selected
  augmentation run

.. _albumentationsx-registered-operators:

Registered operators
--------------------

The plugin registers the following FiftyOne App operators:

.. list-table::
    :header-rows: 1

    * - Operator
      - Purpose
    * - `Augment with AlbumentationsX`
      - Configure, preview, validate, save presets, and execute augmentation
        pipelines.
    * - `Show AlbumentationsX Capabilities`
      - Browse transform support metadata and exclusion reasons.
    * - `Manage AlbumentationsX Presets`
      - Inspect, export, import, rename, or delete named presets.
    * - `View AlbumentationsX Run`
      - Inspect a saved run manifest and generated sample availability.
    * - `Delete AlbumentationsX Run`
      - Remove generated outputs for one run after explicit confirmation.

.. _albumentationsx-data-safety:

Data safety model
-----------------

The plugin is designed to make generated data easy to inspect and safe to
remove:

- source samples are not modified
- source image files are not overwritten
- generated files are written under plugin-owned storage
- generated samples receive plugin tags and provenance fields
- materialized runs write explicit manifests
- cleanup deletes only manifest-listed generated outputs for the selected run
- named presets are separate from generated samples and are never deleted by
  run cleanup

.. _albumentationsx-installation:

Setup
_____

To get started, first install FiftyOne in the Python environment that will run
the App:

.. code-block:: bash

    $ python -m pip install "fiftyone>=1.19,<2"

Next, install a published release of the AlbumentationsX plugin:

.. code-block:: bash

    $ fiftyone plugins download albumentations-team/voxel51-plugin/<release-tag>
    $ fiftyone plugins requirements @albumentations/albumentationsx --install
    $ fiftyone plugins list --enabled --names-only

The plugin list should include:

.. code-block:: text

    @albumentations/albumentationsx

Before continuing, verify the operators that the App will expose:

.. code-block:: bash

    $ fiftyone operators list | grep albumentationsx

.. note::

    Replace `<release-tag>` with a published GitHub release tag, such as
    `v0.1.0`, rather than installing an unreviewed branch tip.

.. _albumentationsx-quickstart:

Quickstart
----------

This is the shortest path for validating the integration in a fresh
environment:

1. Install the plugin and its requirements.
2. Create the deterministic demo dataset.
3. Launch the FiftyOne App.
4. Select a sample.
5. Run `Augment with AlbumentationsX` with `Preview only` enabled.
6. Run the same configuration with `Preview only` disabled.
7. Inspect the generated run with `View AlbumentationsX Run`.
8. Delete the generated outputs with `Delete AlbumentationsX Run`.

For source installs, the commands are:

.. code-block:: bash

    $ uv sync --group dev
    $ export FIFTYONE_PLUGINS_DIR="$PWD"
    $ uv run python scripts/create_demo_dataset.py create --overwrite
    $ uv run fiftyone app launch albumentationsx-demo

.. _albumentationsx-local-development-setup:

Local development setup
-----------------------

For local development from a repository checkout:

.. code-block:: bash

    $ git clone https://github.com/albumentations-team/voxel51-plugin.git
    $ cd voxel51-plugin
    $ uv sync --group dev
    $ export FIFTYONE_PLUGINS_DIR="$PWD"
    $ uv run fiftyone operators list

.. note::

    `FIFTYONE_PLUGINS_DIR` should point at the plugin checkout itself. Avoid
    pointing it at a broad workspace root, because FiftyOne recursively scans
    plugin paths.

Create the deterministic demo dataset and launch the App:

.. code-block:: bash

    $ uv run python scripts/create_demo_dataset.py create --overwrite
    $ uv run fiftyone app launch albumentationsx-demo

The default demo dataset contains three generated image samples with
|Classification|, |Detections|, |Keypoints|, |Polylines|, |Heatmap|, and
|Segmentation| fields.

.. _albumentationsx-applying-transformations:

Apply transformations
_____________________

To apply AlbumentationsX transformations to your dataset, open the
`Augment with AlbumentationsX` operator from the FiftyOne App actions menu.

.. _albumentationsx-first-run:

First run
---------

For your first run:

1. Select one or more source samples.
2. Set `Execution scope` to `Selected samples`.
3. Enable `Preview only`.
4. Set `Pipeline stages` to `1`.
5. Choose `HorizontalFlip`.
6. Keep `p` at `1.0`.
7. Keep `Outputs per sample` at `1`.
8. Run the operator and inspect the preview output.
9. Disable `Preview only`, optionally set a readable `Run label`, and run the
   same configuration again.

The plugin creates new output samples tagged with `albumentationsx-output` and
a run-specific tag. Source samples and source image files remain unchanged.

..
    TODO: Add image:
    ../images/integrations/albumentationsx_first_run_preview.gif

..
    TODO: Add image:
    ../images/integrations/albumentationsx_first_run_outputs.gif

.. _albumentationsx-form-controls:

Form controls
-------------

The main form controls are:

.. list-table::
    :header-rows: 1

    * - Control
      - Purpose
    * - `Named preset`
      - Load a reusable pipeline template from shared plugin storage.
    * - `Previous run`
      - Load a saved run's pipeline config from the active dataset.
    * - `Execution scope`
      - Choose selected samples, the current view, or the entire dataset.
    * - `Preview only`
      - Render bounded selected-sample previews without persistence.
    * - `Dry run`
      - Validate scope, form values, annotation compatibility, and pipeline
        construction without creating outputs.
    * - `Run label`
      - Add a readable prefix to generated run keys.
    * - `Outputs per sample`
      - Generate multiple outputs for each source sample.
    * - `Preset name` and `Preset description`
      - Save the resolved pipeline as a named preset.
    * - `Save preset only`
      - Validate and save a preset without running augmentation.
    * - `Pipeline stages`
      - Choose how many stage slots are visible.

`Named preset` and `Previous run` are mutually exclusive template sources. If
both are selected, the form shows a validation message and blocks execution
until one source is cleared.

Each pipeline stage has its own transform selector, enabled switch, execution
order, and catalog-backed parameter controls. Disabled stages are ignored
without clearing their saved values. Lower execution-order values run earlier.

The form derives defaults from the selected dataset when possible. For example,
crop-like transforms can use image dimensions from selected samples or dataset
metadata instead of forcing users to start from zero.

The form also includes a compact compatibility section. It summarizes the
selected source scope, estimated source count, schema availability, selected
annotation fields, and whether the current pipeline will transform or copy those
fields. Critical conflicts are shown before execution with a corrective action.
Run `Analyze AlbumentationsX Compatibility` when you need the full report with
field tables, target-family details, package versions, and copyable JSON.

Recommended starting points:

.. list-table::
    :header-rows: 1

    * - Dataset content
      - Recommended first pipeline
      - Why
    * - Images only
      - `HorizontalFlip` plus an optional color transform
      - Verifies file generation and visual output quickly.
    * - Boxes or keypoints
      - Geometry-only transforms such as flips, crops, pads, and affine-like
        transforms
      - Keeps spatial annotations synchronized with the image.
    * - Heatmaps or semantic masks
      - Geometry-only transforms
      - Avoids applying image color/intensity changes to label-like arrays.
    * - Unknown or mixed labels
      - `Preview only`, then `Dry run`, then a small materialized run
      - Catches unsupported combinations before writing data.

..
    TODO: Add image:
    ../images/integrations/albumentationsx_multistage_pipeline.gif

.. _albumentationsx-execution-scope:

Execution scope
---------------

`Execution scope` controls which source samples are processed:

.. list-table::
    :header-rows: 1

    * - Scope
      - Use when
    * - `Selected samples`
      - You want a bounded test run or a preview of specific images.
    * - `Current view`
      - You filtered the App to the samples you want to augment.
    * - `Entire dataset`
      - You want to augment every image sample in the active dataset.

For larger views or full datasets, choose delegated execution in FiftyOne so
the App remains responsive while progress is reported:

.. code-block:: bash

    $ fiftyone delegated launch

.. _albumentationsx-preview-and-dry-run:

Preview and dry run
-------------------

Use `Preview only` when you want to inspect selected-sample outputs before
writing anything. Preview returns source images, output images, sampled replay
metadata, and transformed label JSON through the operator output.

Use `Dry run` when you want validation and scope resolution without creating
samples, files, manifests, presets, or FiftyOne custom runs.

Preview and dry run are intentionally non-persistent. They are useful before
running a large current-view or whole-dataset augmentation.

..
    TODO: Add image:
    ../images/integrations/albumentationsx_preview_output.gif

.. _albumentationsx-visualizing-transformations:

Visualize transformations
_________________________

Once you've applied a materialized augmentation run, the generated samples are
added to the dataset. They carry a shared output tag and a run-specific tag:

- `albumentationsx-output`
- `albumentationsx-run-<run-key>`

You can filter for generated samples in the App by matching either tag.

You can also filter programmatically:

.. code-block:: python

    # get all plugin-generated output samples
    output_view = dataset.match_tags("albumentationsx-output")

    # get samples from one augmentation run
    run_view = dataset.match_tags("albumentationsx-run-<run-key>")

Generated samples also include provenance fields:

- `albumentationsx_source_sample_id`
- `albumentationsx_run_key`
- `albumentationsx_transform_summary`
- `albumentationsx_output_tag`

..
    TODO: Add image:
    ../images/integrations/albumentationsx_match_run_tags.gif

.. _albumentationsx-supported-annotations:

Supported annotations
_____________________

The plugin can keep the following FiftyOne label types aligned when the
selected pipeline is compatible:

.. list-table::
    :header-rows: 1

    * - Label type
      - Behavior
    * - `Classification`
      - Copied as static labels.
    * - `Detections`
      - Bounding boxes use Albumentations bbox targets.
    * - `Detection.mask`
      - In-memory instance masks follow their detections.
    * - `Detection.mask_path`
      - File-backed instance masks are loaded and returned as in-memory masks.
    * - `Keypoints`
      - Points use Albumentations keypoint targets.
    * - `Polylines`
      - Vertices use keypoint-style geometry semantics.
    * - `Heatmap`
      - Maps use image-like synchronization for geometry-only pipelines.
    * - `Segmentation`
      - Semantic masks are transformed; file-backed mask outputs are written to
        plugin-owned storage.

If selected annotations cannot be transformed safely, the operator fails before
writing outputs and returns structured diagnostics. For example, selecting a
heatmap and running a mixed geometry plus image-only color/intensity pipeline
is blocked because the heatmap should not receive color operations.

.. note::

    The plugin is intentionally conservative. Unsupported label classes, video
    media, 3D media, unsafe output-only transforms, and unresolved external-data
    transforms are excluded from the normal executable flow.

.. _albumentationsx-run-info:

Inspect augmentation runs
_________________________

Every materialized run receives a public plugin run key such as:

.. code-block:: text

    training-flips-albumentationsx-20260901T120000Z-a1b2c3d4

The optional `Run label` becomes the readable prefix. The run key is used for
generated sample tags, output directories, manifest lookup, and cleanup.

Use the `View AlbumentationsX Run` operator to inspect:

- dependency versions
- resolved pipeline config
- execution scope and status
- source sample IDs and generated sample IDs
- generated sample availability
- relative output paths
- sampled replay metadata
- counters and structured errors

..
    TODO: Add image:
    ../images/integrations/albumentationsx_view_run.gif

.. _albumentationsx-run-manifest:

Run manifest
------------

The run manifest is stored under plugin-owned storage:

.. code-block:: text

    ~/.fiftyone/albumentationsx-plugin/<dataset-name>/<run-key>/manifest.json

The manifest records the pipeline config, output files, generated sample IDs,
dependency versions, execution status, and structured errors. It is the source
of truth for run inspection and cleanup.

`Previous run` uses a saved run's pipeline config as a template for a new run
in the same dataset. It samples fresh randomness. It does not exact-replay each
earlier sample's random parameters.

.. _albumentationsx-saving-transformations:

Save transformations
____________________

If you are satisfied with a pipeline, save it as a named preset from the
`Augment with AlbumentationsX` form by filling `Preset name`. You can either
run the augmentation and save the preset at the same time, or enable
`Save preset only` to validate and save the preset without creating outputs.

Named presets are reusable pipeline templates stored outside dataset-specific
run directories. A preset stores transform names, parameter values, output
count, plugin version, dependency versions, and an optional description. It
does not store source sample IDs, generated sample IDs, output paths, custom
run keys, or sampled replay records.

Use `Manage AlbumentationsX Presets` to inspect, export, import, rename, or
delete named presets.

..
    TODO: Add image:
    ../images/integrations/albumentationsx_manage_presets.gif

.. _albumentationsx-presets-vs-previous-runs:

Named presets versus previous runs
----------------------------------

.. list-table::
    :header-rows: 1

    * - Feature
      - Named preset
      - Previous run
    * - Main purpose
      - Save a reusable augmentation recipe
      - Reuse the pipeline config from a run that already happened
    * - Dataset scope
      - Available across datasets in the same plugin storage root
      - Available for the active dataset
    * - Stores source sample IDs
      - No
      - Yes, in the run manifest
    * - Stores generated output IDs and paths
      - No
      - Yes, in the run manifest
    * - Stores sampled replay records
      - No
      - Yes
    * - Loads with fresh randomness
      - Yes
      - Yes
    * - Exact replay of previous sampled params
      - No
      - No

Use named presets for reusable training recipes. Use previous runs when you
want to start from a pipeline that was already executed on the current dataset.

.. _albumentationsx-cleanup:

Delete generated outputs
________________________

Use `Delete AlbumentationsX Run` when you want to remove generated outputs for
one selected run. Choose the run key and check the confirmation box.

Cleanup deletes only plugin-owned data for that run:

- generated samples
- manifest-listed generated files
- the matching FiftyOne custom run record

Source samples and source files remain unchanged. Preset deletion is separate
from run cleanup and never removes generated samples or source data.

..
    TODO: Add image:
    ../images/integrations/albumentationsx_delete_run.gif

.. _albumentationsx-demo-suites:

Demo and validation suites
__________________________

The default `basic` suite creates `albumentationsx-demo`, which is the
recommended dataset for the first-run walkthrough.

The repository also provides focused suites for broader checks:

.. list-table::
    :header-rows: 1

    * - Suite
      - Dataset
      - Purpose
    * - `basic`
      - `albumentationsx-demo`
      - First-run and smoke workflow
    * - `annotations`
      - `albumentationsx-demo-annotations`
      - Label-family checks, multiple labels, empty containers, and boundary
        geometry
    * - `masks`
      - `albumentationsx-demo-masks`
      - In-memory and file-backed masks, detection masks, and heatmap assets
    * - `validation`
      - `albumentationsx-demo-validation`
      - Intentional edge cases for validation and error UX checks

Create all suites with:

.. code-block:: bash

    $ uv run python scripts/create_demo_dataset.py create --suite all --overwrite

List all suites with:

.. code-block:: bash

    $ uv run python scripts/create_demo_dataset.py list --suite all

Delete all suites and their generated files with:

.. code-block:: bash

    $ uv run python scripts/create_demo_dataset.py delete --suite all --delete-files

.. _albumentationsx-troubleshooting:

Troubleshooting
_______________

If the operators are not visible, check that the plugin is installed and
enabled:

.. code-block:: bash

    $ fiftyone plugins list --enabled --names-only

For local development, confirm `FIFTYONE_PLUGINS_DIR` points at the repository
root that contains `fiftyone.yml`.

If runtime dependencies are missing, install them into the same environment
that launches FiftyOne:

.. code-block:: bash

    $ fiftyone plugins requirements @albumentations/albumentationsx --install

When an augmentation fails, copy the structured diagnostics from the operator
output:

- `errors_json`
- `pipeline_config_json`
- `operator_params_json`

These fields are designed for bug reports and usually include the field, label
type, transform, stage, target, reason, and relevant config context.

For actionable issue reports, include:

- plugin version and release tag
- FiftyOne, AlbumentationsX, and albu-spec versions
- the demo suite or dataset shape used to reproduce the issue
- the selected execution scope
- `errors_json`
- `pipeline_config_json`
- `operator_params_json`
- whether `Preview only`, `Dry run`, or materialized execution was used

.. _albumentationsx-common-errors:

Common errors
-------------

.. list-table::
    :header-rows: 1

    * - Symptom
      - Likely cause
      - What to check
    * - Operators are missing
      - Plugin is not installed, not enabled, or scanned from the wrong
        directory
      - Check `fiftyone plugins list --enabled --names-only` and
        `FIFTYONE_PLUGINS_DIR`
    * - `No module named albu_spec`
      - Plugin requirements were not installed in the environment that launched
        FiftyOne
      - Run the plugin requirements install command from the setup section in
        the environment that launches FiftyOne.
    * - A heatmap blocks an image-only transform
      - The selected pipeline would apply a color/intensity operation to a
        heatmap
      - Use a geometry-only pipeline, deselect the heatmap field, or inspect
        `errors_json`
    * - Preview is blocked
      - Preview needs selected samples and a bounded preview scope
      - Select one or more samples and use `Selected samples`
    * - Preset and previous run conflict
      - Two template sources are selected at once
      - Clear either `Named preset` or `Previous run`

.. _albumentationsx-known-limitations:

Known limitations
_________________

The current plugin focuses on image samples and safe, inspectable App
workflows. The normal executable selector excludes video media, 3D media,
unsafe output-only transforms, unresolved donor-object/mosaic/overlay/text
external-data transforms, and unsupported label classes.

`Previous run` restores pipeline configuration with fresh randomness. It is not
an exact replay mode for previously sampled parameters.

`Polylines` use vertex-based transform semantics. Crops do not perform full
polygon clipping; vertices outside the output image can be removed, and
contours with too few remaining points are dropped.

`Heatmap` support is intended for geometry-only target synchronization. Mixed
geometry plus color/intensity pipelines are blocked when a selected heatmap
would be transformed unsafely.

.. _albumentationsx-older-plugin-differences:

How this differs from the older Albumentations plugin
_____________________________________________________

.. list-table::
    :header-rows: 1

    * - Older plugin behavior
      - AlbumentationsX plugin behavior
    * - Installs `jacobmarks/fiftyone-albumentations-plugin`.
      - Installs `albumentations-team/voxel51-plugin` from a published tag.
    * - Uses mostly classic Albumentations transforms.
      - Exposes catalog-backed AlbumentationsX choices from albu-spec.
    * - Temporary generated batches are the default.
      - Materialized runs are persistent until deleted by run key.
    * - Provides last-run shortcuts.
      - Lets you inspect available runs by explicit run key.
    * - Saves pipelines to the dataset.
      - Saves named presets in shared plugin storage for reuse across datasets.
    * - Uses a quickstart dataset plus optional model inference examples.
      - Uses deterministic generated demo suites with no external downloads.
    * - Claims broad label support.
      - Safety-checks supported annotations before writing outputs.

.. _albumentationsx-publication-checklist:

Publication checklist
_____________________

Before publishing this page in the Voxel51 docs:

- replace `<release-tag>` with the recommended stable release tag, or keep the
  placeholder if docs policy prefers it
- confirm the availability banner values
- confirm the capability counts against the release lockfile
- run the plugin requirements install command in a fresh environment
- create the demo dataset and complete the first-run walkthrough manually
- verify the generated samples, labels, run summary, preset flow, and cleanup
- capture the visual assets listed below
- build the Voxel51 docs site and fix any Sphinx warnings

.. _albumentationsx-visual-assets:

Visual asset checklist
----------------------

Before publishing this page, capture screenshots or GIFs for:

- the operator list or actions menu
- general augmentation settings
- multi-stage pipeline configuration
- selected-sample preview output
- generated samples filtered by output tag or run tag
- run summary inspection
- preset management
- delete confirmation
- capability browser filters
