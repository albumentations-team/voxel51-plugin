"""Compose the augmentation editor from catalog-backed sections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import fiftyone.operators.types as types

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.parameters import AlbuSpecParameterSchemaProvider
from albumentationsx_plugin.core import (
    MAX_OUTPUTS_PER_SAMPLE,
    MAX_PIPELINE_STEPS,
    PIPELINE_STEP_COUNT_FIELD_NAME,
    RUN_LABEL_FIELD_NAME,
    CapabilityStatus,
    FieldKind,
    FormFieldSchema,
    JSONDict,
    ParameterSchemaProvider,
    PipelineConfig,
    TransformCatalogProvider,
    TransformConfig,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    AnnotationField,
    annotation_field_param_name,
    annotation_pipeline_compatibility_conflicts,
    safe_list_supported_annotation_fields,
    selected_annotation_fields_from_params,
)
from albumentationsx_plugin.hosts.fiftyone.augment_validation import (
    AugmentValidationIssue,
    augment_validation_warning,
    validate_augment_template_sources,
    validate_effective_augment_params,
)
from albumentationsx_plugin.hosts.fiftyone.editor_draft import (
    editor_action,
    execution_params,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CHOICES,
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_LABELS,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    selected_execution_scope,
    selected_sample_ids_from_context,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import (
    ANNOTATION_FIELD_GROUP_NAME,
    flatten_fiftyone_form_groups,
    stage_parameter_group_name,
)
from albumentationsx_plugin.hosts.fiftyone.forms.compatibility import (
    annotation_compatibility_warning,
    build_inline_compatibility_preview,
    render_inline_compatibility_preview,
)
from albumentationsx_plugin.hosts.fiftyone.forms.defaults import (
    RandomCropDefaults,
    build_random_crop_defaults,
)
from albumentationsx_plugin.hosts.fiftyone.forms.editor_fields import (
    ADVANCED_STAGE_SECTION_FIELD_PREFIX,
    ANNOTATION_COMPATIBILITY_WARNING_FIELD_NAME,
    ANNOTATION_SECTION_FIELD_NAME,
    AUGMENT_VALIDATION_WARNING_FIELD_NAME,
    EXECUTION_MODE_GUIDANCE_FIELD_NAME,
    GENERAL_SECTION_FIELD_NAME,
    OUTPUTS_PER_SAMPLE_FIELD_NAME,
    PIPELINE_STEP_COUNT_LABEL,
    STAGE_SECTION_FIELD_PREFIX,
    TRANSFORM_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.forms.editor_layout import _arrange_editor
from albumentationsx_plugin.hosts.fiftyone.forms.editor_validation import (
    _dimension_issues,
    _focus_first_invalid,
    _mark_validation_fields,
)
from albumentationsx_plugin.hosts.fiftyone.forms.editor_values import (
    _selected_bool,
    _selected_int,
    _selected_outputs_per_sample,
    _selected_step_count,
    _selected_string,
)
from albumentationsx_plugin.hosts.fiftyone.forms.pipeline_loading import render_pipeline_loader
from albumentationsx_plugin.hosts.fiftyone.forms.preset_saving import render_preset_save_controls
from albumentationsx_plugin.hosts.fiftyone.forms.renderer import (
    FiftyOneFormRenderer,
)
from albumentationsx_plugin.hosts.fiftyone.forms.stage_fields import (
    _annotation_field_caption,
    _annotation_field_default,
    _executable_ui_fields,
    _pipeline_stage_control_fields,
    _selected_transform_name,
    _step_parameter_fields,
)
from albumentationsx_plugin.hosts.fiftyone.output_metadata import build_output_metadata_policy, metadata_policy_summary
from albumentationsx_plugin.hosts.fiftyone.parameter_policy import (
    is_json_fallback_parameter as _is_json_fallback_parameter,
)
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    SAVE_PRESET_DESCRIPTION_FIELD_NAME,
    SAVE_PRESET_NAME_FIELD_NAME,
)
from albumentationsx_plugin.hosts.fiftyone.progress import DELEGATED_EXECUTION_RECOMMENDED_SOURCE_COUNT


@dataclass(frozen=True, slots=True)
class DynamicAugmentFormBuilder:
    """Compose a FiftyOne augment form from backend catalog and schema services."""

    catalog_provider: TransformCatalogProvider = field(default_factory=AlbuSpecCatalogProvider)
    parameter_schema_provider: ParameterSchemaProvider | None = None
    renderer: FiftyOneFormRenderer = field(default_factory=FiftyOneFormRenderer)

    def __post_init__(self) -> None:
        if self.parameter_schema_provider is None:
            object.__setattr__(
                self, "parameter_schema_provider", AlbuSpecParameterSchemaProvider(self.catalog_provider)
            )

    def build(self, ctx: Any | None) -> types.Object:
        """Build the current operator input object for the selected transform."""

        raw_params = _ctx_params(ctx)
        dataset = getattr(ctx, "dataset", None) if ctx is not None else None
        params = dict(raw_params)
        template_source_issues = validate_augment_template_sources(params)
        validation_issues = (
            *template_source_issues,
            *validate_effective_augment_params(
                execution_params(params),
                catalog_provider=self.catalog_provider,
                parameter_schema_provider=self.parameter_schema_provider,
            ),
        )
        supported_transform_names = self._executable_transform_names()
        selected_sample_ids = selected_sample_ids_from_context(ctx)
        selected_scope = _selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
        if (
            not validation_issues
            and editor_action(params) != "save"
            and (editor_action(params) == "preview" or selected_scope == EXECUTION_SCOPE_SELECTED_SAMPLES)
        ):
            validation_issues = _dimension_issues(ctx, params)
        selected_step_count = _selected_step_count(params.get(PIPELINE_STEP_COUNT_FIELD_NAME))
        random_crop_defaults = build_random_crop_defaults(ctx)
        annotation_fields = safe_list_supported_annotation_fields(dataset)
        compatibility_pipeline = _compatibility_pipeline(
            params,
            supported_transform_names=supported_transform_names,
            selected_step_count=selected_step_count,
        )
        annotation_compatibility_conflicts = _annotation_compatibility_conflicts(
            params,
            dataset=dataset,
            pipeline=compatibility_pipeline,
            catalog_provider=self.catalog_provider,
        )
        inline_compatibility_preview = build_inline_compatibility_preview(
            ctx=ctx,
            params=params,
            selected_sample_ids=selected_sample_ids,
            source_scope=selected_scope,
            pipeline=compatibility_pipeline,
            catalog_provider=self.catalog_provider,
        )

        inputs = types.Object()
        self._render_general_settings(
            inputs,
            params,
            selected_step_count=selected_step_count,
            selected_scope=selected_scope,
            dataset=dataset,
            validation_issues=validation_issues,
        )
        render_inline_compatibility_preview(inputs, inline_compatibility_preview)
        self._render_annotation_fields(
            inputs,
            params,
            annotation_fields=annotation_fields,
            compatibility_conflicts=annotation_compatibility_conflicts,
        )
        selection = selected_annotation_fields_from_params(params, dataset)
        inputs.view(
            "_output_metadata_policy",
            types.Notice(
                label="Output metadata",
                description=metadata_policy_summary(build_output_metadata_policy(dataset, selection)),
            ),
        )
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
                params=params,
            )
            self._render_transform_parameters(
                inputs,
                selected_transform_name,
                step_number=step_number,
                params=params,
                random_crop_defaults=random_crop_defaults,
            )
        arranged = _arrange_editor(
            inputs,
            params,
            selected_sample_ids=selected_sample_ids,
            source_count=inline_compatibility_preview.source_count if inline_compatibility_preview else None,
        )
        _mark_validation_fields(arranged, validation_issues)
        scope_prop = arranged.properties[EXECUTION_SCOPE_FIELD_NAME]
        if (
            editor_action(params) != "save"
            and inline_compatibility_preview
            and inline_compatibility_preview.source_count == 0
        ):
            scope_prop.invalid = True
            scope_prop.error_message = "This scope contains no images. Select images or choose a non-empty scope."
        if (
            editor_action(params) != "save"
            and not selected_sample_ids
            and (editor_action(params) == "preview" or selected_scope == EXECUTION_SCOPE_SELECTED_SAMPLES)
        ):
            scope_prop.invalid = True
            scope_prop.error_message = (
                "Select at least one image in the grid before previewing or using Selected samples."
            )
        if annotation_compatibility_conflicts:
            prop = arranged.properties[ANNOTATION_COMPATIBILITY_WARNING_FIELD_NAME]
            prop.invalid = True
            prop.error_message = annotation_compatibility_warning(annotation_compatibility_conflicts)
        _focus_first_invalid(arranged)
        return arranged

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
        dataset: Any,
        validation_issues: tuple[AugmentValidationIssue, ...],
    ) -> None:
        inputs.view(
            GENERAL_SECTION_FIELD_NAME,
            types.Header(
                label="General",
                description="Run settings are configured before individual augmentation stages.",
            ),
        )
        render_pipeline_loader(inputs, dataset, params)
        render_preset_save_controls(inputs, params)
        self._render_execution_scope_selector(inputs, selected_scope=selected_scope)
        self._render_execution_mode_guidance(inputs)
        if validation_issues:
            inputs.view(
                AUGMENT_VALIDATION_WARNING_FIELD_NAME,
                types.Warning(
                    label="Configuration validation",
                    description=augment_validation_warning(validation_issues),
                ),
                invalid=True,
                error_message=augment_validation_warning(validation_issues),
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
                    name=SAVE_PRESET_NAME_FIELD_NAME,
                    kind=FieldKind.STRING,
                    label="Saved pipeline name",
                    required=False,
                    default=_selected_string(params.get(SAVE_PRESET_NAME_FIELD_NAME)),
                    help_text="Used only by Save pipeline. Names may repeat; Save as new always keeps existing pipelines.",
                ),
                FormFieldSchema(
                    name=SAVE_PRESET_DESCRIPTION_FIELD_NAME,
                    kind=FieldKind.STRING,
                    label="Saved pipeline description",
                    required=False,
                    default=_selected_string(params.get(SAVE_PRESET_DESCRIPTION_FIELD_NAME)),
                ),
            ),
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
        compatibility_conflicts: tuple[object, ...],
    ) -> None:
        if not annotation_fields:
            return

        inputs.view(
            ANNOTATION_SECTION_FIELD_NAME,
            types.Header(
                label="Annotations",
                description="Checked fields are included in generated samples. Unchecked fields are omitted.",
            ),
        )
        if compatibility_conflicts:
            inputs.view(
                ANNOTATION_COMPATIBILITY_WARNING_FIELD_NAME,
                types.Warning(
                    label="Annotation compatibility",
                    description=annotation_compatibility_warning(compatibility_conflicts),
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
        params: Mapping[str, object],
    ) -> None:
        capabilities = {cap.name: cap for cap in self.catalog_provider.list_transform_capabilities()}
        filter_name = f"_stage_target_{step_number}"
        target = params.get(filter_name, "all")
        targets = ("all", *sorted({t for name in supported_transform_names for t in capabilities[name].targets}))
        if target not in targets:
            target = "all"
        target_choices = types.DropdownView()
        for value in targets:
            target_choices.add_choice(value, label="All targets" if value == "all" else value)
        inputs.enum(filter_name, targets, label="Filter transforms by target", default=target, view=target_choices)
        filtered = tuple(
            name for name in supported_transform_names if target == "all" or target in capabilities[name].targets
        )
        names = tuple(dict.fromkeys((*filtered, selected_transform_name)))
        label = "Transform"
        choices = types.AutocompleteView(label=label, allow_user_input=False)
        for transform_name in names:
            choices.add_choice(transform_name, label=transform_name)
        capability = capabilities[selected_transform_name]
        help_text = str(capability.metadata.get("docstring_short") or capability.message or "")
        help_text += f" Targets: {', '.join(capability.targets)}."
        if selected_transform_name not in filtered:
            help_text += " The current transform is kept even though it does not match this filter."
        help_text += " Type in Transform to search names. Target filtering does not change your draft or replace annotation compatibility checks."
        inputs.view(f"_stage_help_{step_number}", types.Notice(label=selected_transform_name, description=help_text))

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
        if params.get(pipeline_stage_enabled_field_name(step_number)) is False:
            # Raw inactive values stay in the draft and return on re-enable.
            group = inputs.grid(stage_parameter_group_name(step_number), orientation="2d", gap=2)
            self.renderer.render_into(group, _pipeline_stage_control_fields(params=params, step_number=step_number)[:1])
            return
        assert self.parameter_schema_provider is not None
        parameter_fields = self.parameter_schema_provider.get_parameter_schema(selected_transform_name)
        parameter_group = inputs.grid(
            stage_parameter_group_name(step_number),
            orientation="2d",
            gap=2,
        )
        executable_fields = _executable_ui_fields(
            selected_transform_name=selected_transform_name,
            catalog_provider=self.catalog_provider,
            parameter_fields=parameter_fields,
            params=params,
            step_number=step_number,
            random_crop_defaults=random_crop_defaults,
        )
        standard_fields = tuple(field for field in executable_fields if not _is_json_fallback_parameter(field))
        advanced_fields = tuple(field for field in executable_fields if _is_json_fallback_parameter(field))
        self.renderer.render_into(
            parameter_group,
            (
                *_pipeline_stage_control_fields(params=params, step_number=step_number),
                *_step_parameter_fields(
                    parameter_fields=standard_fields,
                    step_number=step_number,
                ),
            ),
        )
        if advanced_fields:
            parameter_group.view(
                f"{ADVANCED_STAGE_SECTION_FIELD_PREFIX}_{step_number}",
                types.Header(
                    label="Advanced parameters",
                    description="Optional JSON-backed parameters. Leave empty to use AlbumentationsX defaults.",
                ),
            )
            self.renderer.render_into(
                parameter_group,
                _step_parameter_fields(parameter_fields=advanced_fields, step_number=step_number),
            )


def build_dynamic_augment_form(ctx: Any | None) -> types.Object:
    """Build the default dynamic augment operator form."""

    return DynamicAugmentFormBuilder().build(ctx)


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return flatten_fiftyone_form_groups(params) if isinstance(params, Mapping) else {}


def _compatibility_pipeline(
    params: Mapping[str, object],
    *,
    supported_transform_names: tuple[str, ...],
    selected_step_count: int,
) -> PipelineConfig:
    stages: list[tuple[int, int, TransformConfig]] = []
    for step_number in range(1, selected_step_count + 1):
        if not _selected_bool(params.get(pipeline_stage_enabled_field_name(step_number)), default=True):
            continue
        selected_transform_name = _selected_transform_name(
            params.get(pipeline_step_field_name(step_number, TRANSFORM_FIELD_NAME)),
            supported_transform_names=supported_transform_names,
            step_number=step_number,
        )
        execution_order = _selected_int(
            params.get(pipeline_stage_order_field_name(step_number)),
            default=step_number,
            min_value=1,
            max_value=MAX_PIPELINE_STEPS,
        )
        stages.append((execution_order, step_number, TransformConfig(name=selected_transform_name, params={})))

    return PipelineConfig(
        transforms=tuple(transform for _order, _step_number, transform in sorted(stages)),
        outputs_per_sample=_selected_outputs_per_sample(params.get(OUTPUTS_PER_SAMPLE_FIELD_NAME)),
        use_replay=True,
        options={"source": "catalog_mvp_pipeline"},
    )


def _annotation_compatibility_conflicts(
    params: Mapping[str, object],
    *,
    dataset: Any | None,
    pipeline: PipelineConfig,
    catalog_provider: TransformCatalogProvider,
) -> tuple[JSONDict, ...]:
    if dataset is None or not pipeline.transforms:
        return ()
    try:
        selection = selected_annotation_fields_from_params(params, dataset)
    except Exception:
        return ()
    return annotation_pipeline_compatibility_conflicts(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog_provider,
    )


def _selected_execution_scope(params: Mapping[str, object], *, selected_sample_ids: tuple[str, ...]) -> str:
    try:
        return selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
    except ValueError:
        return selected_execution_scope({}, selected_sample_ids=selected_sample_ids)
