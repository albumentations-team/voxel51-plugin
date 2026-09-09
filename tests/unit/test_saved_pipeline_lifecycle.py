from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from albumentationsx_plugin.core import MediaIOError, PipelineConfig, PipelinePreset, PluginError, TransformConfig
from albumentationsx_plugin.hosts.fiftyone.editor_draft import continuation_draft, execution_params
from albumentationsx_plugin.hosts.fiftyone.forms.preset_saving import render_preset_save_controls
from albumentationsx_plugin.hosts.fiftyone.operators.manage_presets import ManageAlbumentationsXPresets
from albumentationsx_plugin.hosts.fiftyone.pipeline_presets import save_pipeline_preset_from_params
from albumentationsx_plugin.hosts.fiftyone.preset_management import execute_preset_management_action, preset_edit_group
from albumentationsx_plugin.storage import FilePipelinePresetStore
from albumentationsx_plugin.storage.preset_import import MAX_IMPORT_BYTES, read_preset_json_file

pytestmark = pytest.mark.unit


def _preset(key="legacy-flip", name="Flip ↔"):
    return PipelinePreset(
        key=key,
        name=name,
        description="Keep  two spaces\nand a new line",
        tags=("geometry", "training ✓"),
        pipeline=PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),)),
        plugin_version="0.1.0",
        dependency_versions={},
        created_at="2026-09-09T00:00:00Z",
        metadata={"custom": "preserved", "annotation_selection": {"selected_fields": []}},
    )


def _manage(root, action, **params):
    return execute_preset_management_action({"_storage_root": str(root), "action": action, **params})


@pytest.mark.parametrize(
    "names",
    [
        ("Flip ↔", "Brightness ☀"),
        ("Flip", "Flip"),
        ("Flip!", "Flip?"),
        ("Flip", "flip"),
        ("A B", "A  B"),
        ("A" * 100 + "1", "A" * 100 + "2"),
        ("↔", "☀"),
    ],
)
def test_create_preserves_colliding_names_as_independently_loadable_pipelines(tmp_path, names):
    store = FilePipelinePresetStore(tmp_path)
    presets = [
        save_pipeline_preset_from_params(
            {"save_preset_name": name, "transform": "HorizontalFlip", "p": probability},
            storage_root=tmp_path,
        ).preset
        for name, probability in zip(names, (1.0, 0.0), strict=True)
    ]
    assert presets[0].key != presets[1].key
    assert len(store.list_presets()) == 2
    for preset, name, probability in zip(presets, names, (1.0, 0.0), strict=True):
        loaded = store.load_preset(preset.key)
        assert loaded.name == name
        assert loaded.pipeline.transforms[0].params["p"] == probability


def test_update_requires_exact_target_and_confirmation_and_preserves_legacy_identity(tmp_path):
    store = FilePipelinePresetStore(tmp_path)
    original = _preset()
    store.save_preset(original)
    path = store.preset_path(original.key)
    before = path.read_bytes()
    params = {"save_preset_name": "New name ↔", "transform": "HorizontalFlip", "p": 0.0, "save_preset_mode": "update"}
    for delta in [
        {},
        {"save_preset_target": original.key},
        {"save_preset_target": "missing", "save_preset_confirm_update": {original.key: True}},
        {"save_preset_target": "../legacy-flip", "save_preset_confirm_update": {original.key: True}},
        {"save_preset_target": original.key, "save_preset_confirm_update": {original.key: True}, "p": 2.0},
    ]:
        with pytest.raises(PluginError):
            save_pipeline_preset_from_params({**params, **delta}, storage_root=tmp_path)
        assert path.read_bytes() == before
    result = save_pipeline_preset_from_params(
        {**params, "save_preset_target": original.key, "save_preset_confirm_update": {original.key: True}},
        storage_root=tmp_path,
    )
    assert result.to_dict()["preset_save_action"] == "updated"
    assert result.preset.key == original.key
    assert result.preset.created_at == original.created_at
    assert result.preset.tags == original.tags
    assert result.preset.metadata["custom"] == "preserved"
    assert result.preset.pipeline.transforms[0].params["p"] == 0.0
    assert store.list_presets() == (result.preset,)


