"""Shared runtime setup for FiftyOne augmentation execution modes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import fiftyone as fo

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.image_pipeline import (
    FixedImagePipeline,
    create_fixed_image_pipeline,
    validate_pipeline_image_shape,
)
from albumentationsx_plugin.core import AugmentationInput, HostAdapterError, JSONDict, PipelineConfig, PluginError
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    annotation_run_metadata,
    annotation_target_requirements_from_inputs,
    selected_annotation_fields_from_params,
    target_and_copy_fields,
    target_data_from_annotation_payload,
    validate_annotation_pipeline_compatibility,
    validate_selected_annotation_fields,
)
from albumentationsx_plugin.hosts.fiftyone.augmentation.external_data import (
    ExternalInputBundle,
    build_external_input_bundle,
)
from albumentationsx_plugin.hosts.fiftyone.augmentation.outputs import annotation_payload_for_source
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_ENTIRE_DATASET,
    EXECUTION_SCOPE_SELECTED_SAMPLES,
    selected_execution_scope,
)
from albumentationsx_plugin.hosts.fiftyone.output_metadata import OUTPUT_METADATA_POLICY, build_output_metadata_policy
from albumentationsx_plugin.hosts.fiftyone.pipeline_compiler import build_fixed_pipeline_config
from albumentationsx_plugin.hosts.fiftyone.samples import DEFAULT_OUTPUT_TAG, FiftyOneSampleAdapter
from albumentationsx_plugin.storage.images import load_rgb_image


@dataclass(frozen=True, slots=True)
class FixedAugmentationRuntime:
    """Prepared catalog-backed runtime shared by materialized and preview runs."""

    config: PipelineConfig
    pipeline: FixedImagePipeline
    source_scope: str
    adapter: FiftyOneSampleAdapter
    source_inputs: tuple[AugmentationInput, ...]
    annotation_metadata: JSONDict
    external_inputs: ExternalInputBundle


def build_fixed_augmentation_runtime(
    *,
    dataset: fo.Dataset,
    params: Mapping[str, object],
    view: Any | None = None,
    selected_sample_ids: Sequence[str] = (),
    output_tag: str = DEFAULT_OUTPUT_TAG,
) -> FixedAugmentationRuntime:
    """Validate params and collect source inputs without writing outputs."""

    config = build_fixed_pipeline_config(params)
    catalog_provider = AlbuSpecCatalogProvider()
    annotation_selection = selected_annotation_fields_from_params(params, dataset)
    validate_selected_annotation_fields(annotation_selection)
    validate_annotation_pipeline_compatibility(
        selection=annotation_selection,
        pipeline=config,
        catalog_provider=catalog_provider,
    )
    target_fields, copy_fields = target_and_copy_fields(
        selection=annotation_selection,
        pipeline=config,
        catalog_provider=catalog_provider,
    )
    config = replace(config, target_fields=target_fields, copy_fields=copy_fields)
    source_scope = selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
    if source_scope == EXECUTION_SCOPE_SELECTED_SAMPLES and not selected_sample_ids:
        raise HostAdapterError("fiftyone", "Select at least one image before using Selected samples.")
    adapter = FiftyOneSampleAdapter(
        dataset=dataset,
        view=None if source_scope == EXECUTION_SCOPE_ENTIRE_DATASET else view,
        selected_sample_ids=selected_sample_ids,
        selected_label_fields=annotation_selection.selected_field_names,
        include_all_label_fields=False,
        output_tag=output_tag,
    )
    source_inputs = tuple(adapter.iter_inputs())
    if not source_inputs:
        raise HostAdapterError("fiftyone", "This scope contains no images. Select images or choose a non-empty scope.")
    # Validate every source before the executor can create a manifest or output.
    for source in source_inputs:
        try:
            image = load_rgb_image(source.filepath)
            validate_pipeline_image_shape(config, image_shape=image.data.shape)
            target_data_from_annotation_payload(
                annotation_payload_for_source(source), image.data.shape, label_fields=config.target_fields
            )
        except PluginError as error:
            raise PluginError(
                error.code,
                f"Sample {source.sample_id}: {error.message}",
                {**error.context, "sample_id": source.sample_id, "filepath": source.filepath},
            ) from error
    external_inputs = build_external_input_bundle(
        config=config,
        catalog_provider=catalog_provider,
        source_inputs=source_inputs,
    )
    runtime_target_requirements = annotation_target_requirements_from_inputs(source_inputs)
    validate_annotation_pipeline_compatibility(
        selection=annotation_selection,
        pipeline=config,
        catalog_provider=catalog_provider,
        runtime_target_requirements=runtime_target_requirements,
    )
    if external_inputs.has_inputs:
        config = replace(
            config,
            options={
                **config.options,
                "external_inputs": external_inputs.summary,
            },
        )
    pipeline = create_fixed_image_pipeline(config)
    annotation_metadata = normalize_json_mapping(
        annotation_run_metadata(
            selection=annotation_selection,
            pipeline=config,
            catalog_provider=catalog_provider,
            runtime_target_requirements=runtime_target_requirements,
        )
    )
    annotation_metadata[OUTPUT_METADATA_POLICY] = build_output_metadata_policy(
        dataset, annotation_selection, sources=source_inputs, transformed_fields=target_fields
    )
    return FixedAugmentationRuntime(
        config=config,
        pipeline=pipeline,
        source_scope=source_scope,
        adapter=adapter,
        source_inputs=source_inputs,
        annotation_metadata=annotation_metadata,
        external_inputs=external_inputs,
    )
