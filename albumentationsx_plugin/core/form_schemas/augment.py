"""Host-neutral input schema for the augmentation workflow."""

from __future__ import annotations

from albumentationsx_plugin.core.contracts import (
    DEFAULT_BRIGHTNESS_RANGE,
    DEFAULT_CONTRAST_RANGE,
    DEFAULT_CROP_SIZE,
    DEFAULT_TRANSFORM_PROBABILITY,
    FIXED_TRANSFORM_NAMES,
    MAX_OUTPUTS_PER_SAMPLE,
    FieldKind,
    FormFieldSchema,
)


def build_augment_form_schema() -> tuple[FormFieldSchema, ...]:
    """Build the current MVP input schema for augmentation configuration.

    The schema is intentionally fixed for now. Later backend tasks will replace
    the transform selector and parameter fields with albu-spec generated data.
    """

    return (
        FormFieldSchema(
            name="transform",
            kind=FieldKind.ENUM,
            label="Transform",
            required=True,
            default="HorizontalFlip",
            choices=FIXED_TRANSFORM_NAMES,
            help_text="Temporary transform selector until catalog integration is implemented.",
        ),
        FormFieldSchema(
            name="p",
            kind=FieldKind.FLOAT,
            label="Probability",
            required=True,
            default=DEFAULT_TRANSFORM_PROBABILITY,
            min_value=0.0,
            max_value=1.0,
            help_text="Probability passed to the selected Albumentations transform.",
        ),
        FormFieldSchema(
            name="outputs_per_sample",
            kind=FieldKind.INTEGER,
            label="Outputs per sample",
            required=True,
            default=1,
            min_value=1,
            max_value=MAX_OUTPUTS_PER_SAMPLE,
            help_text="Number of augmented samples to create for each source sample.",
        ),
        FormFieldSchema(
            name="brightness_range_min",
            kind=FieldKind.FLOAT,
            label="Brightness min",
            default=DEFAULT_BRIGHTNESS_RANGE[0],
            min_value=-1.0,
            max_value=1.0,
            help_text="Lower brightness_range value used by RandomBrightnessContrast.",
        ),
        FormFieldSchema(
            name="brightness_range_max",
            kind=FieldKind.FLOAT,
            label="Brightness max",
            default=DEFAULT_BRIGHTNESS_RANGE[1],
            min_value=-1.0,
            max_value=1.0,
            help_text="Upper brightness_range value used by RandomBrightnessContrast.",
        ),
        FormFieldSchema(
            name="contrast_range_min",
            kind=FieldKind.FLOAT,
            label="Contrast min",
            default=DEFAULT_CONTRAST_RANGE[0],
            min_value=-1.0,
            max_value=1.0,
            help_text="Lower contrast_range value used by RandomBrightnessContrast.",
        ),
        FormFieldSchema(
            name="contrast_range_max",
            kind=FieldKind.FLOAT,
            label="Contrast max",
            default=DEFAULT_CONTRAST_RANGE[1],
            min_value=-1.0,
            max_value=1.0,
            help_text="Upper contrast_range value used by RandomBrightnessContrast.",
        ),
        FormFieldSchema(
            name="crop_width",
            kind=FieldKind.INTEGER,
            label="Crop width",
            default=DEFAULT_CROP_SIZE,
            min_value=1,
            max_value=4096,
            help_text="Output width used by RandomCrop.",
        ),
        FormFieldSchema(
            name="crop_height",
            kind=FieldKind.INTEGER,
            label="Crop height",
            default=DEFAULT_CROP_SIZE,
            min_value=1,
            max_value=4096,
            help_text="Output height used by RandomCrop.",
        ),
        FormFieldSchema(
            name="dry_run",
            kind=FieldKind.BOOLEAN,
            label="Dry run",
            default=False,
            help_text="Preview the configuration without creating output samples.",
        ),
    )