def test_new_save_ignores_stale_load_and_update_targets(tmp_path):
    store = FilePipelinePresetStore(tmp_path)
    original = _preset()
    store.save_preset(original)
    result = save_pipeline_preset_from_params(
        {
            "save_preset_name": original.name,
            "transform": "HorizontalFlip",
            "p": 0.0,
            "pipeline_load_source": f"saved:{original.key}",
            "save_preset_target": original.key,
            "save_preset_confirm_update": {original.key: True},
            "save_preset_mode": "new",
        },
        storage_root=tmp_path,
    )
    assert result.preset.key != original.key
    assert store.load_preset(original.key) == original
    draft = {
        "_editor_action": "preview",
        "save_preset_name": "Retained",
        "save_preset_mode": "update",
        "save_preset_confirm_update": {original.key: True},
    }
    assert "save_preset_name" not in execution_params(draft)
    assert "save_preset_confirm_update" not in continuation_draft(draft)


@pytest.mark.parametrize("mode", ["json", "file"])
def test_import_export_roundtrip_and_explicit_overwrite(tmp_path, mode):
    source = FilePipelinePresetStore(tmp_path / "source")
    original = _preset()
    source.save_preset(original)
    exported = _manage(tmp_path / "source", "export", preset_key=original.key).to_dict()
    copyable = str(exported["importable_preset_json"])
    assert "Flip ↔" in copyable
    assert json.loads(copyable) == original.to_dict()
    file = tmp_path / "export.json"
    file.write_text(copyable, encoding="utf-8")
    params = {"import_mode": mode, "preset_json": copyable, "import_path": str(file)}
    dest = tmp_path / "dest"
    assert _manage(dest, "import", **params).status == "ok"
    store = FilePipelinePresetStore(dest)
    assert store.load_preset(original.key) == original
    before = store.preset_path(original.key).read_bytes()
    collision = _manage(dest, "import", **params)
    assert collision.errors[0]["reason"] == "preset_already_exists"
    assert store.preset_path(original.key).read_bytes() == before
    assert _manage(dest, "import", overwrite=True, **params).status == "ok"
    assert store.load_preset(original.key) == original


@pytest.mark.parametrize("mode", ["json", "file"])
@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("{bad", "invalid_preset_json"),
        ("[]", "summary_json_not_importable"),
        ('{"key":"legacy-flip","path":"/tmp/preset.json"}', "summary_json_not_importable"),
        ('"/tmp/preset.json"', "invalid_preset_shape"),
        ("{}", "invalid_preset_schema"),
        ('{"pipeline":{}}', "invalid_preset_schema"),
        ("NaN", "invalid_preset_json"),
    ],
)
def test_bad_import_preserves_original_bytes(tmp_path, mode, raw, reason):
    store = FilePipelinePresetStore(tmp_path)
    store.save_preset(_preset())
    path = store.preset_path("legacy-flip")
    before = path.read_bytes()
    file = tmp_path / "bad.json"
    file.write_text(raw, encoding="utf-8")
    result = _manage(tmp_path, "import", import_mode=mode, preset_json=raw, import_path=str(file), overwrite=True)
    assert result.status == "error"
    assert result.errors[0]["reason"] == reason
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        {"key": "../legacy-flip"},
        {"schema_version": 2},
        {"pipeline": {"transforms": [{"name": "UnknownTransform", "params": {}}]}},
    ],
)
def test_invalid_schema_or_pipeline_never_overwrites(tmp_path, change):
    store = FilePipelinePresetStore(tmp_path)
    original = _preset()
    store.save_preset(original)
    path = store.preset_path(original.key)
    before = path.read_bytes()
    result = _manage(tmp_path, "import", preset_json=json.dumps({**original.to_dict(), **change}), overwrite=True)
    assert result.status == "error"
    assert result.errors[0]["reason"] in {"invalid_preset_key", "invalid_preset_pipeline"}
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("", "missing_import_path"),
        ("relative.json", "invalid_import_path"),
        ("https://example.com/a.json", "invalid_import_path"),
        ("/tmp/a\0.json", "invalid_import_path"),
        ("/tmp/../a.json", "invalid_import_path"),
    ],
)
def test_import_path_validation_returns_structured_errors(tmp_path, value, reason):
    result = _manage(tmp_path, "import", import_mode="file", import_path=value)
    assert result.errors[0]["reason"] == reason
    assert not FilePipelinePresetStore(tmp_path).preset_dir.exists()


