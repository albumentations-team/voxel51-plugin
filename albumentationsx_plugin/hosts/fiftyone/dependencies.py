"""Runtime dependency helpers shared by FiftyOne operators."""

from __future__ import annotations

from typing import Final

RUNTIME_DEPENDENCY_PACKAGES: Final[dict[str, str]] = {
    "albumentations": "albumentationsx",
    "albu_spec": "albu-spec",
}


def is_known_runtime_dependency(error: ModuleNotFoundError) -> bool:
    """Return whether *error* names a dependency managed by plugin requirements."""

    return error.name in RUNTIME_DEPENDENCY_PACKAGES


def runtime_dependency_package_name(error: ModuleNotFoundError) -> str:
    """Return the pip package name that provides a missing runtime module."""

    module_name = error.name or ""
    return RUNTIME_DEPENDENCY_PACKAGES.get(module_name, module_name)
