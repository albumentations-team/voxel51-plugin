# Recording the AlbumentationsX demonstrations

This is the recording and publishing checklist for the next documentation media
revision. The six GIFs currently committed are real App captures; the recordings
below will replace them with clearer pacing and add error recovery. They have
not been recorded yet. Keep both existing pull requests in **Draft**.

## Deliverables and priorities

Record one continuous, chaptered overview video (about 90–120 seconds) and export
short clips from separate takes. Use the video for an optional PR walkthrough;
place each GIF after the corresponding instructions in the documentation.
One clip should answer one user question. A reader must also be able to follow
the text without playing any media.

| Priority | File | Target length | What the viewer should learn | Documentation placement |
| --- | --- | --- | --- | --- |
| Required | `preview.gif` | 10–14 s | Select a source and see image and labels flip together | Quickstart, after preview steps |
| Required | `edit-pipeline.gif` | 14–18 s | Add, reorder, and edit stages; see the changed result | Build and edit a pipeline |
| Required | `create-outputs.gif` | 12–18 s | Validate first, then create and inspect one persistent output | Quickstart, after creation steps |
| Required | `save-reuse.gif` | 12–18 s | Save a named pipeline, load a copy, and edit it | Save and share pipelines |
| Required | `share-pipeline.gif` | 14–20 s | Export the complete JSON and import it in another environment | Export and import |
| Required | `inspect-run.gif` | 10–14 s | Understand run counters and open generated samples | Run history |
| Required | `validation-error.gif` | 14–20 s | Read a crop error, correct it, and get a successful preview | Correct an invalid crop |
| Required | `cleanup.gif` | 12–16 s | Review exactly what will be deleted and recover the source view | Cleanup and data safety |
| Advanced | `partial-run.gif` | 18–25 s | Inspect an execution failure and retry the intended sources | Inspect and retry a partial or failed run |
| Optional | `annotation-compatibility.gif` | 12–18 s | Resolve a heatmap compatibility conflict explicitly | Supported annotations |
| Required | `overview.mp4` | 90–120 s | Follow one coherent preview → edit → validate → create → reuse → history → cleanup workflow, including correction of a crop error | Collapsed PR walkthrough or plain video link |

The eight required GIFs cover the user-facing workflows and a reproducible error.
Add the advanced partial-run clip only when its failure can be reproduced and
explained honestly. Do not delay the other recordings for that fixture.

## Prepare an attractive, reproducible COCO dataset

Work from the plugin checkout in the environment that runs FiftyOne. The helper
downloads only three selected JPEGs, with real instance masks and official person
keypoints. The official annotations archive is approximately 241 MiB; reuse an
existing copy when available.

```bash
uv sync --group dev
mkdir -p sample_data/generated/coco
curl -fL \
  https://s3.us-east-1.amazonaws.com/images.cocodataset.org/annotations/annotations_trainval2017.zip \
  -o sample_data/generated/coco/annotations_trainval2017.zip

uv run --with pycocotools==2.0.11 python scripts/create_coco_acceptance.py \
  --annotations sample_data/generated/coco/annotations_trainval2017.zip \
  --data-dir sample_data/generated/coco/images \
  --recording-only
```

Keep the printed dataset name and baseline JSON path. The helper chooses a new
dataset name automatically and refuses to overwrite an existing named dataset.
Open that name in the same database used by your App:

```bash
# Replace DATASET_NAME with the name printed by the helper
uv run fiftyone app launch DATASET_NAME
```

