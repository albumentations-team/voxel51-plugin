from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_integration_guide_documents_declared_fiftyone_operator_uris() -> None:
    guide = (ROOT / "docs" / "albumentationsx-fiftyone-integration.md").read_text(encoding="utf-8")
    manifest = _load_yaml(ROOT / "fiftyone.yml")

    plugin_name = manifest["name"]
    assert isinstance(plugin_name, str)
    for operator_name in manifest["operators"]:
        assert isinstance(operator_name, str)
        assert f"`{operator_name}`" in guide
    assert f"`{plugin_name}/`" in guide


@pytest.mark.unit
def test_readme_documents_installation_and_current_limits() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "fiftyone plugins download albumentations-team/voxel51-plugin/<release-tag>" in readme
    assert "fiftyone plugins requirements @albumentations/albumentationsx --install" in readme
    assert "(docs/albumentationsx-fiftyone-integration.md)" in readme
    assert "DESIGN.md" not in readme


@pytest.mark.unit
def test_verification_doc_is_the_complete_local_gate_source() -> None:
    verification = (ROOT / "docs" / "verification.md").read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "pr-checklist.md").read_text(encoding="utf-8")

    for command in (
        "uv sync --group dev",
        "uv lock --check",
        "uv run pre-commit run --all-files",
        "uv run pytest --cov-fail-under=85",
        "uv run pyrefly check",
        "node --test tests/frontend/test_toolbar.cjs",
    ):
        assert command in verification
    assert "[Verification](verification.md)" in checklist


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value
