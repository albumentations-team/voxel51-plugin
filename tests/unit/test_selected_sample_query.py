from types import SimpleNamespace
from typing import Any, cast

import pytest

from albumentationsx_plugin.core import HostAdapterError
from albumentationsx_plugin.hosts.fiftyone.samples import adapter as module

pytestmark = pytest.mark.unit


class SelectedView:
    media_type = "image"

    def __init__(self):
        self.queries = []

    def __iter__(self):
        pytest.fail("Selected-sample execution must not iterate unrelated samples")

    def select(self, ids):
        self.queries.append(tuple(ids))
        return [SimpleNamespace(id=id_) for id_ in ["first", "second"] if id_ in ids]


def test_adapter_queries_active_view_and_preserves_requested_order(monkeypatch):
    view = SelectedView()
    dataset = SimpleNamespace(name="selected-query", media_type="image")
    monkeypatch.setattr(module, "resolve_annotation_fields", lambda *a, **k: ((), ()))
    monkeypatch.setattr(module, "sample_to_augmentation_input", lambda sample, **k: sample.id)
    adapter = module.FiftyOneSampleAdapter(cast(Any, dataset), view=view, selected_sample_ids=("second", "first"))
    assert list(adapter.iter_inputs()) == ["second", "first"]
    assert view.queries == [("second", "first")]
    missing = module.FiftyOneSampleAdapter(cast(Any, dataset), view=view, selected_sample_ids=("first", "outside-view"))
    with pytest.raises(HostAdapterError) as error:
        list(missing.iter_inputs())
    assert error.value.context["sample_ids"] == ["outside-view"]