def test_import_rejects_non_json_file(tmp_path):
    file = tmp_path / "a.txt"
    file.write_text("{}", encoding="utf-8")
    result = _manage(tmp_path, "import", import_mode="file", import_path=str(file))
    assert result.errors[0]["reason"] == "non_json_import_file"
    assert not FilePipelinePresetStore(tmp_path).preset_dir.exists()


def test_local_file_errors_and_utf8_bom(tmp_path):
    file = tmp_path / "preset.json"
    assert (
        _manage(tmp_path, "import", import_mode="file", import_path=str(file)).errors[0]["reason"]
        == "missing_import_file"
    )
    file.mkdir()
    assert (
        _manage(tmp_path, "import", import_mode="file", import_path=str(file)).errors[0]["reason"] == "import_not_file"
    )
    file.rmdir()
    file.write_bytes(b"\xff\xfe")
    assert (
        _manage(tmp_path, "import", import_mode="file", import_path=str(file)).errors[0]["reason"]
        == "invalid_import_encoding"
    )
    file.write_text(json.dumps(_preset().to_dict()), encoding="utf-8-sig")
    assert _manage(tmp_path, "import", import_mode="file", import_path=str(file)).status == "ok"
    file.write_bytes(b" " * (MAX_IMPORT_BYTES + 1))
    with pytest.raises(MediaIOError, match="4 MiB"):
        read_preset_json_file(str(file))


def test_import_rejects_symlinks_and_fifos(tmp_path):
    if sys.platform == "win32":
        pytest.skip("Symlink and FIFO fixtures require Unix")
    else:
        path = tmp_path / "link.json"
        path.symlink_to(tmp_path / "missing.json")
        with pytest.raises(MediaIOError) as error:
            read_preset_json_file(str(path))
        assert error.value.context["reason"] == "unsafe_import_path"
        path.unlink()
        os.mkfifo(path)
        with pytest.raises(MediaIOError) as error:
            read_preset_json_file(str(path))
        assert error.value.context["reason"] == "import_not_file"


def test_edit_rename_duplicate_keep_other_pipelines_and_old_references(tmp_path):
    store = FilePipelinePresetStore(tmp_path)
    original = _preset()
    other = _preset("other", "Other")
    store.save_preset(original)
    store.save_preset(other)
    result = _manage(tmp_path, "rename", preset_key=original.key, new_preset_name=other.name)
    assert result.status == "ok" and result.preset_key == original.key
    group = preset_edit_group(original.key)
    edited = _manage(
        tmp_path,
        "edit",
        preset_key=original.key,
        **{
            group: {
                "name": "改名",
                "description": "Changed\nmetadata",
                "tags": ["↔"],
                "metadata_json": '{"note": "two  spaces"}',
            }
        },
    )
    assert edited.status == "ok"
    preset = store.load_preset(original.key)
    assert preset.name == "改名" and preset.tags == ("↔",)
    assert preset.pipeline == original.pipeline and preset.created_at == original.created_at
    assert preset.metadata == {"note": "two  spaces"}
    before = store.preset_path(original.key).read_bytes()
    for invalid in [{"metadata_json": "{"}, {"tags": [123]}, {"name": ""}, {"metadata_json": "NaN"}]:
        assert _manage(tmp_path, "edit", preset_key=original.key, **{group: invalid}).status == "error"
        assert store.preset_path(original.key).read_bytes() == before
    copied = _manage(tmp_path, "duplicate", preset_key=original.key, new_preset_name=preset.name)
    assert copied.status == "ok" and copied.preset_key != original.key
    assert store.load_preset(copied.preset_key).pipeline == original.pipeline
    assert store.load_preset(other.key) == other
    for action in ("rename", "edit", "duplicate", "delete"):
        assert _manage(tmp_path, action, new_preset_name="Unexpected", confirm_delete=True).status == "error"


