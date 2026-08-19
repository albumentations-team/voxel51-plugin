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
    RUN_LABEL_FIELD_NAME,
    CapabilityStatus,
    FieldKind,
    FormFieldSchema,
    JSONValue,
    ParameterSchemaProvider,
    TransformCatalogProvider,
    UnsupportedTransformError,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.core.serialization import normalize_json_value
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    SELECTED_LABEL_FIELDS_PARAM_NAME,
    AnnotationField,
    annotation_field_param_name,
    annotation_field_selection_is_explicit,
    safe_list_supported_annotation_fields,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CHOICES,
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_LABELS,
    selected_execution_scope,
    selected_sample_ids_from_context,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import (
    flatten_stage_parameter_groups,
    stage_parameter_group_name,
)
from albumentationsx_plugin.hosts.fiftyone.forms.defaults import RandomCropDefaults, build_random_crop_defaults
from albumentationsx_plugin.hosts.fiftyone.forms.renderer import FiftyOneFormRenderer
from albumentationsx_plugin.hosts.fiftyone.presets import (
    PREVIOUS_RUN_KEY_FIELD_NAME,
    list_previous_run_preset_keys,
    params_with_previous_run_preset,
    selected_previous_run_key,
    storage_root_from_params,
)
from albumentationsx_plugin.hosts.fiftyone.progress import DELEGATED_EXECUTION_RECOMMENDED_SOURCE_COUNT

