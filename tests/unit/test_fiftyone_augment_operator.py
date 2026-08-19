from __future__ import annotations

import importlib
import pathlib
import sys
from collections.abc import Iterable, Iterator
from types import SimpleNamespace
from typing import Any

import fiftyone as fo
import pytest
import yaml

import albumentationsx_plugin.hosts.fiftyone.operators.augment as augment_operator_module
from albumentationsx_plugin.core import (
    MAX_PIPELINE_STEPS,
    PipelineConfig,
    RunManifest,
    TransformConfig,
    pipeline_stage_enabled_field_name,
    pipeline_stage_order_field_name,
    pipeline_step_field_name,
)
from albumentationsx_plugin.hosts.fiftyone.annotations import annotation_field_param_name
from albumentationsx_plugin.hosts.fiftyone.augmentation import FixedAugmentationExecutionResult
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_CURRENT_VIEW,
    EXECUTION_SCOPE_ENTIRE_DATASET,
    EXECUTION_SCOPE_FIELD_NAME,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
)
from albumentationsx_plugin.hosts.fiftyone.form_params import stage_parameter_group_name
from albumentationsx_plugin.hosts.fiftyone.operators.augment import (
    OPERATOR_NAME,
    AugmentWithAlbumentationsX,
)
from albumentationsx_plugin.hosts.fiftyone.presets import (
    PREVIOUS_RUN_KEY_FIELD_NAME,
    STORAGE_ROOT_PARAM_NAME,
    operator_params_from_pipeline,
)
from albumentationsx_plugin.hosts.fiftyone.progress import (
    DELEGATED_EXECUTION_RECOMMENDED_SOURCE_COUNT,
    FiftyOneProgressReporter,
)
from albumentationsx_plugin.storage import FileRunStore

ROOT = pathlib.Path(__file__).resolve().parents[2]
ANNOTATION_FIELD_GROUP_NAME = "_annotation_fields"


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


class _FieldSchemaDataset:
    media_type = "image"

    def __init__(self, schema: dict[str, object]) -> None:
        self._schema = schema

    def get_field_schema(self) -> dict[str, object]:
        return self._schema


def _load_manifest() -> dict[str, Any]:
    with (ROOT / "fiftyone.yml").open("r", encoding="utf-8") as file:
        value = yaml.safe_load(file)

    assert isinstance(value, dict)
    return value


def _preset_manifest(run_key: str = "albumentationsx-20260731T150000Z-preset") -> RunManifest:
    return RunManifest(
        run_key=run_key,
        plugin_version="0.1.0",
        dependency_versions={"albumentationsx": "2.3.7", "albu-spec": "0.0.6", "fiftyone": "1.19.0"},
        pipeline=PipelineConfig(
            transforms=(
                TransformConfig(
                    name="RandomBrightnessContrast",
                    params={
                        "brightness_range": [0.1, 0.2],
                        "contrast_range": [0.3, 0.4],
                        "p": 0.8,
                    },
                ),
                TransformConfig(
                    name="RandomCrop",
                    params={
                        "height": 12,
                        "width": 10,
                        "p": 1.0,
                    },
                ),
            ),
            outputs_per_sample=2,
        ),
    )


def _form_properties(input_json: dict[str, Any]) -> dict[str, Any]:
    properties = dict(input_json["type"]["properties"])
    group_names = [
        ANNOTATION_FIELD_GROUP_NAME,
        *(stage_parameter_group_name(step_number) for step_number in range(1, MAX_PIPELINE_STEPS + 1)),
    ]
    for group_name in group_names:
        group = properties.get(group_name)
        if isinstance(group, dict):
            group_type = group.get("type")
            if isinstance(group_type, dict):
                group_properties = group_type.get("properties")
                if isinstance(group_properties, dict):
                    properties.update(group_properties)
    return properties


def _field(label_type: type[fo.Label] | type[str]) -> SimpleNamespace:
    return SimpleNamespace(document_type=label_type)


