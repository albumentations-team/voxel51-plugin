"""Build FiftyOne operator forms from catalog-backed neutral schemas."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

import fiftyone.operators.types as types

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.fixed import build_fixed_pipeline_config
from albumentationsx_plugin.albumentations_backend.fixed.pipeline import validate_pipeline_image_shape
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
    JSONDict,
    JSONValue,
    ParameterSchemaProvider,
    PipelineConfig,
    PluginError,
    TransformCatalogProvider,
    TransformConfig,
    UnsupportedTransformError,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.core.serialization import normalize_json_value
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    FIELD_TYPE_HEATMAP,
    SELECTED_LABEL_FIELDS_PARAM_NAME,
    AnnotationField,
    annotation_field_param_name,
    annotation_field_selection_is_explicit,
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
    ACTION_LABELS,
    EDITOR_ACTION,
    PREVIOUS_SELECTION,
    RETURN_ERRORS,
    REVIEWED_SELECTION,
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
    selected_sample_shapes,
)
from albumentationsx_plugin.hosts.fiftyone.forms.pipeline_loading import render_pipeline_loader
from albumentationsx_plugin.hosts.fiftyone.forms.preset_saving import render_preset_save_controls
from albumentationsx_plugin.hosts.fiftyone.forms.renderer import (
    JSON_STRING_DEFAULT_METADATA_KEY,
    FiftyOneFormRenderer,
)
from albumentationsx_plugin.hosts.fiftyone.forms.sections import add_collapsible_section
from albumentationsx_plugin.hosts.fiftyone.output_metadata import build_output_metadata_policy, metadata_policy_summary
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import (
    SAVE_PRESET_DESCRIPTION_FIELD_NAME,
    SAVE_PRESET_NAME_FIELD_NAME,
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
ANNOTATION_COMPATIBILITY_WARNING_FIELD_NAME: Final[str] = "_annotation_compatibility_warning"
STAGE_SECTION_FIELD_PREFIX: Final[str] = "_pipeline_stage"
ADVANCED_STAGE_SECTION_FIELD_PREFIX: Final[str] = "_pipeline_stage_advanced"
AUGMENT_VALIDATION_WARNING_FIELD_NAME: Final[str] = "_augment_validation_warning"
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
        params = dict(raw_params)
        template_source_issues = validate_augment_template_sources(params)
        validation_issues = (*template_source_issues, *validate_effective_augment_params(execution_params(params)))
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


def _arrange_editor(
    inputs: types.Object,
    params: Mapping[str, object],
    *,
    selected_sample_ids: tuple[str, ...],
    source_count: int | None,
) -> types.Object:
    arranged = types.Object()
    action = editor_action(params)
    choices = types.DropdownView()
    for value, label in ACTION_LABELS.items():
        choices.add_choice(value, label=label)
    arranged.enum(EDITOR_ACTION, choices.values(), default=action, required=True, label="Action", view=choices)
    if params.get(RETURN_ERRORS):
        arranged.view(
            "_previous_execution_error",
            types.Warning(
                label="Previous attempt needs attention",
                description=str(params[RETURN_ERRORS]) + " Your settings are preserved below.",
            ),
        )
    if AUGMENT_VALIDATION_WARNING_FIELD_NAME in inputs.properties:
        arranged.add_property(
            AUGMENT_VALIDATION_WARNING_FIELD_NAME, inputs.properties[AUGMENT_VALIDATION_WARNING_FIELD_NAME]
        )
    arranged.add_property(EXECUTION_SCOPE_FIELD_NAME, inputs.properties[EXECUTION_SCOPE_FIELD_NAME])
    summary = (
        f"Source samples in this scope: {source_count if source_count is not None else 'unknown'}. "
        f"Selected now: {len(selected_sample_ids)}. "
        f"Outputs per source: {_selected_outputs_per_sample(params.get(OUTPUTS_PER_SAMPLE_FIELD_NAME))}. "
        "Creation uses the scope shown above. Preview uses up to 3 selected samples and creates no dataset samples."
    )
    arranged.view("_source_summary", types.Notice(label="Source and outputs", description=summary))
    if action == "validate":
        arranged.view(
            "_validation_scope",
            types.Notice(
                label="Validation scope",
                description="Reads every source image and selected annotation, checks known crop dimensions, and executes every planned output in memory. Creates no files or runs. Stochastic branches can differ on a later run; output write permissions and future input changes are not checked.",
            ),
        )
    if action == "save":
        arranged.view(
            "_save_validation_scope",
            types.Notice(
                label="Pipeline validation",
                description="Saving checks configuration and annotation compatibility. Use Validate without creating samples to check this pipeline against source images before creation.",
            ),
        )
    previous = params.get(PREVIOUS_SELECTION)
    if isinstance(previous, list) and set(previous) != set(selected_sample_ids):
        arranged.view(
            "_selection_changed",
            types.Warning(
                label="Selection changed",
                description=f"The previous draft used {len(previous)} selected sample(s); now {len(selected_sample_ids)} are selected. Review this scope before creating samples.",
            ),
        )
    arranged.list(REVIEWED_SELECTION, types.String(), default=list(selected_sample_ids), view=types.HiddenView())
    for name in (PIPELINE_STEP_COUNT_FIELD_NAME, OUTPUTS_PER_SAMPLE_FIELD_NAME):
        prop = inputs.properties[name]
        prop.view.space = 6
        arranged.add_property(name, prop)
    for name, prop in inputs.properties.items():
        if (
            name.startswith((STAGE_SECTION_FIELD_PREFIX + "_", "_stage_parameters_", "_stage_target_", "_stage_help_"))
            or name == "transform"
            or (name.startswith("step_") and name.endswith("_transform"))
        ):
            arranged.add_property(name, prop)
    for name in (
        ANNOTATION_SECTION_FIELD_NAME,
        ANNOTATION_COMPATIBILITY_WARNING_FIELD_NAME,
        ANNOTATION_FIELD_GROUP_NAME,
    ):
        if name in inputs.properties:
            arranged.add_property(name, inputs.properties[name])
    groups = (
        (
            "_pipeline_library",
            "Load a saved pipeline or run",
            lambda n: n.startswith("_pipeline_") or n == "pipeline_load_source" or n == "_load_pipeline",
        ),
        ("_save_options", "Save pipeline settings", lambda n: n.startswith("save_preset_")),
        ("_run_options", "Run options", lambda n: n in (RUN_LABEL_FIELD_NAME, EXECUTION_MODE_GUIDANCE_FIELD_NAME)),
        ("_compatibility_details", "Compatibility details", lambda n: n.startswith("_dataset_compatibility")),
        ("_metadata_details", "Output metadata details", lambda n: n == "_output_metadata_policy"),
    )
    for key, label, matches in groups:
        group = types.Object()
        for name, prop in inputs.properties.items():
            if name not in arranged.properties and matches(name):
                group.add_property(name, prop)
        if key == "_save_options" and action == "save":
            group.properties[SAVE_PRESET_NAME_FIELD_NAME].required = True
        add_collapsible_section(arranged, key, label, group, expanded=key == "_save_options" and action == "save")
    return arranged


def _mark_validation_fields(inputs: types.Object, issues: tuple[AugmentValidationIssue, ...]) -> None:
    for issue in issues:
        names = issue.fields
        if not names:
            names = (SAVE_PRESET_NAME_FIELD_NAME,) if issue.context.get("preset_name_field") else (EDITOR_ACTION,)
        for name in names:
            _mark_field(inputs, name, issue.message)


def _dimension_issues(ctx: Any, params: Mapping[str, object]) -> tuple[AugmentValidationIssue, ...]:
    config = build_fixed_pipeline_config(execution_params(params))
    stages = sorted(
        (
            _selected_int(
                params.get(pipeline_stage_order_field_name(number)),
                default=number,
                min_value=1,
                max_value=MAX_PIPELINE_STEPS,
            ),
            number,
        )
        for number in range(1, _selected_step_count(params.get(PIPELINE_STEP_COUNT_FIELD_NAME)) + 1)
        if params.get(pipeline_stage_enabled_field_name(number)) is not False
    )
    shapes = selected_sample_shapes(ctx)
    if editor_action(params) == "preview":
        shapes = shapes[:3]
    for sample_id, shape in shapes:
        try:
            validate_pipeline_image_shape(config, image_shape=shape)
        except PluginError as error:
            position = error.context.get("execution_stage")
            number = stages[int(position) - 1][1] if isinstance(position, int) else 1
            parameter = str(error.context.get("parameter_name", "transform"))
            return (
                AugmentValidationIssue(
                    error.code.value,
                    f"Sample {sample_id}, stage {number}: {error.message}",
                    {**error.context, "sample_id": sample_id, "stage_number": number},
                    (pipeline_step_field_name(number, parameter),),
                ),
            )
    return ()


def _mark_field(inputs: types.Object, name: str, message: str) -> bool:
    for key, prop in inputs.properties.items():
        if key == name:
            prop.invalid = True
            prop.error_message = message
            return True
        if isinstance(prop.type, types.Object) and _mark_field(prop.type, name, message):
            if prop.view is not None and hasattr(prop.view, "componentsProps"):
                grid = (prop.view.componentsProps or {}).get("grid", {})
                if grid.get("component") == "details":
                    grid["open"] = True
            return True
    return False


def _focus_first_invalid(inputs: types.Object) -> bool:
    for prop in inputs.properties.values():
        if isinstance(prop.type, types.Object):
            if _focus_first_invalid(prop.type):
                return True
        elif prop.invalid and isinstance(prop.view, types.FieldView):
            props = dict(getattr(prop.view, "componentsProps", {}) or {})
            # TextFieldView consumes `field`, not `input`. Changing the wrapper
            # element remounts the input when it first becomes invalid, so
            # autofocus also works after an edit, not only on initial render.
            props["field"] = {**props.get("field", {}), "autoFocus": True}
            props["container"] = {**props.get("container", {}), "component": "section"}
            # View.to_json merges constructor kwargs last; reconstruct instead
            # of assigning an attribute that those kwargs would overwrite.
            prop.view = types.FieldView(**{**prop.view.to_json(), "componentsProps": props})
            return True
    return False


def build_dynamic_augment_form(ctx: Any | None) -> types.Object:
    """Build the default dynamic augment operator form."""

    return DynamicAugmentFormBuilder().build(ctx)


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return flatten_fiftyone_form_groups(params) if isinstance(params, Mapping) else {}


def _selected_step_count(raw_value: object) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and 1 <= raw_value <= MAX_PIPELINE_STEPS:
        return raw_value
    return 1


def _selected_outputs_per_sample(raw_value: object) -> int:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and 1 <= raw_value <= MAX_OUTPUTS_PER_SAMPLE:
        return raw_value
    return 1


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
    if field.label_type == FIELD_TYPE_HEATMAP:
        return (
            "Heatmap labels use image targets for geometry-only synchronization; "
            "mixed color/intensity stages are blocked."
        )
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
    catalog_provider: TransformCatalogProvider,
    parameter_fields: tuple[FormFieldSchema, ...],
    params: Mapping[str, object],
    step_number: int,
    random_crop_defaults: RandomCropDefaults | None,
) -> tuple[FormFieldSchema, ...]:
    supported_parameter_names = FIXED_SLICE_PARAMETER_NAMES.get(selected_transform_name)
    externally_resolved_parameter_names = _externally_resolved_parameter_names(
        selected_transform_name,
        catalog_provider=catalog_provider,
    )

    fields: list[FormFieldSchema] = []
    for schema_field in parameter_fields:
        if not _is_ui_parameter(schema_field):
            continue
        if schema_field.name in externally_resolved_parameter_names:
            continue
        if (
            supported_parameter_names is not None
            and schema_field.name not in supported_parameter_names
            and not _is_json_fallback_parameter(schema_field)
        ):
            continue
        ui_field = _executable_ui_field(
            selected_transform_name=selected_transform_name,
            field=schema_field,
            random_crop_defaults=random_crop_defaults,
        )
        compact_field = replace(ui_field, help_text=_compact_help_text(ui_field.help_text))
        fields.append(_with_current_default(compact_field, params=params, step_number=step_number))
    return tuple(fields)


def _externally_resolved_parameter_names(
    transform_name: str,
    *,
    catalog_provider: TransformCatalogProvider,
) -> frozenset[str]:
    capability = catalog_provider.get_transform_capability(transform_name)
    if capability is None:
        return frozenset()
    return frozenset(
        requirement.parameter_name
        for requirement in capability.external_inputs
        if requirement.parameter_name is not None
    )


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
            help_text="Lower values run earlier. Each enabled stage must have a different order.",
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
    if field.kind is FieldKind.JSON and isinstance(params[parameter_name], str):
        return replace(
            field,
            required=False,
            default=None,
            metadata={**field.metadata, JSON_STRING_DEFAULT_METADATA_KEY: params[parameter_name]},
        )
    return replace(field, required=False, default=normalize_json_value(params[parameter_name]))


def _is_ui_parameter(field: FormFieldSchema) -> bool:
    if _is_json_fallback_parameter(field):
        return not field.required
    return True


def _is_json_fallback_parameter(field: FormFieldSchema) -> bool:
    return field.metadata.get("schema_status") == SCHEMA_STATUS_JSON_FALLBACK


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
