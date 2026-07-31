"""Host-neutral input schema for the augmentation workflow."""

from __future__ import annotations

from albumentationsx_plugin.core.contracts import FieldKind, FormFieldSchema


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
            choices=("HorizontalFlip",),
            help_text="Temporary transform selector until catalog integration is implemented.",
        ),
        FormFieldSchema(
            name="outputs_per_sample",
            kind=FieldKind.INTEGER,
            label="Outputs per sample",
            required=True,
            default=1,
            min_value=1,
            max_value=1,
            help_text="Number of augmented samples to create for each source sample.",
        ),
        FormFieldSchema(
            name="dry_run",
            kind=FieldKind.BOOLEAN,
            label="Dry run",
            default=True,
            help_text="Preview the configuration without creating output samples.",
        ),
    )
