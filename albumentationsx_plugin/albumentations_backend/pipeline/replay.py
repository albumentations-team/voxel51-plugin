"""Replay/provenance extraction helpers for AlbumentationsX outputs."""

from __future__ import annotations

from collections.abc import Mapping

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.core.serialization import normalize_json_mapping


def extract_replay(output: Mapping[str, object]) -> JSONDict:
    """Return a JSON-safe replay payload from an AlbumentationsX output mapping."""

    replay = output.get("replay", {})
    if not isinstance(replay, Mapping):
        return {}
    return normalize_json_mapping(replay)
