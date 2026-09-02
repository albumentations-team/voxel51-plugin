"""Discover and validate FiftyOne annotation fields for augmentation."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, TypeGuard

import fiftyone as fo

from albumentationsx_plugin.core import (
    AugmentationInput,
    HostAdapterError,
    JSONDict,
    PipelineConfig,
    TransformCatalogProvider,
)
from albumentationsx_plugin.core.serialization import normalize_json_mapping

ANNOTATION_PAYLOAD_KEY: Final[str] = "annotation_payload"
ANNOTATION_EXCLUDED_FIELDS_KEY: Final[str] = "annotation_excluded_fields"
ANNOTATION_FIELD_PARAM_PREFIX: Final[str] = "annotation_field__"
SELECTED_LABEL_FIELDS_PARAM_NAME: Final[str] = "selected_label_fields"

FIELD_TYPE_CLASSIFICATION: Final[str] = "classification"
FIELD_TYPE_DETECTIONS: Final[str] = "detections"
FIELD_TYPE_HEATMAP: Final[str] = "heatmap"
FIELD_TYPE_KEYPOINTS: Final[str] = "keypoints"
FIELD_TYPE_POLYLINES: Final[str] = "polylines"
FIELD_TYPE_SEGMENTATION: Final[str] = "segmentation"

ANNOTATION_ROLE_TRANSFORMED: Final[str] = "transformed"
ANNOTATION_ROLE_COPIED: Final[str] = "copied"

ALBU_TARGET_IMAGE: Final[str] = "image"
ALBU_TARGET_BBOXES: Final[str] = "bboxes"
ALBU_TARGET_KEYPOINTS: Final[str] = "keypoints"
ALBU_TARGET_MASK: Final[str] = "mask"
ALBU_TARGET_ORDER: Final[tuple[str, ...]] = (
    ALBU_TARGET_IMAGE,
    ALBU_TARGET_BBOXES,
    ALBU_TARGET_KEYPOINTS,
    ALBU_TARGET_MASK,
)
_MASK_FIELD: Final[str] = "mask"
_TRANSFORM_TYPE_IMAGE_ONLY: Final[str] = "image_only"
_EXCLUDED_REASON_NOT_SELECTED: Final[str] = "not_selected"


@dataclass(frozen=True, slots=True)
class AnnotationField:
    """Supported FiftyOne label field and the Albumentations target it needs."""

    name: str
    label_type: str
    albu_target: str | None = None

    @property
    def is_spatial(self) -> bool:
        """Return whether this field must track image geometry."""

        return bool(self.albu_targets)

    @property
    def albu_targets(self) -> tuple[str, ...]:
        """Return declared Albumentations target requirements from the schema."""

        return () if self.albu_target is None else (self.albu_target,)

    def to_dict(self, *, role: str | None = None) -> JSONDict:
        """Serialize the field for run manifests and operator diagnostics."""

        payload: JSONDict = {
            "field_name": self.name,
            "label_type": self.label_type,
            "spatial": self.is_spatial,
        }
        if self.albu_target is not None:
            payload["target"] = self.albu_target
        if role is not None:
            payload["role"] = role
        return payload


@dataclass(frozen=True, slots=True)
class AnnotationFieldSelection:
    """Resolved annotation field selection for one augmentation request."""

    selected_fields: tuple[AnnotationField, ...]
    excluded_fields: tuple[JSONDict, ...]
    explicit: bool = False

    @property
    def selected_field_names(self) -> tuple[str, ...]:
        """Return selected field names in dataset schema order."""

        return tuple(field.name for field in self.selected_fields)


def list_supported_annotation_fields(dataset: Any | None) -> tuple[AnnotationField, ...]:
    """Return supported annotation label fields from a FiftyOne dataset schema."""

    if dataset is None:
        return ()
    return tuple(field for field in _annotation_fields_from_schema(_field_schema(dataset)) if field is not None)


def safe_list_supported_annotation_fields(dataset: Any | None) -> tuple[AnnotationField, ...]:
    """Return supported annotation fields without breaking form rendering."""

    try:
        return list_supported_annotation_fields(dataset)
    except Exception:
        return ()


def annotation_field_param_name(field_name: str) -> str:
    """Return a safe FiftyOne operator param name for one annotation field."""

    encoded = base64.urlsafe_b64encode(field_name.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{ANNOTATION_FIELD_PARAM_PREFIX}{encoded}"


def selected_annotation_fields_from_params(
    params: Mapping[str, object],
    dataset: Any | None,
) -> AnnotationFieldSelection:
    """Resolve selected annotation fields from operator params.

    If no annotation controls were submitted, all supported fields are selected
    to preserve the pre-VOX-40 default behavior.
    """

    supported_fields = list_supported_annotation_fields(dataset)
    explicit = annotation_field_selection_is_explicit(params)
    if explicit:
        selected_names = _explicit_selected_field_names(params, supported_fields)
        return resolve_annotation_field_selection(
            dataset,
            selected_label_fields=selected_names,
            include_all_label_fields=False,
            explicit=True,
        )
    return resolve_annotation_field_selection(
        dataset,
        selected_label_fields=(),
        include_all_label_fields=True,
        explicit=False,
    )


def annotation_field_selection_is_explicit(params: Mapping[str, object]) -> bool:
    """Return whether params contain a user-visible annotation field selection."""

    if SELECTED_LABEL_FIELDS_PARAM_NAME in params:
        return True
    return any(str(key).startswith(ANNOTATION_FIELD_PARAM_PREFIX) for key in params)


def resolve_annotation_fields(
    dataset: Any,
    selected_label_fields: Sequence[str] = (),
    *,
    include_all_label_fields: bool = True,
) -> tuple[tuple[str, ...], tuple[JSONDict, ...]]:
    """Return selected supported field names plus excluded field diagnostics."""

    selection = resolve_annotation_field_selection(
        dataset,
        selected_label_fields=selected_label_fields,
        include_all_label_fields=include_all_label_fields,
    )
    return selection.selected_field_names, selection.excluded_fields


def resolve_annotation_field_selection(
    dataset: Any,
    selected_label_fields: Sequence[str] = (),
    *,
    include_all_label_fields: bool = True,
    explicit: bool = False,
) -> AnnotationFieldSelection:
    """Resolve supported/excluded annotation fields against the dataset schema."""

    schema = _field_schema(dataset)
    selected_names = tuple(dict.fromkeys(str(field_name) for field_name in selected_label_fields))
    fields_by_name = {field.name: field for field in _annotation_fields_from_schema(schema) if field is not None}
    unsupported_by_name = _unsupported_label_fields(schema)

    if not selected_names and include_all_label_fields:
        selected_names = tuple(fields_by_name)

    selected_name_set = set(selected_names)
    selected_fields = tuple(field for field_name, field in fields_by_name.items() if field_name in selected_name_set)
    excluded_fields: list[JSONDict] = []

    for field_name in selected_names:
        if field_name in fields_by_name:
            continue
        field = schema.get(field_name)
        if field is None:
            excluded_fields.append(_missing_field_exclusion(field_name, selected=True))
            continue
        label_type = getattr(field, "document_type", None)
        if _is_label_type(label_type):
            excluded_fields.append(_unsupported_field_exclusion(field_name, label_type, selected=True))

    for field_name, field in fields_by_name.items():
        if field_name not in selected_name_set:
            excluded_fields.append(_not_selected_field_exclusion(field))

    for field_name, label_type in unsupported_by_name.items():
        if field_name not in selected_name_set:
            excluded_fields.append(_unsupported_field_exclusion(field_name, label_type, selected=False))

    return AnnotationFieldSelection(
        selected_fields=selected_fields,
        excluded_fields=tuple(excluded_fields),
        explicit=explicit,
    )


def validate_selected_annotation_fields(selection: AnnotationFieldSelection) -> None:
    """Reject explicitly selected fields that cannot be represented safely."""

    blocking = tuple(
        field
        for field in selection.excluded_fields
        if field.get("selected") is True and field.get("reason") != _EXCLUDED_REASON_NOT_SELECTED
    )
    if not blocking:
        return

    first = blocking[0]
    raise HostAdapterError(
        host="fiftyone",
        message="Selected annotation field cannot be used for augmentation.",
        context={
            "reason": "invalid_annotation_field_selection",
            "field_name": str(first.get("field_name", "")),
            "field_reason": str(first.get("reason", "")),
            "excluded_fields": [dict(field) for field in blocking],
        },
    )


def validate_annotation_pipeline_compatibility(
    *,
    selection: AnnotationFieldSelection,
    pipeline: PipelineConfig,
    catalog_provider: TransformCatalogProvider,
    runtime_target_requirements: Mapping[str, Sequence[str]] | None = None,
) -> None:
    """Reject selected spatial fields that a geometric stage cannot transform."""

    conflicts = annotation_pipeline_compatibility_conflicts(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog_provider,
        runtime_target_requirements=runtime_target_requirements,
    )
    if not conflicts:
        return

    first = conflicts[0]
    raise HostAdapterError(
        host="fiftyone",
        message="Selected annotation field cannot be transformed safely by the requested pipeline.",
        context={
            "reason": "annotation_target_incompatible",
            "field_name": str(first.get("field_name", "")),
            "label_type": str(first.get("label_type", "")),
            "target": str(first.get("target", "")),
            "transform_name": str(first.get("transform_name", "")),
            "stage_number": first.get("stage_number"),
            "conflicts": [dict(conflict) for conflict in conflicts],
        },
    )


def annotation_pipeline_compatibility_conflicts(
    *,
    selection: AnnotationFieldSelection,
    pipeline: PipelineConfig,
    catalog_provider: TransformCatalogProvider,
    runtime_target_requirements: Mapping[str, Sequence[str]] | None = None,
) -> tuple[JSONDict, ...]:
    """Return selected field/transform conflicts without raising."""

    conflicts: list[JSONDict] = []
    spatial_fields = tuple(
        field for field in selection.selected_fields if _field_target_requirements(field, runtime_target_requirements)
    )
    if not spatial_fields:
        return ()

    transformed_targets = _transformed_targets(pipeline, catalog_provider)
    for stage_number, transform in enumerate(pipeline.transforms, start=1):
        capability = catalog_provider.get_transform_capability(transform.name)
        if capability is None:
            continue
        if _capability_transform_type(capability.metadata) == _TRANSFORM_TYPE_IMAGE_ONLY:
            conflicts.extend(
                _image_only_stage_conflicts(
                    stage_number=stage_number,
                    transform_name=transform.name,
                    spatial_fields=spatial_fields,
                    transformed_targets=transformed_targets,
                )
            )
            continue
        targets = set(capability.targets)
        for field in spatial_fields:
            for target in _field_target_requirements(field, runtime_target_requirements):
                if target in targets:
                    continue
                conflicts.append(
                    normalize_json_mapping(
                        {
                            "field_name": field.name,
                            "label_type": field.label_type,
                            "target": target,
                            "transform_name": transform.name,
                            "stage_number": stage_number,
                            "reason": "missing_transform_target",
                            "message": (f"{transform.name} does not advertise support for {target} targets."),
                        }
                    )
                )
    return tuple(conflicts)


def _image_only_stage_conflicts(
    *,
    stage_number: int,
    transform_name: str,
    spatial_fields: Sequence[AnnotationField],
    transformed_targets: frozenset[str],
) -> tuple[JSONDict, ...]:
    conflicts: list[JSONDict] = []
    for field in spatial_fields:
        if field.label_type != FIELD_TYPE_HEATMAP or ALBU_TARGET_IMAGE not in transformed_targets:
            continue
        conflicts.append(
            normalize_json_mapping(
                {
                    "field_name": field.name,
                    "label_type": field.label_type,
                    "target": ALBU_TARGET_IMAGE,
                    "transform_name": transform_name,
                    "stage_number": stage_number,
                    "reason": "image_only_stage_would_alter_heatmap",
                    "message": (
                        f"{transform_name} is an image-only stage. Heatmaps can only be safely transformed "
                        "through image-like targets when the active pipeline is geometry-only."
                    ),
                }
            )
        )
    return tuple(conflicts)


def annotation_pipeline_field_roles(
    *,
    selection: AnnotationFieldSelection,
    pipeline: PipelineConfig,
    catalog_provider: TransformCatalogProvider,
) -> tuple[tuple[AnnotationField, str], ...]:
    """Classify selected fields as transformed or copied for one pipeline."""

    transforms_by_target = _transformed_targets(pipeline, catalog_provider)
    roles: list[tuple[AnnotationField, str]] = []
    for field in selection.selected_fields:
        role = (
            ANNOTATION_ROLE_TRANSFORMED
            if field.albu_target is not None and field.albu_target in transforms_by_target
            else ANNOTATION_ROLE_COPIED
        )
        roles.append((field, role))
    return tuple(roles)


def annotation_run_metadata(
    *,
    selection: AnnotationFieldSelection,
    pipeline: PipelineConfig,
    catalog_provider: TransformCatalogProvider,
    runtime_target_requirements: Mapping[str, Sequence[str]] | None = None,
) -> JSONDict:
    """Build manifest metadata for selected/copied/transformed annotation fields."""

    roles = annotation_pipeline_field_roles(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog_provider,
    )
    selected_fields = tuple(field.to_dict(role=role) for field, role in roles)
    transformed_fields = tuple(field.to_dict(role=role) for field, role in roles if role == ANNOTATION_ROLE_TRANSFORMED)
    copied_fields = tuple(field.to_dict(role=role) for field, role in roles if role == ANNOTATION_ROLE_COPIED)
    metadata: dict[str, object] = {
        "fields": [field.name for field in selection.selected_fields],
        "selected_fields": list(selected_fields),
        "transformed_fields": list(transformed_fields),
        "copied_fields": list(copied_fields),
        "excluded_fields": [dict(field) for field in selection.excluded_fields],
    }
    runtime_requirements = _runtime_target_requirements_to_json(runtime_target_requirements)
    if runtime_requirements:
        metadata["runtime_target_requirements"] = runtime_requirements
    return normalize_json_mapping(metadata)


def annotation_target_requirements_from_inputs(
    source_inputs: Sequence[AugmentationInput],
) -> dict[str, tuple[str, ...]]:
    """Infer target requirements from serialized source annotation payloads."""

    requirements: dict[str, set[str]] = {}
    for source_input in source_inputs:
        payload = source_input.metadata.get(ANNOTATION_PAYLOAD_KEY)
        if not isinstance(payload, Mapping):
            continue
        for field_name, field_payload in _payload_fields(payload).items():
            targets = _runtime_field_targets(field_payload)
            if not targets:
                continue
            requirements.setdefault(field_name, set()).update(targets)
    return {field_name: _ordered_targets(targets) for field_name, targets in requirements.items()}


def target_and_copy_fields(
    *,
    selection: AnnotationFieldSelection,
    pipeline: PipelineConfig,
    catalog_provider: TransformCatalogProvider,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return field names for PipelineConfig target_fields and copy_fields."""

    roles = annotation_pipeline_field_roles(
        selection=selection,
        pipeline=pipeline,
        catalog_provider=catalog_provider,
    )
    target_fields = tuple(field.name for field, role in roles if role == ANNOTATION_ROLE_TRANSFORMED)
    copy_fields = tuple(field.name for field, role in roles if role == ANNOTATION_ROLE_COPIED)
    return target_fields, copy_fields


