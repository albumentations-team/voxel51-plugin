"""Small standard-library compatibility helpers for supported Python versions."""

from __future__ import annotations

from enum import Enum

import tomli as tomllib


class StrEnum(str, Enum):
    """String enum with the behavior needed by the plugin on Python 3.10+."""

    def __str__(self) -> str:
        return str(self.value)


__all__ = ["StrEnum", "tomllib"]