SCHEMA_STATUS_JSON_FALLBACK: Final[str] = "json_fallback"
TRANSFORM_FIELD_NAME: Final[str] = "transform"
PROBABILITY_FIELD_NAME: Final[str] = "p"
OUTPUTS_PER_SAMPLE_FIELD_NAME: Final[str] = "outputs_per_sample"
DRY_RUN_FIELD_NAME: Final[str] = "dry_run"
DEFAULT_DYNAMIC_TRANSFORM_NAME: Final[str] = "HorizontalFlip"
PIPELINE_STEP_COUNT_LABEL: Final[str] = "Pipeline stages"
PIPELINE_STAGE_ENABLED_LABEL: Final[str] = "Enabled"
PIPELINE_STAGE_ORDER_LABEL: Final[str] = "Execution order"
RANDOM_CROP_TRANSFORM_NAME: Final[str] = "RandomCrop"
GENERAL_SECTION_FIELD_NAME: Final[str] = "_general_settings"
ANNOTATION_SECTION_FIELD_NAME: Final[str] = "_annotation_settings"
ANNOTATION_FIELD_GROUP_NAME: Final[str] = "_annotation_fields"
STAGE_SECTION_FIELD_PREFIX: Final[str] = "_pipeline_stage"
PREVIOUS_RUN_WARNING_FIELD_NAME: Final[str] = "_previous_run_warning"
EXECUTION_MODE_GUIDANCE_FIELD_NAME: Final[str] = "_execution_mode_guidance"
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

        raw_params = _ctx_params(ctx)
        dataset = getattr(ctx, "dataset", None) if ctx is not None else None
        storage_root = storage_root_from_params(raw_params)
        preset_run_keys = list_previous_run_preset_keys(dataset, storage_root=storage_root)
        selected_preset_run_key = selected_previous_run_key(raw_params)
        preset_warning = ""
        try:
            params = params_with_previous_run_preset(dataset, raw_params, storage_root=storage_root)
        except Exception:
            params = raw_params
            preset_warning = "Previous run settings could not be loaded; current form values are unchanged."
        supported_transform_names = self._executable_transform_names()
        selected_sample_ids = selected_sample_ids_from_context(ctx)
        selected_scope = _selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
        selected_step_count = _selected_step_count(params.get(PIPELINE_STEP_COUNT_FIELD_NAME))
        random_crop_defaults = build_random_crop_defaults(ctx)
        annotation_fields = safe_list_supported_annotation_fields(dataset)

        inputs = types.Object()
        self._render_general_settings(
            inputs,
            params,
            selected_step_count=selected_step_count,
            selected_scope=selected_scope,
            preset_run_keys=preset_run_keys,
            selected_preset_run_key=selected_preset_run_key,
            preset_warning=preset_warning,
        )
        self._render_annotation_fields(inputs, params, annotation_fields=annotation_fields)
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
            self._render_transform_parameters(
                inputs,
                selected_transform_name,
                step_number=step_number,
                params=params,
                random_crop_defaults=random_crop_defaults,
            )
        return inputs

    def _executable_transform_names(self) -> tuple[str, ...]:
        return tuple(
            capability.name
            for capability in self.catalog_provider.list_transform_capabilities()
            if capability.status in {CapabilityStatus.SUPPORTED, CapabilityStatus.SUPPORTED_WITH_DEFAULTS}
        )

    def _render_general_settings(
        self,
        inputs: types.Object,
        params: Mapping[str, object],
        *,
        selected_step_count: int,
        selected_scope: str,
        preset_run_keys: tuple[str, ...],
        selected_preset_run_key: str,
        preset_warning: str,
    ) -> None:
        inputs.view(
            GENERAL_SECTION_FIELD_NAME,
            types.Header(
                label="General",
                description="Run settings are configured before individual augmentation stages.",
            ),
        )
        self._render_previous_run_selector(
            inputs,
            preset_run_keys=preset_run_keys,
            selected_preset_run_key=selected_preset_run_key,
        )
        self._render_execution_scope_selector(inputs, selected_scope=selected_scope)
        self._render_execution_mode_guidance(inputs)
        if preset_warning:
            inputs.view(
                PREVIOUS_RUN_WARNING_FIELD_NAME,
                types.Warning(label="Previous run", description=preset_warning),
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
                    help_text=f"Show 1-{MAX_PIPELINE_STEPS} configurable stage slots.",
                ),
                FormFieldSchema(
                    name=RUN_LABEL_FIELD_NAME,
                    kind=FieldKind.STRING,
                    label="Run label",
                    required=False,
                    default=_selected_string(params.get(RUN_LABEL_FIELD_NAME)),
                    help_text="Optional short prefix for generated run keys.",
                ),
                FormFieldSchema(
                    name=OUTPUTS_PER_SAMPLE_FIELD_NAME,
                    kind=FieldKind.INTEGER,
                    label="Outputs per sample",
                    required=False,
                    default=_selected_outputs_per_sample(params.get(OUTPUTS_PER_SAMPLE_FIELD_NAME)),
                    min_value=1,
                    max_value=MAX_OUTPUTS_PER_SAMPLE,
                ),
                FormFieldSchema(
                    name=DRY_RUN_FIELD_NAME,
                    kind=FieldKind.BOOLEAN,
                    label="Dry run",
                    default=_selected_bool(params.get(DRY_RUN_FIELD_NAME), default=False),
                ),
            ),
        )

    def _render_previous_run_selector(
        self,
        inputs: types.Object,
        *,
        preset_run_keys: tuple[str, ...],
        selected_preset_run_key: str,
    ) -> None:
        if not preset_run_keys and not selected_preset_run_key:
            return

        choices = types.AutocompleteView(label="Previous run", allow_user_input=False)
        choices.add_choice("", label="Do not load previous settings")
        for run_key in _preset_choice_run_keys(preset_run_keys, selected_preset_run_key):
            choices.add_choice(run_key, label=run_key)
        inputs.enum(
            PREVIOUS_RUN_KEY_FIELD_NAME,
            choices.values(),
            label="Previous run",
            default=selected_preset_run_key,
            required=False,
            description="Optionally prefill this form from a saved run in the current dataset.",
            view=choices,
        )

    def _render_execution_scope_selector(self, inputs: types.Object, *, selected_scope: str) -> None:
        choices = types.AutocompleteView(label="Execution scope", allow_user_input=False)
        for scope in EXECUTION_SCOPE_CHOICES:
            choices.add_choice(scope, label=EXECUTION_SCOPE_LABELS[scope])
        inputs.enum(
            EXECUTION_SCOPE_FIELD_NAME,
            EXECUTION_SCOPE_CHOICES,
            label="Execution scope",
            default=selected_scope,
            required=True,
            description="Choose whether to process selected samples, the current view, or the entire dataset.",
            view=choices,
        )

    def _render_execution_mode_guidance(self, inputs: types.Object) -> None:
        inputs.message(
            EXECUTION_MODE_GUIDANCE_FIELD_NAME,
            label="Execution mode",
            description=(
                "Immediate execution is best for small bounded selections. "
                f"Use delegated execution for views or datasets with about "
                f"{DELEGATED_EXECUTION_RECOMMENDED_SOURCE_COUNT}+ source samples "
                "to keep the App responsive and track progress."
            ),
        )

    def _render_annotation_fields(
        self,
        inputs: types.Object,
        params: Mapping[str, object],
        *,
        annotation_fields: tuple[AnnotationField, ...],
    ) -> None:
        if not annotation_fields:
            return

        inputs.view(
            ANNOTATION_SECTION_FIELD_NAME,
            types.Header(
                label="Annotations",
            ),
        )
        group = inputs.grid(
            ANNOTATION_FIELD_GROUP_NAME,
            orientation="2d",
            gap=1,
        )
        for annotation_field in annotation_fields:
            group.bool(
                annotation_field_param_name(annotation_field.name),
                label=annotation_field.name,
                default=_annotation_field_default(annotation_field, params),
                required=False,
                view=types.CheckboxView(caption=_annotation_field_caption(annotation_field)),
            )

    def _render_stage_header(self, inputs: types.Object, step_number: int) -> None:
        inputs.view(
            f"{STAGE_SECTION_FIELD_PREFIX}_{step_number}",
            types.Header(
                label=f"Stage {step_number}",
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
        label = "Transform"
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

    def _render_transform_parameters(
        self,
        inputs: types.Object,
        selected_transform_name: str,
        *,
        step_number: int,
        params: Mapping[str, object],
        random_crop_defaults: RandomCropDefaults | None,
    ) -> None:
        parameter_fields = self.parameter_schema_provider.get_parameter_schema(selected_transform_name)
        parameter_group = inputs.grid(
            stage_parameter_group_name(step_number),
            orientation="2d",
            gap=2,
        )
        self.renderer.render_into(
            parameter_group,
            (
                *_pipeline_stage_control_fields(params=params, step_number=step_number),
                *_step_parameter_fields(
                    parameter_fields=_executable_ui_fields(
                        selected_transform_name=selected_transform_name,
                        parameter_fields=parameter_fields,
                        params=params,
                        step_number=step_number,
                        random_crop_defaults=random_crop_defaults,
                    ),
                    step_number=step_number,
                ),
            ),
        )


def build_dynamic_augment_form(ctx: Any | None) -> types.Object:
    """Build the default dynamic augment operator form."""

    return DynamicAugmentFormBuilder().build(ctx)


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return flatten_stage_parameter_groups(params) if isinstance(params, Mapping) else {}


def _selected_step_count(raw_value: object) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and 1 <= raw_value <= MAX_PIPELINE_STEPS:
        return raw_value
    return 1


def _selected_outputs_per_sample(raw_value: object) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and 1 <= raw_value <= MAX_OUTPUTS_PER_SAMPLE:
        return raw_value
    return 1


def _selected_execution_scope(params: Mapping[str, object], *, selected_sample_ids: tuple[str, ...]) -> str:
    try:
        return selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
    except ValueError:
        return selected_execution_scope({}, selected_sample_ids=selected_sample_ids)


def _selected_bool(raw_value: object, *, default: bool) -> bool:
    return raw_value if isinstance(raw_value, bool) else default


def _selected_int(raw_value: object, *, default: int, min_value: int, max_value: int) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and min_value <= raw_value <= max_value:
        return raw_value
    return default


def _selected_string(raw_value: object) -> str:
    return raw_value if isinstance(raw_value, str) else ""


def _annotation_field_default(field: AnnotationField, params: Mapping[str, object]) -> bool:
    raw_selected_fields = params.get(SELECTED_LABEL_FIELDS_PARAM_NAME)
    if isinstance(raw_selected_fields, list | tuple):
        return field.name in {str(field_name) for field_name in raw_selected_fields}

    if not annotation_field_selection_is_explicit(params):
        return True

    raw_value = params.get(annotation_field_param_name(field.name), True)
    return raw_value is True


def _annotation_field_caption(field: AnnotationField) -> str:
    if field.albu_target is None:
        return "Classification labels are copied."
    return f"{field.label_type.capitalize()} labels use {field.albu_target} targets."


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
    params: Mapping[str, object],
    step_number: int,
    random_crop_defaults: RandomCropDefaults | None,
) -> tuple[FormFieldSchema, ...]:
    supported_parameter_names = FIXED_SLICE_PARAMETER_NAMES.get(selected_transform_name)

    fields: list[FormFieldSchema] = []
    for schema_field in parameter_fields:
        if not _is_visible_parameter(schema_field):
            continue
        if supported_parameter_names is not None and schema_field.name not in supported_parameter_names:
            continue
        ui_field = _executable_ui_field(
            selected_transform_name=selected_transform_name,
            field=schema_field,
            random_crop_defaults=random_crop_defaults,
        )
        compact_field = replace(ui_field, help_text=_compact_help_text(ui_field.help_text))
        fields.append(_with_current_default(compact_field, params=params, step_number=step_number))
    return tuple(fields)


def _pipeline_stage_control_fields(
    *,
    params: Mapping[str, object],
    step_number: int,
) -> tuple[FormFieldSchema, FormFieldSchema]:
    return (
        FormFieldSchema(
            name=pipeline_stage_enabled_field_name(step_number),
            kind=FieldKind.BOOLEAN,
            label=PIPELINE_STAGE_ENABLED_LABEL,
            required=False,
            default=_selected_bool(
                params.get(pipeline_stage_enabled_field_name(step_number)),
                default=True,
            ),
            help_text="Skip this stage without clearing its transform settings.",
        ),
        FormFieldSchema(
            name=pipeline_stage_order_field_name(step_number),
            kind=FieldKind.INTEGER,
            label=PIPELINE_STAGE_ORDER_LABEL,
            required=False,
            default=_selected_int(
                params.get(pipeline_stage_order_field_name(step_number)),
                default=step_number,
                min_value=1,
                max_value=MAX_PIPELINE_STEPS,
            ),
            min_value=1,
            max_value=MAX_PIPELINE_STEPS,
            help_text="Lower values run earlier; ties keep stage slot order.",
        ),
    )


def _with_current_default(
    field: FormFieldSchema,
    *,
    params: Mapping[str, object],
    step_number: int,
) -> FormFieldSchema:
    parameter_name = pipeline_step_field_name(step_number, field.name)
    if parameter_name not in params:
        return field
    return replace(field, required=False, default=normalize_json_value(params[parameter_name]))


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
    return random_crop_defaults.help_text


def _compact_help_text(help_text: str | None) -> str | None:
    if help_text is None:
        return None

    summary = help_text.split("\n-", maxsplit=1)[0]
    summary = summary.split('\n"', maxsplit=1)[0]
    summary = summary.split("Default:", maxsplit=1)[0]
    summary = " ".join(summary.split()).strip().rstrip(":")
    for separator in (". ", "? ", "! "):
        if separator in summary:
            summary = summary.split(separator, maxsplit=1)[0] + separator[0]
            break
    if summary.startswith("Whether to use "):
        summary = "Use " + summary.removeprefix("Whether to use ")
    if summary:
        summary = summary[0].upper() + summary[1:]
    return summary or None


def _step_parameter_fields(
    *,
    parameter_fields: tuple[FormFieldSchema, ...],
    step_number: int,
) -> tuple[FormFieldSchema, ...]:
    return tuple(
        replace(
            field,
            name=pipeline_step_field_name(step_number, field.name),
            label=_parameter_label(field),
        )
        for field in parameter_fields
    )


def _parameter_label(field: FormFieldSchema) -> str:
    if field.name == PROBABILITY_FIELD_NAME:
        return "Probability"
    return field.label or field.name


def _preset_choice_run_keys(preset_run_keys: tuple[str, ...], selected_preset_run_key: str) -> tuple[str, ...]:
    return (
        tuple(dict.fromkeys((*preset_run_keys, selected_preset_run_key)))
        if selected_preset_run_key
        else preset_run_keys
    )
