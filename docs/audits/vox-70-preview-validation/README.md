# VOX-70: preview aspect ratio validation

Issue: [VOX-70](https://linear.app/albumentations/issue/VOX-70).
Branch: `feature/vox-70-preview-aspect-ratio`, based on
`feature/vox-67-coco-ux-audit` at `7fb389d`, including VOX-68 and VOX-69.

Validated on 2026-09-09 with FiftyOne 1.19.0, AlbumentationsX 2.3.8 and
Python 3.12.13. The [original audit](../coco-ux-2026-09-09/README.md) measured a
427 × 640 portrait displayed at 320 × 240, and a 460 × 370 comparison displayed
at 640 × 300, both using `object-fit: fill`.

## Change

All three preview image views use automatic width/height, responsive maximum
width and a maximum height of `min(360px, 50vh)`, with `object-fit: contain`.
The public [`componentsProps` API](https://docs.voxel51.com/api/fiftyone.operators.types.html#fiftyone.operators.types.View)
applies the image/container styles. Intrinsic proportions are preserved, small
images are not enlarged, and the view does not crop image content.

Result schema generation reads actual images from `ctx.results`. Unused or
failed slots no longer render blank images, source fields or diagnostic editors.
The flat return payload retains its existing empty keys for compatibility.

The **Image display** note explains the existing comparison policy: each panel
is fitted independently, with padding when sizes differ. Displayed before/after
sizes therefore do not imply a common pixel scale. Backend pixels, annotations,
comparison labels and overlays are unchanged.

## Browser scenarios

Dataset: `vox-70-preview-layout-validation`, containing the real COCO image 48564
(427 × 640), a deterministic landscape image (960 × 320) and a square image
(400 × 400). All three annotation fields are checked: detections, instance masks
and keypoints. The synthetic samples contain boxes and keypoints.

- Desktop viewport **1920 × 936**, HorizontalFlip p=1, one selected COCO sample:
  preview=1, errors=0, exactly three images; no unused slots appear.
- Same viewport, HorizontalFlip p=1, all three samples: preview=3, errors=0,
  exactly nine images; portrait, landscape and square proportions pass.
- Same viewport, RandomResizedCrop p=1, size `(192, 320)`, all three samples:
  preview=3, errors=0. Outputs have natural size 320 × 192 and render at that size;
  each source retains its own proportions. The annotated comparison retains
  readable before/after labels and padding around the smaller panel.
- Laptop viewport **1366 × 768**, HorizontalFlip p=1, all three samples:
  preview=3, errors=0; all nine images pass ratio, size and horizontal-overflow
  assertions. Wide images shrink to the available dialog width.

For the laptop check, a temporary local harness embeds the real App in an iframe
whose viewport is exactly 1366 × 768. It uses an independent FiftyOne server and
forwards the App unchanged. The same read-only DOM assertion executes inside the
iframe and displays its measurements beneath it. This verifies actual App CSS
at the target viewport, without depending on native window resizing. The main
App remains available at `http://localhost:5154`.

Representative measurements (CSS pixels):

| Image | Natural size | Desktop rendered | Laptop rendered |
| --- | --- | --- | --- |
| COCO portrait | 427 × 640 | 240.1875 × 360 | 240.1875 × 360 |
| Portrait comparison | 460 × 370 | 447.5625 × 360 | 447.5625 × 360 |
| Landscape | 960 × 320 | 919.9922 × 306.6641 | 642.9844 × 214.3281 |
| Landscape comparison | 872 × 190 | 872 × 190 | 642.9922 × 140.1016 |
| Square | 400 × 400 | 360 × 360 | 360 × 360 |

Maximum aspect-ratio error is below **0.01 CSS pixels**, within layout rounding.
The independent source check confirms no generated samples, custom runs or run
storage were created, and the COCO labels remain identical to the audit source.
Existing technical result verbosity remains in VOX-74.

## Repeat the browser assertion

1. Open the App, select one or three samples and complete a preview.
2. Run [assert-preview-layout.js](assert-preview-layout.js) as an expression in
   the browser page/DevTools console after the images have loaded.
3. The assertion throws for missing images, aspect distortion over one pixel,
   cropping/stretching styles, enlargement, excessive height or horizontal
   overflow. It returns viewport and per-image measurements on success.
4. Repeat at desktop and laptop viewport sizes, and with a crop/resize output.
   A single successful sample must report `slots: 1`, not three empty slots.

The assertion reads rendered DOM only. Its saved results below come from the
live App, not a recreated HTML image component. Unit tests additionally cover
zero, one, three, sparse and missing-result slots, including legacy empty keys.

## Checks

- `uv sync --group dev` and `uv lock --check`: passed.
- Focused operator and preview visual checks: **69 passed**.
- Full `uv run pytest --cov-fail-under=85 -q --disable-warnings`:
  **374 passed**, coverage **89.47%**, 336.15 seconds, including the headless
  user-scenario smoke suite and VOX-68/69 regression coverage.
- `uv run pre-commit run --all-files`, separate Pyrefly, and `git diff --check`:
  passed. New evidence files are checked explicitly as well.

## Evidence

- [Portrait comparison](01-portrait-comparison.png)
- [Crop/resize comparison](02-crop-resize-comparison.png)
- [Laptop preview](03-laptop-preview.png)
- [Single portrait measurements](portrait-desktop.json)
- [Three formats on desktop](mixed-desktop.json)
- [Crop/resize measurements](crop-resize-desktop.json)
- [Three formats at 1366 × 768](mixed-laptop.json)
- [Source preservation and no-write checks](source-checks.json)
