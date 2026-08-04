"""Build compact FiftyOne form guidance from catalog and dataset metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from albumentationsx_plugin.core import CapabilityStatus, TransformCapability

IMAGE_TARGET: Final[str] = "image"
BBOX_TARGET: Final[str] = "bboxes"
MASK_TARGET: Final[str] = "mask"
KEYPOINT_TARGET: Final[str] = "keypoints"
LABEL_TARGET: Final[str] = "labels"

DISPLAY_TARGETS: Final[tuple[tuple[str, str], ...]] = (
    (IMAGE_TARGET, "image"),
    (BBOX_TARGET, "bboxes"),
    (MASK_TARGET, "masks"),
    (KEYPOINT_TARGET, "keypoints"),
    (LABEL_TARGET, "labels"),
)
ALBU_TARGET_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    IMAGE_TARGET: ("image",),
    BBOX_TARGET: ("bboxes",),
    MASK_TARGET: ("mask", "masks"),
    KEYPOINT_TARGET: ("keypoints",),
    LABEL_TARGET: (),
}
FIFTYONE_LABEL_TARGETS: Final[dict[str, str]] = {
    "Classification": LABEL_TARGET,
    "Classifications": LABEL_TARGET,
    "Detections": BBOX_TARGET,
    "Keypoints": KEYPOINT_TARGET,
    "Segmentation": MASK_TARGET,
}


@dataclass(frozen=True, slots=True)
class TransformGuidance:
    """Rendered guidance text and severity for one selected transform."""

    label: str
    description: str
    warning: bool = False


@dataclass(frozen=True, slots=True)
class _DatasetTargets:
    targets: tuple[str, ...]
    fields_by_target: Mapping[str, tuple[str, ...]]
    metadata_available: bool


def build_transform_guidance(
    *,
    capability: TransformCapability | None,
    ctx: Any | None,
) -> TransformGuidance:
    """Build a target compatibility message for a selected transform."""

    if capability is None:
        return TransformGuidance(
            label="Target compatibility",
            description="Catalog metadata is unavailable for this transform; validation will run before execution.",
            warning=True,
        )

    dataset_targets = _dataset_targets(ctx)
    unsupported_targets = _unsupported_dataset_targets(capability, dataset_targets.targets)
    description_parts = [
        _transform_summary(capability),
        _target_summary(capability),
        _dataset_summary(dataset_targets),
    ]
    if capability.message is not None:
        description_parts.append(capability.message)
    if capability.advanced_parameters:
        description_parts.append(
            "Hidden advanced parameters use Albumentations defaults: " + ", ".join(capability.advanced_parameters) + "."
        )
    if unsupported_targets:
        description_parts.append(_unsupported_target_warning(unsupported_targets, dataset_targets))

    return TransformGuidance(
        label="Target compatibility",
        description=" ".join(part for part in description_parts if part),
        warning=bool(unsupported_targets) or capability.status not in _safe_statuses(),
    )


def _safe_statuses() -> frozenset[CapabilityStatus]:
    return frozenset({CapabilityStatus.SUPPORTED, CapabilityStatus.SUPPORTED_WITH_DEFAULTS})


def _transform_summary(capability: TransformCapability) -> str:
    docstring_short = capability.metadata.get("docstring_short")
    if isinstance(docstring_short, str) and docstring_short.strip():
        return " ".join(docstring_short.split())
    return "No short catalog description is available for this transform."


def _target_summary(capability: TransformCapability) -> str:
    supported_parts = [
        f"{label}: {_target_support_text(target_name, capability.targets)}" for target_name, label in DISPLAY_TARGETS
    ]
    return "Targets: " + "; ".join(supported_parts) + "."


def _target_support_text(target_name: str, transform_targets: tuple[str, ...]) -> str:
    if target_name == LABEL_TARGET:
        return "copied"
    return "supported" if _target_supported(target_name, transform_targets) else "not supported"


def _target_supported(target_name: str, transform_targets: tuple[str, ...]) -> bool:
    aliases = ALBU_TARGET_ALIASES[target_name]
    return any(alias in transform_targets for alias in aliases)


def _dataset_summary(dataset_targets: _DatasetTargets) -> str:
    if not dataset_targets.metadata_available:
        return "Dataset labels: metadata unavailable; execution validation will still check selected samples."
    if not dataset_targets.targets:
        return "Dataset labels: none detected."

    parts = [
        f"{_target_label(target_name)} ({', '.join(dataset_targets.fields_by_target[target_name])})"
        for target_name in dataset_targets.targets
    ]
    return "Dataset labels: " + "; ".join(parts) + "."


def _unsupported_dataset_targets(
    capability: TransformCapability,
    dataset_targets: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        target_name
        for target_name in dataset_targets
        if target_name != LABEL_TARGET and not _target_supported(target_name, capability.targets)
    )


def _unsupported_target_warning(unsupported_targets: tuple[str, ...], dataset_targets: _DatasetTargets) -> str:
    parts = [
        f"{_target_label(target_name)} fields {', '.join(dataset_targets.fields_by_target[target_name])}"
        for target_name in unsupported_targets
    ]
    return "Warning: selected transform does not declare support for " + "; ".join(parts) + "."


def _dataset_targets(ctx: Any | None) -> _DatasetTargets:
    dataset = getattr(ctx, "dataset", None) if ctx is not None else None
    get_field_schema = getattr(dataset, "get_field_schema", None)
    if not callable(get_field_schema):
        return _DatasetTargets(targets=(), fields_by_target={}, metadata_available=False)

    try:
        schema = get_field_schema()
    except (AttributeError, LookupError, TypeError, ValueError):
        return _DatasetTargets(targets=(), fields_by_target={}, metadata_available=False)
    if not isinstance(schema, Mapping):
        return _DatasetTargets(targets=(), fields_by_target={}, metadata_available=False)

    fields_by_target: dict[str, list[str]] = {}
    for field_name, field in schema.items():
        target_name = _target_from_schema_field(field)
        if target_name is None:
            continue
        fields_by_target.setdefault(target_name, []).append(str(field_name))

    normalized_fields = {target_name: tuple(sorted(fields)) for target_name, fields in fields_by_target.items()}
    return _DatasetTargets(
        targets=tuple(target_name for target_name, _label in DISPLAY_TARGETS if target_name in normalized_fields),
        fields_by_target=normalized_fields,
        metadata_available=True,
    )


def _target_from_schema_field(field: object) -> str | None:
    document_type = _field_document_type(field)
    label_type_name = _label_type_name(document_type)
    return FIFTYONE_LABEL_TARGETS.get(label_type_name)


def _field_document_type(field: object) -> object:
    if isinstance(field, Mapping):
        return field.get("document_type")
    return getattr(field, "document_type", None)


def _label_type_name(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, type):
        return value.__name__
    name = getattr(value, "__name__", None)
    return name if isinstance(name, str) else type(value).__name__


def _target_label(target_name: str) -> str:
    for candidate, label in DISPLAY_TARGETS:
        if candidate == target_name:
            return label
    return target_name
