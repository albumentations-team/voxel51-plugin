from __future__ import annotations

import base64
import io
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import fiftyone as fo
import numpy as np
import pytest
from PIL import Image

from albumentationsx_plugin import __version__
from albumentationsx_plugin.core import PipelineConfig, PipelinePreset, TransformConfig
from albumentationsx_plugin.hosts.fiftyone.operators import AugmentWithAlbumentationsX
from albumentationsx_plugin.hosts.fiftyone.pipeline_loading import load_pipeline_draft, pipeline_draft_prompt_params
from albumentationsx_plugin.storage import FilePipelinePresetStore, FileRunStore
from albumentationsx_plugin.storage.images import write_rgb_image

pytestmark = pytest.mark.integration


def test_loaded_padded_crop_survives_preview_validation_creation_and_cleanup(tmp_path):
    source = write_rgb_image(np.full((32, 32, 3), 75, dtype=np.uint8), tmp_path, "source.png")
    before = source.read_bytes()
    dataset = fo.Dataset(f"vox79-padded-crop-{uuid4().hex}")
    storage = tmp_path / "runs"
    try:
        sample_id = dataset.add_sample(fo.Sample(filepath=str(source), tags=["source"]))
        preset = PipelinePreset(
            key="padded-crop",
            name="Padded crop",
            plugin_version=__version__,
            dependency_versions={},
            pipeline=PipelineConfig(
                transforms=(
                    TransformConfig("HorizontalFlip", {"p": 1.0}),
                    TransformConfig("RandomCrop", {"height": 64, "width": 64, "pad_if_needed": True, "p": 1.0}),
                )
            ),
        )
        FilePipelinePresetStore(storage).save_preset(preset)
        draft = load_pipeline_draft(dataset, "saved:padded-crop", {}, storage_root=storage)
        draft.update({"_storage_root": str(storage), "execution_scope": "selected_samples"})
        ctx = SimpleNamespace(
            dataset=dataset, view=dataset, selected=[sample_id], params={}, trigger=lambda *a, **k: None
        )
        operator = AugmentWithAlbumentationsX()
        for action, expected in [("preview", "preview"), ("validate", "dry_run"), ("create", "completed")]:
            ctx.params = pipeline_draft_prompt_params({**draft, "_editor_action": action})
            result = operator.execute(ctx)
            assert result["execution_status"] == expected, result.get("errors_json")
            assert result["error_count"] == 0
            if action == "preview":
                image_url = result["preview_1_output_image"]
                assert isinstance(image_url, str)
                data = base64.b64decode(image_url.split(",", 1)[1])
                assert Image.open(io.BytesIO(data)).size == (64, 64)
            if action != "create":
                assert len(dataset) == 1
        store = FileRunStore(dataset.name, storage_root=storage)
        run_key = result["run_key"]
        assert isinstance(run_key, str)
        manifest = store.load_manifest(run_key)
        assert manifest.plugin_version == __version__
        assert manifest.pipeline.transforms[1].params["pad_if_needed"] is True
        assert len(dataset) == 2
        output = cast(fo.Sample, dataset[manifest.created_sample_ids[0]])
        assert Image.open(output.filepath).size == (64, 64)
        from albumentationsx_plugin.hosts.fiftyone.run_cleanup import cleanup_run

        cleanup_run(dataset=cast(Any, dataset), run_key=manifest.run_key, confirmed=True, storage_root=storage)
        assert len(dataset) == 1 and dataset.first().tags == ["source"]
        assert source.read_bytes() == before
    finally:
        dataset.delete()
