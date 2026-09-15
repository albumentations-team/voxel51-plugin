"""Materialize transformed annotation assets owned by a plugin run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import cast

import numpy as np

from albumentationsx_plugin.core import JSONDict, JSONValue
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations.fields import FIELD_TYPE_SEGMENTATION
from albumentationsx_plugin.storage.images import build_output_mask_relative_path, write_mask_image

_TYPE_FIELD = "type"
_MASK_FIELD = "mask"
_MASK_PATH_FIELD = "mask_path"
_MASK_RELATIVE_PATH_FIELD = "mask_relative_path"
_SOURCE_MASK_PATH_FIELD = "source_mask_path"
_SEGMENTATION_MASK_ASSET_KIND = "segmentation_mask"


@dataclass(frozen=True, slots=True)
class MaterializedAnnotationAssets:
    """Annotation payload plus manifest-relative files created for labels."""

    labels: JSONDict
    relative_paths: tuple[str, ...] = ()
    metadata: JSONDict | None = None


def materialize_annotation_assets(
    labels: Mapping[str, object],
    *,
    run_dir: str | PathLike[str],
    source_filepath: str | PathLike[str],
    sample_id: str,
    output_index: int,
) -> MaterializedAnnotationAssets:
    """Write transformed file-backed annotation assets and update label payload."""

    fields = labels.get("fields")
    if not isinstance(fields, Mapping):
        return MaterializedAnnotationAssets(labels=normalize_json_mapping(labels))

    run_path = Path(run_dir)
    updated_fields: dict[str, JSONValue] = {}
    relative_paths: list[str] = []
    asset_metadata: list[JSONDict] = []

    try:
        for field_name, raw_field_payload in fields.items():
            field_payload = raw_field_payload if isinstance(raw_field_payload, Mapping) else {}
            updated_field, asset = _materialize_field(
                str(field_name),
                field_payload,
                run_dir=run_path,
                source_filepath=source_filepath,
                sample_id=sample_id,
                output_index=output_index,
            )
            updated_fields[str(field_name)] = updated_field
            if asset:
                relative_paths.append(str(asset["relative_path"]))
                asset_metadata.append(asset)
    except Exception:
        for relative_path in relative_paths:
            (run_path / relative_path).unlink(missing_ok=True)
        raise

    updated_labels = dict(labels)
    updated_labels["fields"] = normalize_json_mapping(updated_fields)
    metadata = {"assets": asset_metadata} if asset_metadata else None
    return MaterializedAnnotationAssets(
        labels=normalize_json_mapping(updated_labels),
        relative_paths=tuple(relative_paths),
        metadata=normalize_json_mapping(metadata) if metadata is not None else None,
    )


def _materialize_field(
    field_name: str,
    field_payload: Mapping[str, object],
    *,
    run_dir: Path,
    source_filepath: str | PathLike[str],
    sample_id: str,
    output_index: int,
) -> tuple[JSONDict, JSONDict | None]:
    if not _should_materialize_mask(field_payload):
        return normalize_json_mapping(field_payload), None

    relative_path = build_output_mask_relative_path(
        source_filepath,
        sample_id=sample_id,
        output_index=output_index,
        field_name=field_name,
    )
    mask_path = write_mask_image(np.asarray(field_payload[_MASK_FIELD]), run_dir, relative_path)
    relative_path_text = relative_path.as_posix()
    updated_field = dict(field_payload)
    updated_field.pop(_MASK_FIELD, None)
    updated_field.pop(_SOURCE_MASK_PATH_FIELD, None)
    updated_field[_MASK_PATH_FIELD] = str(mask_path)
    updated_field[_MASK_RELATIVE_PATH_FIELD] = relative_path_text
    asset = {
        "field_name": field_name,
        "kind": _SEGMENTATION_MASK_ASSET_KIND,
        "relative_path": relative_path_text,
        "filepath": str(mask_path),
    }
    return normalize_json_mapping(updated_field), cast(JSONDict, asset)


def _should_materialize_mask(field_payload: Mapping[str, object]) -> bool:
    return (
        field_payload.get(_TYPE_FIELD) == FIELD_TYPE_SEGMENTATION
        and isinstance(field_payload.get(_SOURCE_MASK_PATH_FIELD), str)
        and field_payload.get(_MASK_FIELD) is not None
    )
