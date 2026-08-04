# Fixed Transform Slice

VOX-10 implements the first executable augmentation path with a deliberately
small transform allowlist. This is not the final catalog model; it is the
end-to-end slice that proves the plugin can read FiftyOne image samples, execute
AlbumentationsX, write plugin-owned output files, and add new FiftyOne samples.

## Runtime Dependency

The plugin depends on `albumentationsx>=2.3,<3`. AlbumentationsX is installed
from the `albumentationsx` package, but the runtime API remains:

```python
import albumentations as A
```

The current lockfile resolves AlbumentationsX `2.3.7`. The fixed slice uses the
2.3 parameter names for `RandomBrightnessContrast`: `brightness_range` and
`contrast_range`.

## Supported Transforms

The temporary allowlist is:

- `HorizontalFlip`
- `RandomBrightnessContrast`
- `RandomCrop`

These three transforms cover the first important execution cases: geometric
image changes without resizing, pixel-level changes, and geometric crop output.
The full MVP should replace this allowlist with an albu-spec-backed dynamic
pipeline rather than growing the fixed list by hand.

## Operator Parameters

- `pipeline_step_count`: number of ordered transform steps, from `1` to `3`;
  defaults to `1`.
- `transform`: step 1 transform, one of the three fixed transform names;
  defaults to `HorizontalFlip`.
- `p`: step 1 transform probability, from `0.0` to `1.0`; defaults to
  `1.0` for deterministic manual checks.
- `step_2_transform` / `step_3_transform`: optional additional ordered step
  transforms when `pipeline_step_count` is `2` or `3`.
- `step_2_p` / `step_3_p`: transform probability for later steps.
- `outputs_per_sample`: number of augmented samples to create per source sample,
  from `1` to `3`; defaults to `1`.
- `brightness_range`: mapped to
  step 1 `RandomBrightnessContrast(brightness_range=(min, max))`; defaults
  to `[-0.2, 0.2]`.
- `contrast_range`: mapped to
  step 1 `RandomBrightnessContrast(contrast_range=(min, max))`; defaults to
  `[-0.2, 0.2]`.
- `width` and `height`: mapped to step 1
  `RandomCrop(width=..., height=...)`; both default to `32`.
- Later-step transform parameters use the same names with the step prefix, such
  as `step_2_brightness_range`, `step_2_height`, and `step_3_width`.
- `dry_run`: validates selection and parameters without writing output files or
  creating samples.

The fixed form intentionally renders only parameters that the fixed executor
uses. Extra albu-spec parameters such as `pad_if_needed`, `border_mode`,
`brightness_by_max`, and `ensure_safe_output` stay hidden until the catalog-wide
pipeline path can execute them faithfully.

For compatibility with the original fixed form, the runner also accepts
`brightness_range_min`, `brightness_range_max`, `contrast_range_min`,
`contrast_range_max`, `crop_width`, and `crop_height`.

VOX-13 renders these fields from albu-spec schemas. VOX-14 moved transform
construction and replay execution behind the shared catalog-driven pipeline
factory. VOX-22 lets the FiftyOne execution UI build an ordered chain from the
three fixed transforms.

## Output Behavior

Source samples, source image files, and source annotations are left unchanged.
A successful execution creates new image files under:

```text
~/.fiftyone/albumentationsx-plugin/<dataset-name>/<run-key>/images/
```

Each created FiftyOne sample is tagged with `albumentationsx-output` and
`albumentationsx-run:<run-key>`. It also stores provenance fields for the source
sample ID, run key, output tag, and transform summary.

VOX-26 copies supported classification labels and transforms supported
`Detections`, `Keypoints`, and in-memory `Segmentation` masks through
Albumentations target APIs for the fixed execution path. Unsupported label
fields are excluded from output samples and recorded in run annotation metadata
with a reason.

VOX-15 saves each non-dry execution under the run directory as `manifest.json`
and registers a FiftyOne custom run. The manifest records versions, source IDs,
created sample IDs, relative output paths, replay records, counters, structured
errors, run annotation fields, and per-output dropped target counts when
Albumentations removes boxes, points, or masks. Dry runs still avoid writing
output files or run metadata.

Static parameter errors fail before writing output files when possible. Runtime
per-sample errors, such as a `RandomCrop` larger than one selected image, are
reported in the operator summary while allowing other selected samples to
complete.

## Verification

Use the complete local gate in [Verification](verification.md). For manual App
verification, create the demo dataset, launch the App, run
`Augment with AlbumentationsX`, and inspect that new output samples appear while
the original samples keep their original filepaths and tags.
