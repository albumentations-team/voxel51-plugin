# Demonstration recordings

These clips show the actual FiftyOne 1.19 App running the 0.1.2 release candidate.
They use COCO photographs, real instance masks, and official person keypoints.
The UI is not a mockup. Text, captions, and the surrounding documentation are English.

For the next recording pass, follow the
[recording guide](../recording-guide.md): shot-by-shot COCO scenarios, error
recovery, pacing, export settings, and updates to both existing draft PRs.
The current clips below have not yet been replaced by those planned recordings.

## Current assets

| Clip | Duration | Size |
| --- | --- | --- |
| [preview.gif](preview.gif) | 11.26 s | 2.67 MiB |
| [edit-pipeline.gif](edit-pipeline.gif) | 15.13 s | 3.78 MiB |
| [create-outputs.gif](create-outputs.gif) | 17.01 s | 2.30 MiB |
| [save-reuse.gif](save-reuse.gif) | 23.76 s | 3.44 MiB |
| [inspect-run.gif](inspect-run.gif) | 11.38 s | 2.84 MiB |
| [cleanup.gif](cleanup.gif) | 14.38 s | 1.49 MiB |

Durations are measured from the encoded GIF frame delays.

The GIFs loop without audio. Captions explain each action; the guide provides
text instructions alongside every clip. All exports are below 5 MiB. The 500 KiB
repository limit still applies to other files; a narrow hook permits these GIFs.
The runtime ZIP and wheel exclude media and recording tools.

## Additional screenshots

- [Compatibility warning](compatibility-warning.png): the COCO surfer with
  mask-derived polylines and a synthetic gradient heatmap. The mixed flip/color
  pipeline is blocked while heatmap is selected.
- [Resolved annotation preview](annotation-preview.jpg): uncheck heatmap and
  preview the remaining detections, masks, keypoints, and polylines. No output
  samples or files are created.

These captures use a separate copy of the three source images. Their derived
polylines and heatmap are illustrative fixtures, not original COCO annotations.

## Documentation page preview

The styled upstream preview was reviewed at [desktop width](page-preview-desktop.jpg)
and [390 px width](page-preview-mobile.jpg). These are contributor review assets;
they are not part of the upstream page or runtime ZIP.

## Dataset and attribution

The dedicated recording dataset contains three COCO 2017 validation images,
10 nonempty instance masks, three person poses, and six missing joints.
COCO metadata identifies these photographs as
[Creative Commons Attribution 2.0](https://creativecommons.org/licenses/by/2.0/).
Photo rights remain with their original creators. The source metadata does not
supply creator names; the original Flickr image references are retained below.

| COCO image | Subject | Original source |
| --- | --- | --- |
| 130586 | Person outdoors | [Flickr photograph](https://farm4.staticflickr.com/3587/3392836274_5d866f582b_z.jpg) |
| 261888 | Cyclist | [Flickr photograph](https://farm5.staticflickr.com/4079/4918743472_0b684750c4_z.jpg) |
| 378116 | Surfer | [Flickr photograph](https://farm6.staticflickr.com/5150/5619719330_f8c8934184_z.jpg) |

Images and annotations were obtained from the
[official COCO downloads](https://cocodataset.org/#download). The recordings show
transformed versions, annotation overlays, and crops of the App. The separate
12-image acceptance suite is not the public recording dataset.

## Capture and verification

See [capture.json](capture.json) for exact source/asset SHA256 hashes, runtime
file hashes, versions, cuts, dimensions, and timestamps. The pipeline has no
fixed seed; the demonstrated settings use deterministic flip probabilities and
fixed brightness/contrast ranges.

- **Preview:** selected surfer, HorizontalFlip p=1, detections and keypoints checked.
- **Edit:** add RandomBrightnessContrast; move it before HorizontalFlip; set
  brightness to [0.3, 0.3], contrast to [0, 0], and flip p=0. Preview and return.
  The editor retains the two stages, their order, and zero probability.
- **Create:** load the saved configuration, change flip p to 1, create one output,
  open its generated-sample view, and close the result dialog.
- **Save/reuse:** save “Surf and light”, select it in Saved pipelines, wait for the
  form to refresh, load an independent copy, and edit its flip probability.
- **History:** inspect completed counters and parameters, open outputs, and load
  the run's pipeline with fresh execution settings.
- **Cleanup:** review one generated sample/file, confirm deletion, inspect success,
  and remove the output-only view stage to reveal the three original sources.

Source file hashes and full serialized detections/keypoints were identical after
App creation and cleanup. The 12-image backend acceptance independently checked
131 masks, 33 poses, missing-joint positions, and source preservation.

Cuts remove idle setup time. The cleanup export covers the local storage path
with a labeled redaction; result counters and confirmation remain visible.
No other UI content or outcome was replaced. Raw recordings contain local paths
and remain in the ignored `source/` directory for local review, outside releases.

## Reproduce the current exports

Create the recording subset with the helper in
[COCO acceptance](../demo-dataset.md#coco-acceptance), adding `--recording-only`.
Launch the plugin in that dataset, use a 1440 × 1000 browser viewport and dark
App theme, dismiss promotional UI, and follow the scenarios above. Wait for a
changed source selector to finish resolving before pressing its load button.

The local master is `source/capture-source.webm`. Export the recorded cuts with:

```bash
uv run --with imageio-ffmpeg==0.6.0 python scripts/export_demo_media.py \
  --source docs/media/source/capture-source.webm \
  --manifest docs/media/capture.json \
  --font /System/Library/Fonts/Supplemental/Arial.ttf \
  --output-dir docs/media
```

On another platform, pass a readable TrueType font path. The exporter uses a
784 × 952 crop, a 42-pixel caption band, 8 fps, a 160-color per-clip palette,
and Bayer dithering. Inspect playback and labels after any recapture or font
change, then refresh the hashes and commit the reviewed exports.
New recordings need their own source/cut metadata and step captions; this
fixed-crop exporter is not a general editor for the new storyboards.
