"""Describe the data copied, regenerated, and omitted on generated samples."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from albumentationsx_plugin.core import AugmentationInput, JSONDict
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations.fields import (
    ANNOTATION_PAYLOAD_KEY,
    AnnotationFieldSelection,
)
from albumentationsx_plugin.hosts.fiftyone.annotations.metadata import GEOMETRY_ATTRIBUTES, excluded_label_metadata
from albumentationsx_plugin.hosts.fiftyone.samples.adapter import (
    OUTPUT_TAG_FIELD,
    RUN_KEY_FIELD,
    SOURCE_SAMPLE_ID_FIELD,
    TRANSFORM_SUMMARY_FIELD,
)

OUTPUT_METADATA_POLICY = "output_metadata_policy"
_PROVENANCE_FIELDS = (SOURCE_SAMPLE_ID_FIELD, RUN_KEY_FIELD, TRANSFORM_SUMMARY_FIELD, OUTPUT_TAG_FIELD)
_REGENERATED_FIELDS = ("id", "filepath", "metadata", "created_at", "last_modified_at", *_PROVENANCE_FIELDS)


def build_output_metadata_policy(
    dataset: Any,
    selection: AnnotationFieldSelection,
    *,
    sources: Sequence[AugmentationInput] | None = None,
    transformed_fields: Sequence[str] = (),
) -> JSONDict:
    """Use schema for the form, and inspected values for execution diagnostics."""

    get_schema = getattr(dataset, "get_field_schema", None)
    schema = get_schema() if callable(get_schema) else {}
    schema = schema if isinstance(schema, Mapping) else {}
    excluded_annotations = [str(field["field_name"]) for field in selection.excluded_fields]
    annotation_names = set(selection.selected_field_names) | set(excluded_annotations)
    excluded_samples = sorted(
        name
        for name in schema
        if not name.startswith("_") and name not in annotation_names and name not in _REGENERATED_FIELDS
    )
    excluded_attributes: list[JSONDict] = []
    for source in sources or ():
        payload = source.metadata.get(ANNOTATION_PAYLOAD_KEY, {})
        fields = payload.get("fields", {}) if isinstance(payload, Mapping) else {}
        if isinstance(fields, Mapping):
            excluded_attributes.extend(
                {"sample_id": source.sample_id, **item}
                for item in excluded_label_metadata(fields, transformed_fields=transformed_fields)
            )
    return normalize_json_mapping(
        {
            "selected_annotation_fields": list(selection.selected_field_names),
            "excluded_annotation_fields": excluded_annotations,
            "excluded_sample_fields": excluded_samples,
            "regenerated_sample_fields": list(_REGENERATED_FIELDS),
            "source_sample_id_field": SOURCE_SAMPLE_ID_FIELD,
            "source_tags_copied": False,
            "label_ids_preserved": False,
            "geometry_attributes_excluded_when_transformed": sorted(GEOMETRY_ATTRIBUTES),
            "attributes_inspected": sources is not None,
            "excluded_label_attributes": excluded_attributes,
        }
    )


def metadata_policy_summary(policy: Mapping[str, object]) -> str:
    """Readable policy shared by the input form and all execution results."""

    def names(key: str) -> str:
        values = policy.get(key, [])
        if not isinstance(values, list | tuple):
            return "None"
        return ", ".join(str(value) for value in values) or "None"

    lines = [
        f"Included annotations: {names('selected_annotation_fields')}.",
        f"Omitted annotations: {names('excluded_annotation_fields')}. Unchecked fields are omitted.",
        f"Omitted source sample fields: {names('excluded_sample_fields')} (including source tags).",
        "Outputs receive new sample/label IDs, filepath, image metadata and output/run tags. "
        f"Originals stay unchanged and are linked by {SOURCE_SAMPLE_ID_FIELD}.",
        "Label tags and custom scalar, list and object attributes are preserved. Per-point metadata keeps its joint indices.",
        f"Excluded on transformed labels: {names('geometry_attributes_excluded_when_transformed')}. "
        "Other custom fields are copied as descriptive data; recompute any additional geometry-derived values.",
    ]
    if policy.get("attributes_inspected"):
        exclusions = policy.get("excluded_label_attributes", [])
        paths = (
            sorted({str(item["field_path"]) for item in exclusions if isinstance(item, Mapping)})
            if isinstance(exclusions, list | tuple)
            else []
        )
        lines.append("Excluded label attributes: " + (", ".join(paths) if paths else "None") + ".")
    else:
        lines.append("Preview or dry run lists the exact unsupported or derived label attributes that will be omitted.")
    return "\n\n".join(lines)


def metadata_policy_output_fields(policy: Mapping[str, object]) -> JSONDict:
    if not policy:
        return {}
    return {
        OUTPUT_METADATA_POLICY: normalize_json_mapping(policy),
        "metadata_policy_summary": metadata_policy_summary(policy),
    }


def policy_from_annotation_metadata(metadata: Mapping[str, object] | None) -> JSONDict:
    policy = metadata.get(OUTPUT_METADATA_POLICY) if metadata is not None else None
    return normalize_json_mapping(policy) if isinstance(policy, Mapping) else {}
