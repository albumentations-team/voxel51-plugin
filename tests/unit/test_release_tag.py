from __future__ import annotations

import pytest

from scripts.verify_release_tag import declared_versions, normalize_release_tag, verify_release_tag

pytestmark = pytest.mark.unit


@pytest.fixture
def release_root(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example-plugin"\nversion = "9.8.7"\nrequires-python = ">=3.10"\n'
    )
    (tmp_path / "fiftyone.yml").write_text("version: 9.8.7\n")
    (tmp_path / "uv.lock").write_text(
        'requires-python = ">=3.10"\n[[package]]\nname = "example-plugin"\nversion = "9.8.7"\n'
    )
    (tmp_path / "albumentationsx_plugin").mkdir()
    (tmp_path / "albumentationsx_plugin/_version.py").write_text('__version__ = "9.8.7"\n')
    return tmp_path


@pytest.mark.parametrize(("tag", "expected"), [("9.8.7", "9.8.7"), ("v9.8.7", "9.8.7"), ("  v9.8.7  ", "9.8.7")])
def test_normalize_release_tag_accepts_optional_v_prefix(tag, expected):
    assert normalize_release_tag(tag) == expected


def test_normalize_release_tag_rejects_empty_tag():
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_release_tag("  ")


def test_current_metadata_is_consistent():
    version = declared_versions()[0]
    assert verify_release_tag(f"v{version}") == version


def test_release_tag_reports_metadata_mismatch(release_root):
    with pytest.raises(ValueError, match="requires version '9.8.8'"):
        verify_release_tag("9.8.8", root=release_root)


@pytest.mark.parametrize("filename", ["fiftyone.yml", "uv.lock", "albumentationsx_plugin/_version.py"])
def test_release_tag_checks_all_shipped_version_sources(release_root, filename):
    path = release_root / filename
    path.write_text(path.read_text().replace("9.8.7", "9.8.6"))
    with pytest.raises(ValueError, match="found"):
        verify_release_tag("9.8.7", root=release_root)


def test_release_tag_reports_python_compatibility_mismatch(release_root):
    path = release_root / "uv.lock"
    path.write_text(path.read_text().replace(">=3.10", ">=3.11"))
    with pytest.raises(ValueError, match="Python compatibility mismatch"):
        verify_release_tag("v9.8.7", root=release_root)
