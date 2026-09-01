from __future__ import annotations

import pytest

from scripts.smoke_supported_transforms import SMOKE_PARAMETER_OVERRIDES, smoke_supported_transforms


@pytest.mark.unit
def test_supported_transform_smoke_overrides_cover_known_default_gaps() -> None:
    results = smoke_supported_transforms(transform_names=tuple(SMOKE_PARAMETER_OVERRIDES))

    assert len(results) == len(SMOKE_PARAMETER_OVERRIDES)
    assert all(result.status == "passed" for result in results)


@pytest.mark.unit
def test_supported_transform_smoke_reports_unknown_requested_transform() -> None:
    results = smoke_supported_transforms(transform_names=("NotARealTransform",))

    assert len(results) == 1
    assert results[0].transform_name == "NotARealTransform"
    assert results[0].status == "failed"
    assert results[0].reason_code == "unknown_or_unselectable_transform"
