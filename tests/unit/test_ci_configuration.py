from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_ci_covers_operating_systems_and_python_versions() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    for os_name in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert f'"{os_name}"' in workflow

    for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
        assert f'"{version}"' in workflow

    assert workflow.count("runs-on: ${{ matrix.os }}") == 3
    assert "pre-commit run --all-files --show-diff-on-failure" in workflow
    assert "experimental-python:" in workflow
    assert "continue-on-error: true" in workflow
    assert "runs-on: ${{ matrix.os }}" in release_workflow
