from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_readme_documents_declared_fiftyone_operator_uris() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manifest = _load_yaml(ROOT / "fiftyone.yml")

    plugin_name = manifest["name"]
    assert isinstance(plugin_name, str)
    for operator_name in manifest["operators"]:
        assert isinstance(operator_name, str)
        assert f"{plugin_name}/{operator_name}" in readme


@pytest.mark.unit
def test_readme_documents_mvp_limitations_without_overclaiming_annotation_coverage() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "## MVP limitations" in readme
    assert "catalog-backed normal MVP choices" in readme
    assert "supported_with_defaults" in readme
    assert "Annotation-aware execution covers supported FiftyOne classification" in readme
    assert "Unsupported label classes" in readme
    assert "Dynamic forms hide advanced optional JSON fallback parameters" in readme


@pytest.mark.unit
def test_verification_doc_is_the_complete_local_gate_source() -> None:
    verification = (ROOT / "docs" / "verification.md").read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "pr-checklist.md").read_text(encoding="utf-8")

    for command in (
        "uv sync --group dev",
        "uv run pre-commit run --all-files",
        "uv run pytest",
        "uv run pyrefly check",
    ):
        assert command in verification
    assert "[Verification](verification.md)" in checklist


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value
