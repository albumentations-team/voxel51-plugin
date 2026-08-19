from __future__ import annotations

import json
from typing import Any, cast

import albumentations as A
import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.pipeline import (
    AlbumentationsPipelineFactory,
    AlbumentationsTransformRegistry,
)
from albumentationsx_plugin.albumentations_backend.pipeline.coercion import coerce_transform_params
from albumentationsx_plugin.albumentations_backend.pipeline.replay import extract_replay
from albumentationsx_plugin.core import (
    FieldKind,
    FormFieldSchema,
    InvalidParameterError,
    ParameterSchemaProvider,
    PipelineConfig,
    TransformConfig,
    UnsupportedTransformError,
)


def _rgb_array(width: int = 6, height: int = 5) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 0] = np.arange(width, dtype=np.uint8)
    image[..., 1] = np.arange(height, dtype=np.uint8)[:, None] * 10
    image[..., 2] = 80
    return image


@pytest.mark.unit
def test_pipeline_factory_builds_allowed_transform_and_records_replay() -> None:
    config = PipelineConfig(
        transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),),
        seed=123,
    )
    runner = AlbumentationsPipelineFactory().create_runner(config)
    source = _rgb_array()

    result = runner.apply(source)

    np.testing.assert_array_equal(result.image, source[:, ::-1, :])
    assert result.replay["applied"] is True
    transforms = result.replay["transforms"]
    assert isinstance(transforms, list)
    first_transform = transforms[0]
    assert isinstance(first_transform, dict)
    assert first_transform["__class_fullname__"] == "HorizontalFlip"


@pytest.mark.unit
def test_pipeline_factory_constructs_catalog_transform_outside_fixed_slice() -> None:
    config = PipelineConfig(
        transforms=(TransformConfig(name="ToGray", params={"method": "average", "p": 1.0}),),
        seed=123,
    )
    runner = AlbumentationsPipelineFactory().create_runner(config)

    result = runner.apply(_rgb_array())

    assert result.image.shape == (5, 6, 3)
    assert result.image.dtype == np.uint8
    np.testing.assert_array_equal(result.image[..., 0], result.image[..., 1])
    np.testing.assert_array_equal(result.image[..., 1], result.image[..., 2])
    assert json.loads(json.dumps(result.replay)) == result.replay


@pytest.mark.unit
def test_pipeline_factory_rejects_unknown_excluded_and_arbitrary_transform_names() -> None:
    factory = AlbumentationsPipelineFactory()

    with pytest.raises(UnsupportedTransformError) as unknown_error:
        factory.create_runner(PipelineConfig(transforms=(TransformConfig(name="os.system"),)))

    with pytest.raises(UnsupportedTransformError) as excluded_error:
        factory.create_runner(PipelineConfig(transforms=(TransformConfig(name="Normalize"),)))

    assert unknown_error.value.context["reason_code"] == "unknown_transform"
    assert excluded_error.value.context["reason_code"] == "non_uint8_image_output"


@pytest.mark.unit
def test_pipeline_factory_rejects_invalid_params_before_constructor() -> None:
    factory = AlbumentationsPipelineFactory()

    with pytest.raises(InvalidParameterError) as missing_error:
        factory.create_runner(PipelineConfig(transforms=(TransformConfig(name="RandomCrop", params={"p": 1.0}),)))

    with pytest.raises(InvalidParameterError) as unknown_error:
        factory.create_runner(
            PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0, "legacy": True}),))
        )

    with pytest.raises(InvalidParameterError) as bounded_error:
        factory.create_runner(PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 2.0}),)))

    assert missing_error.value.context["reason_code"] == "missing_required_parameter"
    assert unknown_error.value.context["unknown_parameters"] == ["legacy"]
    assert bounded_error.value.context["bound"] == 1


@pytest.mark.unit
def test_parameter_coercion_enforces_exclusive_bounds_from_albu_spec_constraints() -> None:
    schema = (
        FormFieldSchema(
            name="alpha",
            kind=FieldKind.FLOAT,
            min_value=0.0,
            max_value=1.0,
            metadata={"constraints": {"gt": 0.0, "lt": 1.0}},
        ),
    )

    with pytest.raises(InvalidParameterError) as lower_error:
        coerce_transform_params(TransformConfig(name="ExclusiveTransform", params={"alpha": 0.0}), schema)

    with pytest.raises(InvalidParameterError) as upper_error:
        coerce_transform_params(TransformConfig(name="ExclusiveTransform", params={"alpha": 1.0}), schema)

    assert lower_error.value.context["bound"] == 0.0
    assert "greater than" in lower_error.value.message
    assert upper_error.value.context["bound"] == 1.0
    assert "less than" in upper_error.value.message
    assert coerce_transform_params(TransformConfig(name="ExclusiveTransform", params={"alpha": 0.5}), schema) == {
        "alpha": 0.5
    }


