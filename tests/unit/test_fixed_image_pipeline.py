from __future__ import annotations

import importlib.metadata
from typing import cast

import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.fixed import (
    build_fixed_pipeline_config,
    create_fixed_image_pipeline,
    validate_fixed_pipeline_config,
)
from albumentationsx_plugin.core import (
    MAX_PIPELINE_STEPS,
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
def test_horizontal_flip_pipeline_transforms_heatmap_image_sequence_target() -> None:
    config = build_fixed_pipeline_config(
        {
            "transform": "HorizontalFlip",
            "p": 1.0,
            "outputs_per_sample": 1,
        }
    )
    pipeline = create_fixed_image_pipeline(config)
    source = _rgb_array()
    heatmaps = np.arange(20, dtype=np.float32).reshape(1, 4, 5, 1)

    result = pipeline.apply(source, targets={"heatmaps": heatmaps})
    result_heatmaps = cast(np.ndarray, result.targets["heatmaps"])

    assert result_heatmaps.shape == heatmaps.shape
    np.testing.assert_array_equal(result_heatmaps[0, :, :, 0], heatmaps[0, :, ::-1, 0])


@pytest.mark.unit
def test_reference_image_pipeline_uses_external_metadata_targets() -> None:
    config = build_fixed_pipeline_config(
        {
            "transform": "HistogramMatching",
            "blend_ratio": [1.0, 1.0],
            "metadata_key": "ignored_user_value",
            "p": 1.0,
        }
    )

    assert config.transforms == (
        TransformConfig(name="HistogramMatching", params={"blend_ratio": [1.0, 1.0], "p": 1.0}),
    )

    pipeline = create_fixed_image_pipeline(config)
    source = _rgb_array(width=8, height=6)
    reference = np.full_like(source, 220)

    result = pipeline.apply(source, targets={"hm_metadata": [reference]})

    assert result.image.shape == source.shape
    assert result.replay["applied"] is True
    transforms = result.replay["transforms"]
    assert isinstance(transforms, list)
    first_transform = transforms[0]
    assert isinstance(first_transform, dict)
    assert first_transform["__class_fullname__"] == "HistogramMatching"


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
def test_fixed_pipeline_parses_advanced_json_fallback_parameters_before_config() -> None:
    config = build_fixed_pipeline_config(
        {
            "transform": "RandomCrop",
            "height": 4,
            "width": 5,
            "fill": "[1, 2, 3]",
            "fill_mask": "",
        }
    )

    assert config.transforms == (
        TransformConfig(
            name="RandomCrop",
            params={
                "height": 4,
                "width": 5,
                "fill": [1, 2, 3],
                "p": 1.0,
            },
        ),
    )


@pytest.mark.unit
def test_fixed_pipeline_rejects_invalid_advanced_json_fallback_parameters() -> None:
    with pytest.raises(InvalidParameterError) as error:
        build_fixed_pipeline_config(
            {
                "transform": "RandomCrop",
                "height": 4,
                "width": 5,
                "fill": "[1,",
            }
        )

    assert error.value.context["transform_name"] == "RandomCrop"
    assert error.value.context["parameter_name"] == "fill"
    assert error.value.context["reason_code"] == "invalid_json_parameter"
    assert error.value.context["expected"] == "tuple[float, ...] | float"
    assert error.value.context["received_value"] == "[1,"


@pytest.mark.unit
def test_fixed_pipeline_builds_more_than_three_stage_transform_chain() -> None:
    config = build_fixed_pipeline_config(
        {
            "pipeline_step_count": 4,
            "transform": "HorizontalFlip",
            "p": 1.0,
            "step_2_transform": "VerticalFlip",
            "step_2_p": 0.9,
            "step_3_transform": "ToGray",
            "step_3_method": "average",
            "step_3_p": 0.8,
            "step_4_transform": "Blur",
            "step_4_blur_range": [3, 3],
            "step_4_p": 0.7,
        }
    )

    assert config.transforms == (
        TransformConfig(name="HorizontalFlip", params={"p": 1.0}),
        TransformConfig(name="VerticalFlip", params={"p": 0.9}),
        TransformConfig(name="ToGray", params={"num_output_channels": 3, "method": "average", "p": 0.8}),
        TransformConfig(name="Blur", params={"blur_range": [3, 3], "p": 0.7}),
    )


@pytest.mark.unit
def test_fixed_pipeline_orders_enabled_stage_slots_without_losing_settings() -> None:
    config = build_fixed_pipeline_config(
        {
            "pipeline_step_count": 4,
            "transform": "HorizontalFlip",
            "pipeline_stage_order": 3,
            "p": 1.0,
            "step_2_pipeline_stage_enabled": False,
            "step_2_transform": "RandomBrightnessContrast",
            "step_2_brightness_range": [-0.5, 0.5],
            "step_2_contrast_range": [-0.5, 0.5],
            "step_2_p": 0.5,
            "step_3_transform": "VerticalFlip",
            "step_3_pipeline_stage_order": 1,
            "step_3_p": 0.8,
            "step_4_transform": "ToGray",
            "step_4_pipeline_stage_order": 2,
            "step_4_method": "average",
            "step_4_p": 0.7,
        }
    )

    assert config.transforms == (
        TransformConfig(name="VerticalFlip", params={"p": 0.8}),
        TransformConfig(name="ToGray", params={"num_output_channels": 3, "method": "average", "p": 0.7}),
        TransformConfig(name="HorizontalFlip", params={"p": 1.0}),
    )


@pytest.mark.unit
def test_fixed_pipeline_rejects_pipeline_with_no_enabled_stage() -> None:
    with pytest.raises(InvalidParameterError) as error:
        build_fixed_pipeline_config(
            {
                "pipeline_step_count": 2,
                "pipeline_stage_enabled": False,
                "step_2_pipeline_stage_enabled": False,
            }
        )

    assert error.value.context["parameter_name"] == "pipeline_stages"


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
        build_fixed_pipeline_config({"pipeline_step_count": MAX_PIPELINE_STEPS + 1})

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
