"""Shared runtime setup for FiftyOne augmentation execution modes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import fiftyone as fo

from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
from albumentationsx_plugin.albumentations_backend.fixed import (
    FixedImagePipeline,
    build_fixed_pipeline_config,
    create_fixed_image_pipeline,
)
from albumentationsx_plugin.core import AugmentationInput, JSONDict, PipelineConfig
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations import (
    annotation_run_metadata,
    selected_annotation_fields_from_params,
    target_and_copy_fields,
    validate_annotation_pipeline_compatibility,
    validate_selected_annotation_fields,
)
from albumentationsx_plugin.hosts.fiftyone.execution_scope import (
    EXECUTION_SCOPE_ENTIRE_DATASET,
    selected_execution_scope,
)
from albumentationsx_plugin.hosts.fiftyone.samples import DEFAULT_OUTPUT_TAG, FiftyOneSampleAdapter


@dataclass(frozen=True, slots=True)
class FixedAugmentationRuntime:
    """Prepared fixed-pipeline runtime shared by materialized and preview runs."""

    config: PipelineConfig
    pipeline: FixedImagePipeline
    source_scope: str
    adapter: FiftyOneSampleAdapter
    source_inputs: tuple[AugmentationInput, ...]
    annotation_metadata: JSONDict


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
    pipeline = create_fixed_image_pipeline(config)
    source_scope = selected_execution_scope(params, selected_sample_ids=selected_sample_ids)
    adapter = FiftyOneSampleAdapter(
        dataset=dataset,
        view=None if source_scope == EXECUTION_SCOPE_ENTIRE_DATASET else view,
        selected_sample_ids=selected_sample_ids,
        selected_label_fields=annotation_selection.selected_field_names,
        include_all_label_fields=False,
        output_tag=output_tag,
    )
    source_inputs = tuple(adapter.iter_inputs())
    annotation_metadata = normalize_json_mapping(
        annotation_run_metadata(
            selection=annotation_selection,
            pipeline=config,
            catalog_provider=catalog_provider,
        )
    )
    return FixedAugmentationRuntime(
        config=config,
        pipeline=pipeline,
        source_scope=source_scope,
        adapter=adapter,
        source_inputs=source_inputs,
        annotation_metadata=annotation_metadata,
    )
