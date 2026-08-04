from __future__ import annotations

import importlib
import pathlib
import sys
from collections.abc import Iterable, Iterator
from typing import Any

import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.augment as augment_operator_module
from albumentationsx_plugin.hosts.fiftyone.augmentation import FixedAugmentationExecutionResult
from albumentationsx_plugin.hosts.fiftyone.operators.augment import (
    OPERATOR_NAME,
    AugmentWithAlbumentationsX,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


class _ImageMetadata:
    def __init__(self, *, width: int | None = None, height: int | None = None) -> None:
        self.width = width
        self.height = height


class _Sample:
    def __init__(self, sample_id: str, *, width: int | None = None, height: int | None = None) -> None:
        self.id = sample_id
        self.metadata = None if width is None or height is None else _ImageMetadata(width=width, height=height)


class _SampleCollection:
    def __init__(self, samples: Iterable[_Sample]) -> None:
        self._samples = {sample.id: sample for sample in samples}

    def __iter__(self) -> Iterator[_Sample]:
        return iter(self._samples.values())

    def select(self, sample_ids: Iterable[str]) -> _SampleCollection:
        return _SampleCollection(self._samples[sample_id] for sample_id in sample_ids if sample_id in self._samples)

    def get_sample(self, sample_id: str) -> _Sample:
        return self._samples[sample_id]


class _DatasetSchema:
    def __init__(self, fields: dict[str, str]) -> None:
        self._fields = fields

    def get_field_schema(self) -> dict[str, dict[str, str]]:
        return {field_name: {"document_type": document_type} for field_name, document_type in self._fields.items()}


class _BrokenDatasetSchema:
    def get_field_schema(self) -> dict[str, object]:
        raise RuntimeError("schema backend is unavailable")


def _load_manifest() -> dict[str, Any]:
    with (ROOT / "fiftyone.yml").open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


@pytest.mark.unit
def test_augment_operator_config_matches_manifest() -> None:
    manifest = _load_manifest()
    operator = AugmentWithAlbumentationsX()

    config = operator.config

    assert OPERATOR_NAME in manifest["operators"]
    assert config.name == OPERATOR_NAME
    assert config.label == "Augment with AlbumentationsX"
    assert config.description == "Build and apply AlbumentationsX augmentation pipelines to selected samples."
    assert config.dynamic is True
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is False
    assert config.allow_distributed_execution is False
    assert config.risk_level.value == "low"


@pytest.mark.unit
def test_augment_operator_module_import_does_not_load_backend_dependencies() -> None:
    for module_name in ("albumentations", "albu_spec"):
        sys.modules.pop(module_name, None)

    importlib.reload(augment_operator_module)

    assert "albumentations" not in sys.modules
    assert "albu_spec" not in sys.modules


@pytest.mark.unit
def test_augment_operator_resolves_dynamic_default_input_and_output() -> None:
    operator = AugmentWithAlbumentationsX()

    input_json = operator.resolve_input(ctx=None).to_json()
    output_json = operator.resolve_output(ctx=None).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_json["view"]["label"] == "Augment with AlbumentationsX"
    assert input_json["view"]["name"] == "PromptView"
    assert input_json["view"]["submit_button_label"] == "Run augmentation"
    assert input_properties["_general_settings"]["view"]["name"] == "Header"
    assert input_properties["_general_settings"]["view"]["label"] == "General"
    assert input_properties["_pipeline_stage_1"]["view"]["name"] == "Header"
    assert input_properties["_pipeline_stage_1"]["view"]["label"] == "Stage 1"
    assert input_properties["_target_compatibility"]["view"]["name"] == "Notice"
    assert "Dataset labels: metadata unavailable" in input_properties["_target_compatibility"]["view"]["description"]
    assert input_properties["pipeline_step_count"]["type"]["name"] == "Number"
    assert input_properties["pipeline_step_count"]["default"] == 1
    assert input_properties["pipeline_step_count"]["required"] is False
    transform_values = input_properties["transform"]["type"]["values"]
    assert input_properties["transform"]["type"]["name"] == "Enum"
    assert input_properties["transform"]["default"] == "HorizontalFlip"
    assert input_properties["transform"]["required"] is False
    assert input_properties["transform"]["view"]["name"] == "AutocompleteView"
    assert "HorizontalFlip" in transform_values
    assert "RandomBrightnessContrast" in transform_values
    assert "RandomCrop" in transform_values
    assert "ToGray" in transform_values
    assert "CoarseDropout" in transform_values
    assert len(transform_values) > 3
    assert "Normalize" not in transform_values
    assert "BBoxSafeRandomCrop" not in transform_values
    assert input_properties["run_label"]["type"]["name"] == "String"
    assert input_properties["run_label"]["default"] == ""
    assert input_properties["run_label"]["required"] is False
    assert input_properties["p"]["type"]["name"] == "Number"
    assert input_properties["p"]["default"] == 1.0
    assert "Constraints: >= 0, <= 1." in input_properties["p"]["view"]["description"]
    assert input_properties["outputs_per_sample"]["type"]["name"] == "Number"
    assert input_properties["outputs_per_sample"]["required"] is False
    assert input_properties["outputs_per_sample"]["default"] == 1
    assert input_properties["dry_run"]["type"]["name"] == "Boolean"
    assert output_json["type"]["properties"]["run_key"]["type"]["name"] == "String"
    assert output_json["type"]["properties"]["processed_count"]["type"]["name"] == "Number"
    assert output_json["type"]["properties"]["created_count"]["type"]["name"] == "Number"
    assert output_json["type"]["properties"]["error_count"]["type"]["name"] == "Number"
    assert output_json["type"]["properties"]["manifest_path"]["type"]["name"] == "String"
    assert output_json["type"]["properties"]["fiftyone_run_key"]["type"]["name"] == "String"


@pytest.mark.unit
def test_augment_operator_resolves_ordered_pipeline_steps() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {
            "pipeline_step_count": 2,
            "transform": "HorizontalFlip",
            "step_2_transform": "RandomBrightnessContrast",
        }

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["pipeline_step_count"]["default"] == 2
    assert input_properties["_pipeline_stage_1"]["view"]["label"] == "Stage 1"
    assert input_properties["transform"]["default"] == "HorizontalFlip"
    assert input_properties["_pipeline_stage_2"]["view"]["label"] == "Stage 2"
    assert input_properties["step_2_transform"]["default"] == "RandomBrightnessContrast"
    assert input_properties["step_2_brightness_range"]["type"]["name"] == "Tuple"
    assert input_properties["step_2_contrast_range"]["type"]["name"] == "Tuple"
    assert input_properties["step_2_p"]["default"] == 1.0
    assert "step_2_brightness_by_max" not in input_properties
    assert "step_2_ensure_safe_output" not in input_properties
    assert "step_3_transform" not in input_properties


@pytest.mark.unit
def test_augment_operator_resolves_later_step_random_crop_defaults() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {
            "pipeline_step_count": 3,
            "transform": "HorizontalFlip",
            "step_2_transform": "RandomBrightnessContrast",
            "step_3_transform": "RandomCrop",
        }

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["step_3_height"]["required"] is False
    assert input_properties["step_3_height"]["default"] == 32
    assert input_properties["step_3_width"]["required"] is False
    assert input_properties["step_3_width"]["default"] == 32
    assert input_properties["step_3_p"]["default"] == 1.0
    assert "step_3_pad_if_needed" not in input_properties
    assert "step_3_border_mode" not in input_properties


@pytest.mark.unit
def test_augment_operator_resolve_input_reports_missing_runtime_dependency(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    def fake_build_dynamic_augment_form(_ctx: object):
        raise ModuleNotFoundError("No module named 'albu_spec'", name="albu_spec")

    monkeypatch.setattr(augment_operator_module, "_build_dynamic_augment_form", fake_build_dynamic_augment_form)

    input_json = operator.resolve_input(ctx=None).to_json()
    message = input_json["type"]["properties"]["missing_runtime_dependency"]

    assert message["view"]["label"] == "Missing runtime dependency"
    assert "albu-spec" in message["view"]["description"]


@pytest.mark.unit
def test_augment_operator_resolves_selected_transform_parameter_schema() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "RandomBrightnessContrast"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["brightness_range"]["type"]["name"] == "Tuple"
    assert input_properties["brightness_range"]["default"] == [-0.2, 0.2]
    assert input_properties["contrast_range"]["type"]["name"] == "Tuple"
    assert input_properties["contrast_range"]["default"] == [-0.2, 0.2]
    assert input_properties["p"]["default"] == 1.0
    assert "brightness_by_max" not in input_properties
    assert "ensure_safe_output" not in input_properties
    assert "execution_scope" not in input_properties


@pytest.mark.unit
def test_augment_operator_renders_target_compatibility_for_supported_dataset_labels() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = _DatasetSchema(
            {
                "ground_truth": "Classification",
                "detections": "Detections",
                "keypoints": "Keypoints",
                "segmentation": "Segmentation",
            }
        )
        params = {"transform": "HorizontalFlip"}

    input_json = operator.resolve_input(Context()).to_json()
    target_guidance = input_json["type"]["properties"]["_target_compatibility"]["view"]

    assert target_guidance["name"] == "Notice"
    assert (
        "Targets: image: supported; bboxes: supported; masks: supported; keypoints: supported; labels: copied."
        in (target_guidance["description"])
    )
    assert (
        "Dataset labels: bboxes (detections); masks (segmentation); keypoints (keypoints); labels (ground_truth)."
        in (target_guidance["description"])
    )


@pytest.mark.unit
def test_augment_operator_warns_when_transform_does_not_support_dataset_labels() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = _DatasetSchema({"detections": "Detections"})
        params = {"transform": "RandomBrightnessContrast"}

    input_json = operator.resolve_input(Context()).to_json()
    target_guidance = input_json["type"]["properties"]["_target_compatibility"]["view"]

    assert target_guidance["name"] == "Warning"
    assert "bboxes: not supported" in target_guidance["description"]
    assert "Dataset labels: bboxes (detections)." in target_guidance["description"]
    assert (
        "Warning: selected transform does not declare support for bboxes fields detections."
        in (target_guidance["description"])
    )


@pytest.mark.unit
def test_augment_operator_renders_target_guidance_without_dataset_metadata() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    target_guidance = input_json["type"]["properties"]["_target_compatibility"]["view"]

    assert target_guidance["name"] == "Notice"
    assert "Dataset labels: metadata unavailable" in target_guidance["description"]
    assert "Hidden advanced parameters use Albumentations defaults:" in target_guidance["description"]


@pytest.mark.unit
def test_augment_operator_keeps_target_guidance_resilient_to_schema_errors() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = _BrokenDatasetSchema()
        params = {"transform": "HorizontalFlip"}

    input_json = operator.resolve_input(Context()).to_json()
    target_guidance = input_json["type"]["properties"]["_target_compatibility"]["view"]

    assert target_guidance["name"] == "Notice"
    assert "Dataset labels: metadata unavailable" in target_guidance["description"]


@pytest.mark.unit
def test_augment_operator_resolves_random_crop_without_initial_required_errors() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["height"]["required"] is False
    assert input_properties["height"]["default"] == 32
    assert input_properties["width"]["required"] is False
    assert input_properties["width"]["default"] == 32
    assert input_properties["p"]["default"] == 1.0
    assert "pad_if_needed" not in input_properties
    assert "pad_position" not in input_properties
    assert "border_mode" not in input_properties


@pytest.mark.unit
def test_augment_operator_limits_random_crop_defaults_to_selected_sample_dimensions() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = _SampleCollection((_Sample("sample-1", width=24, height=18),))
        selected = ("sample-1",)
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["height"]["required"] is False
    assert input_properties["height"]["default"] == 18
    assert input_properties["width"]["required"] is False
    assert input_properties["width"]["default"] == 24
    assert "Default is limited by the selected image dimensions." in input_properties["height"]["view"]["description"]
    assert "Default is limited by the selected image dimensions." in input_properties["width"]["view"]["description"]


@pytest.mark.unit
def test_augment_operator_limits_random_crop_defaults_to_selected_samples_context() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        selected_samples = _SampleCollection(
            (
                _Sample("sample-1", width=29, height=27),
                _Sample("sample-2", width=21, height=19),
            )
        )
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["height"]["default"] == 19
    assert input_properties["width"]["default"] == 21
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["height"]["view"]["description"])
    )
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["width"]["view"]["description"])
    )


