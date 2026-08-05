from __future__ import annotations

from albumentationsx_plugin._compat import StrEnum, tomllib


class _ExampleStatus(StrEnum):
    READY = "ready"


def test_python_compatibility_helpers_match_standard_library_behavior() -> None:
    assert isinstance(_ExampleStatus.READY, str)
    assert str(_ExampleStatus.READY) == "ready"
    assert tomllib.loads("[project]\nversion = '0.1.0'\n") == {"project": {"version": "0.1.0"}}
