from __future__ import annotations

import pytest

from scripts.verify_release_tag import normalize_release_tag, verify_release_tag


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("0.1.0", "0.1.0"),
        ("v0.1.0", "0.1.0"),
        ("  v0.1.0  ", "0.1.0"),
    ],
)
def test_normalize_release_tag_accepts_optional_v_prefix(tag: str, expected: str) -> None:
    assert normalize_release_tag(tag) == expected


@pytest.mark.unit
def test_normalize_release_tag_rejects_empty_tag() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_release_tag("  ")


@pytest.mark.unit
def test_current_metadata_matches_the_v0_1_0_release_tag() -> None:
    assert verify_release_tag("v0.1.0") == "0.1.0"


@pytest.mark.unit
def test_release_tag_reports_metadata_mismatch() -> None:
    with pytest.raises(ValueError, match="Release tag '0.1.1' requires version '0.1.1'"):
        verify_release_tag("0.1.1")
