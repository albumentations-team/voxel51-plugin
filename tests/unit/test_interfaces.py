from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable
from typing import cast

import pytest

from albumentationsx_plugin.albumentations_backend import interfaces as backend_interfaces
from albumentationsx_plugin.core import (
    AugmentationInput,
    AugmentationResult,
    CapabilityStatus,
    FieldKind,
    FormFieldSchema,
    JSONDict,
    PipelineConfig,
    RunManifest,
    TransformCapability,
    TransformConfig,
)
from albumentationsx_plugin.core.interfaces import (
    HostSampleAdapter,
    OutputStorageBackend,
    ParameterSchemaProvider,
    PipelineFactory,
    PipelineRunner,
    RunStore,
    TransformCatalogProvider,
)
from albumentationsx_plugin.hosts import interfaces as host_interfaces


class FakeCatalog:
    def __init__(self) -> None:
        self._capabilities = (
            TransformCapability(name="HorizontalFlip", status=CapabilityStatus.SUPPORTED),
            TransformCapability(
                name="Normalize",
                status=CapabilityStatus.UNSUPPORTED_OUTPUT,
                reason_code="preview_output_not_image",
            ),
        )

    def list_transform_capabilities(self) -> tuple[TransformCapability, ...]:
        return self._capabilities

    def get_transform_capability(self, name: str) -> TransformCapability | None:
        for capability in self._capabilities:
            if capability.name == name:
                return capability
        return None


class FakeSchemaProvider:
    def get_parameter_schema(self, transform_name: str) -> tuple[FormFieldSchema, ...]:
        assert transform_name == "HorizontalFlip"
        return (
            FormFieldSchema(
                name="p",
                kind=FieldKind.FLOAT,
                default=0.5,
                min_value=0,
                max_value=1,
            ),
        )


class FakeRunner:
    def run(self, source: AugmentationInput) -> AugmentationResult:
        return AugmentationResult(
            source_sample_id=source.sample_id,
            output_filepath=f"outputs/{source.sample_id}.jpg",
            replay={"applied": True},
        )


class FakeFactory:
    def validate(self, config: PipelineConfig) -> None:
        assert config.transforms

    def create_runner(self, config: PipelineConfig) -> PipelineRunner:
        self.validate(config)
        return FakeRunner()


class FakeHostAdapter:
    @property
    def host_name(self) -> str:
        return "fake-host"

    def iter_inputs(self) -> Iterable[AugmentationInput]:
        yield AugmentationInput(sample_id="source-1", filepath="/tmp/source-1.jpg")

    def create_output_sample(self, result: AugmentationResult, manifest: RunManifest) -> str:
        assert manifest.run_key
        return f"{result.source_sample_id}-created"


class FakeRunStore:
    def __init__(self) -> None:
        self._manifests: dict[str, RunManifest] = {}

    def save_manifest(self, manifest: RunManifest) -> None:
        self._manifests[manifest.run_key] = manifest

    def load_manifest(self, run_key: str) -> RunManifest:
        return self._manifests[run_key]

    def list_run_keys(self) -> tuple[str, ...]:
        return tuple(self._manifests)

    def delete_manifest(self, run_key: str) -> None:
        self._manifests.pop(run_key, None)


class FakeOutputStorage:
    def __init__(self) -> None:
        self._outputs: dict[tuple[str, str], bytes] = {}

    def prepare_run(self, run_key: str) -> None:
        assert run_key

    def write_output(self, run_key: str, relative_path: str, data: bytes) -> str:
        self._outputs[(run_key, relative_path)] = data
        return relative_path

    def delete_outputs(self, manifest: RunManifest) -> JSONDict:
        deleted = 0
        for relative_path in manifest.output_paths:
            if self._outputs.pop((manifest.run_key, relative_path), None) is not None:
                deleted += 1
        return cast(JSONDict, {"deleted": deleted, "run_key": manifest.run_key})


def _sample_pipeline() -> PipelineConfig:
    return PipelineConfig(transforms=(TransformConfig(name="HorizontalFlip", params={"p": 1.0}),))


