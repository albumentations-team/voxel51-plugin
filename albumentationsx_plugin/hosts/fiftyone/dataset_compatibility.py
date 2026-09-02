"""Read-only compatibility reporting for the active FiftyOne dataset."""

from __future__ import annotations

import importlib.metadata
import json
import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import albumentationsx_plugin
from albumentationsx_plugin.albumentations_backend.catalog.classification import is_mvp_supported_status
from albumentationsx_plugin.core import JSONDict, TransformCapability
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    ALBU_TARGET_BBOXES,
    ALBU_TARGET_IMAGE,
    ALBU_TARGET_KEYPOINTS,
    ALBU_TARGET_MASK,
    ALBU_TARGET_ORDER,
    ANNOTATION_ROLE_COPIED,
    ANNOTATION_ROLE_TRANSFORMED,
    FIELD_TYPE_HEATMAP,
    AnnotationField,
    AnnotationFieldSelection,
    resolve_annotation_field_selection,
)
from albumentationsx_plugin.hosts.fiftyone.dependencies import runtime_dependency_package_name
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CURRENT_VIEW,
    EXECUTION_SCOPE_ENTIRE_DATASET,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    execution_scope_label,
)

_LOGGER = logging.getLogger(__name__)
_TRANSFORM_TYPE_IMAGE_ONLY = "image_only"
_EXAMPLE_LIMIT = 8
_EMPTY_SELECTION = AnnotationFieldSelection(selected_fields=(), excluded_fields=(), explicit=False)
_TARGET_HOST_USE: Mapping[str, str] = {
    ALBU_TARGET_IMAGE: "Source image pixels and heatmap geometry maps.",
    ALBU_TARGET_BBOXES: "FiftyOne Detections bounding boxes.",
    ALBU_TARGET_KEYPOINTS: "FiftyOne Keypoints and Polyline vertices.",
    ALBU_TARGET_MASK: "FiftyOne Segmentation masks and runtime Detection masks.",
}
_TARGET_LIMITATIONS: Mapping[str, str] = {
    ALBU_TARGET_IMAGE: "Heatmaps are conditional: geometry-only image-target stages can sync them safely.",
    ALBU_TARGET_BBOXES: "Detection instance masks may also require mask targets and are checked at execution time.",
    ALBU_TARGET_KEYPOINTS: "Polyline vertices are converted through keypoint targets.",
    ALBU_TARGET_MASK: "File-backed segmentation masks are materialized as plugin-owned output assets.",
}


class CompatibilityCatalogProvider(Protocol):
    """Catalog provider surface needed by the dataset compatibility report."""

    @property
    def version_info(self) -> Mapping[str, object]:
        """Return package versions that define the capability snapshot."""
        ...

    def list_transform_capabilities(self) -> tuple[TransformCapability, ...]:
        """Return every capability entry in deterministic order."""
        ...


@dataclass(frozen=True, slots=True)
class CompatibilitySourceSummary:
    """Dataset/view/selection scope described by the report."""

    dataset_name: str
    media_type: str
    source_scope: str
    source_scope_label: str
    selected_sample_count: int
    source_count: int
    source_count_available: bool

    def to_dict(self) -> JSONDict:
        """Serialize the source summary for FiftyOne operator output."""

        return {
            "dataset_name": self.dataset_name,
            "media_type": self.media_type,
            "source_scope": self.source_scope,
            "source_scope_label": self.source_scope_label,
            "selected_sample_count": self.selected_sample_count,
            "source_count": self.source_count,
            "source_count_available": self.source_count_available,
        }


