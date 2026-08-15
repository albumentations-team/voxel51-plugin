from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_release_tag import normalize_release_tag, verify_release_tag

ROOT = Path(__file__).resolve().parents[2]


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


@pytest.mark.unit
def test_release_tag_reports_python_compatibility_mismatch(tmp_path) -> None:
    for filename in ("pyproject.toml", "fiftyone.yml", "uv.lock"):
        (tmp_path / filename).write_text((ROOT / filename).read_text(encoding="utf-8"), encoding="utf-8")

    lockfile = (tmp_path / "uv.lock").read_text(encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        lockfile.replace('requires-python = ">=3.10"', 'requires-python = ">=3.11"', 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Python compatibility mismatch"):
        verify_release_tag("v0.1.0", root=tmp_path)
