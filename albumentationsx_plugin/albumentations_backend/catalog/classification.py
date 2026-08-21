"""Capability classification rules for albu-spec transform metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from albumentationsx_plugin.core import CapabilityStatus, TransformCapability

IMAGE_TARGET: Final[str] = "image"
TWO_DIMENSIONAL_TRANSFORM_TYPES: Final[frozenset[str]] = frozenset({"image_only", "dual"})
EXTERNAL_DATA_PARAMETER_NAMES: Final[frozenset[str]] = frozenset({"metadata_key"})
HIDDEN_TRANSFORM_NAMES: Final[frozenset[str]] = frozenset({"NoOp"})
UNSUPPORTED_OUTPUT_TRANSFORM_NAMES: Final[frozenset[str]] = frozenset({"Normalize", "ToFloat"})
ANNOTATION_REQUIRED_TRANSFORM_NAMES: Final[frozenset[str]] = frozenset(
    {
        "AtLeastOneBBoxRandomCrop",
        "BBoxSafeRandomCrop",
        "ConstrainedCoarseDropout",
        "CropNonEmptyMaskIfExists",
        "MaskDropout",
        "RandomCropNearBBox",
        "RandomSizedBBoxSafeCrop",
    }
)
SIMPLE_TYPE_HINTS: Final[frozenset[str]] = frozenset(
    {
        "bool",
        "int",
        "int | None",
        "float",
        "float | None",
        "str",
        "str | None",
        "tuple[int, int]",
        "tuple[int, int] | None",
        "tuple[float, float]",
        "tuple[float, float] | None",
    }
)


def classify_transform_metadata(metadata: Any) -> TransformCapability:
    """Convert one albu-spec `TransformMetadata` object into a core capability."""

    name = _metadata_str(metadata, "name")
    targets = tuple(str(target) for target in getattr(metadata, "targets", ()))
    transform_type = _metadata_str(metadata, "transform_type")
    parameter_names = tuple(str(parameter_name) for parameter_name in _parameters(metadata))
    base_metadata = _base_metadata(metadata, parameter_names=parameter_names)

    if IMAGE_TARGET not in targets or transform_type not in TWO_DIMENSIONAL_TRANSFORM_TYPES:
        return TransformCapability(
            name=name,
            status=CapabilityStatus.BLOCKED_MEDIA_TARGET,
            targets=targets,
            reason_code="not_image_2d",
            message="Transform is not available for 2D image inputs in the MVP.",
            metadata=base_metadata,
        )

    if name in HIDDEN_TRANSFORM_NAMES:
        return TransformCapability(
            name=name,
            status=CapabilityStatus.HIDDEN,
            targets=targets,
            reason_code="not_user_visible",
            message="Transform is intentionally hidden from normal UI choices.",
            metadata=base_metadata,
        )

    if name in UNSUPPORTED_OUTPUT_TRANSFORM_NAMES:
        return TransformCapability(
            name=name,
            status=CapabilityStatus.UNSUPPORTED_OUTPUT,
            targets=targets,
            reason_code="non_uint8_image_output",
            message="Transform can produce model-input arrays that are not safe plugin image outputs yet.",
            metadata=base_metadata,
        )

    if name in ANNOTATION_REQUIRED_TRANSFORM_NAMES:
        return TransformCapability(
            name=name,
            status=CapabilityStatus.UNSUPPORTED_TARGET,
            targets=targets,
            reason_code="requires_annotation_target",
            message="Transform depends on bbox or mask targets that are not wired into the image-only MVP.",
            metadata=base_metadata,
        )

    if any(parameter_name in EXTERNAL_DATA_PARAMETER_NAMES for parameter_name in parameter_names):
        return TransformCapability(
            name=name,
            status=CapabilityStatus.REQUIRES_EXTERNAL_DATA,
            targets=targets,
            reason_code="requires_metadata_input",
            message="Transform requires extra metadata or reference data not wired into the MVP pipeline.",
            metadata=base_metadata,
        )

    if not bool(getattr(metadata, "has_init_schema", False)):
        return TransformCapability(
            name=name,
            status=CapabilityStatus.REQUIRES_MANUAL_SCHEMA,
            targets=targets,
            reason_code="missing_init_schema",
            message="Transform has no albu-spec InitSchema metadata for automatic form generation.",
            metadata=base_metadata,
        )

    unsupported_required = _unsupported_required_parameters(metadata)
    if unsupported_required:
        return TransformCapability(
            name=name,
            status=CapabilityStatus.REQUIRES_MANUAL_SCHEMA,
            targets=targets,
            reason_code="unsupported_required_parameters",
            message="Transform has required parameters that need a manual schema before UI exposure.",
            advanced_parameters=unsupported_required,
            metadata=base_metadata,
        )

    advanced_parameters = _advanced_parameters(metadata)
    if advanced_parameters:
        return TransformCapability(
            name=name,
            status=CapabilityStatus.SUPPORTED_WITH_DEFAULTS,
            targets=targets,
            reason_code="advanced_parameters_json_editable",
            message="Transform uses typed controls where possible and JSON-backed controls for advanced optional parameters.",
            advanced_parameters=advanced_parameters,
            metadata=base_metadata,
        )

    return TransformCapability(
        name=name,
        status=CapabilityStatus.SUPPORTED,
        targets=targets,
        metadata=base_metadata,
    )


def is_mvp_supported_status(status: CapabilityStatus) -> bool:
    """Return whether a capability should appear in normal MVP transform choices."""

    return status in {CapabilityStatus.SUPPORTED, CapabilityStatus.SUPPORTED_WITH_DEFAULTS}


def _base_metadata(metadata: Any, *, parameter_names: tuple[str, ...]) -> dict[str, object]:
    supported_bbox_types = getattr(metadata, "supported_bbox_types", None)
    return {
        "module": _metadata_str(metadata, "module"),
        "transform_type": _metadata_str(metadata, "transform_type"),
        "has_init_schema": bool(getattr(metadata, "has_init_schema", False)),
        "parameter_names": list(parameter_names),
        "docstring_short": _optional_metadata_str(metadata, "docstring_short"),
        "supported_bbox_types": [] if supported_bbox_types is None else [str(value) for value in supported_bbox_types],
    }


def _advanced_parameters(metadata: Any) -> tuple[str, ...]:
    return tuple(
        parameter_name
        for parameter_name, parameter in _parameters(metadata).items()
        if not _is_supported_type_hint(getattr(parameter, "type_hint", None))
    )


def _unsupported_required_parameters(metadata: Any) -> tuple[str, ...]:
    return tuple(
        parameter_name
        for parameter_name, parameter in _parameters(metadata).items()
        if _is_required(parameter) and not _is_supported_type_hint(getattr(parameter, "type_hint", None))
    )


def _parameters(metadata: Any) -> Mapping[str, Any]:
    parameters = getattr(metadata, "parameters", {})
    if isinstance(parameters, Mapping):
        return parameters
    return {}


def _is_required(parameter: Any) -> bool:
    if str(getattr(parameter, "name", "")) == "p":
        return False
    if getattr(parameter, "default", None) is not None:
        return False

    type_hint = getattr(parameter, "type_hint", None)
    if isinstance(type_hint, list):
        return None not in type_hint
    if isinstance(type_hint, str):
        return "None" not in type_hint
    return True


def _is_supported_type_hint(type_hint: object) -> bool:
    if isinstance(type_hint, list):
        return all(isinstance(value, str | int | float | bool | None) for value in type_hint)
    if not isinstance(type_hint, str):
        return False
    if type_hint in SIMPLE_TYPE_HINTS:
        return True
    if type_hint.startswith("tuple[") and type_hint.endswith("]") and "|" not in type_hint and "..." not in type_hint:
        return all(
            part.strip() in {"int", "float"} for part in type_hint.removeprefix("tuple[").removesuffix("]").split(",")
        )
    return False


def _metadata_str(metadata: Any, field_name: str) -> str:
    value = getattr(metadata, field_name, "")
    return value if isinstance(value, str) and value else "<unknown>"


def _optional_metadata_str(metadata: Any, field_name: str) -> str | None:
    value = getattr(metadata, field_name, None)
    return value if isinstance(value, str) and value else None