@pytest.mark.unit
def test_parameter_coercion_parses_json_fallback_values_and_reports_expected_shape() -> None:
    schema = (
        FormFieldSchema(
            name="advanced",
            kind=FieldKind.JSON,
            metadata={
                "schema_status": "json_fallback",
                "type_hint": "dict[str, object] | None",
            },
        ),
    )

    assert coerce_transform_params(
        TransformConfig(name="JsonTransform", params={"advanced": '{"alpha": [1, null]}'}),
        schema,
    ) == {"advanced": {"alpha": [1, None]}}

    with pytest.raises(InvalidParameterError) as error:
        coerce_transform_params(TransformConfig(name="JsonTransform", params={"advanced": '{"alpha":'}), schema)

    assert error.value.context["parameter_name"] == "advanced"
    assert error.value.context["reason_code"] == "invalid_json_parameter"
    assert error.value.context["expected"] == "dict[str, object] | None"
    assert error.value.context["received_value"] == '{"alpha":'


@pytest.mark.unit
def test_pipeline_factory_wraps_constructor_errors() -> None:
    factory = AlbumentationsPipelineFactory(
        registry=cast(AlbumentationsTransformRegistry, _RejectingRegistry()),
        parameter_schema_provider=cast(ParameterSchemaProvider, _EmptySchemaProvider()),
    )

    with pytest.raises(InvalidParameterError) as error:
        factory.create_runner(PipelineConfig(transforms=(TransformConfig(name="RejectingTransform"),)))

    assert error.value.context["parameter_name"] == "<constructor>"
    assert error.value.context["reason_code"] == "albumentations_constructor_error"
    assert "constructor rejected" in str(error.value.context["error"])


@pytest.mark.unit
def test_pipeline_runner_wraps_albumentations_runtime_errors() -> None:
    config = PipelineConfig(
        transforms=(TransformConfig(name="RandomCrop", params={"height": 8, "width": 8, "p": 1.0}),),
    )
    runner = AlbumentationsPipelineFactory().create_runner(config)

    with pytest.raises(InvalidParameterError) as error:
        runner.apply(_rgb_array(width=4, height=4))

    assert error.value.context["parameter_name"] == "<runtime>"
    assert error.value.context["reason_code"] == "albumentations_runtime_error"


@pytest.mark.unit
def test_pipeline_runner_seed_is_deterministic_for_new_runners() -> None:
    config = PipelineConfig(
        transforms=(
            TransformConfig(
                name="RandomBrightnessContrast",
                params={
                    "brightness_range": [-0.3, 0.3],
                    "contrast_range": [-0.3, 0.3],
                    "p": 1.0,
                },
            ),
        ),
        seed=42,
    )
    factory = AlbumentationsPipelineFactory()
    source = _rgb_array()

    first = factory.create_runner(config).apply(source)
    second = factory.create_runner(config).apply(source)

    np.testing.assert_array_equal(first.image, second.image)
    assert first.replay == second.replay


@pytest.mark.unit
def test_replay_extraction_normalizes_numpy_values() -> None:
    replay = extract_replay(
        {
            "replay": {
                "array": np.asarray([[1, 2], [3, 4]], dtype=np.int64),
                "scalar": np.float32(0.5),
                "nested": [{"values": np.asarray([1.0, 2.0], dtype=np.float32)}],
            }
        }
    )

    assert replay == {
        "array": [[1, 2], [3, 4]],
        "scalar": pytest.approx(0.5),
        "nested": [{"values": [pytest.approx(1.0), pytest.approx(2.0)]}],
    }
    assert json.loads(json.dumps(replay)) == replay


class _RejectingTransform(A.ImageOnlyTransform):
    def __init__(self, **_kwargs: Any) -> None:
        raise ValueError("constructor rejected")

    def apply(self, img: np.ndarray, **_params: Any) -> np.ndarray:
        return img


class _RejectingRegistry:
    def get_transform_class(self, _transform_name: str) -> type[A.BasicTransform]:
        return _RejectingTransform


class _EmptySchemaProvider:
    def get_parameter_schema(self, _transform_name: str) -> tuple[FormFieldSchema, ...]:
        return ()