@pytest.mark.unit
def test_augment_operator_config_matches_manifest() -> None:
    manifest = _load_manifest()
    operator = AugmentWithAlbumentationsX()

    config = operator.config

    assert OPERATOR_NAME in manifest["operators"]
    assert config.name == OPERATOR_NAME
    assert config.label == "Augment with AlbumentationsX"
    assert (
        config.description == "Build and apply AlbumentationsX augmentation pipelines to samples, views, or datasets."
    )
    assert config.dynamic is True
    assert config.allow_immediate_execution is True
    assert config.allow_delegated_execution is True
    assert config.default_choice_to_delegated is False
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
    input_properties = _form_properties(input_json)

    assert input_json["view"]["label"] == "Augment with AlbumentationsX"
    assert input_json["view"]["name"] == "PromptView"
    assert input_json["view"]["submit_button_label"] == "Run augmentation"
    assert input_properties["_general_settings"]["view"]["name"] == "Header"
    assert input_properties["_general_settings"]["view"]["label"] == "General"
    assert input_properties["_pipeline_stage_1"]["view"]["name"] == "Header"
    assert input_properties["_pipeline_stage_1"]["view"]["label"] == "Stage 1"
    assert input_properties[stage_parameter_group_name(1)]["view"]["name"] == "GridView"
    assert input_properties[stage_parameter_group_name(1)]["view"]["orientation"] == "2d"
    assert "_target_compatibility" not in input_properties
    assert input_properties["pipeline_step_count"]["type"]["name"] == "Number"
    assert input_properties["pipeline_step_count"]["default"] == 1
    assert input_properties["pipeline_step_count"]["required"] is False
    assert input_properties["pipeline_stage_enabled"]["type"]["name"] == "Boolean"
    assert input_properties["pipeline_stage_enabled"]["default"] is True
    assert input_properties["pipeline_stage_enabled"]["view"]["caption"] == (
        "Skip this stage without clearing its transform settings."
    )
    assert input_properties["pipeline_stage_order"]["type"]["name"] == "Number"
    assert input_properties["pipeline_stage_order"]["default"] == 1
    assert input_properties["pipeline_stage_order"]["view"]["caption"] == (
        "Lower values run earlier; ties keep stage slot order."
    )
    transform_values = input_properties["transform"]["type"]["values"]
    assert input_properties["transform"]["type"]["name"] == "Enum"
    assert input_properties["transform"]["default"] == "HorizontalFlip"
    assert input_properties["transform"]["required"] is False
    assert input_properties["transform"]["view"]["name"] == "AutocompleteView"
    assert input_properties["transform"]["view"]["label"] == "Transform"
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
    assert input_properties[EXECUTION_SCOPE_FIELD_NAME]["type"]["name"] == "Enum"
    assert input_properties[EXECUTION_SCOPE_FIELD_NAME]["default"] == EXECUTION_SCOPE_CURRENT_VIEW
    assert input_properties[EXECUTION_SCOPE_FIELD_NAME]["required"] is True
    assert set(input_properties[EXECUTION_SCOPE_FIELD_NAME]["type"]["values"]) == {
        EXECUTION_SCOPE_SELECTED_SAMPLES,
        EXECUTION_SCOPE_CURRENT_VIEW,
        EXECUTION_SCOPE_ENTIRE_DATASET,
    }
    assert input_properties["_execution_mode_guidance"]["view"]["name"] == "Notice"
    assert input_properties["_execution_mode_guidance"]["view"]["label"] == "Execution mode"
    assert (
        str(DELEGATED_EXECUTION_RECOMMENDED_SOURCE_COUNT)
        in input_properties["_execution_mode_guidance"]["view"]["description"]
    )
    assert input_properties["p"]["type"]["name"] == "Number"
    assert input_properties["p"]["default"] == 1.0
    assert input_properties["p"]["view"]["label"] == "Probability"
    assert input_properties["p"]["view"]["description"] is None
    assert input_properties["p"]["view"]["caption"] == "Probability of applying the transform."
    assert input_properties["outputs_per_sample"]["type"]["name"] == "Number"
    assert input_properties["outputs_per_sample"]["required"] is False
    assert input_properties["outputs_per_sample"]["default"] == 1
    assert input_properties["dry_run"]["type"]["name"] == "Boolean"
    assert output_json["type"]["properties"]["run_key"]["type"]["name"] == "String"
    assert output_json["type"]["properties"]["source_scope"]["type"]["name"] == "String"
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
    input_properties = _form_properties(input_json)

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
def test_augment_operator_renders_flexible_stage_slots() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {
            "pipeline_step_count": 4,
            "transform": "HorizontalFlip",
            "step_2_transform": "RandomBrightnessContrast",
            "step_2_pipeline_stage_enabled": False,
            "step_3_transform": "VerticalFlip",
            "step_4_transform": "ToGray",
            "step_4_pipeline_stage_order": 1,
        }

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = _form_properties(input_json)

    assert input_properties["pipeline_step_count"]["default"] == 4
    assert input_properties["_pipeline_stage_4"]["view"]["label"] == "Stage 4"
    assert input_properties["step_2_pipeline_stage_enabled"]["default"] is False
    assert input_properties["step_4_pipeline_stage_order"]["default"] == 1
    assert input_properties["step_4_transform"]["default"] == "ToGray"
    assert input_properties["step_4_num_output_channels"]["default"] == 3
    assert "step_5_transform" not in input_properties


