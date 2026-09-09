"""Transient editor snapshots and explicit actions for the augmentation prompt."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any
from uuid import uuid4

from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    selected_execution_scope,
    selected_sample_ids_from_context,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import DRAFT_ID, flatten_fiftyone_form_groups

EDITOR_ACTION = "_editor_action"
EDITOR_DRAFT = "_editor_draft"
RESULT_DETAILS = "_result_details"
REVIEWED_SELECTION = "_reviewed_selection"
PREVIOUS_SELECTION = "_previous_selection"
DRAFT_DATASET = "_draft_dataset"
RETURN_ERRORS = "_return_errors"
ACTION_LABELS = {
    "preview": "Preview",
    "create": "Create augmented samples",
    "save": "Save pipeline",
    "validate": "Validate without creating samples",
}


def editor_action(params: Mapping[str, object]) -> str:
    """Infer the initial action for callers using the existing boolean API."""
    action = params.get(EDITOR_ACTION)
    if isinstance(action, str) and action in ACTION_LABELS:
        return action
    if params.get("save_preset_only") is True:
        return "save"
    if params.get("preview_only") is True:
        return "preview"
    if params.get("dry_run") is True:
        return "validate"
    return "create"


def execution_params(params: Mapping[str, object]) -> dict[str, object]:
    """Translate the UI action while retaining the legacy API's validation."""
    effective = dict(params)
    if EDITOR_ACTION in params:
        action = editor_action(params)
        effective.update(
            preview_only=action == "preview", dry_run=action == "validate", save_preset_only=action == "save"
        )
        # A name retained in a draft does not implicitly request a save.
        if action != "save":
            effective.pop("save_preset_name", None)
            effective.pop("save_preset_description", None)
    return effective


def snapshot_editor(ctx: Any, params: Mapping[str, object]) -> dict[str, object]:
    """Keep the submitted values, including disabled stages and invalid JSON."""
    draft = deepcopy(flatten_fiftyone_form_groups(params))
    draft.pop(RETURN_ERRORS, None)
    draft[DRAFT_ID] = uuid4().hex
    draft.setdefault(DRAFT_DATASET, getattr(getattr(ctx, "dataset", None), "name", None))
    selected = selected_sample_ids_from_context(ctx)
    draft[REVIEWED_SELECTION] = list(selected)
    if not draft.get("execution_scope"):
        draft["execution_scope"] = selected_execution_scope({}, selected_sample_ids=selected)
    return draft


def continuation_draft(draft: Mapping[str, object], *, action: str | None = None) -> dict[str, object]:
    """Give every return to the editor isolated form paths."""
    copied = deepcopy(dict(draft))
    copied[DRAFT_ID] = uuid4().hex
    copied[PREVIOUS_SELECTION] = copied.pop(REVIEWED_SELECTION, [])
    if action is not None:
        copied[EDITOR_ACTION] = action
        copied.update(preview_only=action == "preview", dry_run=action == "validate", save_preset_only=action == "save")
    return copied
