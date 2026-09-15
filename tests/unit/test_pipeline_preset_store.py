from __future__ import annotations

import json

import pytest

from albumentationsx_plugin.core import MediaIOError, PipelineConfig, PipelinePreset, TransformConfig
from albumentationsx_plugin.storage import FilePipelinePresetStore, build_dataset_run_dir, build_preset_key


@pytest.mark.unit
def test_pipeline_preset_store_saves_lists_loads_and_deletes_shared_presets(tmp_path) -> None:
    store = FilePipelinePresetStore(storage_root=tmp_path)
    preset = PipelinePreset(
        key=build_preset_key("Training defaults"),
        name="Training defaults",
        plugin_version="0.1.0",
        dependency_versions={"fiftyone": "1.19.0", "albumentationsx": "2.3.8", "albu-spec": "0.0.6"},
        pipeline=PipelineConfig(
            transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),),
            outputs_per_sample=2,
        ),
    )

    store.save_preset(preset)

    assert store.preset_dir == tmp_path / "presets"
    assert store.preset_path(preset.key).is_file()
    assert store.preset_dir != build_dataset_run_dir("dataset", "run", storage_root=tmp_path).parent
    assert store.list_preset_keys() == (preset.key,)
    assert store.list_presets() == (preset,)
    assert store.load_preset(preset.key) == preset

    store.delete_preset(preset.key)

    assert store.list_presets() == ()
    assert not store.preset_path(preset.key).exists()


@pytest.mark.unit
def test_pipeline_preset_store_rejects_key_mismatch(tmp_path) -> None:
    store = FilePipelinePresetStore(storage_root=tmp_path)
    preset_path = store.preset_path("expected")
    preset_path.parent.mkdir(parents=True)
    preset_path.write_text(
        json.dumps(
            PipelinePreset(
                key="other",
                name="Other",
                plugin_version="0.1.0",
                dependency_versions={},
                pipeline=PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip"),)),
            ).to_dict()
        ),
        encoding="utf-8",
    )

    with pytest.raises(MediaIOError) as error:
        store.load_preset("expected")

    assert error.value.context["reason"] == "preset_key_mismatch"


@pytest.mark.unit
def test_pipeline_preset_store_renames_without_overwriting_existing_preset(tmp_path) -> None:
    store = FilePipelinePresetStore(storage_root=tmp_path)
    source = PipelinePreset(
        key=build_preset_key("Training defaults"),
        name="Training defaults",
        plugin_version="0.1.0",
        dependency_versions={"fiftyone": "1.19.0"},
        pipeline=PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),)),
        created_at="2026-08-01T00:00:00Z",
    )
    collision = PipelinePreset(
        key=build_preset_key("Validation defaults"),
        name="Validation defaults",
        plugin_version="0.1.0",
        dependency_versions={"fiftyone": "1.19.0"},
        pipeline=PipelineConfig(transforms=(TransformConfig(name="VerticalFlip", params={"p": 1.0}),)),
    )
    renamed = PipelinePreset(
        key=collision.key,
        name="Validation defaults",
        plugin_version=source.plugin_version,
        dependency_versions=source.dependency_versions,
        pipeline=source.pipeline,
        created_at=source.created_at,
        updated_at="2026-08-02T00:00:00Z",
    )
    store.save_preset(source)
    store.save_preset(collision)

    with pytest.raises(MediaIOError) as error:
        store.rename_preset(source.key, renamed)

    assert error.value.context["reason"] == "preset_already_exists"
    assert store.load_preset(source.key) == source
    assert store.load_preset(collision.key) == collision

    store.rename_preset(source.key, renamed, overwrite=True)

    assert not store.preset_exists(source.key)
    assert store.load_preset(renamed.key) == renamed