def test_store_atomic_create_and_failed_write_preserve_existing(tmp_path, monkeypatch):
    store = FilePipelinePresetStore(tmp_path)
    original = _preset()

    def save(index):
        try:
            store.save_preset(replace(original, description=str(index)))
            return index
        except MediaIOError as error:
            assert error.context["reason"] == "preset_already_exists"
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        winners = [value for value in pool.map(save, range(4)) if value is not None]
    assert len(winners) == 1
    assert store.load_preset(original.key).description == str(winners[0])
    path = store.preset_path(original.key)
    before = path.read_bytes()
    with pytest.raises(TypeError):
        store.save_preset(replace(original, metadata={"nan": float("nan")}), overwrite=True)
    assert path.read_bytes() == before

    def fail_replace(*args):
        raise OSError("simulated disk error")

    monkeypatch.setattr(type(path), "replace", fail_replace)
    with pytest.raises(MediaIOError):
        store.save_preset(original, overwrite=True)
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".preset.*.tmp"))


def test_dynamic_forms_expose_only_selected_import_mode_and_isolate_edits(tmp_path):
    op = ManageAlbumentationsXPresets()
    for mode, visible, hidden in [("json", "preset_json", "import_path"), ("file", "import_path", "preset_json")]:
        ctx = SimpleNamespace(params={"action": "import", "import_mode": mode, "_storage_root": str(tmp_path)})
        fields = op.resolve_input(ctx).to_json()["type"]["properties"]
        assert visible in fields and hidden not in fields
    store = FilePipelinePresetStore(tmp_path)
    store.save_preset(_preset())
    store.save_preset(_preset("other", "Other"))
    ctx = SimpleNamespace(
        params={
            "action": "edit",
            "preset_key": "other",
            "_storage_root": str(tmp_path),
            preset_edit_group("legacy-flip"): {"name": "Stale"},
        }
    )
    fields = op.resolve_input(ctx).to_json()["type"]["properties"]
    edits = fields[preset_edit_group("other")]["type"]["properties"]
    assert edits["name"]["default"] == "Other"
    assert preset_edit_group("legacy-flip") not in fields


def test_update_form_blocks_unconfirmed_replacement(tmp_path):
    import fiftyone.operators.types as types

    store = FilePipelinePresetStore(tmp_path)
    store.save_preset(_preset())
    params: dict[str, object] = {
        "_editor_action": "save",
        "_storage_root": str(tmp_path),
        "save_preset_mode": "update",
        "save_preset_target": "legacy-flip",
    }
    inputs = types.Object()
    render_preset_save_controls(inputs, params)
    assert inputs.properties["save_preset_confirm_update"].type.properties["legacy-flip"].invalid is True
    assert "Flip ↔" in inputs.properties["save_preset_confirm_update"].type.properties["legacy-flip"].error_message
    params["save_preset_confirm_update"] = {"legacy-flip": True}
    inputs = types.Object()
    render_preset_save_controls(inputs, params)
    assert inputs.properties["save_preset_confirm_update"].type.properties["legacy-flip"].invalid is False
    other = _preset("other", "Other")
    store.save_preset(other)
    before = store.preset_path(other.key).read_bytes()
    params.update(save_preset_target=other.key, save_preset_name=other.name, transform="HorizontalFlip", p=0.0)
    inputs = types.Object()
    render_preset_save_controls(inputs, params)
    assert inputs.properties["save_preset_confirm_update"].type.properties["other"].invalid is True
    with pytest.raises(PluginError, match="Confirm replacement"):
        save_pipeline_preset_from_params(params, storage_root=tmp_path)
    assert store.preset_path(other.key).read_bytes() == before
