"""Verify that a release tag matches the plugin's declared version."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_VERSION = re.compile(r"^version:\s*(?P<version>\S+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ReleaseMetadata:
    """Version and compatibility declarations that must move together."""

    project_version: str
    plugin_version: str
    runtime_version: str
    lock_project_version: str
    project_requires_python: str
    lock_requires_python: str


def normalize_release_tag(tag: str) -> str:
    """Return a PEP 440 version from a conventional Git tag."""
    normalized = tag.strip()
    if normalized.startswith("v"):
        normalized = normalized[1:]

    if not normalized:
        raise ValueError("Release tag must not be empty")

    return normalized


def release_metadata(root: Path = ROOT) -> ReleaseMetadata:
    """Return release metadata declared in project files under *root*."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise ValueError("pyproject.toml must declare project.version")
    if not isinstance(project.get("requires-python"), str):
        raise ValueError("pyproject.toml must declare project.requires-python")

    manifest = (root / "fiftyone.yml").read_text(encoding="utf-8")
    match = _MANIFEST_VERSION.search(manifest)
    if match is None:
        raise ValueError("fiftyone.yml must declare version")

    lockfile = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    lock_requires_python = lockfile.get("requires-python")
    if not isinstance(lock_requires_python, str):
        raise ValueError("uv.lock must declare requires-python")

    runtime_tree = ast.parse((root / "albumentationsx_plugin/_version.py").read_text(encoding="utf-8"))
    runtime_versions = [
        node.value.value
        for node in runtime_tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
    ]
    if len(runtime_versions) != 1 or not isinstance(runtime_versions[0], str):
        raise ValueError("_version.py must declare a literal __version__")
    locked = [entry["version"] for entry in lockfile.get("package", []) if entry.get("name") == project.get("name")]
    if len(locked) != 1:
        raise ValueError("uv.lock must contain exactly one root project version")

    return ReleaseMetadata(
        project_version=project["version"],
        runtime_version=runtime_versions[0],
        lock_project_version=locked[0],
        plugin_version=match.group("version"),
        project_requires_python=project["requires-python"],
        lock_requires_python=lock_requires_python,
    )


def declared_versions(root: Path = ROOT) -> tuple[str, str]:
    """Return the package and FiftyOne plugin versions declared in *root*."""
    metadata = release_metadata(root)
    return metadata.project_version, metadata.plugin_version


def verify_release_tag(tag: str, root: Path = ROOT) -> str:
    """Ensure *tag*, package metadata, and plugin metadata use one version."""
    expected_version = normalize_release_tag(tag)
    metadata = release_metadata(root)
    declared = {
        "pyproject.toml": metadata.project_version,
        "fiftyone.yml": metadata.plugin_version,
        "_version.py": metadata.runtime_version,
        "uv.lock": metadata.lock_project_version,
    }
    mismatches = {name: version for name, version in declared.items() if version != expected_version}
    if mismatches:
        actual_versions = ", ".join(f"{name}={version}" for name, version in declared.items())
        raise ValueError(f"Release tag {tag!r} requires version {expected_version!r}; found {actual_versions}")
    if metadata.project_requires_python != metadata.lock_requires_python:
        raise ValueError(
            "Python compatibility mismatch: "
            f"pyproject.toml={metadata.project_requires_python}, uv.lock={metadata.lock_requires_python}"
        )

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
