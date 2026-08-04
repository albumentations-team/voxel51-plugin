from __future__ import annotations

import importlib.metadata

import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.fixed import (
    build_fixed_pipeline_config,
    create_fixed_image_pipeline,
    validate_fixed_pipeline_config,
)
from albumentationsx_plugin.core import (
    InvalidParameterError,
    PipelineConfig,
    TransformConfig,
    UnsupportedTransformError,
)


def _rgb_array(width: int = 5, height: int = 4) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 0] = np.arange(width, dtype=np.uint8)
    image[..., 1] = np.arange(height, dtype=np.uint8)[:, None]
    return image


@pytest.mark.unit
def test_fixed_pipeline_uses_albumentationsx_runtime_package() -> None:
    assert importlib.metadata.version("albumentationsx").startswith("2.3.")


@pytest.mark.unit
def test_horizontal_flip_pipeline_transforms_rgb_array_and_records_replay() -> None:
    config = build_fixed_pipeline_config(
        {
            "transform": "HorizontalFlip",
            "p": 1.0,
            "outputs_per_sample": 1,
        }
    )
    pipeline = create_fixed_image_pipeline(config)
    source = _rgb_array()

    result = pipeline.apply(source)

    np.testing.assert_array_equal(result.image, source[:, ::-1, :])
    assert result.replay["applied"] is True
    transforms = result.replay["transforms"]
    assert isinstance(transforms, list)
    first_transform = transforms[0]
    assert isinstance(first_transform, dict)
    assert first_transform["__class_fullname__"] == "HorizontalFlip"


@pytest.mark.unit
def test_fixed_pipeline_builds_ordered_transform_chain() -> None:
    config = build_fixed_pipeline_config(
        {
            "pipeline_step_count": 3,
            "transform": "HorizontalFlip",
            "p": 1.0,
            "step_2_transform": "RandomBrightnessContrast",
            "step_2_brightness_range": [-0.1, 0.1],
            "step_2_contrast_range": [-0.2, 0.2],
            "step_2_p": 0.5,
            "step_3_transform": "RandomCrop",
            "step_3_height": 4,
            "step_3_width": 5,
            "step_3_p": 1.0,
        }
    )

    assert config.transforms == (
        TransformConfig(name="HorizontalFlip", params={"p": 1.0}),
        TransformConfig(
            name="RandomBrightnessContrast",
            params={
                "p": 0.5,
                "brightness_range": [-0.1, 0.1],
                "contrast_range": [-0.2, 0.2],
            },
        ),
        TransformConfig(name="RandomCrop", params={"p": 1.0, "height": 4, "width": 5}),
    )


@pytest.mark.unit
def test_fixed_pipeline_executes_ordered_transform_chain() -> None:
    config = build_fixed_pipeline_config(
        {
            "pipeline_step_count": 2,
            "transform": "HorizontalFlip",
            "p": 1.0,
            "step_2_transform": "HorizontalFlip",
            "step_2_p": 1.0,
        }
    )
    pipeline = create_fixed_image_pipeline(config)
    source = _rgb_array()

    result = pipeline.apply(source)

    np.testing.assert_array_equal(result.image, source)
    transforms = result.replay["transforms"]
    assert isinstance(transforms, list)
    transform_names: list[object] = []
    for transform in transforms:
        assert isinstance(transform, dict)
        transform_names.append(transform["__class_fullname__"])
    assert transform_names == ["HorizontalFlip", "HorizontalFlip"]


@pytest.mark.unit
def test_random_brightness_contrast_config_uses_albumentationsx_range_params() -> None:
    config = build_fixed_pipeline_config(
        {
            "transform": "RandomBrightnessContrast",
            "brightness_range_min": -0.1,
            "brightness_range_max": 0.3,
            "contrast_range_min": -0.4,
            "contrast_range_max": 0.2,
        }
    )

    assert config.transforms == (
        TransformConfig(
            name="RandomBrightnessContrast",
            params={
                "p": 1.0,
                "brightness_range": [-0.1, 0.3],
                "contrast_range": [-0.4, 0.2],
            },
        ),
    )