@pytest.mark.unit
def test_augment_operator_renders_annotation_field_toggles() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = _FieldSchemaDataset(
            {
                "ground_truth": _field(fo.Classification),
                "detections": _field(fo.Detections),
                "polylines": _field(fo.Polylines),
            }
        )
        params: dict[str, object] = {}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = _form_properties(input_json)
    ground_truth_param = annotation_field_param_name("ground_truth")
    detections_param = annotation_field_param_name("detections")

    assert input_properties["_annotation_settings"]["view"]["name"] == "Header"
    assert input_properties["_annotation_settings"]["view"]["label"] == "Annotations"
    assert input_properties[ANNOTATION_FIELD_GROUP_NAME]["view"]["name"] == "GridView"
    assert input_properties[ground_truth_param]["type"]["name"] == "Boolean"
    assert input_properties[ground_truth_param]["default"] is True
    assert input_properties[ground_truth_param]["view"]["name"] == "CheckboxView"
    assert input_properties[ground_truth_param]["view"]["caption"] == "Classification labels are copied."
    assert input_properties[detections_param]["type"]["name"] == "Boolean"
    assert input_properties[detections_param]["default"] is True
    assert "bboxes targets" in input_properties[detections_param]["view"]["caption"]
    assert annotation_field_param_name("polylines") not in input_properties


@pytest.mark.unit
def test_augment_operator_preserves_annotation_field_toggle_values() -> None:
    operator = AugmentWithAlbumentationsX()
    detections_param = annotation_field_param_name("detections")

    class Context:
        dataset = _FieldSchemaDataset({"detections": _field(fo.Detections)})
        params = {detections_param: False}

    input_properties = _form_properties(operator.resolve_input(Context()).to_json())

    assert input_properties[detections_param]["default"] is False


@pytest.mark.unit
def test_augment_operator_defaults_scope_to_selected_samples_when_selection_exists() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        selected = ("sample-1",)
        params: dict[str, object] = {}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = input_json["type"]["properties"]

    assert input_properties[EXECUTION_SCOPE_FIELD_NAME]["default"] == EXECUTION_SCOPE_SELECTED_SAMPLES


@pytest.mark.unit
def test_augment_operator_prefills_form_from_previous_run_manifest(tmp_path) -> None:
    operator = AugmentWithAlbumentationsX()
    dataset_name = "preset-dataset"
    manifest = _preset_manifest()
    FileRunStore(dataset_name, storage_root=tmp_path).save_manifest(manifest)

    context = SimpleNamespace(
        dataset=SimpleNamespace(name=dataset_name),
        params={
            PREVIOUS_RUN_KEY_FIELD_NAME: manifest.run_key,
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
        },
    )

    input_json = operator.resolve_input(context).to_json()
    input_properties = _form_properties(input_json)

    assert input_properties[PREVIOUS_RUN_KEY_FIELD_NAME]["type"]["name"] == "Enum"
    assert input_properties[PREVIOUS_RUN_KEY_FIELD_NAME]["default"] == manifest.run_key
    assert manifest.run_key in input_properties[PREVIOUS_RUN_KEY_FIELD_NAME]["type"]["values"]
    assert input_properties["pipeline_step_count"]["default"] == 2
    assert input_properties["outputs_per_sample"]["default"] == 2
    assert input_properties["transform"]["default"] == "RandomBrightnessContrast"
    assert input_properties["brightness_range"]["default"] == [0.1, 0.2]
    assert input_properties["contrast_range"]["default"] == [0.3, 0.4]
    assert input_properties["p"]["default"] == 0.8
    assert input_properties["step_2_transform"]["default"] == "RandomCrop"
    assert input_properties["step_2_height"]["default"] == 12
    assert input_properties["step_2_width"]["default"] == 10
    assert input_properties["step_2_p"]["default"] == 1.0