@pytest.mark.unit
def test_augment_operator_limits_random_crop_defaults_to_selected_view_samples() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        view = _SampleCollection(
            (
                _Sample("sample-1", width=7, height=5),
                _Sample("sample-2", width=30, height=28),
                _Sample("sample-3", width=22, height=24),
            )
        )
        selected = ("sample-2", "sample-3")
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["height"]["default"] == 24
    assert input_properties["width"]["default"] == 22
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["height"]["view"]["description"])
    )
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["width"]["view"]["description"])
    )


@pytest.mark.unit
def test_augment_operator_uses_static_random_crop_defaults_when_selected_metadata_is_missing() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = _SampleCollection((_Sample("sample-1"),))
        selected = ("sample-1",)
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["height"]["default"] == 32
    assert input_properties["width"]["default"] == 32


@pytest.mark.unit
def test_augment_operator_uses_conservative_random_crop_defaults_for_mixed_selected_dimensions() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = _SampleCollection(
            (
                _Sample("sample-1", width=80, height=60),
                _Sample("sample-2", width=20, height=16),
            )
        )
        selected = ("sample-1", "sample-2")
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["height"]["default"] == 16
    assert input_properties["width"]["default"] == 20
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["height"]["view"]["description"])
    )
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["width"]["view"]["description"])
    )


