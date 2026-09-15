from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from albumentationsx_plugin.albumentations_backend.fixed import (
    build_fixed_pipeline_config,
    create_fixed_image_pipeline,
)
from albumentationsx_plugin.core import PipelineConfig, PipelinePreset, TransformConfig
from albumentationsx_plugin.hosts.fiftyone.form_params import flatten_fiftyone_form_groups
from albumentationsx_plugin.hosts.fiftyone.pipeline_loading import load_pipeline_draft, pipeline_draft_prompt_params
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import save_pipeline_preset_from_params
from albumentationsx_plugin.storage import FilePipelinePresetStore

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("crop_stage", [1, 2])
def test_imported_padding_survives_edit_save_and_execution(tmp_path, crop_stage):
    crop = TransformConfig(name="RandomCrop", params={"height": 64, "width": 64, "pad_if_needed": True, "p": 1.0})
    transforms = (crop,) if crop_stage == 1 else (TransformConfig(name="HorizontalFlip", params={"p": 1.0}), crop)
    preset = PipelinePreset(
        key="padded-crop",
        name="Padded crop",
        pipeline=PipelineConfig(transforms=transforms),
        plugin_version="0.1.0",
        dependency_versions={},
    )
    store = FilePipelinePresetStore(storage_root=tmp_path)
    store.save_preset(PipelinePreset.from_dict(preset.to_dict()))
    dataset = SimpleNamespace(name="padding", media_type="image", get_field_schema=lambda: {})

    draft = load_pipeline_draft(dataset, "saved:padded-crop", {}, storage_root=tmp_path)
    params = flatten_fiftyone_form_groups(pipeline_draft_prompt_params(draft))
    config = build_fixed_pipeline_config(params)
    assert config.transforms[crop_stage - 1].params["pad_if_needed"] is True
    image = np.full((32, 32, 3), 75, dtype=np.uint8)
    assert create_fixed_image_pipeline(config).apply(image).image.shape == (64, 64, 3)

    saved = save_pipeline_preset_from_params(
        {**params, "save_preset_name": "Edited padded crop"}, dataset=dataset, storage_root=tmp_path
    ).preset
    exported = PipelinePreset.from_dict(store.load_preset(saved.key).to_dict())
    assert exported.pipeline.transforms[crop_stage - 1].params["pad_if_needed"] is True
    assert create_fixed_image_pipeline(exported.pipeline).apply(image).image.shape == (64, 64, 3)


def test_nondefault_brightness_option_survives_editor_conversion():
    config = build_fixed_pipeline_config(
        {"transform": "RandomBrightnessContrast", "brightness_by_max": True, "ensure_safe_output": True, "p": 1.0}
    )
    assert config.transforms[0].params["brightness_by_max"] is True
    assert config.transforms[0].params["ensure_safe_output"] is True


def test_prepared_pipeline_does_not_reconstruct_catalog_or_transforms(monkeypatch):
    config = build_fixed_pipeline_config({"transform": "HorizontalFlip", "p": 1.0})
    pipeline = create_fixed_image_pipeline(config)

    def unexpected(*args, **kwargs):
        pytest.fail("A prepared pipeline must not rebuild catalogs or transforms per output")

    from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
    from albumentationsx_plugin.albumentations_backend.pipeline.factory import AlbumentationsPipelineFactory

    monkeypatch.setattr(AlbuSpecCatalogProvider, "get_transform_capability", unexpected)
    monkeypatch.setattr(AlbumentationsPipelineFactory, "_build_transforms", unexpected)
    image = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
    for _ in range(3):
        np.testing.assert_array_equal(pipeline.apply(image).image, image[:, ::-1])


def test_shape_checks_still_run_for_each_prepared_pipeline_input():
    config = build_fixed_pipeline_config({"transform": "RandomCrop", "height": 8, "width": 8, "p": 1.0})
    pipeline = create_fixed_image_pipeline(config)
    assert pipeline.apply(np.zeros((16, 16, 3), dtype=np.uint8)).image.shape == (8, 8, 3)
    from albumentationsx_plugin.core import InvalidParameterError

    with pytest.raises(InvalidParameterError, match="exceeds the image dimension"):
        pipeline.apply(np.zeros((4, 4, 3), dtype=np.uint8))
    padded = replace(
        config,
        transforms=(TransformConfig(name="RandomCrop", params={**config.transforms[0].params, "pad_if_needed": True}),),
    )
    assert create_fixed_image_pipeline(padded).apply(np.zeros((4, 4, 3), dtype=np.uint8)).image.shape == (8, 8, 3)
