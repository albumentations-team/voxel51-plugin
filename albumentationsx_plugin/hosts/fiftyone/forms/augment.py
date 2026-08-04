"""Build FiftyOne operator forms from catalog-backed neutral schemas."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

import fiftyone.operators.types as types

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.parameters import AlbuSpecParameterSchemaProvider
from albumentationsx_plugin.core import (
    DEFAULT_BRIGHTNESS_RANGE,
    DEFAULT_CONTRAST_RANGE,
    DEFAULT_CROP_SIZE,
    DEFAULT_TRANSFORM_PROBABILITY,
    FIXED_TRANSFORM_NAMES,
    MAX_OUTPUTS_PER_SAMPLE,
    MAX_PIPELINE_STEPS,
    PIPELINE_STEP_COUNT_FIELD_NAME,
    CapabilityStatus,
    FieldKind,
    FormFieldSchema,
    JSONValue,
    ParameterSchemaProvider,
    TransformCatalogProvider,
    UnsupportedTransformError,
    pipeline_step_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.forms.defaults import RandomCropDefaults, build_random_crop_defaults
from albumentationsx_plugin.hosts.fiftyone.forms.guidance import TransformGuidance, build_transform_guidance
from albumentationsx_plugin.hosts.fiftyone.forms.renderer import FiftyOneFormRenderer

SCHEMA_STATUS_JSON_FALLBACK: Final[str] = "json_fallback"
TRANSFORM_FIELD_NAME: Final[str] = "transform"
PROBABILITY_FIELD_NAME: Final[str] = "p"
OUTPUTS_PER_SAMPLE_FIELD_NAME: Final[str] = "outputs_per_sample"
DRY_RUN_FIELD_NAME: Final[str] = "dry_run"
DEFAULT_DYNAMIC_TRANSFORM_NAME: Final[str] = "HorizontalFlip"
PIPELINE_STEP_COUNT_LABEL: Final[str] = "Pipeline steps"
RANDOM_CROP_TRANSFORM_NAME: Final[str] = "RandomCrop"
GENERAL_SECTION_FIELD_NAME: Final[str] = "_general_settings"
STAGE_SECTION_FIELD_PREFIX: Final[str] = "_pipeline_stage"
TARGET_GUIDANCE_FIELD_NAME: Final[str] = "_target_compatibility"
FIXED_SLICE_PARAMETER_NAMES: Final[dict[str, tuple[str, ...]]] = {
    "HorizontalFlip": (PROBABILITY_FIELD_NAME,),
    "RandomBrightnessContrast": ("brightness_range", "contrast_range", PROBABILITY_FIELD_NAME),
    RANDOM_CROP_TRANSFORM_NAME: ("height", "width", PROBABILITY_FIELD_NAME),
}


@dataclass(frozen=True, slots=True)
class DynamicAugmentFormBuilder:
    """Compose a FiftyOne augment form from backend catalog and schema services."""

    catalog_provider: TransformCatalogProvider = field(default_factory=AlbuSpecCatalogProvider)
    parameter_schema_provider: ParameterSchemaProvider = field(default_factory=AlbuSpecParameterSchemaProvider)
    renderer: FiftyOneFormRenderer = field(default_factory=FiftyOneFormRenderer)

    def build(self, ctx: Any | None) -> types.Object:
        """Build the current operator input object for the selected transform."""

        params = _ctx_params(ctx)
        supported_transform_names = self._executable_transform_names()
        selected_step_count = _selected_step_count(params.get(PIPELINE_STEP_COUNT_FIELD_NAME))
        random_crop_defaults = build_random_crop_defaults(ctx)

        inputs = types.Object()
        self._render_general_settings(inputs, selected_step_count)
        for step_number in range(1, selected_step_count + 1):
            self._render_stage_header(inputs, step_number)
            selected_transform_name = _selected_transform_name(
                params.get(pipeline_step_field_name(step_number, TRANSFORM_FIELD_NAME)),
                supported_transform_names=supported_transform_names,
                step_number=step_number,
            )
            self._render_transform_selector(
                inputs,
                supported_transform_names=supported_transform_names,
                selected_transform_name=selected_transform_name,
                step_number=step_number,
            )
            self._render_transform_guidance(inputs, selected_transform_name, step_number=step_number, ctx=ctx)
            self._render_transform_parameters(
                inputs,
                selected_transform_name,
                step_number=step_number,
                random_crop_defaults=random_crop_defaults,
            )
        return inputs

    def _executable_transform_names(self) -> tuple[str, ...]:
        return tuple(
            capability.name
            for capability in self.catalog_provider.list_transform_capabilities()
            if capability.status in {CapabilityStatus.SUPPORTED, CapabilityStatus.SUPPORTED_WITH_DEFAULTS}
        )

    def _render_general_settings(self, inputs: types.Object, selected_step_count: int) -> None:
        inputs.view(
            GENERAL_SECTION_FIELD_NAME,
            types.Header(
                label="General",
                description="Run settings are configured before individual augmentation stages.",
            ),
        )
        self.renderer.render_into(
            inputs,
            (
                FormFieldSchema(
                    name=PIPELINE_STEP_COUNT_FIELD_NAME,
                    kind=FieldKind.INTEGER,
                    label=PIPELINE_STEP_COUNT_LABEL,
                    required=False,
                    default=selected_step_count,
                    min_value=1,
                    max_value=MAX_PIPELINE_STEPS,
                ),
                FormFieldSchema(
                    name=OUTPUTS_PER_SAMPLE_FIELD_NAME,
                    kind=FieldKind.INTEGER,
                    label="Outputs per sample",
                    required=False,
                    default=1,
                    min_value=1,
                    max_value=MAX_OUTPUTS_PER_SAMPLE,
                ),
                FormFieldSchema(
                    name=DRY_RUN_FIELD_NAME,
                    kind=FieldKind.BOOLEAN,
                    label="Dry run",
                    default=False,
                ),
            ),
        )

    def _render_stage_header(self, inputs: types.Object, step_number: int) -> None:
        inputs.view(
            f"{STAGE_SECTION_FIELD_PREFIX}_{step_number}",
            types.Header(
                label=f"Stage {step_number}",
                description=f"Configure augmentation stage {step_number} of the ordered pipeline.",
            ),
        )

    def _render_transform_selector(
        self,
        inputs: types.Object,
        *,
        supported_transform_names: tuple[str, ...],
        selected_transform_name: str,
        step_number: int,
    ) -> None:
        label = _step_label(step_number, "Transform")
        choices = types.AutocompleteView(label=label, allow_user_input=False)
        for transform_name in supported_transform_names:
            choices.add_choice(transform_name, label=transform_name)

        inputs.enum(
            pipeline_step_field_name(step_number, TRANSFORM_FIELD_NAME),
            choices.values(),
            label=label,
            default=selected_transform_name,
            required=False,
            view=choices,
        )

    def _render_transform_guidance(
        self,
        inputs: types.Object,
        selected_transform_name: str,
        *,
        step_number: int,
        ctx: Any | None,
    ) -> None:
        guidance = build_transform_guidance(
            capability=self.catalog_provider.get_transform_capability(selected_transform_name),
            ctx=ctx,
        )
        inputs.view(
            pipeline_step_field_name(step_number, TARGET_GUIDANCE_FIELD_NAME),
            _guidance_view(guidance),
        )

    def _render_transform_parameters(
        self,
        inputs: types.Object,
        selected_transform_name: str,
        *,
        step_number: int,
        random_crop_defaults: RandomCropDefaults | None,
    ) -> None:
        parameter_fields = self.parameter_schema_provider.get_parameter_schema(selected_transform_name)
        self.renderer.render_into(
            inputs,
            _step_parameter_fields(
                parameter_fields=_executable_ui_fields(
                    selected_transform_name=selected_transform_name,
                    parameter_fields=parameter_fields,
                    random_crop_defaults=random_crop_defaults,
                ),
                step_number=step_number,
            ),
        )


def build_dynamic_augment_form(ctx: Any | None) -> types.Object:
    """Build the default dynamic augment operator form."""

    return DynamicAugmentFormBuilder().build(ctx)


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return params if isinstance(params, Mapping) else {}


def _guidance_view(guidance: TransformGuidance) -> types.View:
    view_cls = types.Warning if guidance.warning else types.Notice
    return view_cls(label=guidance.label, description=guidance.description)


def _selected_step_count(raw_value: object) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and 1 <= raw_value <= MAX_PIPELINE_STEPS:
        return raw_value
    return 1


def _selected_transform_name(
    raw_value: object,
    *,
    supported_transform_names: tuple[str, ...],
    step_number: int,
) -> str:
    if isinstance(raw_value, str) and raw_value in supported_transform_names:
        return raw_value
    default_for_step = _default_transform_name_for_step(step_number, supported_transform_names)
    if default_for_step is not None:
        return default_for_step
    if DEFAULT_DYNAMIC_TRANSFORM_NAME in supported_transform_names:
        return DEFAULT_DYNAMIC_TRANSFORM_NAME
    try:
        return supported_transform_names[0]
    except IndexError as error:
        raise UnsupportedTransformError(
            DEFAULT_DYNAMIC_TRANSFORM_NAME,
            message="No supported transforms are available for the augment form.",
            context={"reason_code": "empty_catalog"},
        ) from error


def _default_transform_name_for_step(
    step_number: int,
    supported_transform_names: tuple[str, ...],
) -> str | None:
    try:
        candidate = FIXED_TRANSFORM_NAMES[step_number - 1]
    except IndexError:
        candidate = DEFAULT_DYNAMIC_TRANSFORM_NAME
    return candidate if candidate in supported_transform_names else None


def _executable_ui_fields(
    *,
    selected_transform_name: str,
    parameter_fields: tuple[FormFieldSchema, ...],
    random_crop_defaults: RandomCropDefaults | None,
) -> tuple[FormFieldSchema, ...]:
    supported_parameter_names = FIXED_SLICE_PARAMETER_NAMES.get(selected_transform_name)

    return tuple(
        _executable_ui_field(
            selected_transform_name=selected_transform_name,
            field=field,
            random_crop_defaults=random_crop_defaults,
        )
        for field in parameter_fields
        if _is_visible_parameter(field)
        if supported_parameter_names is None or field.name in supported_parameter_names
    )


def _is_visible_parameter(field: FormFieldSchema) -> bool:
    return field.metadata.get("schema_status") != SCHEMA_STATUS_JSON_FALLBACK


def _executable_ui_field(
    *,
    selected_transform_name: str,
    field: FormFieldSchema,
    random_crop_defaults: RandomCropDefaults | None,
) -> FormFieldSchema:
    if field.name == PROBABILITY_FIELD_NAME:
        return replace(field, required=False, default=DEFAULT_TRANSFORM_PROBABILITY)
    if selected_transform_name == "RandomBrightnessContrast" and field.name == "brightness_range":
        return replace(field, required=False, default=_number_range_default(DEFAULT_BRIGHTNESS_RANGE))
    if selected_transform_name == "RandomBrightnessContrast" and field.name == "contrast_range":
        return replace(field, required=False, default=_number_range_default(DEFAULT_CONTRAST_RANGE))
    if selected_transform_name == RANDOM_CROP_TRANSFORM_NAME:
        return _random_crop_ui_field(field, random_crop_defaults=random_crop_defaults)
    return field


def _number_range_default(values: tuple[float, float]) -> list[JSONValue]:
    return [values[0], values[1]]


def _random_crop_ui_field(
    field: FormFieldSchema,
    *,
    random_crop_defaults: RandomCropDefaults | None,
) -> FormFieldSchema:
    if field.name not in {"height", "width"}:
        return field

    default = _random_crop_field_default(field.name, random_crop_defaults)
    return replace(
        field,
        required=False,
        default=default,
        help_text=_field_help_text(field, random_crop_defaults),
    )


def _random_crop_field_default(field_name: str, random_crop_defaults: RandomCropDefaults | None) -> int:
    if random_crop_defaults is None:
        return DEFAULT_CROP_SIZE
    if field_name == "height":
        return random_crop_defaults.height
    return random_crop_defaults.width


def _field_help_text(field: FormFieldSchema, random_crop_defaults: RandomCropDefaults | None) -> str | None:
    if random_crop_defaults is None:
        return field.help_text
    if field.help_text is None:
        return random_crop_defaults.help_text
    return f"{field.help_text} {random_crop_defaults.help_text}"


def _step_parameter_fields(
    *,
    parameter_fields: tuple[FormFieldSchema, ...],
    step_number: int,
) -> tuple[FormFieldSchema, ...]:
    return tuple(
        replace(
            field,
            name=pipeline_step_field_name(step_number, field.name),
            label=_step_label(step_number, field.label or field.name),
        )
        for field in parameter_fields
    )


def _step_label(step_number: int, label: str) -> str:
    return f"Step {step_number} {label}"