@pytest.mark.unit
def test_operator_params_from_pipeline_preserves_stages_up_to_editor_limit() -> None:
    pipeline = PipelineConfig(
        transforms=tuple(
            TransformConfig(name="HorizontalFlip", params={"p": 1.0}) for _step_number in range(MAX_PIPELINE_STEPS)
        ),
        outputs_per_sample=2,
    )

    params = operator_params_from_pipeline(pipeline)

    assert params["pipeline_step_count"] == MAX_PIPELINE_STEPS
    assert params["outputs_per_sample"] == 2
    for step_number in range(1, MAX_PIPELINE_STEPS + 1):
        assert params[pipeline_stage_enabled_field_name(step_number)] is True
        assert params[pipeline_stage_order_field_name(step_number)] == step_number
        assert params[pipeline_step_field_name(step_number, "transform")] == "HorizontalFlip"
        assert params[pipeline_step_field_name(step_number, "p")] == 1.0


@pytest.mark.unit
def test_augment_operator_prefill_overrides_stale_submitted_form_values(tmp_path) -> None:
    operator = AugmentWithAlbumentationsX()
    dataset_name = "preset-stale-form-dataset"
    manifest = _preset_manifest()
    FileRunStore(dataset_name, storage_root=tmp_path).save_manifest(manifest)

    context = SimpleNamespace(
        dataset=SimpleNamespace(name=dataset_name),
        params={
            PREVIOUS_RUN_KEY_FIELD_NAME: manifest.run_key,
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            "pipeline_step_count": 1,
            "outputs_per_sample": 1,
            "transform": "HorizontalFlip",
            "p": 1.0,
        },
    )

    input_json = operator.resolve_input(context).to_json()
    input_properties = _form_properties(input_json)

    assert input_properties["pipeline_step_count"]["default"] == 2
    assert input_properties["outputs_per_sample"]["default"] == 2
    assert input_properties["transform"]["default"] == "RandomBrightnessContrast"
    assert input_properties["brightness_range"]["default"] == [0.1, 0.2]
    assert input_properties["contrast_range"]["default"] == [0.3, 0.4]
    assert input_properties["p"]["default"] == 0.8
    assert input_properties["step_2_transform"]["default"] == "RandomCrop"
    assert input_properties["step_2_height"]["default"] == 12
    assert input_properties["step_2_width"]["default"] == 10


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
    input_properties = _form_properties(input_json)

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
    input_properties = _form_properties(input_json)

    assert input_properties["brightness_range"]["type"]["name"] == "Tuple"
    assert input_properties["brightness_range"]["default"] == [-0.2, 0.2]
    assert input_properties["contrast_range"]["type"]["name"] == "Tuple"
    assert input_properties["contrast_range"]["default"] == [-0.2, 0.2]
    assert input_properties["p"]["default"] == 1.0
    assert "brightness_by_max" not in input_properties
    assert "ensure_safe_output" not in input_properties
    assert input_properties[EXECUTION_SCOPE_FIELD_NAME]["default"] == EXECUTION_SCOPE_CURRENT_VIEW


