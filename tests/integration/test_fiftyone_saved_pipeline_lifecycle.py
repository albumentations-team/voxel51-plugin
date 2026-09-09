from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import fiftyone as fo
import numpy as np
import pytest

from albumentationsx_plugin.hosts.fiftyone.form_params import flatten_fiftyone_form_groups
from albumentationsx_plugin.hosts.fiftyone.operators import AugmentWithAlbumentationsX, ManageAlbumentationsXPresets
from albumentationsx_plugin.hosts.fiftyone.pipeline_loading import load_pipeline_draft, pipeline_draft_prompt_params
from albumentationsx_plugin.hosts.fiftyone.result_presentation import outcome_summary
from albumentationsx_plugin.storage import FilePipelinePresetStore
from albumentationsx_plugin.storage.images import write_rgb_image

pytestmark = pytest.mark.integration


def test_editor_saved_pipeline_lifecycle_preserves_source_and_rejects_unconfirmed_update(tmp_path):
    source = write_rgb_image(np.arange(720, dtype=np.uint8).reshape(12, 20, 3), tmp_path, "source.png")
    original_bytes = source.read_bytes()
    dataset = fo.Dataset(f"vox49-lifecycle-{uuid4().hex}")
    try:
        sample_id = dataset.add_sample(fo.Sample(filepath=str(source), tags=["source"]))
        ctx = SimpleNamespace(
            dataset=dataset, view=dataset, selected=[sample_id], params={}, trigger=lambda *a, **k: None
        )
        operator = AugmentWithAlbumentationsX()
        store = FilePipelinePresetStore(tmp_path / "storage")
        saved = []
        for name, p in [("Поворот", 1.0), ("Яркость", 0.0)]:
            ctx.params = pipeline_draft_prompt_params(
                {
                    "_pipeline_draft_id": uuid4().hex,
                    "_editor_action": "save",
                    "_storage_root": str(store.storage_root),
                    "save_preset_mode": "new",
                    "save_preset_name": name,
                    "transform": "HorizontalFlip",
                    "p": p,
                }
            )
            result = cast(dict[str, Any], operator.execute(ctx))
            assert result["execution_status"] == "preset_saved"
            saved.append(store.load_preset(result["preset_key"]))
        assert saved[0].key != saved[1].key
        draft = {}
        for preset, p in zip(saved, (1.0, 0.0), strict=True):
            draft = load_pipeline_draft(dataset, f"saved:{preset.key}", {}, storage_root=store.storage_root)
            assert draft["p"] == p
        path = store.preset_path(saved[0].key)
        before = path.read_bytes()
        draft.update(
            {
                "_editor_action": "save",
                "_storage_root": str(store.storage_root),
                "save_preset_mode": "update",
                "save_preset_target": saved[0].key,
                "save_preset_name": "Поворот исправленный",
                "p": 0.0,
            }
        )
        ctx.params = pipeline_draft_prompt_params(draft)
        assert flatten_fiftyone_form_groups(ctx.params)["save_preset_target"] == saved[0].key
        result = cast(dict[str, Any], operator.execute(ctx))
        assert result["execution_status"] == "failed"
        assert result["errors"][0]["context"]["reason_code"] == "confirmation_required"
        assert path.read_bytes() == before
        draft["save_preset_confirm_update"] = {saved[0].key: True}
        ctx.params = pipeline_draft_prompt_params(draft)
        result = cast(dict[str, Any], operator.execute(ctx))
        assert outcome_summary(result)[0] == "Pipeline updated"
        assert "Поворот исправленный" in outcome_summary(result)[1]
        assert store.load_preset(saved[0].key).pipeline.transforms[0].params["p"] == 0.0
        assert store.load_preset(saved[1].key) == saved[1]

        manager = ManageAlbumentationsXPresets()
        ctx.params = {"action": "export", "preset_key": saved[0].key, "_storage_root": str(store.storage_root)}
        exported = manager.execute(ctx)
        file = tmp_path / "portable.json"
        file.write_text(exported["importable_preset_json"], encoding="utf-8")
        ctx.params = {
            "action": "import",
            "import_mode": "file",
            "import_path": str(file),
            "_storage_root": str(tmp_path / "imported"),
        }
        assert manager.execute(ctx)["status"] == "ok"
        imported = FilePipelinePresetStore(tmp_path / "imported").load_preset(saved[0].key)
        assert imported == store.load_preset(saved[0].key)
        assert len(dataset) == 1 and dataset.first().tags == ["source"]
        assert source.read_bytes() == original_bytes
    finally:
        dataset.delete()
