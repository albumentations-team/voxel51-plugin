"""Build FiftyOne operator forms from catalog-backed neutral schemas."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

import fiftyone.operators.types as types

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.parameters import AlbuSpecParameterSchemaProvider
from albumentationsx_plugin.core import (
    FIXED_TRANSFORM_NAMES,
    MAX_OUTPUTS_PER_SAMPLE,
    FieldKind,
    FormFieldSchema,
    ParameterSchemaProvider,
    TransformCatalogProvider,
    UnsupportedTransformError,
)
from albumentationsx_plugin.hosts.fiftyone.forms.renderer import FiftyOneFormRenderer

TRANSFORM_FIELD_NAME: Final[str] = "transform"
OUTPUTS_PER_SAMPLE_FIELD_NAME: Final[str] = "outputs_per_sample"
DRY_RUN_FIELD_NAME: Final[str] = "dry_run"
DEFAULT_DYNAMIC_TRANSFORM_NAME: Final[str] = "HorizontalFlip"


@dataclass(frozen=True, slots=True)
class DynamicAugmentFormBuilder:
    """Compose a FiftyOne augment form from backend catalog and schema services."""

    catalog_provider: TransformCatalogProvider = field(default_factory=AlbuSpecCatalogProvider)
    parameter_schema_provider: ParameterSchemaProvider = field(default_factory=AlbuSpecParameterSchemaProvider)
    renderer: FiftyOneFormRenderer = field(default_factory=FiftyOneFormRenderer)

    def build(self, ctx: Any | None) -> types.Object:
        """Build the current operator input object for the selected transform."""

        params = _ctx_params(ctx)
        supported_transform_names = self._supported_transform_names()
        selected_transform_name = _selected_transform_name(
            params.get(TRANSFORM_FIELD_NAME),
            supported_transform_names=supported_transform_names,
        )

        inputs = types.Object()
        self._render_transform_selector(
            inputs,
            supported_transform_names=supported_transform_names,
            selected_transform_name=selected_transform_name,
        )
        self._render_transform_parameters(inputs, selected_transform_name)
        self._render_execution_fields(inputs)
        self._render_execution_scope(inputs, selected_transform_name)
        return inputs

    def _supported_transform_names(self) -> tuple[str, ...]:
        return tuple(
            capability.name
            for capability in self.catalog_provider.list_transform_capabilities()
            if capability.status.value in {"supported", "supported_with_defaults"}
        )

    def _render_transform_selector(
        self,
        inputs: types.Object,
        *,
        supported_transform_names: tuple[str, ...],
        selected_transform_name: str,
    ) -> None:
        choices = types.AutocompleteView(label="Transform", allow_user_input=False)
        for transform_name in supported_transform_names:
            choices.add_choice(transform_name, label=transform_name)

        inputs.enum(
            TRANSFORM_FIELD_NAME,
            choices.values(),
            label="Transform",
            default=selected_transform_name,
            required=True,
            view=choices,
        )

    def _render_transform_parameters(self, inputs: types.Object, selected_transform_name: str) -> None:
        parameter_fields = self.parameter_schema_provider.get_parameter_schema(selected_transform_name)
        self.renderer.render_into(inputs, parameter_fields)

    def _render_execution_fields(self, inputs: types.Object) -> None:
        self.renderer.render_into(
            inputs,
            (
                FormFieldSchema(
                    name=OUTPUTS_PER_SAMPLE_FIELD_NAME,
                    kind=FieldKind.INTEGER,
                    label="Outputs per sample",
                    required=True,
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

    def _render_execution_scope(self, inputs: types.Object, selected_transform_name: str) -> None:
        if selected_transform_name not in FIXED_TRANSFORM_NAMES:
            inputs.message(
                "execution_scope",
                label="Schema preview",
                description="Execution for catalog-wide transforms will be enabled by the dynamic pipeline task.",
            )


def build_dynamic_augment_form(ctx: Any | None) -> types.Object:
    """Build the default dynamic augment operator form."""

    return DynamicAugmentFormBuilder().build(ctx)


def _ctx_params(ctx: Any | None) -> Mapping[str, object]:
    params = getattr(ctx, "params", {}) if ctx is not None else {}
    return params if isinstance(params, Mapping) else {}


def _selected_transform_name(raw_value: object, *, supported_transform_names: tuple[str, ...]) -> str:
    if isinstance(raw_value, str) and raw_value in supported_transform_names:
        return raw_value
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
