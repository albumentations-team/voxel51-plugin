# Release v0.1.0

This page is the release note and checklist for the first public MVP release of
`@albumentations/albumentationsx`.

## MVP Scope

`v0.1.0` is a working FiftyOne plugin MVP:

- installs as a local FiftyOne plugin from this repository;
- registers `Augment with AlbumentationsX`, `View AlbumentationsX Run`, and
  `Delete AlbumentationsX Run`;
- renders catalog-backed AlbumentationsX transform forms from albu-spec
  metadata;
- lets users configure up to ten ordered augmentation stage slots;
- can prefill augmentation settings from a previous run in the current dataset;
- applies the pipeline to selected samples in the active dataset or filtered
  view;
- creates new output samples without mutating source samples or source files;
- transforms supported FiftyOne `Classification`, `Detections`, `Keypoints`,
  `Polylines`, `Heatmap`, and `Segmentation` mask fields in the executable
  path;
- persists run manifests with sampled replay metadata and dependency versions;
- supports read-only run inspection and confirmed cleanup of generated samples
  and files.

## Known Limitations

- Execution is image-focused and writes generated image samples under
  plugin-owned run directories.
- The executable picker exposes the `110` normal MVP choices classified as
  `supported` or `supported_with_defaults` by the current albu-spec catalog.
  The default stage presets are `HorizontalFlip`,
  `RandomBrightnessContrast`, and `RandomCrop`, but they are not the complete
  transform set.
- Advanced optional JSON fallback parameters are hidden for
  `supported_with_defaults` transforms.
- Previous-run presets reuse saved pipeline configuration with fresh randomness;
  they do not replay per-sample random parameters from earlier outputs.
- Unsupported FiftyOne label classes, 3D/media transforms, external-data
  transforms, and transforms with unsafe outputs are excluded from normal App
  choices.
- File-backed semantic segmentation masks are materialized as plugin-owned PNGs;
  detection instance masks and transformed heatmaps are stored in memory on
  generated samples.
- Polyline support uses vertex-based semantics rather than full polygon
  clipping. Heatmap support is limited to geometry-only target synchronization;
  mixed geometry + image-only color/intensity pipelines are blocked when
  heatmaps are selected.
- Cleaned runs keep `manifest.json` for auditability, so they remain visible in
  `View AlbumentationsX Run` but are hidden from cleanup suggestions.
- Successful or partial cleanup runs ask the FiftyOne App to reload the dataset
  so removed generated samples disappear without a manual browser refresh.
- The original `v0.1.0` release was source-install oriented. Current public
  tags should also publish the checksummed GitHub Release artifacts documented
  in [Release artifacts](release-artifacts.md).
- Manual FiftyOne App validation is still required before publishing the
  `v0.1.0` tag.

## Capability Report

The final catalog snapshot for this release is
[Capability Report v0.1.0](capability-report-v0.1.0.md):

- version key: `albumentationsx-2.3.8__albu-spec-0.0.6`
- total transforms: `134`
- normal MVP choices: `110`

Regenerate it with the release candidate check listed in
[Verification](verification.md#release-candidate-checks) when AlbumentationsX,
albu-spec, or catalog classification rules change.

## Automated Gate

Run the complete local gate from
[Verification](verification.md#complete-local-gate), then run the release
candidate capability check from
[Verification](verification.md#release-candidate-checks). Record the exact
results in the pull request and GitHub release notes.

## Manual FiftyOne App Gate

Validate from the final release branch before tagging:

1. Install dependencies with `uv sync --group dev`.
2. Point FiftyOne at this plugin checkout.
3. Create the deterministic demo dataset with
   `uv run python scripts/create_demo_dataset.py create --overwrite`.
4. Launch `albumentationsx-demo` in the FiftyOne App.
5. Select one or more samples.
6. Run `Augment with AlbumentationsX` with a non-dry geometry pipeline, such as
   `HorizontalFlip`.
7. Run `Augment with AlbumentationsX` again, select the previous run key, and
   confirm the form is prefilled from the saved pipeline config.
8. Confirm generated samples appear after the automatic App reload.
9. Confirm transformed supported annotations remain aligned with the generated
   images: detections and detection masks move with boxes, keypoints and
   polylines flip with the image, heatmap values remain spatially aligned, and
   segmentation masks preserve discrete regions.
10. Run `View AlbumentationsX Run` and confirm counts, versions, transform
   config, replay availability, selected annotation fields, runtime target
   requirements, and dropped annotation diagnostics are visible.
11. Run a second `Augment with AlbumentationsX` check with a selected `Heatmap`
   field and a mixed geometry + image-only color/intensity pipeline; confirm the
   operator rejects it before creating outputs.
12. Run `Delete AlbumentationsX Run` with confirmation checked.
13. Confirm generated samples and output files are gone, source samples and
   source files remain, and the cleaned run is not suggested for cleanup again.

## Git Tag Checklist

Before publishing:

1. Merge the tested MVP state from `dev` into `main` by pull request.
2. Create or align `release/v0.1.0` from the final `main` release candidate.
3. Keep release-only changes limited to version metadata, release notes,
   capability report updates, documentation, and validation fixes.
4. Run the automated and manual gates above from `release/v0.1.0`.
5. Merge `release/v0.1.0` back to `main`.
6. Merge the accepted release branch back to `dev` so release metadata does not
   diverge.
7. Tag the accepted release commit on `main`:

```bash
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

8. Publish GitHub release notes that link this page, the capability report, the
   attached install notes, and `SHA256SUMS`.

## Hotfix Pattern

For urgent fixes after `v0.1.0`, branch from the released `main` commit or
`v0.1.0` tag, validate the fix, merge it back to both `main` and `dev`, and tag
the patch as `v0.1.1`.

## Post-Release Follow-Up

- Broaden target-aware transform coverage beyond the MVP executable slice.
- Improve multi-step pipeline editing, previews, progress, and validation UX.
- Keep release artifacts and automation aligned with
  [Release artifacts](release-artifacts.md).
- Continue sending albu-spec bug fixes upstream instead of adding plugin-local
  workarounds.
