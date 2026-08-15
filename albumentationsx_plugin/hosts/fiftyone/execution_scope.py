"""Execution-scope helpers for FiftyOne augmentation runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

EXECUTION_SCOPE_FIELD_NAME: Final[str] = "execution_scope"
EXECUTION_SCOPE_SELECTED_SAMPLES: Final[str] = "selected_samples"
EXECUTION_SCOPE_CURRENT_VIEW: Final[str] = "current_view"
EXECUTION_SCOPE_ENTIRE_DATASET: Final[str] = "entire_dataset"
EXECUTION_SCOPE_CHOICES: Final[tuple[str, ...]] = (
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    EXECUTION_SCOPE_CURRENT_VIEW,
    EXECUTION_SCOPE_ENTIRE_DATASET,
)
EXECUTION_SCOPE_LABELS: Final[dict[str, str]] = {
    EXECUTION_SCOPE_SELECTED_SAMPLES: "Selected samples",
    EXECUTION_SCOPE_CURRENT_VIEW: "Current view",
    EXECUTION_SCOPE_ENTIRE_DATASET: "Entire dataset",
}


def default_execution_scope(selected_sample_ids: Sequence[str]) -> str:
    """Return the safest default scope for the current selection state."""

    return EXECUTION_SCOPE_SELECTED_SAMPLES if selected_sample_ids else EXECUTION_SCOPE_CURRENT_VIEW


def selected_execution_scope(
    params: Mapping[str, object],
    *,
    selected_sample_ids: Sequence[str],
) -> str:
    """Return the requested execution scope or the context-aware default."""

    raw_value = params.get(EXECUTION_SCOPE_FIELD_NAME)
    if raw_value is None or raw_value == "":
        return default_execution_scope(selected_sample_ids)
    if isinstance(raw_value, str) and raw_value in EXECUTION_SCOPE_CHOICES:
        return raw_value
    raise ValueError(f"Unsupported execution scope: {raw_value!r}")


def execution_scope_label(scope: str) -> str:
    """Return a human-readable execution-scope label."""

    return EXECUTION_SCOPE_LABELS.get(scope, scope)


__all__ = [
    "EXECUTION_SCOPE_CHOICES",
    "EXECUTION_SCOPE_CURRENT_VIEW",
    "EXECUTION_SCOPE_ENTIRE_DATASET",
    "EXECUTION_SCOPE_FIELD_NAME",
    "EXECUTION_SCOPE_LABELS",
    "EXECUTION_SCOPE_SELECTED_SAMPLES",
    "default_execution_scope",
    "execution_scope_label",
    "selected_execution_scope",
]