Verify that `@albumentations/albumentationsx` is enabled in this environment.
Use the surfer (COCO 378116) as the recurring main subject, with the cyclist
(261888) and outdoor portrait (130586) visible in the source grid. Select
`detections` and `keypoints`. Show readable boxes and skeletons; turn on masks
for the annotation demonstration if they obscure the main subject in other takes.
Keep the photo attribution in [the media README](media/README.md#dataset-and-attribution).

Use a dedicated recording dataset and plugin storage. Before each take, restore
the three-source view, clear old selections, and clean up only the test runs you
created. Use **Run history** cleanup, preserving the original photographs and
annotations. Rehearse the complete take before recording.

## Capture settings

- Capture the real App at 24–30 fps, preferably at 1440 × 1000 or higher.
  Store raw takes and editing projects in ignored `docs/media/source/`.
- Use one App theme throughout, readable UI text, a stable browser size, and
  a clean desktop. Dismiss banners and notifications before the take.
- Frame the active controls and the resulting image together when possible.
  Avoid a tall crop dominated by empty dialog space. Use a deliberate cut or
  gentle pan between controls and results when both cannot remain legible.
- Keep the cursor visible, move it deliberately, and use a subtle click highlight.
  Pause briefly over the control before clicking. Avoid rapid pointer circling.
- Use short English captions for each step, outside important UI content.
  For example: “Select one source”, “Preview without saving”, “Labels flip
  with the image”. A single static caption for the entire take is insufficient.
- Wait for dynamic selectors to finish loading before choosing a value. Do not
  publish transient blank controls or “Required property” errors unless the
  clip is deliberately explaining that error.
- Keep final results still for at least 2–3 seconds. For an error, allow enough
  time to read the cause before showing the correction.

## Shot-by-shot plans

Times are approximate editing targets, not a demand to fit slow UI operations
into a fixed duration. Shorten the take or split the topic when text becomes
unreadable. Each recording must include the actual final App state.

### 1. Preview

1. **0–2 s:** show the three photos; select the surfer. Caption: “Select one source”.
2. **2–5 s:** show `HorizontalFlip`, probability 1, and the selected label fields.
3. **5–7 s:** choose **Preview**, then submit. Trim the loading interval.
4. **7–11 s:** hold the annotated before/after view; briefly point to a matching
   box or joint. Caption: “Image and labels flip together”.
5. End with the result visible. The accompanying text explains that preview
   creates no files, samples, or history record.

### 2. Edit and reorder

1. Show the existing flip stage, then add `RandomBrightnessContrast`.
2. Put brightness first using **Execution order**. Set brightness limits to
   `[0.3, 0.3]`, contrast limits to `[0, 0]`, and its probability to 1.
3. Set flip probability to 0. Caption: “Keep a stage without applying it”.
4. Preview and hold the visibly brighter, unflipped image for 3 seconds.
5. Use **Back to editor**, briefly show that order and probability were retained.
   If showing the second preview with flip enabled would exceed 18 seconds,
   include that comparison in the overview video instead.

### 3. Validate and create

1. Show one selected source and one output per sample, with flip probability 1.
2. Choose **Validate without creating samples**; hold the successful result.
3. Return and choose **Create augmented samples**. Caption: “Create one output”.
4. Trim processing, then show the created count and open the generated sample.
5. Hold the augmented image and labels for 3 seconds. Show its provenance in the
   overview video if it would make the GIF too long.

### 4. Save and reuse

1. Save the pipeline as a new entry named **Surf and light**.
2. Open **Saved pipelines → Inspect saved pipelines** and select that entry.
3. Wait for the selection to resolve, then use **Edit a copy of this pipeline**.
4. Change the flip probability and hold the editable configuration.
   Caption: “Editing a copy keeps the saved original unchanged”.

### 5. Share through JSON

1. Use **Export saved pipeline** and show **Importable pipeline JSON**.
2. Copy the complete object, then cut to another recording environment with
   the same plugin version and dataset fields. Caption: “Import in another environment”.
3. Choose **Import saved pipeline → Paste full JSON**, paste, and submit.
4. Open the imported entry and show its name and stages. Keep clipboard text,
   tokens, and unrelated windows out of the recording.

Do not silently overwrite a preset for a staged round trip. If demonstrating
import in the same storage instead, show the duplicate-ID message and the
explicit **Overwrite existing saved pipeline** choice, and explain it in the
caption. The exported ID is retained; a new display name does not change it.

### 6. History

1. Select the just-created run in **Run history**.
2. Hold its outcome, created/error counts, scope, and transform summary long
   enough to read. Use one output per source to keep the example obvious.
3. Choose **Open generated samples** and hold the actual output view.
4. Put **Use pipeline from this run** in the overview or another take if adding
   it would leave insufficient time to inspect the counters.

### 7. Crop error and correction

1. On one selected COCO source, choose **Validate without creating samples**,
   then configure `RandomCrop` with width and height 1024 and **Pad if needed**
   disabled. These images are smaller than the crop.
2. The helper supplies image metadata, so the form can highlight the invalid
   dimensions and disable submission immediately. Hold the real inline error
   for 3 seconds. Caption: “The crop exceeds the source size”.
3. Enable **Pad if needed** or reduce dimensions to fit, showing the changed
   control clearly. If a different dataset instead returns a server-side
   validation error, use **Back to editor** before making that correction.
4. Submit validation successfully, then preview and hold the corrected result.
   Caption: “Correct the pipeline before creating outputs”.

This is a preflight error: no samples or history record are created. It must
not be presented as a partial run or as a failed source that can be opened
from history.

### 8. Cleanup

Use a finished demo run; cleanup does not stop an active worker.

1. Select the demo run and choose **Review deletion of generated outputs**.
2. Hold the run identity, sample/file counts, and output scope for 3 seconds.
3. Confirm once. Trim processing, then show the actual deletion result.
4. Close the result and remove the output-only **Select** stage. Hold the three
   original COCO photographs. Caption: “Original samples remain unchanged”.

Keep confirmation and scope visible even when redacting a personal path. Do not
remove the confirmation step for pacing.

### 9. Optional advanced failure and retry

Use a separate copy of the recording dataset. A missing input or oversized crop
detected during preparation rejects the whole operation and cannot demonstrate
a partial run. Use a reproducible, controlled output-stage fault fixture that
allows one output to succeed and subsequent attempts to fail. Record the fixture,
affected stage, and reset instructions with the take; label the capture
“Simulated output failure” if the failure is injected.

Show the real partial outcome and counters, **Open failed source samples**, the
reported cause, its correction, and **Use pipeline from this run**. Review a
scope containing only those sources, validate, then create and inspect the new
run. Use one output per source. The retry creates a separate run with fresh
randomness; it is not a resume operation. Keep successful earlier outputs
visible when explaining what is retained. Never fabricate errors or counters
in an image editor. If no repeatable fixture is available, omit this clip and
retain the documented recovery steps.

### 10. Optional annotation compatibility

Use the separate fixture described in the media README: COCO labels plus derived
polylines and an illustrative heatmap. Show the mixed flip/color conflict with
the heatmap selected, uncheck **heatmap**, then hold the successful preview.
State that the heatmap is omitted from outputs. Identify the additional labels
as fixtures rather than original COCO annotations.

### Overview video chapters

Use the same source and named pipeline throughout. Suggested chapters:
**0:00** select and preview; **0:15** edit and reorder; **0:30** correct a crop
error; **0:45** validate and create; **1:00** save/reuse and share; **1:20** inspect
history; **1:35** review cleanup and return to sources. Adjust timestamps after
editing. English captions are required; clear English narration is optional.
Supply an English caption file if the video includes narration.

## Edit and export

Cut idle waiting at state boundaries, keeping a brief loading cue where needed
to explain the transition. Use a short dissolve only if it improves continuity;
do not cross-fade important values into each other. Keep normal-speed clicks,
typing, error reading, and results. Do not accelerate the entire recording to
reach a duration target. A final result visible for a fraction of a second is
not a usable demonstration.

Export the overview as H.264 MP4 with a broadly compatible pixel format
(`yuv420p`). Keep a high-quality master. For GIFs, start at 12–15 fps and a width
of 900–1100 pixels; adjust the crop, palette, and duration to keep each under
5 MiB while preserving readable labels. Open the export at the documentation's
480-pixel display width and at full size. If the text becomes too small, crop
closer or split the clip. Do not reduce resolution until the result is unreadable.

The existing `scripts/export_demo_media.py` reproduces the **old single-master**
captures, with a fixed portrait crop, 8 fps, and one caption per clip. It does
not automatically support new masters, changing crops, or step captions. Export
new takes from your editor or deliberately adapt the exporter and manifest;
do not reuse the old timestamps against unrelated footage.

For each replacement, update `docs/media/capture.json` with the source file/hash,
runtime versions and commit, dataset, crop, cuts, captions, export settings,
actual encoded duration, dimensions, and final SHA256. Keep the record of any
unchanged assets accurate. Update the media README's asset table and attribution.
Raw footage and the overview MP4 stay under ignored `docs/media/source/`; the
repository's general 500 KiB file limit is unchanged, with a GIF-only exception.

## Add the media to the existing pull requests

### A. Plugin PR #75

Work in the existing plugin checkout. Check for unrelated local changes first;
do not discard them. Use the existing branch:

```bash
git status --short
git switch feature/release-docs-and-demos
```

1. Replace the six existing GIFs in `docs/media/` using their current filenames.
   Add `share-pipeline.gif` and `validation-error.gif`; add optional clips only
   when recorded and reviewed. Do not commit raw videos or editing projects.
2. Update `docs/media/README.md` and `capture.json`. Preserve COCO attribution.
3. In `docs/albumentationsx-fiftyone-integration.md`, place each clip after its
   steps, with descriptive alt text, an English caption, and a full-size link.
   The current media URLs are pinned to a commit: replacing local files alone
   will **not** update those images. Commit and push the assets first, obtain
   the full media commit with `git rev-parse HEAD`, then update the raw image
   URLs to that commit in a follow-up documentation commit.
4. Update `docs/fiftyone-integration.rst` in the same change. Use upstream image
   paths as shown below. Do not add placeholders for unrecorded clips.
5. Run the relevant checks and push to the existing PR branch:

```bash
uv run pre-commit run --all-files
uv run pytest tests/unit/test_documentation.py tests/unit/test_release_artifacts.py -q
git add docs/media docs/albumentationsx-fiftyone-integration.md docs/fiftyone-integration.rst
git diff --cached --stat
git commit -m "Refresh COCO workflow demonstrations"
git push origin feature/release-docs-and-demos
```

For the two-commit media pinning flow, stage only assets for the first commit,
then the text changes for the second. Review `git diff --cached` before each
commit. This updates [plugin PR #75](https://github.com/albumentations-team/voxel51-plugin/pull/75)
automatically; do not create a replacement PR.

### B. FiftyOne PR #8471

Use the existing FiftyOne checkout and `docs/albumentationsx-integration` branch.
Copy the maintained RST page to `docs/source/integrations/albumentations.rst` and
the referenced GIFs/screenshots to `docs/source/images/integrations/albumentationsx/`.
The push remote for the existing branch is `fork` (`borodinlabs/fiftyone`).
Confirm that remote with `git remote -v` in your FiftyOne checkout before pushing.
Keep the plugin recording guide and capture manifest in the plugin
repository, outside the upstream documentation change.

Use a figure below the relevant steps:

```rst
.. figure:: /images/integrations/albumentationsx/validation-error.gif
    :alt: Correct an oversized crop and preview the padded result.
    :width: 480px

    Correct an oversized crop before creating outputs. Select the image to
    view it at full size.
```

Preserve the existing page URL and all ten legacy `albumentations-*` anchors.
Keep the plugin's RST and the upstream copy identical. In the FiftyOne checkout,
build the page using its documented preview setup:

```bash
bash docs/preview_page.bash docs/source/integrations/albumentations.rst
sphinx-build -W -b html docs/build/preview docs/build/preview/_build
git diff --check
git add docs/source/integrations/albumentations.rst \
  docs/source/images/integrations/albumentationsx
git diff --cached --stat
git commit -m "Clarify AlbumentationsX workflow demonstrations"
git push fork docs/albumentationsx-integration
```

This updates [FiftyOne PR #8471](https://github.com/voxel51/fiftyone/pull/8471).
Do not change its base branch or move it out of Draft. CI can continue running;
record outstanding checks without waiting for every job to finish.

### C. Add the overview video to the PR description

Keep the opening description short: problem, changed behavior, publication
dependency, validation, and links. Do not restore a full-height inline GIF.
In GitHub's PR description editor, drag the reviewed `overview.mp4` from the
local source directory into the text field. Wait for the upload to complete,
then keep the returned attachment URL as a plain link or inside a collapsed
section. Preview the description before saving:

```markdown
<details>
<summary>Optional COCO walkthrough (about two minutes)</summary>

[Watch the walkthrough](PASTE_THE_COMPLETED_GITHUB_UPLOAD_URL_HERE)

Preview, pipeline editing, crop-error recovery, creation, saved pipelines,
history, and cleanup. Idle processing has been shortened.

</details>
```

An uploaded PR attachment is a reviewer aid. The upstream page should use its
checked-in GIFs and text; do not introduce a temporary local or private video
URL into the public documentation. If GitHub rejects the video size, shorten
or compress the MP4 and retry; do not add a large binary to the repository to
work around an upload limit.

## Final review checklist

- [ ] The subject, chosen fields, pipeline settings, and captions agree with the text.
- [ ] Each clip shows an action and a readable result, including error correction.
- [ ] Waits are shortened; useful reading time and the cleanup confirmation remain.
- [ ] Results, errors, and counters come from the real App; any injected failure is disclosed.
- [ ] Personal paths are removed or clearly redacted without covering scope or outcomes.
- [ ] Sources and annotations still match the helper's baseline after creation/cleanup.
- [ ] Encoded durations, dimensions, hashes, versions, and credits match the final files.
- [ ] All GIFs are below 5 MiB and readable at normal documentation width.
- [ ] The rendered page loads every image, has no horizontal overflow at 390 px,
      and provides useful text without animation.
- [ ] Both RST copies match, all legacy anchors remain, and pinned Markdown URLs
      resolve to the new media commit.
- [ ] Updated desktop/mobile page screenshots and short PR descriptions match the page.
- [ ] Both PRs remain Draft; the matching release and installation links remain
      publication gates. Rebuild affected release artifacts if packaged docs changed.
