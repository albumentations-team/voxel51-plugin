from __future__ import annotations

import importlib.util
import pathlib
import re
import tomllib
from types import ModuleType
from typing import Any

import yaml

import albumentationsx_plugin

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_plugin_entrypoint() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fiftyone_plugin_entrypoint", ROOT / "__init__.py")
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


def test_plugin_metadata_matches_package_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = _load_yaml(ROOT / "fiftyone.yml")

    assert manifest["name"] == "@albumentations/albumentationsx"
    assert manifest["type"] == "plugin"
    assert manifest["version"] == pyproject["project"]["version"] == albumentationsx_plugin.__version__
    assert manifest["fiftyone"]["version"] == ">=1.19,<2"


def test_plugin_requirements_include_runtime_dependencies() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirement_names = {
        _requirement_name(line)
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    for requirement in pyproject["project"]["dependencies"]:
        assert _requirement_name(requirement) in requirement_names


def test_plugin_manifest_declares_registered_operators() -> None:
    manifest = _load_yaml(ROOT / "fiftyone.yml")

    assert manifest["operators"] == [
        "augment_with_albumentationsx",
        "view_albumentationsx_run",
        "delete_albumentationsx_run",
    ]


def test_root_entrypoint_registers_declared_operators() -> None:
    module = _load_plugin_entrypoint()

    class Registrar:
        def __init__(self) -> None:
            self.registered: list[type[object]] = []

        def register(self, cls: type[object]) -> None:
            self.registered.append(cls)

    registrar = Registrar()

    assert module.register(registrar) is None
    assert [operator.__name__ for operator in registrar.registered] == [
        "AugmentWithAlbumentationsX",
        "ViewAlbumentationsXRun",
        "DeleteAlbumentationsXRun",
    ]


def _requirement_name(requirement: str) -> str:
    return re.split(r"[\[<>=!~;]", requirement, maxsplit=1)[0].strip().lower()