@pytest.mark.unit
def test_augment_operator_resolves_catalog_transform_parameter_schema() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "ToGray"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["transform"]["default"] == "ToGray"
    assert input_properties["num_output_channels"]["type"]["name"] == "Number"
    assert input_properties["num_output_channels"]["default"] == 3
    assert input_properties["method"]["type"]["name"] == "Enum"
    assert "weighted_average" in input_properties["method"]["type"]["values"]
    assert input_properties["p"]["default"] == 1.0


@pytest.mark.unit
def test_augment_operator_hides_supported_with_defaults_advanced_parameters() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "CoarseDropout"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["transform"]["default"] == "CoarseDropout"
    assert input_properties["num_holes_range"]["type"]["name"] == "Tuple"
    assert input_properties["hole_height_range"]["type"]["name"] == "Tuple"
    assert input_properties["hole_width_range"]["type"]["name"] == "Tuple"
    assert input_properties["p"]["default"] == 1.0
    assert "fill" not in input_properties
    assert "fill_mask" not in input_properties


@pytest.mark.unit
def test_augment_operator_ignores_excluded_catalog_transform_selection() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "Normalize"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties["transform"]["default"] == "HorizontalFlip"
    assert input_properties["p"]["type"]["name"] == "Number"
    assert "method" not in input_properties
    assert "mean" not in input_properties
    assert "execution_scope" not in input_properties


