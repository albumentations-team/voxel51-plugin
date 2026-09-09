"""Read typed values from annotation payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import numpy as np
import numpy.typing as npt

from albumentationsx_plugin.core import JSONValue
from albumentationsx_plugin.core.serialization import normalize_json_value
from albumentationsx_plugin.hosts.fiftyone.annotations.target_types import _TYPE_FIELD


def _payload_fields(payload: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    fields = payload.get("fields")
    if not isinstance(fields, Mapping):
        return {}
    return {
        str(field_name): field_payload
        for field_name, field_payload in fields.items()
        if isinstance(field_payload, Mapping)
    }


def _payload_type(payload: Mapping[str, object]) -> str:
    value = payload.get(_TYPE_FIELD)
    return value if isinstance(value, str) else ""


def _payload_sequence(payload: Mapping[str, object], key: str) -> list[Any]:
    value = payload.get(key)
    return list(value) if isinstance(value, list | tuple) else []


def _runtime_sequence(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return list(value)
    return list(cast(Sequence[Any], value))


def _output_sequence(payload: Mapping[str, object], key: str) -> list[Any]:
    value = payload.get(key)
    if isinstance(value, np.ndarray):
        return list(value)
    return list(value) if isinstance(value, list | tuple) else []


def _float_sequence(value: object) -> list[float]:
    if not isinstance(value, list | tuple | np.ndarray):
        return []
    result: list[float] = []
    for item in value:
        if isinstance(item, int | float | np.integer | np.floating) and not isinstance(item, bool):
            result.append(float(item))
    return result


def _target_index(value: object) -> int:
    if isinstance(value, int | float | np.integer | np.floating) and not isinstance(value, bool):
        return int(round(float(value)))
    raise TypeError(f"Unsupported annotation target index: {value!r}")


def _shape_context(array: np.ndarray) -> list[int]:
    return [int(part) for part in array.shape]


def _array_or_sequence(value: object) -> JSONValue:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return normalize_json_value(value.tolist())
    return normalize_json_value(value)


def _optional_array(value: object) -> npt.NDArray[np.float32] | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float32)


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _optional_heatmap_range(value: object) -> list[float] | None:
    values = _float_sequence(value)
    return values[:2] if len(values) >= 2 else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_bool(value: object, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str)]


def _mapping(value: object) -> Mapping[str, JSONValue]:
    return value if isinstance(value, Mapping) else {}


def _set_optional(payload: dict[str, Any], key: str, value: object) -> None:
    if value is not None:
        payload[key] = normalize_json_value(value)


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))
