from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import fiftyone as fo
import pytest

from albumentationsx_plugin.core import (
    AugmentationInput,
    CapabilityStatus,
    HostAdapterError,
    PipelineConfig,
    TransformCapability,
    TransformConfig,
)
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    ANNOTATION_PAYLOAD_KEY,
    SELECTED_LABEL_FIELDS_PARAM_NAME,
    annotation_field_param_name,
    annotation_pipeline_compatibility_conflicts,
    annotation_run_metadata,
    annotation_target_requirements_from_inputs,
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
            "heatmap": _field(fo.Heatmap),
            "regression": _field(fo.Regression),
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


def _source_input_with_payload(payload: dict[str, object]) -> AugmentationInput:
    return AugmentationInput(
        sample_id="sample-1",
        filepath="/tmp/source.png",
        metadata={ANNOTATION_PAYLOAD_KEY: payload},
    )


def _detection_payload(*, with_mask: bool) -> dict[str, object]:
    detection: dict[str, object] = {
        "label": "object",
        "bounding_box": [0.1, 0.2, 0.3, 0.4],
    }
    if with_mask:
        detection["mask"] = [[1, 0], [0, 1]]
    return {
        "fields": {
            "detections": {
                "type": "detections",
                "detections": [detection],
            }
        }
    }


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
        "polylines",
        "heatmap",
    )
    assert {(field["field_name"], field["reason"], field["selected"]) for field in selection.excluded_fields} == {
        ("regression", "unsupported_label_type", False)
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
        "polylines",
        "heatmap",
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
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["regression"]},
        _dataset(),
    )

    with pytest.raises(HostAdapterError) as error:
        validate_selected_annotation_fields(selection)

    assert error.value.context["reason"] == "invalid_annotation_field_selection"
    assert error.value.context["field_name"] == "regression"
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
def test_annotation_pipeline_compatibility_allows_copied_heatmap_for_image_only_stages() -> None:
    selection = selected_annotation_fields_from_params(
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["heatmap"]},
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
def test_annotation_pipeline_compatibility_blocks_heatmap_with_mixed_image_only_stage() -> None:
    selection = selected_annotation_fields_from_params(
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["heatmap"]},
        _dataset(),
    )
    pipeline = PipelineConfig(
        transforms=(
            TransformConfig(name="HorizontalFlip"),
            TransformConfig(name="ColorOnly"),
        )
    )
    catalog = _CatalogProvider(
        (
            _capability("HorizontalFlip", transform_type="dual", targets=("image", "mask", "bboxes", "keypoints")),
            _capability("ColorOnly", transform_type="image_only", targets=("image",)),
        )
    )

    with pytest.raises(HostAdapterError) as error:
        validate_annotation_pipeline_compatibility(
            selection=selection,
            pipeline=pipeline,
            catalog_provider=catalog,
        )

    assert error.value.context["reason"] == "annotation_target_incompatible"
    assert error.value.context["field_name"] == "heatmap"
    assert error.value.context["target"] == "image"
    assert error.value.context["transform_name"] == "ColorOnly"
    conflicts = annotation_pipeline_compatibility_conflicts(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog,
    )
    assert conflicts[0]["reason"] == "image_only_stage_would_alter_heatmap"


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
def test_runtime_annotation_requirements_include_detection_instance_masks() -> None:
    requirements = annotation_target_requirements_from_inputs(
        (_source_input_with_payload(_detection_payload(with_mask=True)),)
    )

    assert requirements == {"detections": ("bboxes", "mask")}


@pytest.mark.unit
def test_runtime_annotation_requirements_include_heatmaps_as_images() -> None:
    requirements = annotation_target_requirements_from_inputs(
        (
            _source_input_with_payload(
                {
                    "fields": {
                        "heatmap": {
                            "type": "heatmap",
                            "map": [[0.0, 0.5], [1.0, 0.25]],
                        }
                    }
                }
            ),
        )
    )

    assert requirements == {"heatmap": ("image",)}


@pytest.mark.unit
def test_runtime_annotation_requirements_include_polylines_as_keypoints() -> None:
    requirements = annotation_target_requirements_from_inputs(
        (
            _source_input_with_payload(
                {
                    "fields": {
                        "polylines": {
                            "type": "polylines",
                            "polylines": [
                                {
                                    "label": "road",
                                    "points": [[[0.1, 0.2], [0.3, 0.4]]],
                                }
                            ],
                        }
                    }
                }
            ),
        )
    )

    assert requirements == {"polylines": ("keypoints",)}


@pytest.mark.unit
def test_runtime_detection_masks_require_mask_compatible_geometry() -> None:
    selection = selected_annotation_fields_from_params(
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["detections"]},
        _dataset(),
    )
    pipeline = PipelineConfig(transforms=(TransformConfig(name="BBoxOnlyGeometry"),))
    catalog = _CatalogProvider((_capability("BBoxOnlyGeometry", transform_type="dual", targets=("image", "bboxes")),))
    requirements = annotation_target_requirements_from_inputs(
        (_source_input_with_payload(_detection_payload(with_mask=True)),)
    )

    with pytest.raises(HostAdapterError) as error:
        validate_annotation_pipeline_compatibility(
            selection=selection,
            pipeline=pipeline,
            catalog_provider=catalog,
            runtime_target_requirements=requirements,
        )

    assert error.value.context["reason"] == "annotation_target_incompatible"
    assert error.value.context["field_name"] == "detections"
    assert error.value.context["target"] == "mask"
    assert error.value.context["transform_name"] == "BBoxOnlyGeometry"


@pytest.mark.unit
def test_runtime_bbox_only_detections_do_not_require_mask_compatible_geometry() -> None:
    selection = selected_annotation_fields_from_params(
        {SELECTED_LABEL_FIELDS_PARAM_NAME: ["detections"]},
        _dataset(),
    )
    pipeline = PipelineConfig(transforms=(TransformConfig(name="BBoxOnlyGeometry"),))
    catalog = _CatalogProvider((_capability("BBoxOnlyGeometry", transform_type="dual", targets=("image", "bboxes")),))
    requirements = annotation_target_requirements_from_inputs(
        (_source_input_with_payload(_detection_payload(with_mask=False)),)
    )

    validate_annotation_pipeline_compatibility(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog,
        runtime_target_requirements=requirements,
    )

    assert (
        annotation_pipeline_compatibility_conflicts(
            selection=selection,
            pipeline=pipeline,
            catalog_provider=catalog,
            runtime_target_requirements=requirements,
        )
        == ()
    )


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
            runtime_target_requirements={"detections": ("bboxes", "mask")},
        ),
    )
    transformed_fields = cast(list[dict[str, Any]], metadata["transformed_fields"])
    copied_fields = cast(list[dict[str, Any]], metadata["copied_fields"])
    excluded_fields = cast(list[dict[str, Any]], metadata["excluded_fields"])

    assert target_fields == ("detections", "keypoints", "segmentation", "polylines", "heatmap")
    assert copy_fields == ("ground_truth",)
    assert metadata["fields"] == ["ground_truth", "detections", "keypoints", "segmentation", "polylines", "heatmap"]
    assert [field["field_name"] for field in transformed_fields] == [
        "detections",
        "keypoints",
        "segmentation",
        "polylines",
        "heatmap",
    ]
    assert [field["field_name"] for field in copied_fields] == ["ground_truth"]
    assert metadata["runtime_target_requirements"] == {"detections": ["bboxes", "mask"]}
    assert ("secondary_detections", "not_selected") in {
        (field["field_name"], field["reason"]) for field in excluded_fields
    }