def _explicit_selected_field_names(
    params: Mapping[str, object],
    supported_fields: Sequence[AnnotationField],
) -> tuple[str, ...]:
    raw_selected_fields = params.get(SELECTED_LABEL_FIELDS_PARAM_NAME)
    if isinstance(raw_selected_fields, list | tuple):
        return tuple(str(field_name) for field_name in raw_selected_fields)

    names: list[str] = []
    for field in supported_fields:
        raw_value = params.get(annotation_field_param_name(field.name), True)
        if raw_value is True:
            names.append(field.name)
    return tuple(names)


def _annotation_fields_from_schema(schema: Mapping[str, Any]) -> tuple[AnnotationField | None, ...]:
    fields: list[AnnotationField | None] = []
    for field_name, field in schema.items():
        label_type = getattr(field, "document_type", None)
        if not _is_label_type(label_type):
            continue
        fields.append(_annotation_field(str(field_name), label_type))
    return tuple(fields)


def _annotation_field(field_name: str, label_type: object) -> AnnotationField | None:
    if isinstance(label_type, type) and issubclass(label_type, fo.Classification):
        return AnnotationField(field_name, FIELD_TYPE_CLASSIFICATION)
    if isinstance(label_type, type) and issubclass(label_type, fo.Detections):
        return AnnotationField(field_name, FIELD_TYPE_DETECTIONS, albu_target=ALBU_TARGET_BBOXES)
    if isinstance(label_type, type) and issubclass(label_type, fo.Heatmap):
        return AnnotationField(field_name, FIELD_TYPE_HEATMAP, albu_target=ALBU_TARGET_IMAGE)
    if isinstance(label_type, type) and issubclass(label_type, fo.Keypoints):
        return AnnotationField(field_name, FIELD_TYPE_KEYPOINTS, albu_target=ALBU_TARGET_KEYPOINTS)
    if isinstance(label_type, type) and issubclass(label_type, fo.Polylines):
        return AnnotationField(field_name, FIELD_TYPE_POLYLINES, albu_target=ALBU_TARGET_KEYPOINTS)
    if isinstance(label_type, type) and issubclass(label_type, fo.Segmentation):
        return AnnotationField(field_name, FIELD_TYPE_SEGMENTATION, albu_target=ALBU_TARGET_MASK)
    return None


