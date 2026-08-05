"""Verify that a release tag matches the plugin's declared version."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_VERSION = re.compile(r"^version:\s*(?P<version>\S+)\s*$", re.MULTILINE)


def normalize_release_tag(tag: str) -> str:
    """Return a PEP 440 version from a conventional Git tag."""
    normalized = tag.strip()
    if normalized.startswith("v"):
        normalized = normalized[1:]

    if not normalized:
        raise ValueError("Release tag must not be empty")

    return normalized


def declared_versions(root: Path = ROOT) -> tuple[str, str]:
    """Return the package and FiftyOne plugin versions declared in *root*."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise ValueError("pyproject.toml must declare project.version")

    manifest = (root / "fiftyone.yml").read_text(encoding="utf-8")
    match = _MANIFEST_VERSION.search(manifest)
    if match is None:
        raise ValueError("fiftyone.yml must declare version")

    return project["version"], match.group("version")


def verify_release_tag(tag: str, root: Path = ROOT) -> str:
    """Ensure *tag*, package metadata, and plugin metadata use one version."""
    expected_version = normalize_release_tag(tag)
    project_version, plugin_version = declared_versions(root)
    declared = {"pyproject.toml": project_version, "fiftyone.yml": plugin_version}
    mismatches = {name: version for name, version in declared.items() if version != expected_version}
    if mismatches:
        actual_versions = ", ".join(f"{name}={version}" for name, version in declared.items())
        raise ValueError(f"Release tag {tag!r} requires version {expected_version!r}; found {actual_versions}")

    return expected_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, with or without a leading 'v'")
    args = parser.parse_args(argv)

    try:
        version = verify_release_tag(args.tag)
    except ValueError as error:
        parser.error(str(error))

    print(f"Release metadata matches tag {args.tag}: version {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