@pytest.mark.unit
def test_augment_operator_resolves_random_crop_without_initial_required_errors() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = _form_properties(input_json)

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
    input_properties = _form_properties(input_json)

    assert input_properties["height"]["required"] is False
    assert input_properties["height"]["default"] == 18
    assert input_properties["width"]["required"] is False
    assert input_properties["width"]["default"] == 24
    assert "Default is limited by the selected image dimensions." in input_properties["height"]["view"]["caption"]
    assert "Default is limited by the selected image dimensions." in input_properties["width"]["view"]["caption"]


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
    input_properties = _form_properties(input_json)

    assert input_properties["height"]["default"] == 19
    assert input_properties["width"]["default"] == 21
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["height"]["view"]["caption"])
    )
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["width"]["view"]["caption"])
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
    input_properties = _form_properties(input_json)

    assert input_properties["height"]["default"] == 24
    assert input_properties["width"]["default"] == 22
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["height"]["view"]["caption"])
    )
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["width"]["view"]["caption"])
    )


@pytest.mark.unit
def test_augment_operator_uses_static_random_crop_defaults_when_selected_metadata_is_missing() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = _SampleCollection((_Sample("sample-1"),))
        selected = ("sample-1",)
        params = {"transform": "RandomCrop"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = _form_properties(input_json)

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
    input_properties = _form_properties(input_json)

    assert input_properties["height"]["default"] == 16
    assert input_properties["width"]["default"] == 20
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["height"]["view"]["caption"])
    )
    assert (
        "Selected images have mixed dimensions; default is limited by the smallest selected image."
        in (input_properties["width"]["view"]["caption"])
    )


@pytest.mark.unit
def test_augment_operator_resolves_catalog_transform_parameter_schema() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "ToGray"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = _form_properties(input_json)

    assert input_properties["transform"]["default"] == "ToGray"
    assert input_properties["num_output_channels"]["type"]["name"] == "Number"
    assert input_properties["num_output_channels"]["default"] == 3
    assert input_properties["method"]["type"]["name"] == "Enum"
    assert "weighted_average" in input_properties["method"]["type"]["values"]
    assert input_properties["p"]["default"] == 1.0


@pytest.mark.unit
def test_augment_operator_renders_compact_readable_transform_parameters() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "ElasticTransform"}

    input_properties = _form_properties(operator.resolve_input(Context()).to_json())

    assert input_properties["_pipeline_stage_1"]["view"]["description"] is None
    assert input_properties["alpha"]["view"]["label"] == "Alpha"
    assert input_properties["alpha"]["view"]["description"] is None
    assert input_properties["alpha"]["view"]["caption"] == "Scaling factor for the random displacement fields."
    assert input_properties["alpha"]["view"]["componentsProps"]["item"]["sx"]["width"] == {
        "xs": "100%",
        "md": "calc(50% - 8px)",
    }
    assert input_properties["approximate"]["view"]["name"] == "SwitchView"
    assert input_properties["approximate"]["view"]["caption"] == (
        "Use an approximate version of the elastic transform."
    )
    assert input_properties["interpolation"]["view"]["name"] == "DropdownView"
    assert [choice["label"] for choice in input_properties["interpolation"]["view"]["choices"]] == [
        "Nearest (0)",
        "Linear (1)",
        "Cubic (2)",
        "Area (3)",
        "Lanczos4 (4)",
    ]
    assert input_properties["noise_distribution"]["view"]["caption"] == (
        "Distribution used to generate the displacement fields."
    )
    assert input_properties["map_resolution_range"]["view"]["caption"] == (
        "Range for sampling the displacement map resolution relative to the target size."
    )
    assert input_properties["p"]["view"]["label"] == "Probability"


@pytest.mark.unit
def test_augment_operator_hides_supported_with_defaults_advanced_parameters() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        params = {"transform": "CoarseDropout"}

    input_json = operator.resolve_input(Context()).to_json()
    input_properties = _form_properties(input_json)

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
    input_properties = _form_properties(input_json)

    assert input_properties["transform"]["default"] == "HorizontalFlip"
    assert input_properties["p"]["type"]["name"] == "Number"
    assert "method" not in input_properties
    assert "mean" not in input_properties
    assert input_properties[EXECUTION_SCOPE_FIELD_NAME]["default"] == EXECUTION_SCOPE_CURRENT_VIEW


