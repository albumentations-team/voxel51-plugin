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
The full MVP should replace this allowlist with albu-spec-backed catalog and
form generation rather than growing the fixed list by hand.

## Operator Parameters

- `transform`: one of the three fixed transform names.
- `p`: transform probability, from `0.0` to `1.0`.
- `outputs_per_sample`: number of augmented samples to create per source sample,
  from `1` to `3`.
- `brightness_range_min` and `brightness_range_max`: mapped to
  `RandomBrightnessContrast(brightness_range=(min, max))`.
- `contrast_range_min` and `contrast_range_max`: mapped to
  `RandomBrightnessContrast(contrast_range=(min, max))`.
- `crop_width` and `crop_height`: mapped to `RandomCrop(width=..., height=...)`.
- `dry_run`: validates selection and parameters without writing output files or
  creating samples.

The form is flat because dynamic catalog-driven parameter rendering is a later
task.

## Output Behavior

Source samples and source image files are left unchanged. A successful execution
creates new image files under:

```text
~/.fiftyone/albumentationsx-plugin/<dataset-name>/<run-key>/images/
```

Each created FiftyOne sample is tagged with `albumentationsx-output` and
`albumentationsx-run:<run-key>`. It also stores provenance fields for the source
sample ID, run key, output tag, and transform summary.

Static parameter errors fail before writing output files when possible. Runtime
per-sample errors, such as a `RandomCrop` larger than one selected image, are
reported in the operator summary while allowing other selected samples to
complete.

## Verification

Use the complete local gate in [Verification](verification.md). For manual App
verification, create the demo dataset, launch the App, run
`Augment with AlbumentationsX`, and inspect that new output samples appear while
the original samples keep their original filepaths and tags.