def _field_target_requirements(
    field: AnnotationField,
    runtime_target_requirements: Mapping[str, Sequence[str]] | None,
) -> tuple[str, ...]:
    runtime_targets = () if runtime_target_requirements is None else runtime_target_requirements.get(field.name, ())
    return _ordered_targets((*field.albu_targets, *runtime_targets))


def _runtime_target_requirements_to_json(
    runtime_target_requirements: Mapping[str, Sequence[str]] | None,
) -> dict[str, list[str]]:
    if not runtime_target_requirements:
        return {}
    return {
        field_name: list(targets)
        for field_name, targets in (
            (str(field_name), _ordered_targets(targets)) for field_name, targets in runtime_target_requirements.items()
        )
        if targets
    }


def _runtime_field_targets(field_payload: Mapping[str, object]) -> tuple[str, ...]:
    field_type = _payload_type(field_payload)
    if field_type == FIELD_TYPE_DETECTIONS:
        detections = _payload_sequence(field_payload, "detections")
        targets = {ALBU_TARGET_BBOXES}
        if any(_MASK_FIELD in detection for detection in detections):
            targets.add(ALBU_TARGET_MASK)
        return _ordered_targets(targets)
    if field_type == FIELD_TYPE_HEATMAP:
        return (ALBU_TARGET_IMAGE,)
    if field_type in {FIELD_TYPE_KEYPOINTS, FIELD_TYPE_POLYLINES}:
        return (ALBU_TARGET_KEYPOINTS,)
    if field_type == FIELD_TYPE_SEGMENTATION and _MASK_FIELD in field_payload:
        return (ALBU_TARGET_MASK,)
    return ()


