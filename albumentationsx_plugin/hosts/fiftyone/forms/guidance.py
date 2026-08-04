"""Build compact FiftyOne form guidance from catalog and dataset metadata."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from albumentationsx_plugin.core import CapabilityStatus, TransformCapability
from albumentationsx_plugin.hosts.fiftyone.forms.targets import (
    FIFTYONE_LABEL_TARGETS,
    TARGET_DISPLAY_ORDER,
    TargetKind,
    target_label,
    target_supported,
)

LOGGER = logging.getLogger(__name__)
TARGET_GUIDANCE_LABEL: Final[str] = "Target compatibility"
SAFE_CAPABILITY_STATUSES: Final[frozenset[CapabilityStatus]] = frozenset(
    {CapabilityStatus.SUPPORTED, CapabilityStatus.SUPPORTED_WITH_DEFAULTS}
)


@dataclass(frozen=True, slots=True)
class TransformGuidance:
    """Rendered guidance text and severity for one selected transform."""

    label: str
    description: str
    warning: bool = False


@dataclass(frozen=True, slots=True)
class _DatasetTargets:
    targets: tuple[TargetKind, ...]
    fields_by_target: Mapping[TargetKind, tuple[str, ...]]
    metadata_available: bool


@dataclass(frozen=True, slots=True)
class _GuidanceContext:
    capability: TransformCapability
    dataset_targets: _DatasetTargets
    unsupported_targets: tuple[TargetKind, ...]


def build_transform_guidance(
    *,
    capability: TransformCapability | None,
    ctx: Any | None,
) -> TransformGuidance:
    """Build a target compatibility message for a selected transform."""

    if capability is None:
        return _missing_capability_guidance()

    guidance_context = _build_guidance_context(capability, ctx)

    return TransformGuidance(
        label=TARGET_GUIDANCE_LABEL,
        description=_guidance_description(guidance_context),
        warning=_guidance_is_warning(guidance_context),
    )


def _missing_capability_guidance() -> TransformGuidance:
    return TransformGuidance(
        label=TARGET_GUIDANCE_LABEL,
        description="Catalog metadata is unavailable for this transform; validation will run before execution.",
        warning=True,
    )


def _build_guidance_context(capability: TransformCapability, ctx: Any | None) -> _GuidanceContext:
    dataset_targets = _dataset_targets(ctx)
    return _GuidanceContext(
        capability=capability,
        dataset_targets=dataset_targets,
        unsupported_targets=_unsupported_dataset_targets(capability, dataset_targets.targets),
    )


def _guidance_description(guidance_context: _GuidanceContext) -> str:
    return " ".join(
        part
        for part in (
            _transform_summary(guidance_context.capability),
            _target_summary(guidance_context.capability),
            _dataset_summary(guidance_context.dataset_targets),
            _capability_message(guidance_context.capability),
            _advanced_parameter_summary(guidance_context.capability),
            _unsupported_target_warning(guidance_context.unsupported_targets, guidance_context.dataset_targets),
        )
        if part
    )


def _guidance_is_warning(guidance_context: _GuidanceContext) -> bool:
    return (
        bool(guidance_context.unsupported_targets) or guidance_context.capability.status not in SAFE_CAPABILITY_STATUSES
    )


def _transform_summary(capability: TransformCapability) -> str:
    docstring_short = capability.metadata.get("docstring_short")
    if isinstance(docstring_short, str) and docstring_short.strip():
        return " ".join(docstring_short.split())
    return "No short catalog description is available for this transform."


def _target_summary(capability: TransformCapability) -> str:
    supported_parts = [
        f"{target_label(target_kind)}: {_target_support_text(target_kind, capability.targets)}"
        for target_kind in TARGET_DISPLAY_ORDER
    ]
    return "Targets: " + "; ".join(supported_parts) + "."


def _target_support_text(target_kind: TargetKind, transform_targets: tuple[str, ...]) -> str:
    if target_kind == TargetKind.LABELS:
        return "copied"
    return "supported" if target_supported(target_kind, transform_targets) else "not supported"


def _capability_message(capability: TransformCapability) -> str | None:
    return capability.message


def _advanced_parameter_summary(capability: TransformCapability) -> str | None:
    if not capability.advanced_parameters:
        return None
    return "Hidden advanced parameters use Albumentations defaults: " + ", ".join(capability.advanced_parameters) + "."


def _dataset_summary(dataset_targets: _DatasetTargets) -> str:
    summary = _dataset_targets_summary(dataset_targets)
    return "Dataset labels: " + summary


def _dataset_targets_summary(dataset_targets: _DatasetTargets) -> str:
    if not dataset_targets.metadata_available:
        return "metadata unavailable; execution validation will still check selected samples."
    if not dataset_targets.targets:
        return "none detected."
    parts = [
        f"{target_label(target_kind)} ({', '.join(dataset_targets.fields_by_target[target_kind])})"
        for target_kind in dataset_targets.targets
    ]
    return "; ".join(parts) + "."


def _unsupported_dataset_targets(
    capability: TransformCapability,
    dataset_targets: tuple[TargetKind, ...],
) -> tuple[TargetKind, ...]:
    return tuple(
        target_kind
        for target_kind in dataset_targets
        if target_kind != TargetKind.LABELS and not target_supported(target_kind, capability.targets)
    )


def _unsupported_target_warning(
    unsupported_targets: tuple[TargetKind, ...],
    dataset_targets: _DatasetTargets,
) -> str | None:
    if not unsupported_targets:
        return None
    parts = [
        f"{target_label(target_kind)} fields {', '.join(dataset_targets.fields_by_target[target_kind])}"
        for target_kind in unsupported_targets
    ]
    return "Warning: selected transform does not declare support for " + "; ".join(parts) + "."


def _missing_dataset_targets() -> _DatasetTargets:
    return _DatasetTargets(targets=(), fields_by_target={}, metadata_available=False)


def _dataset_targets(ctx: Any | None) -> _DatasetTargets:
    dataset = getattr(ctx, "dataset", None) if ctx is not None else None
    get_field_schema = getattr(dataset, "get_field_schema", None)
    if not callable(get_field_schema):
        return _missing_dataset_targets()

    try:
        schema = get_field_schema()
    except Exception:
        LOGGER.debug("Failed to fetch dataset field schema for target guidance.", exc_info=True)
        return _missing_dataset_targets()
    if not isinstance(schema, Mapping):
        return _missing_dataset_targets()

    fields_by_target: dict[TargetKind, list[str]] = {}
    for field_name, field in schema.items():
        target_kind = _target_from_schema_field(field)
        if target_kind is None:
            continue
        fields_by_target.setdefault(target_kind, []).append(str(field_name))

    normalized_fields = {target_kind: tuple(sorted(fields)) for target_kind, fields in fields_by_target.items()}
    return _DatasetTargets(
        targets=tuple(target_kind for target_kind in TARGET_DISPLAY_ORDER if target_kind in normalized_fields),
        fields_by_target=normalized_fields,
        metadata_available=True,
    )


def _target_from_schema_field(field: object) -> TargetKind | None:
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
