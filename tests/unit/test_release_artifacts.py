from __future__ import annotations

from zipfile import ZipFile

import pytest

from scripts.build_release_artifacts import build_release_artifacts, install_notes_name, plugin_archive_name


@pytest.mark.unit
def test_build_release_artifacts_creates_plugin_zip_install_notes_and_checksums(tmp_path) -> None:
    (tmp_path / ".gitignore").write_text("*\n", encoding="utf-8")

    artifacts = build_release_artifacts("v0.1.0", dist_dir=tmp_path)

    assert artifacts.version == "0.1.0"
    assert artifacts.plugin_zip == tmp_path / plugin_archive_name("0.1.0")
    assert artifacts.install_notes == tmp_path / install_notes_name("0.1.0")
    assert artifacts.checksums == tmp_path / "SHA256SUMS"
    assert artifacts.plugin_zip in artifacts.checksummed_files
    assert artifacts.install_notes in artifacts.checksummed_files

    with ZipFile(artifacts.plugin_zip) as archive:
        names = set(archive.namelist())

    assert "__init__.py" in names
    assert "fiftyone.yml" in names
    assert "requirements.txt" in names
    assert "albumentationsx_plugin/__init__.py" in names
    assert "docs/verification.md" in names
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)

    install_notes = artifacts.install_notes.read_text(encoding="utf-8")
    assert "releases/download/v0.1.0/albumentationsx-fiftyone-plugin-v0.1.0.zip" in install_notes
    assert "fiftyone plugins requirements @albumentations/albumentationsx --install" in install_notes

    checksums = artifacts.checksums.read_text(encoding="utf-8")
    assert "albumentationsx-fiftyone-plugin-v0.1.0.zip" in checksums
    assert "albumentationsx-fiftyone-plugin-v0.1.0-install.md" in checksums
    assert ".gitignore" not in checksums