def _ordered_targets(targets: Sequence[str] | set[str]) -> tuple[str, ...]:
    target_set = {str(target) for target in targets if str(target)}
    ordered = [target for target in ALBU_TARGET_ORDER if target in target_set]
    ordered.extend(sorted(target_set.difference(ALBU_TARGET_ORDER)))
    return tuple(ordered)


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
    value = payload.get("type")
    return value if isinstance(value, str) else ""


def _payload_sequence(payload: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _unsupported_label_fields(schema: Mapping[str, Any]) -> dict[str, type[fo.Label]]:
    fields: dict[str, type[fo.Label]] = {}
    for field_name, field in schema.items():
        label_type = getattr(field, "document_type", None)
        if _is_label_type(label_type) and _annotation_field(str(field_name), label_type) is None:
            fields[str(field_name)] = label_type
    return fields


def _field_schema(dataset: Any) -> Mapping[str, Any]:
    get_field_schema = getattr(dataset, "get_field_schema", None)
    if not callable(get_field_schema):
        return {}
    schema = get_field_schema()
    return schema if isinstance(schema, Mapping) else {}


def _missing_field_exclusion(field_name: str, *, selected: bool) -> JSONDict:
    return {
        "field_name": field_name,
        "reason": "missing_field",
        "selected": selected,
        "message": "Selected label field does not exist in the dataset schema.",
    }


def _unsupported_field_exclusion(field_name: str, label_type: object, *, selected: bool) -> JSONDict:
    return {
        "field_name": field_name,
        "label_type": _label_type_name(label_type),
        "reason": "unsupported_label_type",
        "selected": selected,
        "message": "Label field is not supported by annotation-aware augmentation yet.",
    }


def _not_selected_field_exclusion(field: AnnotationField) -> JSONDict:
    return {
        **field.to_dict(),
        "reason": _EXCLUDED_REASON_NOT_SELECTED,
        "selected": False,
        "message": "Label field was not selected for this augmentation run.",
    }


def _transformed_targets(
    pipeline: PipelineConfig,
    catalog_provider: TransformCatalogProvider,
) -> frozenset[str]:
    targets: set[str] = set()
    for transform in pipeline.transforms:
        capability = catalog_provider.get_transform_capability(transform.name)
        if capability is None:
            continue
        if _capability_transform_type(capability.metadata) == _TRANSFORM_TYPE_IMAGE_ONLY:
            continue
        targets.update(capability.targets)
    return frozenset(targets)


def _capability_transform_type(metadata: Mapping[str, object]) -> str:
    value = metadata.get("transform_type")
    return value if isinstance(value, str) else ""


def _is_label_type(value: object) -> TypeGuard[type[fo.Label]]:
    return isinstance(value, type) and issubclass(value, fo.Label)


def _label_type_name(value: object) -> str:
    return value.__name__ if isinstance(value, type) else type(value).__name__