@pytest.mark.unit
def test_fixed_pipeline_accepts_dynamic_form_parameter_names() -> None:
    brightness_config = build_fixed_pipeline_config(
        {
            "transform": "RandomBrightnessContrast",
            "brightness_range": [-0.1, 0.3],
            "contrast_range": [-0.4, 0.2],
        }
    )
    crop_config = build_fixed_pipeline_config(
        {
            "transform": "RandomCrop",
            "height": 16,
            "width": 17,
        }
    )

    assert brightness_config.transforms[0].params["brightness_range"] == [-0.1, 0.3]
    assert brightness_config.transforms[0].params["contrast_range"] == [-0.4, 0.2]
    assert crop_config.transforms[0].params["height"] == 16
    assert crop_config.transforms[0].params["width"] == 17


@pytest.mark.unit
def test_fixed_pipeline_builds_catalog_backed_transform_configs() -> None:
    config = build_fixed_pipeline_config(
        {
            "pipeline_step_count": 3,
            "transform": "ToGray",
            "method": "average",
            "p": 1.0,
            "step_2_transform": "Blur",
            "step_2_blur_range": [3, 5],
            "step_2_p": 1.0,
            "step_3_transform": "CoarseDropout",
            "step_3_num_holes_range": [1, 1],
            "step_3_hole_height_range": [0.1, 0.1],
            "step_3_hole_width_range": [0.1, 0.1],
            "step_3_p": 1.0,
        }
    )

    assert config.options["source"] == "catalog_mvp_pipeline"
    assert config.transforms == (
        TransformConfig(name="ToGray", params={"num_output_channels": 3, "method": "average", "p": 1.0}),
        TransformConfig(name="Blur", params={"blur_range": [3, 5], "p": 1.0}),
        TransformConfig(
            name="CoarseDropout",
            params={
                "num_holes_range": [1, 1],
                "hole_height_range": [0.1, 0.1],
                "hole_width_range": [0.1, 0.1],
                "p": 1.0,
            },
        ),
    )


@pytest.mark.unit
def test_random_crop_validates_source_image_dimensions_before_execution() -> None:
    config = build_fixed_pipeline_config(
        {
            "transform": "RandomCrop",
            "crop_height": 8,
            "crop_width": 8,
        }
    )

    with pytest.raises(InvalidParameterError) as error:
        validate_fixed_pipeline_config(config, image_shape=(4, 5, 3))

    assert error.value.context["transform_name"] == "RandomCrop"
    assert error.value.context["parameter_name"] == "height"
    assert error.value.context["image_value"] == 4


@pytest.mark.unit
def test_fixed_pipeline_rejects_unknown_transform_and_invalid_parameters() -> None:
    with pytest.raises(UnsupportedTransformError) as unsupported_error:
        build_fixed_pipeline_config({"transform": "Normalize"})

    with pytest.raises(InvalidParameterError) as output_count_error:
        build_fixed_pipeline_config({"outputs_per_sample": 4})

    with pytest.raises(InvalidParameterError) as step_count_error:
        build_fixed_pipeline_config({"pipeline_step_count": 4})

    with pytest.raises(InvalidParameterError) as range_error:
        build_fixed_pipeline_config(
            {
                "transform": "RandomBrightnessContrast",
                "brightness_range_min": 0.5,
                "brightness_range_max": -0.5,
            }
        )

    with pytest.raises(InvalidParameterError) as unknown_param_error:
        validate_fixed_pipeline_config(
            PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0, "legacy": True}),))
        )

    with pytest.raises(InvalidParameterError) as direct_probability_error:
        validate_fixed_pipeline_config(
            PipelineConfig(
                transforms=(
                    TransformConfig(
                        name="RandomBrightnessContrast",
                        params={"p": 2.0, "brightness_range": [-0.2, 0.2], "contrast_range": [-0.2, 0.2]},
                    ),
                )
            )
        )

    assert unsupported_error.value.context["reason_code"] == "non_uint8_image_output"
    assert output_count_error.value.context["parameter_name"] == "outputs_per_sample"
    assert step_count_error.value.context["parameter_name"] == "pipeline_step_count"
    assert range_error.value.context["parameter_name"] == "brightness_range"
    assert direct_probability_error.value.context["parameter_name"] == "p"
    assert unknown_param_error.value.context["unknown_parameters"] == ["legacy"]
