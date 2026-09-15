"""Navigate to created outputs and refresh the dataset."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from albumentationsx_plugin.hosts.fiftyone.operators.augment_values import _ctx_params
from albumentationsx_plugin.hosts.fiftyone.presets import (
    storage_root_from_params,
)


def _trigger_dataset_reload(ctx: Any, result: Any) -> None:
    if getattr(result, "dry_run", False) or getattr(result, "created_count", 0) < 1:
        return

    trigger = getattr(ctx, "trigger", None)
    if not callable(trigger):
        return
    trigger("reload_dataset")


def _open_created_outputs(ctx: Any, result: Mapping[str, object]) -> None:
    from fiftyone.operators.operations import Operations

    from albumentationsx_plugin.hosts.fiftyone.run_summary import build_run_summary

    summary = build_run_summary(
        ctx.dataset,
        str(result["run_key"]),
        storage_root=storage_root_from_params(_ctx_params(ctx)),
    )
    if summary.available_generated_sample_ids:
        Operations(ctx).set_view(view=ctx.dataset.select(list(summary.available_generated_sample_ids)))
