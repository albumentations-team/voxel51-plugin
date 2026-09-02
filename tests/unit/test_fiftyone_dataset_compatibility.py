from __future__ import annotations

import importlib
import json
import pathlib
import sys
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast

import fiftyone as fo
import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.compatibility as compatibility_operator_module
from albumentationsx_plugin.core import CapabilityStatus, TransformCapability
from albumentationsx_plugin.hosts.fiftyone.dataset_compatibility import (
    build_dataset_compatibility_report,
    missing_dependency_compatibility_report,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CURRENT_VIEW,
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
)
from albumentationsx_plugin.hosts.fiftyone.operators.compatibility import (
    OPERATOR_NAME,
    AnalyzeAlbumentationsXCompatibility,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


class _Dataset:
    media_type = "image"

    def __init__(self, schema: dict[str, object], *, name: str = "compatibility-demo", count: int = 3) -> None:
        self.name = name
        self._schema = schema
        self._count = count

    def get_field_schema(self) -> dict[str, object]:
        return self._schema

    def count(self) -> int:
        return self._count


class _BrokenSchemaDataset:
    name = "broken-schema"
    media_type = "image"

    def get_field_schema(self) -> dict[str, object]:
        raise RuntimeError("schema backend unavailable")

    def count(self) -> int:
        return 1


class _View:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class _CatalogProvider:
    @property
    def version_info(self) -> Mapping[str, object]:
        return {"albumentationsx": "2.3.8", "albu_spec": "0.0.6"}

    def list_transform_capabilities(self) -> tuple[TransformCapability, ...]:
        return (
            _capability("ColorOnly", targets=("image",), transform_type="image_only"),
            _capability("HorizontalFlip", targets=("image", "bboxes", "keypoints", "mask"), transform_type="dual"),
            _capability(
                "RandomCrop",
                targets=("image", "bboxes", "keypoints", "mask"),
                transform_type="dual",
                status=CapabilityStatus.SUPPORTED_WITH_DEFAULTS,
            ),
            _capability(
                "Normalize",
                targets=("image",),
                transform_type="image_only",
                status=CapabilityStatus.UNSUPPORTED_OUTPUT,
            ),
            _capability(
                "VolumeOnly",
                targets=("volume",),
                transform_type="volume",
                status=CapabilityStatus.BLOCKED_MEDIA_TARGET,
            ),
        )


def _load_manifest() -> dict[str, Any]:
    with (ROOT / "fiftyone.yml").open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


def _field(label_type: type[fo.Label] | type[str]) -> SimpleNamespace:
    return SimpleNamespace(document_type=label_type)


def _dataset(*, count: int = 3) -> _Dataset:
    return _Dataset(
        {
            "ground_truth": _field(fo.Classification),
            "detections": _field(fo.Detections),
            "heatmap": _field(fo.Heatmap),
            "regression": _field(fo.Regression),
            "filepath": _field(str),
        },
        count=count,
    )


def _capability(
    name: str,
    *,
    targets: tuple[str, ...],
    transform_type: str,
    status: CapabilityStatus = CapabilityStatus.SUPPORTED,
) -> TransformCapability:
    return TransformCapability(
        name=name,
        status=status,
        targets=targets,
        metadata={"transform_type": transform_type},
    )


@pytest.mark.unit
def test_dataset_compatibility_report_lists_fields_targets_and_recommendations() -> None:
    report = build_dataset_compatibility_report(
        dataset=_dataset(),
        view=_View(2),
        selected_sample_ids=("sample-1",),
        source_scope=EXECUTION_SCOPE_CURRENT_VIEW,
        provider=_CatalogProvider(),
    )

    payload = cast(dict[str, Any], report.to_dict())
    field_rows = cast(list[dict[str, Any]], payload["annotation_fields"])
    target_rows = cast(list[dict[str, Any]], payload["target_families"])
    fields = {row["field_name"]: row for row in field_rows}
    targets = {row["target"]: row for row in target_rows}

    assert payload["status"] == "ok"
    assert payload["dataset_name"] == "compatibility-demo"
    assert payload["source_scope"] == EXECUTION_SCOPE_CURRENT_VIEW
    assert payload["source_count"] == 2
    assert payload["selected_sample_count"] == 1
    assert payload["capability_version_key"] == "albumentationsx-2.3.8__albu-spec-0.0.6"
    assert payload["detected_field_count"] == 4
    assert payload["supported_field_count"] == 3
    assert payload["unsupported_field_count"] == 1
    assert payload["copied_field_count"] == 1
    assert payload["transformable_field_count"] == 2
    assert payload["total_transform_count"] == 5
    assert payload["executable_transform_count"] == 3
    assert payload["excluded_transform_count"] == 2
    assert json.loads(str(payload["status_counts_json"])) == {
        "blocked_media_target": 1,
        "supported": 2,
        "supported_with_defaults": 1,
        "unsupported_output": 1,
    }
    assert fields["ground_truth"]["support_status"] == "copy_supported"
    assert fields["ground_truth"]["role"] == "copied"
    assert fields["detections"]["support_status"] == "transform_supported"
    assert fields["detections"]["target"] == "bboxes"
    assert fields["heatmap"]["support_status"] == "conditional"
    assert "geometry-only" in str(fields["heatmap"]["limitations"]).lower()
    assert fields["regression"]["support_status"] == "unsupported"
    assert targets["image"]["supported_transform_count"] == 3
    assert targets["image"]["excluded_transform_count"] == 1
    assert targets["volume"]["status"] == "not_available"
    assert "Preview only" in payload["recommendations_text"]
    assert "heatmap" in payload["recommendations_text"]
    assert json.loads(str(payload["report_json"]))["counts"]["executable_transforms"] == 3


@pytest.mark.unit
def test_dataset_compatibility_report_counts_selected_scope_without_view_count() -> None:
    report = build_dataset_compatibility_report(
        dataset=_dataset(count=9),
        selected_sample_ids=("sample-1", "sample-2"),
        source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
        provider=_CatalogProvider(),
    )

    payload = cast(dict[str, Any], report.to_dict())

    assert payload["source_scope"] == EXECUTION_SCOPE_SELECTED_SAMPLES
    assert payload["source_count"] == 2
    assert payload["source_count_available"] is True
    assert payload["selected_sample_count"] == 2


@pytest.mark.unit
def test_dataset_compatibility_report_handles_schema_errors() -> None:
    report = build_dataset_compatibility_report(
        dataset=_BrokenSchemaDataset(),
        source_scope=EXECUTION_SCOPE_CURRENT_VIEW,
        provider=_CatalogProvider(),
    )

    payload = cast(dict[str, Any], report.to_dict())

    assert payload["status"] == "ok"
    assert payload["metadata_available"] is False
    assert "RuntimeError" in payload["schema_warning"]
    assert payload["annotation_fields"] == []
    assert "schema could not be read" in payload["recommendations_text"]


@pytest.mark.unit
@pytest.mark.parametrize("missing_name", ("albumentations", "albu_spec"))
def test_missing_dependency_compatibility_report(missing_name: str) -> None:
    error = ModuleNotFoundError(f"No module named '{missing_name}'", name=missing_name)

    payload = cast(
        dict[str, Any],
        missing_dependency_compatibility_report(error, source_scope=EXECUTION_SCOPE_CURRENT_VIEW),
    )

    assert payload["status"] == "error"
    assert "Install the" in payload["message"]
    assert payload["source_scope"] == EXECUTION_SCOPE_CURRENT_VIEW
    assert payload["annotation_fields"] == []
    assert payload["target_families"] == []
    assert payload["report_json"]


@pytest.mark.unit
def test_compatibility_operator_config_matches_manifest() -> None:
    manifest = _load_manifest()
    operator = AnalyzeAlbumentationsXCompatibility()

    config = operator.config

    assert OPERATOR_NAME in manifest["operators"]
    assert config.name == OPERATOR_NAME
    assert config.label == "Analyze AlbumentationsX Compatibility"
    assert config.dynamic is True
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is False
    assert config.allow_distributed_execution is False
    assert config.risk_level.value == "low"


@pytest.mark.unit
def test_compatibility_operator_module_import_does_not_load_backend_dependencies() -> None:
    for module_name in ("albumentations", "albu_spec"):
        sys.modules.pop(module_name, None)

    importlib.reload(compatibility_operator_module)

    assert "albumentations" not in sys.modules
    assert "albu_spec" not in sys.modules


@pytest.mark.unit
def test_compatibility_operator_resolves_input_output_and_placement() -> None:
    operator = AnalyzeAlbumentationsXCompatibility()
    context = SimpleNamespace(dataset=_dataset(), selected=("sample-1",), params={})

    input_json = cast(dict[str, Any], operator.resolve_input(context).to_json())
    output_json = cast(dict[str, Any], operator.resolve_output(ctx=None).to_json())
    placement_json = cast(dict[str, Any], operator.resolve_placement(context).to_json())
    input_properties = input_json["type"]["properties"]
    output_properties = output_json["type"]["properties"]
    placement_view = cast(dict[str, Any], placement_json["view"])

    assert input_json["view"]["label"] == "Analyze AlbumentationsX Compatibility"
    assert input_json["view"]["submit_button_label"] == "Analyze compatibility"
    assert input_properties[EXECUTION_SCOPE_FIELD_NAME]["type"]["name"] == "Enum"
    assert input_properties[EXECUTION_SCOPE_FIELD_NAME]["default"] == EXECUTION_SCOPE_SELECTED_SAMPLES
    assert output_properties["annotation_fields"]["type"]["name"] == "List"
    assert output_properties["target_families"]["type"]["name"] == "List"
    assert output_properties["report_json"]["view"]["name"] == "CodeView"
    assert placement_json["place"] == "samples-grid-actions"
    assert placement_view["disabled"] is False


@pytest.mark.unit
def test_compatibility_operator_disables_placement_without_image_dataset() -> None:
    operator = AnalyzeAlbumentationsXCompatibility()

    placement_json = cast(dict[str, Any], operator.resolve_placement(SimpleNamespace(dataset=None)).to_json())
    placement_view = cast(dict[str, Any], placement_json["view"])

    assert placement_view["disabled"] is True
    assert "Open an image dataset" in placement_view["title"]


@pytest.mark.unit
def test_compatibility_operator_execute_delegates_to_report_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    operator = AnalyzeAlbumentationsXCompatibility()
    dataset = _dataset()
    view = _View(1)
    context = SimpleNamespace(
        dataset=dataset,
        view=view,
        selected=("sample-1",),
        params={EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_CURRENT_VIEW},
    )

    class Result:
        def to_dict(self) -> dict[str, object]:
            return {"status": "ok", "source_scope": EXECUTION_SCOPE_CURRENT_VIEW}

    def fake_build_report(**kwargs: object) -> Result:
        assert kwargs["dataset"] is dataset
        assert kwargs["view"] is view
        assert kwargs["selected_sample_ids"] == ("sample-1",)
        assert kwargs["source_scope"] == EXECUTION_SCOPE_CURRENT_VIEW
        return Result()

    monkeypatch.setattr(compatibility_operator_module, "build_dataset_compatibility_report", fake_build_report)

    assert operator.execute(context) == {"status": "ok", "source_scope": EXECUTION_SCOPE_CURRENT_VIEW}


@pytest.mark.unit
def test_compatibility_operator_execute_surfaces_invalid_scope() -> None:
    operator = AnalyzeAlbumentationsXCompatibility()
    context = SimpleNamespace(dataset=_dataset(), selected=(), params={EXECUTION_SCOPE_FIELD_NAME: "stale"})

    payload = cast(dict[str, Any], operator.execute(context))

    assert payload["status"] == "error"
    assert "valid source scope" in payload["message"]


@pytest.mark.unit
def test_compatibility_operator_execute_handles_missing_runtime_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    operator = AnalyzeAlbumentationsXCompatibility()
    error = ModuleNotFoundError("No module named 'albu_spec'", name="albu_spec")
    context = SimpleNamespace(dataset=_dataset(), view=None, selected=(), params={})

    def raise_missing_dependency(**kwargs: object) -> object:
        raise error

    monkeypatch.setattr(
        compatibility_operator_module,
        "build_dataset_compatibility_report",
        raise_missing_dependency,
    )

    payload = cast(dict[str, Any], operator.execute(context))

    assert payload["status"] == "error"
    assert "albu-spec" in payload["message"]
    assert payload["annotation_fields"] == []
