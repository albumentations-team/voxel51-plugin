from __future__ import annotations

import hashlib
import posixpath
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

import pytest

from scripts.build_release_artifacts import (
    PLUGIN_FILE_INVENTORY,
    ROOT,
    build_release_artifacts,
    install_notes_name,
    plugin_archive_name,
)
from scripts.verify_release_tag import declared_versions

pytestmark = pytest.mark.unit


@pytest.fixture
def release_root(tmp_path):
    root = tmp_path / "source"
    names = (ROOT / PLUGIN_FILE_INVENTORY).read_text().splitlines()
    for name in [*names, PLUGIN_FILE_INVENTORY, "pyproject.toml", "uv.lock"]:
        if not name or name.startswith("#"):
            continue
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return root


@pytest.mark.parametrize("prefix", ["", "v"])
def test_release_artifact_contents_version_links_and_checksums(release_root, tmp_path, prefix):
    version = declared_versions(release_root)[0]
    tag = prefix + version
    artifacts = build_release_artifacts(tag, root=release_root, dist_dir=tmp_path / "dist")
    assert artifacts.version == version
    assert artifacts.plugin_zip.name == plugin_archive_name(version)
    assert artifacts.install_notes.name == install_notes_name(version)
    with ZipFile(artifacts.plugin_zip) as archive:
        names = set(archive.namelist())
        assert {
            "__init__.py",
            "fiftyone.yml",
            "requirements.txt",
            "albumentationsx_plugin/_version.py",
            "DESIGN.md",
            "docs/verification.md",
        } <= names
        for asset in ["albumentations.svg", "albumentations-white.svg", "toolbar.js"]:
            assert f"albumentationsx_plugin/hosts/fiftyone/assets/{asset}" in names
        assert not any(
            "audits/" in name or "/generated/" in name or "__pycache__" in name or name.endswith(".rst")
            for name in names
        )
        for name in names:
            if not name.endswith(".md"):
                continue
            for target in re.findall(r"\]\(([^)]+)\)", archive.read(name).decode()):
                link = urlsplit(target)
                if link.scheme or not link.path:
                    continue
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(link.path)))
                assert resolved in names, (name, target)
        extracted = tmp_path / "extracted"
        archive.extractall(extracted)
    result = subprocess.check_output(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import albumentationsx_plugin; print(albumentationsx_plugin.__version__)",
            str(extracted),
        ],
        cwd=tmp_path,
        text=True,
    )
    assert result.strip() == version
    notes = artifacts.install_notes.read_text()
    assert f"releases/download/{tag}/{plugin_archive_name(version)}" in notes
    assert f"releases/download/{tag}/SHA256SUMS" in notes
    for line in artifacts.checksums.read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((artifacts.checksums.parent / name).read_bytes()).hexdigest() == digest


def test_local_files_cannot_change_archive_contents(release_root, tmp_path):
    version = declared_versions(release_root)[0]
    before = build_release_artifacts(version, root=release_root, dist_dir=tmp_path / "before").plugin_zip.read_bytes()
    for name in [
        "docs/local-notes.md",
        "docs/audits/private.json",
        "sample_data/generated/local.png",
        "albumentationsx_plugin/local.py",
        "albumentationsx_plugin/__pycache__/local.pyc",
    ]:
        path = release_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Local data must never be distributed.")
    after = build_release_artifacts(version, root=release_root, dist_dir=tmp_path / "after").plugin_zip.read_bytes()
    assert before == after


def test_missing_required_artifact_input_fails(release_root, tmp_path):
    (release_root / "requirements.txt").unlink()
    with pytest.raises(ValueError, match="Required plugin file is missing"):
        build_release_artifacts(declared_versions(release_root)[0], root=release_root, dist_dir=tmp_path / "dist")