def _sample_manifest(pipeline: PipelineConfig) -> RunManifest:
    return RunManifest(
        run_key="albumentationsx-20260731T120102Z-a1b2c3d4",
        plugin_version="0.0.0",
        dependency_versions={"backend": "fake"},
        pipeline=pipeline,
        source_sample_ids=("source-1",),
        created_sample_ids=("source-1-created",),
        output_paths=("outputs/source-1.jpg",),
    )


@pytest.mark.unit
def test_backend_and_host_interface_modules_are_stable_facades() -> None:
    assert backend_interfaces.TransformCatalogProvider is TransformCatalogProvider
    assert backend_interfaces.ParameterSchemaProvider is ParameterSchemaProvider
    assert backend_interfaces.PipelineFactory is PipelineFactory
    assert backend_interfaces.PipelineRunner is PipelineRunner
    assert host_interfaces.HostSampleAdapter is HostSampleAdapter


@pytest.mark.unit
@pytest.mark.parametrize(
    "module_name",
    (
        "albumentationsx_plugin.core.interfaces",
        "albumentationsx_plugin.albumentations_backend.interfaces",
        "albumentationsx_plugin.hosts.interfaces",
    ),
)
def test_interface_modules_do_not_import_runtime_integrations(module_name: str) -> None:
    for runtime_module in ("fiftyone", "albumentations", "albu_spec"):
        sys.modules.pop(runtime_module, None)

    importlib.import_module(module_name)

    assert "fiftyone" not in sys.modules
    assert "albumentations" not in sys.modules
    assert "albu_spec" not in sys.modules


@pytest.mark.unit
def test_catalog_and_schema_provider_protocols_are_easy_to_mock() -> None:
    catalog: TransformCatalogProvider = FakeCatalog()
    schema_provider: ParameterSchemaProvider = FakeSchemaProvider()

    assert isinstance(catalog, TransformCatalogProvider)
    assert isinstance(schema_provider, ParameterSchemaProvider)
    assert catalog.get_transform_capability("HorizontalFlip") == TransformCapability(
        name="HorizontalFlip",
        status=CapabilityStatus.SUPPORTED,
    )
    assert catalog.get_transform_capability("Normalize") is not None
    assert schema_provider.get_parameter_schema("HorizontalFlip") == (
        FormFieldSchema(
            name="p",
            kind=FieldKind.FLOAT,
            default=0.5,
            min_value=0,
            max_value=1,
        ),
    )


@pytest.mark.unit
def test_pipeline_and_host_protocols_connect_through_core_dtos() -> None:
    pipeline = _sample_pipeline()
    factory: PipelineFactory = FakeFactory()
    host: HostSampleAdapter = FakeHostAdapter()
    manifest = _sample_manifest(pipeline)

    runner = factory.create_runner(pipeline)
    result = runner.run(next(iter(host.iter_inputs())))
    created_sample_id = host.create_output_sample(result, manifest)

    assert isinstance(factory, PipelineFactory)
    assert isinstance(runner, PipelineRunner)
    assert isinstance(host, HostSampleAdapter)
    assert created_sample_id == "source-1-created"
    assert result.output_filepath == "outputs/source-1.jpg"


@pytest.mark.unit
def test_storage_protocols_are_manifest_based_and_mockable() -> None:
    pipeline = _sample_pipeline()
    manifest = _sample_manifest(pipeline)
    run_store: RunStore = FakeRunStore()
    output_storage: OutputStorageBackend = FakeOutputStorage()

    output_storage.prepare_run(manifest.run_key)
    stored_path = output_storage.write_output(manifest.run_key, manifest.output_paths[0], b"image-bytes")
    run_store.save_manifest(manifest)

    assert isinstance(run_store, RunStore)
    assert isinstance(output_storage, OutputStorageBackend)
    assert stored_path == "outputs/source-1.jpg"
    assert run_store.list_run_keys() == (manifest.run_key,)
    assert run_store.load_manifest(manifest.run_key) == manifest
    assert output_storage.delete_outputs(manifest) == {"deleted": 1, "run_key": manifest.run_key}

    run_store.delete_manifest(manifest.run_key)
    assert run_store.list_run_keys() == ()
