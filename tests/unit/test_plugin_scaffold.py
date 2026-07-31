from __future__ import annotations

import importlib.util
import pathlib
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


def test_plugin_manifest_has_no_operators_until_vox_7() -> None:
    manifest = _load_yaml(ROOT / "fiftyone.yml")

    assert manifest["operators"] == []


def test_root_entrypoint_register_is_noop_until_vox_7() -> None:
    module = _load_plugin_entrypoint()

    class Registrar:
        def __init__(self) -> None:
            self.registered: list[type[object]] = []

        def register(self, cls: type[object]) -> None:
            self.registered.append(cls)

    registrar = Registrar()

    assert module.register(registrar) is None
    assert registrar.registered == []
