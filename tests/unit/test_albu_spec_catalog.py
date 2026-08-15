from __future__ import annotations

import importlib
import importlib.metadata
import json
import sys

import pytest

from albumentationsx_plugin.albumentations_backend.catalog import (
    AlbuSpecCatalogProvider,
    build_albu_spec_catalog_snapshot,
    build_capability_report,
)
from albumentationsx_plugin.core import CapabilityStatus
from scripts import report_transform_capabilities


@pytest.mark.unit
def test_albu_spec_catalog_snapshot_detects_version_drift() -> None:
    snapshot = build_albu_spec_catalog_snapshot()

    assert snapshot["version_key"] == "albumentationsx-2.3.8__albu-spec-0.0.6"
    assert snapshot["versions"] == {
        "albumentationsx": importlib.metadata.version("albumentationsx"),
        "albu_spec": importlib.metadata.version("albu-spec"),
    }
    assert snapshot["total_count"] == 134
    assert snapshot["supported_count"] == 110
    assert snapshot["status_counts"] == {
        "blocked_media_target": 7,
        "hidden": 1,
        "requires_external_data": 7,
        "supported": 69,
        "supported_with_defaults": 41,
        "unsupported_output": 2,
        "unsupported_target": 7,
    }


@pytest.mark.unit
def test_albu_spec_catalog_classifies_key_transform_capabilities() -> None:
    catalog = AlbuSpecCatalogProvider()

    horizontal_flip = catalog.get_transform_capability("HorizontalFlip")
    random_crop = catalog.get_transform_capability("RandomCrop")
    histogram_matching = catalog.get_transform_capability("HistogramMatching")
    normalize = catalog.get_transform_capability("Normalize")
    center_crop_3d = catalog.get_transform_capability("CenterCrop3D")
    bbox_safe_crop = catalog.get_transform_capability("BBoxSafeRandomCrop")
    noop = catalog.get_transform_capability("NoOp")

    assert horizontal_flip is not None
    assert horizontal_flip.status == CapabilityStatus.SUPPORTED
    assert horizontal_flip.metadata["parameter_names"] == ["p"]

    assert random_crop is not None
    assert random_crop.status == CapabilityStatus.SUPPORTED_WITH_DEFAULTS
    assert random_crop.reason_code == "advanced_parameters_hidden"
    assert "fill" in random_crop.advanced_parameters

    assert histogram_matching is not None
    assert histogram_matching.status == CapabilityStatus.REQUIRES_EXTERNAL_DATA
    assert histogram_matching.reason_code == "requires_metadata_input"

    assert normalize is not None
    assert normalize.status == CapabilityStatus.UNSUPPORTED_OUTPUT
    assert normalize.reason_code == "non_uint8_image_output"

    assert center_crop_3d is not None
    assert center_crop_3d.status == CapabilityStatus.BLOCKED_MEDIA_TARGET
    assert center_crop_3d.reason_code == "not_image_2d"

    assert bbox_safe_crop is not None
    assert bbox_safe_crop.status == CapabilityStatus.UNSUPPORTED_TARGET
    assert bbox_safe_crop.reason_code == "requires_annotation_target"

    assert noop is not None
    assert noop.status == CapabilityStatus.HIDDEN
    assert noop.reason_code == "not_user_visible"


@pytest.mark.unit
def test_albu_spec_catalog_lists_supported_choices_without_fiftyone_ui_imports() -> None:
    sys.modules.pop("fiftyone", None)
    importlib.import_module("albumentationsx_plugin.albumentations_backend.catalog")

    catalog = AlbuSpecCatalogProvider()
    names = catalog.list_supported_transform_names()

    assert "fiftyone" not in sys.modules
    assert "HorizontalFlip" in names
    assert "RandomBrightnessContrast" in names
    assert "RandomCrop" in names
    assert "Normalize" not in names
    assert "CenterCrop3D" not in names
    assert "BBoxSafeRandomCrop" not in names


@pytest.mark.unit
def test_capability_report_groups_supported_and_excluded_transforms() -> None:
    report = build_capability_report()

    assert "version key: albumentationsx-2.3.8__albu-spec-0.0.6" in report
    assert "- supported: 69" in report
    assert "- supported_with_defaults: 41" in report
    assert "- unsupported_output: Normalize, ToFloat" in report
    assert "- blocked_media_target: CenterCrop3D" in report


@pytest.mark.unit
def test_capability_report_script_outputs_json_and_files(tmp_path, capsys) -> None:
    output_path = tmp_path / "catalog-report.json"

    assert report_transform_capabilities.main(["--format", "json"]) == 0
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert payload["version_key"] == "albumentationsx-2.3.8__albu-spec-0.0.6"

    assert report_transform_capabilities.main(["--format", "json", "--output", str(output_path)]) == 0
    written_payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert written_payload["status_counts"] == payload["status_counts"]
