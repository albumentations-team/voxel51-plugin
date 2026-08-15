"""Execution-scope helpers for FiftyOne augmentation runs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

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


def selected_sample_ids_from_context(ctx: Any | None) -> tuple[str, ...]:
    """Return selected sample IDs from a FiftyOne operator context."""

    selected = getattr(ctx, "selected", ()) if ctx is not None else ()
    if isinstance(selected, Iterable) and not isinstance(selected, str | bytes | Mapping):
        return tuple(str(sample_id) for sample_id in selected)
    return ()


def source_selected_sample_ids(selected_sample_ids: Sequence[str], source_scope: str) -> tuple[str, ...]:
    """Return sample IDs that should constrain execution for the chosen scope."""

    _validate_execution_scope(source_scope)
    return tuple(selected_sample_ids) if source_scope == EXECUTION_SCOPE_SELECTED_SAMPLES else ()


def source_view_from_context(ctx: Any, source_scope: str) -> Any | None:
    """Return the FiftyOne view that should constrain execution for the chosen scope."""

    _validate_execution_scope(source_scope)
    if source_scope == EXECUTION_SCOPE_ENTIRE_DATASET:
        return None
    return getattr(ctx, "view", None)


def execution_scope_label(scope: str) -> str:
    """Return a human-readable execution-scope label."""

    return EXECUTION_SCOPE_LABELS.get(scope, scope)


def _validate_execution_scope(source_scope: str) -> None:
    if source_scope not in EXECUTION_SCOPE_CHOICES:
        raise ValueError(f"Unsupported execution scope: {source_scope!r}")


__all__ = [
    "EXECUTION_SCOPE_CHOICES",
    "EXECUTION_SCOPE_CURRENT_VIEW",
    "EXECUTION_SCOPE_ENTIRE_DATASET",
    "EXECUTION_SCOPE_FIELD_NAME",
    "EXECUTION_SCOPE_LABELS",
    "EXECUTION_SCOPE_SELECTED_SAMPLES",
    "default_execution_scope",
    "execution_scope_label",
    "selected_sample_ids_from_context",
    "selected_execution_scope",
    "source_selected_sample_ids",
    "source_view_from_context",
]
