"""Resolve FiftyOne-scoped external data for AlbumentationsX transforms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from albumentationsx_plugin.core import (
    AugmentationInput,
    ExternalInputKind,
    ExternalInputRequirement,
    InvalidParameterError,
    JSONDict,
    PipelineConfig,
    TransformCatalogProvider,
)
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.storage.images import RGBArray, load_rgb_image

REFERENCE_IMAGE_POOL_RESOLVER: Final[str] = "reference_image_pool"
REFERENCE_IMAGE_POOL_POLICY: Final[str] = "all_other_sources_in_execution_scope"


@dataclass(frozen=True, slots=True)
class ExternalInputSourceData:
    """External targets and JSON-safe provenance for one source sample."""

    source_sample_id: str
    targets: Mapping[str, object]
    metadata: JSONDict


@dataclass(frozen=True, slots=True)
class ExternalInputBundle:
    """Resolved external data for a prepared augmentation runtime."""

    source_data: tuple[ExternalInputSourceData, ...] = ()
    summary: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", normalize_json_mapping(self.summary))

    @property
    def has_inputs(self) -> bool:
        """Return whether the pipeline needs external input targets."""

        return bool(self.source_data)

    def targets_for_source(self, source_sample_id: str) -> Mapping[str, object]:
        """Return in-memory Albumentations targets for one source sample."""

        for source in self.source_data:
            if source.source_sample_id == source_sample_id:
                return dict(source.targets)
        return {}

    def metadata_for_source(self, source_sample_id: str) -> JSONDict:
        """Return JSON-safe external input provenance for one source sample."""

        for source in self.source_data:
            if source.source_sample_id == source_sample_id:
                return normalize_json_mapping(source.metadata)
        return {}


@dataclass(frozen=True, slots=True)
class _PipelineExternalInput:
    transform_name: str
    requirement: ExternalInputRequirement


def build_external_input_bundle(
    *,
    config: PipelineConfig,
    catalog_provider: TransformCatalogProvider,
    source_inputs: Sequence[AugmentationInput],
) -> ExternalInputBundle:
    """Resolve external inputs needed by a pipeline from the prepared source scope."""

    requirements = _pipeline_external_inputs(config, catalog_provider=catalog_provider)
    if not requirements:
        return ExternalInputBundle()

    _validate_supported_requirements(requirements)
    reference_requirements = tuple(
        requirement for requirement in requirements if requirement.requirement.resolver == REFERENCE_IMAGE_POOL_RESOLVER
    )
    if not reference_requirements:
        return ExternalInputBundle(summary=_summary(requirements, source_count=len(source_inputs)))

    if len(source_inputs) < 2:
        raise InvalidParameterError(
            transform_name="<pipeline>",
            parameter_name="external_inputs",
            message="Reference-image transforms require at least two source samples in the execution scope.",
            context={
                "reason_code": "insufficient_reference_image_pool",
                "source_count": len(source_inputs),
                "required_min_source_count": 2,
                "transform_names": sorted({requirement.transform_name for requirement in reference_requirements}),
                "resolver": REFERENCE_IMAGE_POOL_RESOLVER,
            },
        )

    reference_images_by_sample_id = _load_reference_images(source_inputs)
    source_data = tuple(
        _source_external_data(
            source,
            source_inputs=source_inputs,
            reference_requirements=reference_requirements,
            reference_images_by_sample_id=reference_images_by_sample_id,
        )
        for source in source_inputs
    )
    return ExternalInputBundle(
        source_data=source_data,
        summary=_summary(requirements, source_count=len(source_inputs)),
    )


def _pipeline_external_inputs(
    config: PipelineConfig,
    *,
    catalog_provider: TransformCatalogProvider,
) -> tuple[_PipelineExternalInput, ...]:
    requirements: list[_PipelineExternalInput] = []
    for transform in config.transforms:
        capability = catalog_provider.get_transform_capability(transform.name)
        if capability is None:
            continue
        requirements.extend(
            _PipelineExternalInput(transform_name=transform.name, requirement=requirement)
            for requirement in capability.external_inputs
        )
    return tuple(requirements)


def _validate_supported_requirements(requirements: tuple[_PipelineExternalInput, ...]) -> None:
    unsupported = tuple(
        requirement
        for requirement in requirements
        if requirement.requirement.resolver != REFERENCE_IMAGE_POOL_RESOLVER
        or requirement.requirement.kind is not ExternalInputKind.METADATA_SEQUENCE
        or not requirement.requirement.metadata_key
    )
    if not unsupported:
        return

    raise InvalidParameterError(
        transform_name="<pipeline>",
        parameter_name="external_inputs",
        message="Pipeline includes external inputs that the FiftyOne adapter cannot resolve yet.",
        context={
            "reason_code": "unsupported_external_input_resolver",
            "requirements": [_requirement_metadata(requirement) for requirement in unsupported],
        },
    )


def _load_reference_images(source_inputs: Sequence[AugmentationInput]) -> dict[str, RGBArray]:
    return {source.sample_id: load_rgb_image(source.filepath).data for source in source_inputs}


def _source_external_data(
    source: AugmentationInput,
    *,
    source_inputs: Sequence[AugmentationInput],
    reference_requirements: tuple[_PipelineExternalInput, ...],
    reference_images_by_sample_id: Mapping[str, RGBArray],
) -> ExternalInputSourceData:
    reference_sources = tuple(candidate for candidate in source_inputs if candidate.sample_id != source.sample_id)
    reference_source_ids = tuple(candidate.sample_id for candidate in reference_sources)
    targets: dict[str, object] = {}
    for metadata_key in _metadata_keys(reference_requirements):
        targets[metadata_key] = [reference_images_by_sample_id[sample_id] for sample_id in reference_source_ids]

    return ExternalInputSourceData(
        source_sample_id=source.sample_id,
        targets=targets,
        metadata=_source_metadata(
            reference_requirements,
            reference_source_ids=reference_source_ids,
        ),
    )


def _metadata_keys(requirements: tuple[_PipelineExternalInput, ...]) -> tuple[str, ...]:
    metadata_keys: list[str] = []
    for pipeline_requirement in requirements:
        metadata_key = pipeline_requirement.requirement.metadata_key
        if metadata_key and metadata_key not in metadata_keys:
            metadata_keys.append(metadata_key)
    return tuple(metadata_keys)


def _source_metadata(
    requirements: tuple[_PipelineExternalInput, ...],
    *,
    reference_source_ids: tuple[str, ...],
) -> JSONDict:
    return normalize_json_mapping(
        {
            "policy": REFERENCE_IMAGE_POOL_POLICY,
            "requirements": [
                {
                    **_requirement_metadata(requirement),
                    "reference_source_sample_ids": list(reference_source_ids),
                    "reference_source_count": len(reference_source_ids),
                }
                for requirement in requirements
            ],
        }
    )


def _summary(requirements: tuple[_PipelineExternalInput, ...], *, source_count: int) -> JSONDict:
    return normalize_json_mapping(
        {
            "resolvers": sorted({str(requirement.requirement.resolver) for requirement in requirements}),
            "requirements": [_requirement_metadata(requirement) for requirement in requirements],
            "reference_image_pool": {
                "policy": REFERENCE_IMAGE_POOL_POLICY,
                "source_count": source_count,
            },
        }
    )


def _requirement_metadata(requirement: _PipelineExternalInput) -> JSONDict:
    return normalize_json_mapping(
        {
            "transform_name": requirement.transform_name,
            "name": requirement.requirement.name,
            "kind": requirement.requirement.kind.value,
            "parameter_name": requirement.requirement.parameter_name,
            "metadata_key": requirement.requirement.metadata_key,
            "resolver": requirement.requirement.resolver,
            "required": requirement.requirement.required,
        }
    )
