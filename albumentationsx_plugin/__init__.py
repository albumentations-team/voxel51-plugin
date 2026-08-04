"""AlbumentationsX plugin internals for FiftyOne."""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_PACKAGE_NAME = "fiftyone-albumentationsx-plugin"


def _version_from_project_metadata() -> str:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not pyproject_path.exists():
        return "0+unknown"

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    value = project.get("version", "0+unknown")
    return value if isinstance(value, str) else "0+unknown"


try:
    __version__ = version(_PACKAGE_NAME)
except PackageNotFoundError:
    __version__ = _version_from_project_metadata()

__all__ = ["__version__"]
