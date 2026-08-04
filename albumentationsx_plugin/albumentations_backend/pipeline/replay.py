"""Replay/provenance extraction helpers for AlbumentationsX outputs."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.core.serialization import normalize_json_mapping


def extract_replay(output: Mapping[str, object]) -> JSONDict:
    """Return a JSON-safe replay payload from an AlbumentationsX output mapping."""

    replay = output.get("replay", {})
    if not isinstance(replay, Mapping):
        return {}
    return normalize_json_mapping(_json_ready_mapping(replay))


def _json_ready_mapping(value: Mapping[object, object]) -> dict[str, object]:
    return {str(key): _json_ready_replay(nested_value) for key, nested_value in value.items()}


def _json_ready_replay(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return _json_ready_mapping(value)
    if isinstance(value, list | tuple):
        return [_json_ready_replay(nested_value) for nested_value in value]
    return value