@pytest.mark.unit
def test_augment_operator_resolves_samples_grid_placement() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        selected = ("sample-1",)

    placement_json = operator.resolve_placement(Context()).to_json()
    view_json = placement_json["view"]

    assert placement_json["place"] == "samples-grid-actions"
    assert isinstance(view_json, dict)
    assert view_json["name"] == "Button"
    assert view_json["label"] == "Augment with AlbumentationsX"
    assert view_json["prompt"] is True
    assert view_json["disabled"] is False


@pytest.mark.unit
def test_augment_operator_disables_samples_grid_placement_without_selection() -> None:
    operator = AugmentWithAlbumentationsX()

    placement_json = operator.resolve_placement(ctx=None).to_json()
    view_json = placement_json["view"]

    assert isinstance(view_json, dict)
    assert view_json["disabled"] is True
    assert view_json["title"] == "Select samples to augment."


@pytest.mark.unit
def test_augment_operator_execute_delegates_to_fixed_executor(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        view = object()
        selected = ("sample-1",)
        params = {"transform": "HorizontalFlip"}
        triggered: list[str] = []

        @classmethod
        def trigger(cls, operator_name: str):
            cls.triggered.append(operator_name)

    def fake_execute_fixed_augmentation(**kwargs):
        assert kwargs["dataset"] is Context.dataset
        assert kwargs["view"] is Context.view
        assert kwargs["selected_sample_ids"] == ("sample-1",)
        assert kwargs["params"] == {"transform": "HorizontalFlip"}
        return FixedAugmentationExecutionResult(
            run_key="albumentationsx-20260731T120000Z-test",
            processed_count=1,
            created_count=1,
            skipped_count=0,
            error_count=0,
            dry_run=False,
            output_tag="albumentationsx-output",
            output_dir="/tmp/outputs",
            manifest_path="/tmp/outputs/manifest.json",
            fiftyone_run_key="albumentationsx_20260731T120000Z_test",
        )

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    assert operator.execute(Context()) == {
        "run_key": "albumentationsx-20260731T120000Z-test",
        "processed_count": 1,
        "created_count": 1,
        "skipped_count": 0,
        "error_count": 0,
        "dry_run": False,
        "output_tag": "albumentationsx-output",
        "output_dir": "/tmp/outputs",
        "manifest_path": "/tmp/outputs/manifest.json",
        "fiftyone_run_key": "albumentationsx_20260731T120000Z_test",
        "errors": [],
    }
    assert Context.triggered == ["reload_dataset"]


@pytest.mark.unit
def test_augment_operator_execute_does_not_refresh_dry_runs(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        selected = ("sample-1",)
        params = {"transform": "HorizontalFlip", "dry_run": True}
        triggered: list[str] = []

        @classmethod
        def trigger(cls, operator_name: str):
            cls.triggered.append(operator_name)

    def fake_execute_fixed_augmentation(**_kwargs):
        return FixedAugmentationExecutionResult(
            run_key="albumentationsx-20260731T120000Z-test",
            processed_count=1,
            created_count=0,
            skipped_count=0,
            error_count=0,
            dry_run=True,
            output_tag="albumentationsx-output",
            output_dir="/tmp/outputs",
            fiftyone_run_key="albumentationsx_20260731T120000Z_test",
        )

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    result = operator.execute(Context())

    assert result["dry_run"] is True
    assert result["created_count"] == 0
    assert Context.triggered == []


@pytest.mark.unit
def test_augment_operator_execute_reports_empty_selection_without_backend_call(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        selected = ()
        params = {"dry_run": True}

    def fake_execute_fixed_augmentation(**_kwargs):
        raise AssertionError("backend should not run without selected samples")

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    result = operator.execute(Context())

    assert result["error_count"] == 1
    assert result["dry_run"] is True
    errors = result["errors"]
    assert isinstance(errors, list)
    first_error = errors[0]
    assert isinstance(first_error, dict)
    assert first_error["code"] == "no_selected_samples"


@pytest.mark.unit
def test_augment_operator_execute_reports_missing_runtime_dependency(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        selected = ("sample-1",)
        params: dict[str, object] = {}

    def fake_execute_fixed_augmentation(**_kwargs: object):
        raise ModuleNotFoundError("No module named 'albumentations'", name="albumentations")

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    result = operator.execute(Context())

    assert result["error_count"] == 1
    errors = result["errors"]
    assert isinstance(errors, list)
    first_error = errors[0]
    assert isinstance(first_error, dict)
    assert first_error["code"] == "missing_runtime_dependency"
    assert first_error["context"] == {
        "missing_module": "albumentations",
        "package": "albumentationsx",
    }
