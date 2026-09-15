"""Preserve descriptive label metadata and report deliberate exclusions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any, cast

import fiftyone as fo
import numpy as np

from albumentationsx_plugin.core import JSONDict, JSONValue
from albumentationsx_plugin.core.serialization import normalize_json_mapping, normalize_json_value

CUSTOM_FIELDS = "custom_fields"
ATTRIBUTE_SPECS = "attribute_specs"
METADATA_EXCLUSIONS = "metadata_exclusions"
GEOMETRY_ATTRIBUTES = frozenset(
    {"area", "bbox_area", "mask_area", "segmentation_area", "perimeter", "centroid", "center", "num_keypoints"}
)
_METADATA_KEYS = (CUSTOM_FIELDS, "attributes", ATTRIBUTE_SPECS, METADATA_EXCLUSIONS, "tags")
_CONTAINERS = {"detections": "detections", "keypoints": "keypoints", "polylines": "polylines"}
_ATTRIBUTE_TYPES = {
    "Attribute": fo.Attribute,
    "BooleanAttribute": fo.BooleanAttribute,
    "CategoricalAttribute": fo.CategoricalAttribute,
    "NumericAttribute": fo.NumericAttribute,
    "ListAttribute": fo.ListAttribute,
}


@lru_cache(maxsize=16)
def _builtin_fields(label_type: type[fo.Label]) -> frozenset[str]:
    return frozenset(label_type().field_names)


def _json_metadata(value: object) -> JSONValue:
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Metadata object keys must be strings")
        return {str(key): _json_metadata(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_metadata(item) for item in value]
    return normalize_json_value(value)


def capture_label_metadata(label: fo.Label, payload: JSONDict) -> JSONDict:
    """Add dynamic fields without allowing them to overwrite payload structure."""

    custom: JSONDict = {}
    exclusions: list[JSONValue] = []
    builtin = _builtin_fields(type(label))
    handled = set(payload) - {"type"}
    for name, value in label.iter_fields():
        if name == "id" or (name == "attributes" and name in builtin) or name in handled:
            continue
        if name in builtin:
            if name == "tags":
                payload["tags"] = _json_metadata(value)
            elif value is not None:
                exclusions.append({"name": name, "reason": "unsupported_builtin_field"})
            continue
        try:
            custom[name] = _json_metadata(value)
        except TypeError:
            exclusions.append({"name": name, "reason": "not_json_serializable"})
    if custom:
        payload[CUSTOM_FIELDS] = custom

    attributes: JSONDict = {}
    specs: JSONDict = {}
    legacy_attributes = getattr(label, "attributes", {}) if "attributes" in builtin else {}
    for name, attribute in cast(Mapping[str, Any], legacy_attributes).items():
        try:
            attributes[name] = _json_metadata(attribute.value)
            extra = {key: value for key, value in attribute.iter_fields() if key != "value" and value is not None}
            specs[name] = {"type": type(attribute).__name__, "fields": _json_metadata(extra)}
            if type(attribute).__name__ not in _ATTRIBUTE_TYPES:
                raise TypeError("Unsupported attribute type")
        except TypeError:
            attributes.pop(name, None)
            specs.pop(name, None)
            exclusions.append({"name": f"attributes.{name}", "reason": "not_json_serializable"})
    if "attributes" in builtin:
        payload["attributes"] = attributes
    if specs:
        payload[ATTRIBUTE_SPECS] = specs
    if exclusions:
        payload[METADATA_EXCLUSIONS] = exclusions
    return payload


def metadata_fields(payload: Mapping[str, object]) -> JSONDict:
    """Copy only descriptive metadata when rebuilding geometry payloads."""

    return normalize_json_mapping({key: payload[key] for key in _METADATA_KEYS if key in payload})


def restore_label_metadata(label: fo.Label, payload: Mapping[str, object]) -> Any:
    """Restore custom fields and legacy Attribute values using fixed label types."""

    custom = payload.get(CUSTOM_FIELDS, {})
    if isinstance(custom, Mapping):
        for name, value in custom.items():
            if not isinstance(name, str) or name.startswith("_") or name in _builtin_fields(type(label)):
                raise ValueError(f"Reserved custom label field: {name}")
            label[name] = _json_metadata(value)
    attributes = payload.get("attributes", {})
    specs = payload.get(ATTRIBUTE_SPECS, {})
    if isinstance(attributes, Mapping) and "attributes" in _builtin_fields(type(label)):
        restored = {}
        for name, value in attributes.items():
            spec = specs.get(name, {}) if isinstance(specs, Mapping) else {}
            kind = spec.get("type") if isinstance(spec, Mapping) else None
            attribute_type = _ATTRIBUTE_TYPES.get(str(kind), _attribute_type(value))
            extra = spec.get("fields", {}) if isinstance(spec, Mapping) else {}
            extra = normalize_json_mapping(extra) if isinstance(extra, Mapping) else {}
            restored[name] = attribute_type(**{**extra, "value": _json_metadata(value)})
        label["attributes"] = restored
    if "tags" in payload and "tags" in _builtin_fields(type(label)):
        label["tags"] = payload["tags"]
    return label


def _attribute_type(value: object) -> type[fo.Attribute]:
    if isinstance(value, bool):
        return fo.BooleanAttribute
    if isinstance(value, int | float):
        return fo.NumericAttribute
    if isinstance(value, str):
        return fo.CategoricalAttribute
    if isinstance(value, list):
        return fo.ListAttribute
    return fo.Attribute


def _label_payloads(field: Mapping[str, object]) -> list[tuple[str, Mapping[str, object]]]:
    labels: list[tuple[str, Mapping[str, object]]] = [("", field)]
    member = _CONTAINERS.get(str(field.get("type")))
    if member:
        children = field.get(member, [])
        if isinstance(children, list | tuple):
            labels.extend(
                (f".{member}[{index}]", child) for index, child in enumerate(children) if isinstance(child, Mapping)
            )
    return labels


def excluded_label_metadata(fields: Mapping[str, object], *, transformed_fields: Sequence[str] = ()) -> list[JSONDict]:
    """List exact field paths excluded by serialization or geometry policy."""

    excluded: list[JSONDict] = []
    for field_name, field in fields.items():
        if not isinstance(field, Mapping):
            continue
        for suffix, label in _label_payloads(field):
            for exclusion in cast(list[Mapping[str, object]], label.get(METADATA_EXCLUSIONS, [])):
                excluded.append(
                    {"field_path": f"{field_name}{suffix}.{exclusion['name']}", "reason": str(exclusion["reason"])}
                )
            if field_name not in transformed_fields:
                continue
            for key in (CUSTOM_FIELDS, "attributes"):
                values = label.get(key, {})
                if not isinstance(values, Mapping):
                    continue
                for name in values:
                    if str(name).lower() in GEOMETRY_ATTRIBUTES:
                        prefix = "attributes." if key == "attributes" else ""
                        excluded.append(
                            {"field_path": f"{field_name}{suffix}.{prefix}{name}", "reason": "geometry_dependent"}
                        )
    return excluded


def remove_geometry_metadata(fields: JSONDict, transformed_fields: Sequence[str]) -> JSONDict:
    """Exclude known derived values instead of copying stale measurements."""

    updated = normalize_json_mapping(fields)
    for field_name in transformed_fields:
        field = updated.get(field_name)
        if not isinstance(field, Mapping):
            continue
        for _suffix, label in _label_payloads(field):
            for key in (CUSTOM_FIELDS, "attributes", ATTRIBUTE_SPECS):
                values = label.get(key)
                if isinstance(values, dict):
                    for name in tuple(values):
                        if str(name).lower() in GEOMETRY_ATTRIBUTES:
                            del values[name]
    return updated
