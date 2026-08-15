from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest

from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CURRENT_VIEW,
    EXECUTION_SCOPE_ENTIRE_DATASET,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    selected_sample_ids_from_context,
    source_selected_sample_ids,
    source_view_from_context,
)


@pytest.mark.unit
def test_selected_sample_ids_from_context_returns_normalized_ids() -> None:
    ctx = SimpleNamespace(selected=("sample-1", 2))

    assert selected_sample_ids_from_context(ctx) == ("sample-1", "2")


@pytest.mark.unit
@pytest.mark.parametrize(
    "selected",
    [
        None,
        "sample-1",
        b"sample-1",
        {"id": "sample-1"},
    ],
)
def test_selected_sample_ids_from_context_ignores_non_sequence_values(selected: object) -> None:
    ctx = SimpleNamespace(selected=selected)

    assert selected_sample_ids_from_context(ctx) == ()


@pytest.mark.unit
def test_source_view_from_context_routes_supported_scopes() -> None:
    view = object()
    ctx = SimpleNamespace(view=view)

    assert source_view_from_context(ctx, EXECUTION_SCOPE_SELECTED_SAMPLES) is view
    assert source_view_from_context(ctx, EXECUTION_SCOPE_CURRENT_VIEW) is view
    assert source_view_from_context(ctx, EXECUTION_SCOPE_ENTIRE_DATASET) is None


@pytest.mark.unit
def test_source_selected_sample_ids_routes_supported_scopes() -> None:
    selected_sample_ids = ("sample-1", "sample-2")

    assert source_selected_sample_ids(selected_sample_ids, EXECUTION_SCOPE_SELECTED_SAMPLES) == selected_sample_ids
    assert source_selected_sample_ids(selected_sample_ids, EXECUTION_SCOPE_CURRENT_VIEW) == ()
    assert source_selected_sample_ids(selected_sample_ids, EXECUTION_SCOPE_ENTIRE_DATASET) == ()


@pytest.mark.unit
@pytest.mark.parametrize(
    "helper",
    [
        lambda: source_view_from_context(SimpleNamespace(view=object()), "unsupported"),
        lambda: source_selected_sample_ids(("sample-1",), "unsupported"),
    ],
)
def test_scope_routing_rejects_unknown_scope(helper: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match="Unsupported execution scope"):
        helper()
