from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Mapping

import pytest

from albumentationsx_plugin.core import (
    AugmentationInput,
    AugmentationResult,
    CapabilityStatus,
    FieldKind,
    FormFieldSchema,
    InvalidParameterError,
    MediaIOError,
    PipelineConfig,
    PluginError,
    RunManifest,
    TransformCapability,
    TransformConfig,
    UnsupportedTransformError,
)


def _json_round_trip(value: Mapping[str, object]) -> dict[str, object]:
    decoded = json.loads(json.dumps(value))
    assert isinstance(decoded, dict)
    return decoded


@pytest.mark.unit
def test_core_import_does_not_import_runtime_integrations() -> None:
    for module_name in ("fiftyone", "albumentations", "albu_spec"):
        sys.modules.pop(module_name, None)

    importlib.import_module("albumentationsx_plugin.core")

    assert "fiftyone" not in sys.modules
    assert "albumentations" not in sys.modules
    assert "albu_spec" not in sys.modules


@pytest.mark.unit
def test_pipeline_config_round_trips_through_json() -> None:
    config = PipelineConfig(
        transforms=(
            TransformConfig(name="HorizontalFlip", params={"p": 0.5}),
            TransformConfig(name="RandomBrightnessContrast", params={"brightness_limit": (-0.2, 0.2)}),
        ),
        outputs_per_sample=2,
        target_fields=("ground_truth",),
        copy_fields=("weather",),
        seed=42,
        options={"execution": "immediate"},
    )

    decoded = _json_round_trip(config.to_dict())

    assert PipelineConfig.from_dict(decoded) == PipelineConfig(
        transforms=(
            TransformConfig(name="HorizontalFlip", params={"p": 0.5}),
            TransformConfig(name="RandomBrightnessContrast", params={"brightness_limit": [-0.2, 0.2]}),
        ),
        outputs_per_sample=2,
        target_fields=("ground_truth",),
        copy_fields=("weather",),
        seed=42,
        options={"execution": "immediate"},
    )


@pytest.mark.unit
def test_capability_and_form_schema_round_trip_through_json() -> None:
    capability = TransformCapability(
        name="RandomCrop",
        status=CapabilityStatus.SUPPORTED_WITH_DEFAULTS,
        targets=("image", "bboxes"),
        reason_code="advanced_defaults",
        message="Some optional parameters use defaults.",
        advanced_parameters=("pad_if_needed",),
        metadata={"source": "albu-spec"},
    )
    field = FormFieldSchema(
        name="border_mode",
        kind=FieldKind.ENUM,
        label="Border mode",
        required=True,
        default="constant",
        choices=("constant", "reflect"),
        help_text="How to fill pixels outside the source image.",
    )

    assert TransformCapability.from_dict(_json_round_trip(capability.to_dict())) == capability
    assert FormFieldSchema.from_dict(_json_round_trip(field.to_dict())) == field


@pytest.mark.unit
def test_augmentation_input_result_and_manifest_round_trip_through_json() -> None:
    error = MediaIOError(
        filepath="/tmp/missing.jpg",
        message="Image file does not exist.",
        context={"sample_id": "source-2"},
    )
    pipeline = PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),))
    source = AugmentationInput(
        sample_id="source-1",
        filepath="/tmp/source.jpg",
        width=640,
        height=480,
        selected_label_fields=("ground_truth",),
        metadata={"split": "train"},
    )
    result = AugmentationResult(
        source_sample_id=source.sample_id,
        output_filepath="/tmp/output.jpg",
        labels={"classification": {"label": "cat"}},
        replay={"applied": True},
        errors=(error.to_dict(),),
    )
    manifest = RunManifest(
        run_key="albumentationsx-20260731T120102Z-a1b2c3d4",
        plugin_version="0.0.0",
        dependency_versions={"fiftyone": "1.19.0", "albumentationsx": "2.3.7", "albu-spec": "0.0.6"},
        pipeline=pipeline,
        source_sample_ids=(source.sample_id,),
        created_sample_ids=("created-1",),
        output_paths=("images/created-1.jpg",),
        replay_records=(result.replay,),
        counters={"processed": 1, "created": 1, "errors": 1},
        errors=(error.to_dict(),),
    )

    assert AugmentationInput.from_dict(_json_round_trip(source.to_dict())) == source
    assert AugmentationResult.from_dict(_json_round_trip(result.to_dict())) == result
    assert RunManifest.from_dict(_json_round_trip(manifest.to_dict())) == manifest


@pytest.mark.unit
def test_model_validation_rejects_invalid_defaults() -> None:
    with pytest.raises(ValueError, match="name"):
        TransformConfig(name="")

    with pytest.raises(ValueError, match="outputs_per_sample"):
        PipelineConfig(transforms=(), outputs_per_sample=0)

    with pytest.raises(ValueError, match="enum"):
        FormFieldSchema(name="mode", kind=FieldKind.ENUM)

    with pytest.raises(TypeError, match="JSON"):
        TransformConfig(name="Bad", params={"callable": object()})


@pytest.mark.unit
def test_errors_expose_reason_codes_messages_and_context() -> None:
    error = InvalidParameterError(
        transform_name="RandomCrop",
        parameter_name="height",
        message="height must be less than or equal to image height.",
        context={"sample_id": "source-1"},
    )

    payload = error.to_dict()

    assert error.reason_code == "invalid_parameter"
    assert str(error) == "height must be less than or equal to image height."
    assert payload == {
        "code": "invalid_parameter",
        "message": "height must be less than or equal to image height.",
        "context": {
            "transform_name": "RandomCrop",
            "parameter_name": "height",
            "sample_id": "source-1",
        },
    }
    assert PluginError.from_dict(_json_round_trip(payload)).to_dict() == payload


@pytest.mark.unit
def test_specific_errors_include_default_context() -> None:
    unsupported = UnsupportedTransformError("Normalize")
    io_error = MediaIOError("/tmp/source.jpg", "Image could not be read.")

    assert unsupported.to_dict()["context"] == {"transform_name": "Normalize"}
    assert io_error.to_dict()["context"] == {"filepath": "/tmp/source.jpg"}