@dataclass(frozen=True, slots=True)
class AnnotationCompatibilityRow:
    """One detected label field and its augmentation support status."""

    field_name: str
    label_type: str
    support_status: str
    role: str
    target: str
    compatible_transform_count: int
    compatible_transform_examples: tuple[str, ...]
    recommended_filter: str
    limitations: str
    message: str

    def to_dict(self) -> JSONDict:
        """Serialize the field row for list and JSON outputs."""

        return {
            "field_name": self.field_name,
            "label_type": self.label_type,
            "support_status": self.support_status,
            "role": self.role,
            "target": self.target,
            "compatible_transform_count": self.compatible_transform_count,
            "compatible_transform_examples": ", ".join(self.compatible_transform_examples),
            "recommended_filter": self.recommended_filter,
            "limitations": self.limitations,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class TargetFamilyCompatibilityRow:
    """One Albumentations target family exposed by the current catalog."""

    target: str
    status: str
    supported_transform_count: int
    excluded_transform_count: int
    image_only_transform_count: int
    geometry_transform_count: int
    example_transforms: tuple[str, ...]
    host_annotation_use: str
    limitations: str

    def to_dict(self) -> JSONDict:
        """Serialize the target row for list and JSON outputs."""

        return {
            "target": self.target,
            "status": self.status,
            "supported_transform_count": self.supported_transform_count,
            "excluded_transform_count": self.excluded_transform_count,
            "image_only_transform_count": self.image_only_transform_count,
            "geometry_transform_count": self.geometry_transform_count,
            "example_transforms": ", ".join(self.example_transforms),
            "host_annotation_use": self.host_annotation_use,
            "limitations": self.limitations,
        }


@dataclass(frozen=True, slots=True)
class DatasetCompatibilityReport:
    """Complete read-only payload returned by the compatibility operator."""

    status: str
    message: str
    plugin_version: str
    fiftyone_version: str
    albumentationsx_version: str
    albu_spec_version: str
    capability_version_key: str
    source: CompatibilitySourceSummary
    metadata_available: bool
    schema_warning: str
    detected_field_count: int
    supported_field_count: int
    unsupported_field_count: int
    copied_field_count: int
    transformable_field_count: int
    total_transform_count: int
    executable_transform_count: int
    excluded_transform_count: int
    status_counts: Mapping[str, int]
    annotation_fields: tuple[AnnotationCompatibilityRow, ...]
    target_families: tuple[TargetFamilyCompatibilityRow, ...]
    recommendations: tuple[str, ...]

    def to_dict(self) -> JSONDict:
        """Serialize the report for FiftyOne output fields."""

        field_rows = [row.to_dict() for row in self.annotation_fields]
        target_rows = [row.to_dict() for row in self.target_families]
        return cast(
            JSONDict,
            {
                "status": self.status,
                "message": self.message,
                "plugin_version": self.plugin_version,
                "fiftyone_version": self.fiftyone_version,
                "albumentationsx_version": self.albumentationsx_version,
                "albu_spec_version": self.albu_spec_version,
                "capability_version_key": self.capability_version_key,
                **self.source.to_dict(),
                "metadata_available": self.metadata_available,
                "schema_warning": self.schema_warning,
                "detected_field_count": self.detected_field_count,
                "supported_field_count": self.supported_field_count,
                "unsupported_field_count": self.unsupported_field_count,
                "copied_field_count": self.copied_field_count,
                "transformable_field_count": self.transformable_field_count,
                "total_transform_count": self.total_transform_count,
                "executable_transform_count": self.executable_transform_count,
                "excluded_transform_count": self.excluded_transform_count,
                "status_counts_json": _json_text(dict(self.status_counts)),
                "annotation_fields": field_rows,
                "annotation_fields_json": _json_text(field_rows),
                "target_families": target_rows,
                "target_families_json": _json_text(target_rows),
                "recommendations_text": "\n".join(f"- {recommendation}" for recommendation in self.recommendations),
                "recommendations_json": _json_text(list(self.recommendations)),
                "report_json": _json_text(
                    {
                        "status": self.status,
                        "message": self.message,
                        "versions": {
                            "plugin": self.plugin_version,
                            "fiftyone": self.fiftyone_version,
                            "albumentationsx": self.albumentationsx_version,
                            "albu_spec": self.albu_spec_version,
                            "capability_version_key": self.capability_version_key,
                        },
                        "source": self.source.to_dict(),
                        "metadata_available": self.metadata_available,
                        "schema_warning": self.schema_warning,
                        "counts": {
                            "detected_fields": self.detected_field_count,
                            "supported_fields": self.supported_field_count,
                            "unsupported_fields": self.unsupported_field_count,
                            "copied_fields": self.copied_field_count,
                            "transformable_fields": self.transformable_field_count,
                            "total_transforms": self.total_transform_count,
                            "executable_transforms": self.executable_transform_count,
                            "excluded_transforms": self.excluded_transform_count,
                            "status_counts": dict(self.status_counts),
                        },
                        "annotation_fields": field_rows,
                        "target_families": target_rows,
                        "recommendations": list(self.recommendations),
                    }
                ),
            },
        )


def build_dataset_compatibility_report(
    *,
    dataset: Any | None,
    view: Any | None = None,
    selected_sample_ids: Sequence[str] = (),
    source_scope: str = EXECUTION_SCOPE_CURRENT_VIEW,
    provider: CompatibilityCatalogProvider | None = None,
) -> DatasetCompatibilityReport:
    """Build a read-only compatibility report for the active dataset context."""

    if dataset is None:
        return _missing_dataset_report(source_scope=source_scope, selected_sample_ids=selected_sample_ids)

    source = _source_summary(
        dataset=dataset,
        view=view,
        selected_sample_ids=selected_sample_ids,
        source_scope=source_scope,
    )
    selection, metadata_available, schema_warning = _safe_annotation_selection(dataset)
    catalog = provider or _default_catalog_provider()
    capabilities = catalog.list_transform_capabilities()
    executable_capabilities = tuple(
        capability for capability in capabilities if is_mvp_supported_status(capability.status)
    )
    field_rows = _annotation_field_rows(selection, executable_capabilities)
    target_rows = _target_family_rows(capabilities)
    supported_field_count = len(selection.selected_fields)
    unsupported_field_count = sum(1 for field in field_rows if field.support_status == "unsupported")
    copied_field_count = sum(1 for field in field_rows if field.role == ANNOTATION_ROLE_COPIED)
    transformable_field_count = sum(1 for field in field_rows if field.role == ANNOTATION_ROLE_TRANSFORMED)
    version_info = _version_info(catalog)

    return DatasetCompatibilityReport(
        status="ok",
        message=_report_message(
            source, supported_field_count=supported_field_count, unsupported_field_count=unsupported_field_count
        ),
        plugin_version=albumentationsx_plugin.__version__,
        fiftyone_version=_dependency_version("fiftyone"),
        albumentationsx_version=str(version_info.get("albumentationsx", "")),
        albu_spec_version=str(version_info.get("albu_spec", "")),
        capability_version_key=_version_key(version_info),
        source=source,
        metadata_available=metadata_available,
        schema_warning=schema_warning,
        detected_field_count=len(field_rows),
        supported_field_count=supported_field_count,
        unsupported_field_count=unsupported_field_count,
        copied_field_count=copied_field_count,
        transformable_field_count=transformable_field_count,
        total_transform_count=len(capabilities),
        executable_transform_count=len(executable_capabilities),
        excluded_transform_count=len(capabilities) - len(executable_capabilities),
        status_counts=_status_counts(capabilities),
        annotation_fields=field_rows,
        target_families=target_rows,
        recommendations=_recommendations(
            source,
            field_rows=field_rows,
            target_rows=target_rows,
            metadata_available=metadata_available,
        ),
    )


def missing_dependency_compatibility_report(
    error: ModuleNotFoundError,
    *,
    source_scope: str = "",
) -> JSONDict:
    """Return a compatibility payload when a catalog runtime dependency is missing."""

    package_name = runtime_dependency_package_name(error)
    report = _empty_report(
        status="error",
        message=(
            f"Install the '{package_name}' package in the active FiftyOne Python environment, "
            "then reload the FiftyOne App."
        ),
        source=_empty_source(source_scope=source_scope),
    )
    return report.to_dict()


def dataset_compatibility_error_report(
    message: str,
    *,
    source_scope: str = "",
    selected_sample_ids: Sequence[str] = (),
) -> JSONDict:
    """Return a compatibility payload for invalid operator input."""

    report = _empty_report(
        status="error",
        message=message,
        source=_empty_source(source_scope=source_scope, selected_sample_ids=selected_sample_ids),
        recommendations=(message,),
    )
    return report.to_dict()


def _annotation_field_rows(
    selection: AnnotationFieldSelection,
    executable_capabilities: Sequence[TransformCapability],
) -> tuple[AnnotationCompatibilityRow, ...]:
    rows: list[AnnotationCompatibilityRow] = []
    for field in selection.selected_fields:
        rows.append(_supported_field_row(field, executable_capabilities))
    for exclusion in selection.excluded_fields:
        if exclusion.get("reason") == "not_selected":
            continue
        rows.append(_unsupported_field_row(exclusion))
    return tuple(rows)


def _supported_field_row(
    field: AnnotationField,
    executable_capabilities: Sequence[TransformCapability],
) -> AnnotationCompatibilityRow:
    compatible_capabilities = _compatible_capabilities_for_field(field, executable_capabilities)
    examples = _capability_examples(compatible_capabilities)
    if field.albu_target is None:
        return AnnotationCompatibilityRow(
            field_name=field.name,
            label_type=field.label_type,
            support_status="copy_supported",
            role=ANNOTATION_ROLE_COPIED,
            target="",
            compatible_transform_count=len(compatible_capabilities),
            compatible_transform_examples=examples,
            recommended_filter="All executable transforms; label is copied unchanged.",
            limitations="Semantic validity of copied labels is user-owned after crops or heavy geometry.",
            message="Classification-like labels are copied to generated samples without geometric conversion.",
        )
    if field.label_type == FIELD_TYPE_HEATMAP:
        return AnnotationCompatibilityRow(
            field_name=field.name,
            label_type=field.label_type,
            support_status="conditional",
            role=ANNOTATION_ROLE_TRANSFORMED,
            target=field.albu_target,
            compatible_transform_count=len(compatible_capabilities),
            compatible_transform_examples=examples,
            recommended_filter="Use image-target geometry transforms; avoid mixed geometry plus image-only stages.",
            limitations=(
                "Geometry-only pipelines transform heatmaps; image-only-only pipelines copy heatmaps unchanged; "
                "mixed geometry plus image-only pipelines are blocked."
            ),
            message="Heatmaps use image-like targets for geometry-only synchronization.",
        )
    return AnnotationCompatibilityRow(
        field_name=field.name,
        label_type=field.label_type,
        support_status="transform_supported",
        role=ANNOTATION_ROLE_TRANSFORMED,
        target=field.albu_target,
        compatible_transform_count=len(compatible_capabilities),
        compatible_transform_examples=examples,
        recommended_filter=f"Target filter: {field.albu_target}; image-only stages are also safe.",
        limitations=_field_limitations(field),
        message=f"{field.label_type.capitalize()} labels are converted through Albumentations `{field.albu_target}` targets.",
    )


def _unsupported_field_row(exclusion: Mapping[str, object]) -> AnnotationCompatibilityRow:
    field_name = _mapping_string(exclusion, "field_name")
    label_type = _mapping_string(exclusion, "label_type")
    return AnnotationCompatibilityRow(
        field_name=field_name,
        label_type=label_type,
        support_status="unsupported",
        role="excluded",
        target="",
        compatible_transform_count=0,
        compatible_transform_examples=(),
        recommended_filter="Deselect or handle this field outside the plugin.",
        limitations=_mapping_string(exclusion, "reason"),
        message=_mapping_string(exclusion, "message"),
    )


def _compatible_capabilities_for_field(
    field: AnnotationField,
    executable_capabilities: Sequence[TransformCapability],
) -> tuple[TransformCapability, ...]:
    if field.albu_target is None:
        return tuple(executable_capabilities)
    if field.label_type == FIELD_TYPE_HEATMAP:
        return tuple(
            capability
            for capability in executable_capabilities
            if field.albu_target in capability.targets and not _is_image_only(capability)
        )
    return tuple(
        capability
        for capability in executable_capabilities
        if _is_image_only(capability) or field.albu_target in capability.targets
    )


def _target_family_rows(capabilities: Sequence[TransformCapability]) -> tuple[TargetFamilyCompatibilityRow, ...]:
    rows: list[TargetFamilyCompatibilityRow] = []
    for target in _ordered_targets(tuple({target for capability in capabilities for target in capability.targets})):
        target_capabilities = tuple(capability for capability in capabilities if target in capability.targets)
        supported = tuple(
            capability for capability in target_capabilities if is_mvp_supported_status(capability.status)
        )
        image_only = tuple(capability for capability in supported if _is_image_only(capability))
        geometry = tuple(capability for capability in supported if not _is_image_only(capability))
        rows.append(
            TargetFamilyCompatibilityRow(
                target=target,
                status="available" if supported else "not_available",
                supported_transform_count=len(supported),
                excluded_transform_count=len(target_capabilities) - len(supported),
                image_only_transform_count=len(image_only),
                geometry_transform_count=len(geometry),
                example_transforms=_capability_examples(supported),
                host_annotation_use=_TARGET_HOST_USE.get(
                    target, "Not wired to a FiftyOne annotation adapter in the MVP."
                ),
                limitations=_TARGET_LIMITATIONS.get(
                    target, "Transforms for this target family are not exposed by the MVP host adapter."
                ),
            )
        )
    return tuple(rows)


def _safe_annotation_selection(dataset: Any) -> tuple[AnnotationFieldSelection, bool, str]:
    try:
        return resolve_annotation_field_selection(dataset, include_all_label_fields=True), True, ""
    except Exception as error:
        _LOGGER.debug("Error while resolving annotation field compatibility", exc_info=True)
        return _EMPTY_SELECTION, False, f"{type(error).__name__}: {error}"


def _source_summary(
    *,
    dataset: Any,
    view: Any | None,
    selected_sample_ids: Sequence[str],
    source_scope: str,
) -> CompatibilitySourceSummary:
    source_count, source_count_available = _source_count(
        dataset=dataset,
        view=view,
        selected_sample_ids=selected_sample_ids,
        source_scope=source_scope,
    )
    return CompatibilitySourceSummary(
        dataset_name=_object_string_attr(dataset, "name"),
        media_type=_object_string_attr(dataset, "media_type"),
        source_scope=source_scope,
        source_scope_label=execution_scope_label(source_scope),
        selected_sample_count=len(tuple(selected_sample_ids)),
        source_count=source_count,
        source_count_available=source_count_available,
    )


def _source_count(
    *,
    dataset: Any,
    view: Any | None,
    selected_sample_ids: Sequence[str],
    source_scope: str,
) -> tuple[int, bool]:
    if source_scope == EXECUTION_SCOPE_SELECTED_SAMPLES:
        return len(tuple(selected_sample_ids)), True
    source = dataset if source_scope == EXECUTION_SCOPE_ENTIRE_DATASET else view or dataset
    count = _safe_count(source)
    if count is None:
        return 0, False
    return count, True


def _safe_count(collection: Any) -> int | None:
    count = getattr(collection, "count", None)
    if callable(count):
        try:
            value = count()
        except Exception:
            _LOGGER.debug("Error while counting source collection", exc_info=True)
            return None
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    try:
        value = len(collection)
    except Exception:
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _report_message(
    source: CompatibilitySourceSummary,
    *,
    supported_field_count: int,
    unsupported_field_count: int,
) -> str:
    if not source.source_count_available:
        count_text = "unknown number of"
    elif source.source_count == 1:
        count_text = "1"
    else:
        count_text = str(source.source_count)
    field_text = f"{supported_field_count} supported label field(s)"
    if unsupported_field_count:
        field_text = f"{field_text} and {unsupported_field_count} unsupported label field(s)"
    return f"Analyzed {count_text} source sample(s) from {source.source_scope_label.lower()} with {field_text}."


def _recommendations(
    source: CompatibilitySourceSummary,
    *,
    field_rows: Sequence[AnnotationCompatibilityRow],
    target_rows: Sequence[TargetFamilyCompatibilityRow],
    metadata_available: bool,
) -> tuple[str, ...]:
    recommendations: list[str] = []
    if not metadata_available:
        recommendations.append(
            "Dataset schema could not be read; fix schema access before relying on annotation-aware runs."
        )
    if source.source_scope == EXECUTION_SCOPE_SELECTED_SAMPLES and source.source_count == 0:
        recommendations.append("Select one or more samples before running a selected-samples augmentation.")
    if not field_rows:
        recommendations.append(
            "No supported label fields were detected; image outputs can still be augmented without annotation sync."
        )
    if any(row.support_status == "unsupported" for row in field_rows):
        recommendations.append(
            "Unsupported label fields are excluded from annotation-aware execution and should be handled separately."
        )
    if any(row.label_type == FIELD_TYPE_HEATMAP for row in field_rows):
        recommendations.append(
            "For heatmap fields, keep transformed pipelines geometry-only or disable the heatmap field."
        )
    spatial_targets = tuple(row.target for row in field_rows if row.target)
    for target in _ordered_targets(spatial_targets):
        if _target_row(target_rows, target) is not None:
            recommendations.append(
                f"For `{target}` labels, filter transform capabilities by target `{target}` before building presets."
            )
    recommendations.append("Use Preview only on a small selection before materializing outputs for a new dataset.")
    return tuple(dict.fromkeys(recommendations))


def _field_limitations(field: AnnotationField) -> str:
    if field.albu_target == ALBU_TARGET_BBOXES:
        return "Detection masks add runtime mask-target requirements when present."
    if field.albu_target == ALBU_TARGET_KEYPOINTS:
        return "Polyline vertices are represented as keypoints during augmentation."
    if field.albu_target == ALBU_TARGET_MASK:
        return "Segmentation masks must be readable and are written as plugin-owned assets when file-backed."
    return ""


def _target_row(
    rows: Sequence[TargetFamilyCompatibilityRow],
    target: str,
) -> TargetFamilyCompatibilityRow | None:
    for row in rows:
        if row.target == target:
            return row
    return None


def _capability_examples(capabilities: Sequence[TransformCapability]) -> tuple[str, ...]:
    return tuple(capability.name for capability in sorted(capabilities, key=lambda item: item.name)[:_EXAMPLE_LIMIT])


def _ordered_targets(targets: Sequence[str]) -> tuple[str, ...]:
    target_set = {target for target in targets if target}
    ordered = [target for target in ALBU_TARGET_ORDER if target in target_set]
    ordered.extend(sorted(target_set.difference(ALBU_TARGET_ORDER)))
    return tuple(ordered)


def _status_counts(capabilities: Sequence[TransformCapability]) -> dict[str, int]:
    return dict(sorted(Counter(capability.status.value for capability in capabilities).items()))


def _is_image_only(capability: TransformCapability) -> bool:
    return _metadata_string(capability.metadata, "transform_type") == _TRANSFORM_TYPE_IMAGE_ONLY


def _metadata_string(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else ""


def _version_info(provider: CompatibilityCatalogProvider) -> Mapping[str, object]:
    value = getattr(provider, "version_info", {})
    return value if isinstance(value, Mapping) else {}


def _version_key(version_info: Mapping[str, object]) -> str:
    if "albumentationsx" not in version_info or "albu_spec" not in version_info:
        return ""
    return f"albumentationsx-{version_info['albumentationsx']}__albu-spec-{version_info['albu_spec']}"


def _dependency_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


def _object_string_attr(value: Any, name: str) -> str:
    raw_value = getattr(value, name, "")
    return raw_value if isinstance(raw_value, str) else str(raw_value or "")


def _mapping_string(value: Mapping[str, object], key: str) -> str:
    raw_value = value.get(key)
    return raw_value if isinstance(raw_value, str) else ""


def _json_text(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _missing_dataset_report(
    *,
    source_scope: str,
    selected_sample_ids: Sequence[str],
) -> DatasetCompatibilityReport:
    return _empty_report(
        status="error",
        message="Open a FiftyOne image dataset before analyzing AlbumentationsX compatibility.",
        source=_empty_source(source_scope=source_scope, selected_sample_ids=selected_sample_ids),
        recommendations=("Open an image dataset, then rerun the compatibility report.",),
    )


def _empty_source(
    *,
    source_scope: str,
    selected_sample_ids: Sequence[str] = (),
) -> CompatibilitySourceSummary:
    return CompatibilitySourceSummary(
        dataset_name="",
        media_type="",
        source_scope=source_scope,
        source_scope_label=execution_scope_label(source_scope),
        selected_sample_count=len(tuple(selected_sample_ids)),
        source_count=0,
        source_count_available=False,
    )


def _empty_report(
    *,
    status: str,
    message: str,
    source: CompatibilitySourceSummary,
    recommendations: tuple[str, ...] = (),
) -> DatasetCompatibilityReport:
    return DatasetCompatibilityReport(
        status=status,
        message=message,
        plugin_version=albumentationsx_plugin.__version__,
        fiftyone_version=_dependency_version("fiftyone"),
        albumentationsx_version="",
        albu_spec_version="",
        capability_version_key="",
        source=source,
        metadata_available=False,
        schema_warning="",
        detected_field_count=0,
        supported_field_count=0,
        unsupported_field_count=0,
        copied_field_count=0,
        transformable_field_count=0,
        total_transform_count=0,
        executable_transform_count=0,
        excluded_transform_count=0,
        status_counts={},
        annotation_fields=(),
        target_families=(),
        recommendations=recommendations,
    )


def _default_catalog_provider() -> CompatibilityCatalogProvider:
    from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider

    return AlbuSpecCatalogProvider()