@pytest.mark.unit
def test_augment_operator_resolves_samples_grid_placement() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = SimpleNamespace(media_type="image")
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
def test_augment_operator_resolves_samples_grid_placement_without_selection_for_image_dataset() -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = SimpleNamespace(media_type="image")
        selected = ()

    placement_json = operator.resolve_placement(Context()).to_json()
    view_json = placement_json["view"]

    assert isinstance(view_json, dict)
    assert view_json["disabled"] is False
    assert view_json["prompt"] is True


@pytest.mark.unit
def test_augment_operator_disables_samples_grid_placement_without_dataset_context() -> None:
    operator = AugmentWithAlbumentationsX()

    placement_json = operator.resolve_placement(ctx=None).to_json()
    view_json = placement_json["view"]

    assert isinstance(view_json, dict)
    assert view_json["disabled"] is True
    assert view_json["title"] == "Open an image dataset before running augmentation."


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
        assert kwargs["params"] == {
            "transform": "HorizontalFlip",
            EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES,
        }
        assert kwargs["storage_root"] is None
        assert isinstance(kwargs["progress_reporter"], FiftyOneProgressReporter)
        return FixedAugmentationExecutionResult(
            run_key="albumentationsx-20260731T120000Z-test",
            source_scope=EXECUTION_SCOPE_SELECTED_SAMPLES,
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
        "source_scope": EXECUTION_SCOPE_SELECTED_SAMPLES,
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
def test_augment_operator_execute_delegates_current_view_scope_without_selection(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        view = object()
        selected = ()
        params = {
            "transform": "HorizontalFlip",
            EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_CURRENT_VIEW,
        }

    def fake_execute_fixed_augmentation(**kwargs):
        assert kwargs["dataset"] is Context.dataset
        assert kwargs["view"] is Context.view
        assert kwargs["selected_sample_ids"] == ()
        assert kwargs["params"][EXECUTION_SCOPE_FIELD_NAME] == EXECUTION_SCOPE_CURRENT_VIEW
        return FixedAugmentationExecutionResult(
            run_key="albumentationsx-20260731T120000Z-current-view",
            source_scope=EXECUTION_SCOPE_CURRENT_VIEW,
            processed_count=2,
            created_count=0,
            skipped_count=0,
            error_count=0,
            dry_run=True,
            output_tag="albumentationsx-output",
            output_dir="/tmp/outputs",
        )

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    result = operator.execute(Context())

    assert result["source_scope"] == EXECUTION_SCOPE_CURRENT_VIEW
    assert result["processed_count"] == 2
    assert result["error_count"] == 0


@pytest.mark.unit
def test_augment_operator_execute_delegates_entire_dataset_scope_without_view(monkeypatch) -> None:
    operator = AugmentWithAlbumentationsX()

    class Context:
        dataset = object()
        view = object()
        selected = ()
        params = {
            "transform": "HorizontalFlip",
            EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_ENTIRE_DATASET,
        }

    def fake_execute_fixed_augmentation(**kwargs):
        assert kwargs["dataset"] is Context.dataset
        assert kwargs["view"] is None
        assert kwargs["selected_sample_ids"] == ()
        assert kwargs["params"][EXECUTION_SCOPE_FIELD_NAME] == EXECUTION_SCOPE_ENTIRE_DATASET
        return FixedAugmentationExecutionResult(
            run_key="albumentationsx-20260731T120000Z-entire-dataset",
            source_scope=EXECUTION_SCOPE_ENTIRE_DATASET,
            processed_count=3,
            created_count=0,
            skipped_count=0,
            error_count=0,
            dry_run=True,
            output_tag="albumentationsx-output",
            output_dir="/tmp/outputs",
        )

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    result = operator.execute(Context())

    assert result["source_scope"] == EXECUTION_SCOPE_ENTIRE_DATASET
    assert result["processed_count"] == 3
    assert result["error_count"] == 0


@pytest.mark.unit
def test_augment_operator_execute_applies_previous_run_preset_without_submitted_defaults(
    monkeypatch,
    tmp_path,
) -> None:
    operator = AugmentWithAlbumentationsX()
    dataset_name = "preset-execute-dataset"
    manifest = _preset_manifest()
    FileRunStore(dataset_name, storage_root=tmp_path).save_manifest(manifest)

    class Context:
        dataset = SimpleNamespace(name=dataset_name)
        view = object()
        selected = ("sample-1",)
        params = {
            PREVIOUS_RUN_KEY_FIELD_NAME: manifest.run_key,
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
        }

    def fake_execute_fixed_augmentation(**kwargs):
        params = kwargs["params"]
        assert kwargs["dataset"] is Context.dataset
        assert kwargs["view"] is Context.view
        assert kwargs["selected_sample_ids"] == ("sample-1",)
        assert kwargs["storage_root"] == str(tmp_path)
        assert params[PREVIOUS_RUN_KEY_FIELD_NAME] == manifest.run_key
        assert params["pipeline_step_count"] == 2
        assert params["outputs_per_sample"] == 2
        assert params["transform"] == "RandomBrightnessContrast"
        assert params["brightness_range"] == [0.1, 0.2]
        assert params["contrast_range"] == [0.3, 0.4]
        assert params["p"] == 0.8
        assert params["step_2_transform"] == "RandomCrop"
        assert params["step_2_height"] == 12
        assert params["step_2_width"] == 10
        return FixedAugmentationExecutionResult(
            run_key="albumentationsx-20260731T120000Z-preset-copy",
            processed_count=1,
            created_count=0,
            skipped_count=0,
            error_count=0,
            dry_run=True,
            output_tag="albumentationsx-output",
            output_dir="/tmp/outputs",
        )

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    result = operator.execute(Context())

    assert result["run_key"] == "albumentationsx-20260731T120000Z-preset-copy"
    assert result["error_count"] == 0


@pytest.mark.unit
def test_augment_operator_execute_previous_run_preset_overrides_submitted_defaults(
    monkeypatch,
    tmp_path,
) -> None:
    operator = AugmentWithAlbumentationsX()
    dataset_name = "preset-execute-stale-dataset"
    manifest = _preset_manifest()
    FileRunStore(dataset_name, storage_root=tmp_path).save_manifest(manifest)

    class Context:
        dataset = SimpleNamespace(name=dataset_name)
        view = object()
        selected = ("sample-1",)
        params = {
            PREVIOUS_RUN_KEY_FIELD_NAME: manifest.run_key,
            STORAGE_ROOT_PARAM_NAME: str(tmp_path),
            "pipeline_step_count": 1,
            "outputs_per_sample": 1,
            "transform": "HorizontalFlip",
            "p": 1.0,
        }

    def fake_execute_fixed_augmentation(**kwargs):
        params = kwargs["params"]
        assert params[PREVIOUS_RUN_KEY_FIELD_NAME] == manifest.run_key
        assert params["pipeline_step_count"] == 2
        assert params["outputs_per_sample"] == 2
        assert params["transform"] == "RandomBrightnessContrast"
        assert params["brightness_range"] == [0.1, 0.2]
        assert params["contrast_range"] == [0.3, 0.4]
        assert params["p"] == 0.8
        assert params["step_2_transform"] == "RandomCrop"
        assert params["step_2_height"] == 12
        assert params["step_2_width"] == 10
        return FixedAugmentationExecutionResult(
            run_key="albumentationsx-20260731T120000Z-preset-copy",
            processed_count=1,
            created_count=0,
            skipped_count=0,
            error_count=0,
            dry_run=True,
            output_tag="albumentationsx-output",
            output_dir="/tmp/outputs",
        )

    monkeypatch.setattr(augment_operator_module, "_execute_fixed_augmentation", fake_execute_fixed_augmentation)

    result = operator.execute(Context())

    assert result["run_key"] == "albumentationsx-20260731T120000Z-preset-copy"
    assert result["error_count"] == 0


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
        params = {"dry_run": True, EXECUTION_SCOPE_FIELD_NAME: EXECUTION_SCOPE_SELECTED_SAMPLES}

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
    error_context = first_error["context"]
    assert isinstance(error_context, dict)
    assert error_context["source_scope"] == EXECUTION_SCOPE_SELECTED_SAMPLES


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
