from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import fiftyone as fo
import pytest

from albumentationsx_plugin.core import (
    CapabilityStatus,
    HostAdapterError,
    PipelineConfig,
    TransformCapability,
    TransformConfig,
)
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    SELECTED_LABEL_FIELDS_PARAM_NAME,
    annotation_field_param_name,
    annotation_pipeline_compatibility_conflicts,
    annotation_run_metadata,
    selected_annotation_fields_from_params,
    target_and_copy_fields,
    validate_annotation_pipeline_compatibility,
    validate_selected_annotation_fields,
)


class _Dataset:
    def __init__(self, schema: dict[str, object]) -> None:
        self._schema = schema

    def get_field_schema(self) -> dict[str, object]:
        return self._schema


class _CatalogProvider:
    def __init__(self, capabilities: tuple[TransformCapability, ...]) -> None:
        self._capabilities = {capability.name: capability for capability in capabilities}

    def list_transform_capabilities(self) -> tuple[TransformCapability, ...]:
        return tuple(self._capabilities.values())

    def get_transform_capability(self, name: str) -> TransformCapability | None:
        return self._capabilities.get(name)

    def list_supported_transform_names(self) -> tuple[str, ...]:
        return tuple(self._capabilities)


def _field(label_type: type[fo.Label] | type[str]) -> SimpleNamespace:
    return SimpleNamespace(document_type=label_type)


def _dataset() -> _Dataset:
    return _Dataset(
        {
            "ground_truth": _field(fo.Classification),
            "detections": _field(fo.Detections),
            "secondary_detections": _field(fo.Detections),
            "keypoints": _field(fo.Keypoints),
            "segmentation": _field(fo.Segmentation),
            "polylines": _field(fo.Polylines),
            "filepath": _field(str),
        }
    )


def _capability(name: str, *, transform_type: str, targets: tuple[str, ...]) -> TransformCapability:
    return TransformCapability(
        name=name,
        status=CapabilityStatus.SUPPORTED,
        targets=targets,
        metadata={"transform_type": transform_type},
    )


@pytest.mark.unit
def test_annotation_field_selection_defaults_to_supported_fields_and_records_exclusions() -> None:
    selection = selected_annotation_fields_from_params({}, _dataset())

    assert selection.explicit is False
    assert selection.selected_field_names == (
        "ground_truth",
        "detections",
        "secondary_detections",
        "keypoints",
        "segmentation",
    )
    assert {(field["field_name"], field["reason"], field["selected"]) for field in selection.excluded_fields} == {
        ("polylines", "unsupported_label_type", False)
    }


@pytest.mark.unit
def test_annotation_field_selection_uses_checkbox_params_and_records_unselected_fields() -> None:
    selection = selected_annotation_fields_from_params(
        {annotation_field_param_name("detections"): False},
        _dataset(),
    )

    assert selection.explicit is True
    assert selection.selected_field_names == (
        "ground_truth",
        "secondary_detections",
        "keypoints",
        "segmentation",
    )
    assert ("detections", "not_selected", False) in {
        (field["field_name"], field["reason"], field["selected"]) for field in selection.excluded_fields
    }


@pytest.mark.unit
def test_annotation_field_selection_accepts_legacy_selected_label_fields_param() -> None:
    selection = selected_annotation_fields_from_params(
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["secondary_detections"]},
        _dataset(),
    )

    assert selection.explicit is True
    assert selection.selected_field_names == ("secondary_detections",)


@pytest.mark.unit
def test_selected_unsupported_annotation_field_blocks_execution() -> None:
    selection = selected_annotation_fields_from_params(
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["polylines"]},
        _dataset(),
    )

    with pytest.raises(HostAdapterError) as error:
        validate_selected_annotation_fields(selection)

    assert error.value.context["reason"] == "invalid_annotation_field_selection"
    assert error.value.context["field_name"] == "polylines"
    assert error.value.context["field_reason"] == "unsupported_label_type"


@pytest.mark.unit
def test_annotation_pipeline_compatibility_allows_image_only_stages() -> None:
    selection = selected_annotation_fields_from_params(
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["detections"]},
        _dataset(),
    )
    pipeline = PipelineConfig(transforms=(TransformConfig(name="ColorOnly"),))
    catalog = _CatalogProvider((_capability("ColorOnly", transform_type="image_only", targets=("image",)),))

    validate_annotation_pipeline_compatibility(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog,
    )

    assert (
        annotation_pipeline_compatibility_conflicts(
            selection=selection,
            pipeline=pipeline,
            catalog_provider=catalog,
        )
        == ()
    )


@pytest.mark.unit
def test_annotation_pipeline_compatibility_blocks_missing_spatial_target() -> None:
    selection = selected_annotation_fields_from_params(
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["detections"]},
        _dataset(),
    )
    pipeline = PipelineConfig(transforms=(TransformConfig(name="MaskOnlyGeometry"),))
    catalog = _CatalogProvider((_capability("MaskOnlyGeometry", transform_type="dual", targets=("image", "mask")),))

    with pytest.raises(HostAdapterError) as error:
        validate_annotation_pipeline_compatibility(
            selection=selection,
            pipeline=pipeline,
            catalog_provider=catalog,
        )

    assert error.value.context["reason"] == "annotation_target_incompatible"
    assert error.value.context["field_name"] == "detections"
    assert error.value.context["target"] == "bboxes"
    assert error.value.context["transform_name"] == "MaskOnlyGeometry"


@pytest.mark.unit
def test_annotation_run_metadata_records_selected_transformed_copied_and_excluded_fields() -> None:
    selection = selected_annotation_fields_from_params(
        {annotation_field_param_name("secondary_detections"): False},
        _dataset(),
    )
    pipeline = PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip"),))
    catalog = _CatalogProvider(
        (_capability("HorizontalFlip", transform_type="dual", targets=("image", "mask", "bboxes", "keypoints")),)
    )

    target_fields, copy_fields = target_and_copy_fields(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog,
    )
    metadata = cast(
        dict[str, Any],
        annotation_run_metadata(
            selection=selection,
            pipeline=pipeline,
            catalog_provider=catalog,
        ),
    )
    transformed_fields = cast(list[dict[str, Any]], metadata["transformed_fields"])
    copied_fields = cast(list[dict[str, Any]], metadata["copied_fields"])
    excluded_fields = cast(list[dict[str, Any]], metadata["excluded_fields"])

    assert target_fields == ("detections", "keypoints", "segmentation")
    assert copy_fields == ("ground_truth",)
    assert metadata["fields"] == ["ground_truth", "detections", "keypoints", "segmentation"]
    assert [field["field_name"] for field in transformed_fields] == [
        "detections",
        "keypoints",
        "segmentation",
    ]
    assert [field["field_name"] for field in copied_fields] == ["ground_truth"]
    assert ("secondary_detections", "not_selected") in {
        (field["field_name"], field["reason"]) for field in excluded_fields
    }
