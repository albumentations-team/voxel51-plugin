"""Exercise every currently selectable AlbumentationsX transform once."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class TransformSmokeResult:
    """One transform smoke execution result."""

    transform_name: str
    status: str
    reason_code: str = ""
    message: str = ""
    external_inputs: tuple[str, ...] = ()


SMOKE_PARAMETER_OVERRIDES: dict[str, dict[str, object]] = {
    "CenterCrop": {"height": 64, "width": 64},
    "Crop": {"x_min": 0, "y_min": 0, "x_max": 96, "y_max": 96},
    "CropAndPad": {"px": 4},
    "GridElasticDeform": {"num_grid_xy": [4, 4], "magnitude": 4},
    "LetterBox": {"size": [96, 96]},
    "LongestMaxSize": {"max_size": 96},
    "RandomResizedCrop": {"size": [96, 96]},
    "RandomSizedCrop": {"min_max_height": [64, 96], "size": [96, 96]},
    "Resize": {"height": 96, "width": 96},
    "SmallestMaxSize": {"max_size": 96},
    "XYMasking": {
        "num_masks_x_range": [1, 1],
        "num_masks_y_range": [1, 1],
        "mask_x_length_range": [8, 8],
        "mask_y_length_range": [8, 8],
    },
}


def smoke_supported_transforms(transform_names: Sequence[str] | None = None) -> tuple[TransformSmokeResult, ...]:
    """Construct and execute every transform exposed by the normal selector."""

    _ensure_project_root_on_path()

    from albumentationsx_plugin.albumentations_backend.catalog import AlbuSpecCatalogProvider
    from albumentationsx_plugin.albumentations_backend.fixed import (
        build_fixed_pipeline_config,
        create_fixed_image_pipeline,
    )
    from albumentationsx_plugin.albumentations_backend.parameters import AlbuSpecParameterSchemaProvider
    from albumentationsx_plugin.core import CapabilityStatus, PluginError

    catalog_provider = AlbuSpecCatalogProvider()
    parameter_schema_provider = AlbuSpecParameterSchemaProvider(catalog_provider=catalog_provider)
    image = _source_image()
    results: list[TransformSmokeResult] = []
    requested_transform_names = set(transform_names or ())
    seen_transform_names: set[str] = set()

    for capability in catalog_provider.list_transform_capabilities():
        if capability.status not in {CapabilityStatus.SUPPORTED, CapabilityStatus.SUPPORTED_WITH_DEFAULTS}:
            continue
        if requested_transform_names and capability.name not in requested_transform_names:
            continue
        seen_transform_names.add(capability.name)

        external_targets = _external_targets(capability)
        if external_targets is None:
            results.append(
                TransformSmokeResult(
                    transform_name=capability.name,
                    status="skipped",
                    reason_code="unsupported_external_input_fixture",
                    message="Smoke helper has no deterministic fixture for this external input resolver.",
                    external_inputs=tuple(requirement.name for requirement in capability.external_inputs),
                )
            )
            continue

        try:
            config = build_fixed_pipeline_config(
                _smoke_params(capability.name),
                catalog_provider=catalog_provider,
                parameter_schema_provider=parameter_schema_provider,
            )
            pipeline = create_fixed_image_pipeline(config)
            pipeline.apply(image, targets=external_targets)
        except PluginError as error:
            results.append(_plugin_error_result(capability.name, error))
        except Exception as error:
            results.append(
                TransformSmokeResult(
                    transform_name=capability.name,
                    status="failed",
                    reason_code=type(error).__name__,
                    message=str(error),
                    external_inputs=tuple(requirement.name for requirement in capability.external_inputs),
                )
            )
        else:
            results.append(
                TransformSmokeResult(
                    transform_name=capability.name,
                    status="passed",
                    external_inputs=tuple(requirement.name for requirement in capability.external_inputs),
                )
            )

    for transform_name in sorted(requested_transform_names - seen_transform_names):
        results.append(
            TransformSmokeResult(
                transform_name=transform_name,
                status="failed",
                reason_code="unknown_or_unselectable_transform",
                message="Transform is not exposed by the normal supported selector.",
            )
        )

    return tuple(results)


def _smoke_params(transform_name: str) -> dict[str, object]:
    return {
        "transform": transform_name,
        "p": 1.0,
        "outputs_per_sample": 1,
        **SMOKE_PARAMETER_OVERRIDES.get(transform_name, {}),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report format. Defaults to text.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the report to.",
    )
    parser.add_argument(
        "--transform",
        action="append",
        default=None,
        help="Transform name to smoke. May be passed multiple times. Defaults to every supported transform.",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Exit with status 0 even when transform smoke failures are found.",
    )
    args = parser.parse_args(argv)

    results = smoke_supported_transforms(transform_names=args.transform)
    report = _render_json_report(results) if args.format == "json" else _render_text_report(results)
    if args.output is None:
        print(report)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{report}\n", encoding="utf-8")

    if not args.allow_failures and any(result.status in {"failed", "skipped"} for result in results):
        return 1
    return 0


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def _source_image() -> np.ndarray:
    y_indices, x_indices = np.indices((128, 128), dtype=np.uint8)
    return np.stack(
        (
            x_indices,
            y_indices,
            np.bitwise_xor(x_indices, y_indices),
        ),
        axis=2,
    )


def _reference_images() -> list[np.ndarray]:
    source = _source_image()
    return [np.flipud(source).copy(), np.fliplr(source).copy()]


def _external_targets(capability: Any) -> Mapping[str, object] | None:
    targets: dict[str, object] = {}
    for requirement in capability.external_inputs:
        if requirement.resolver != "reference_image_pool" or not requirement.metadata_key:
            return None
        targets[requirement.metadata_key] = _reference_images()
    return targets


def _plugin_error_result(transform_name: str, error: Any) -> TransformSmokeResult:
    context = getattr(error, "context", {})
    reason_code = ""
    if isinstance(context, Mapping):
        raw_reason = context.get("reason_code")
        reason_code = raw_reason if isinstance(raw_reason, str) else ""
    return TransformSmokeResult(
        transform_name=transform_name,
        status="failed",
        reason_code=reason_code or type(error).__name__,
        message=str(error),
    )


def _render_json_report(results: Sequence[TransformSmokeResult]) -> str:
    return json.dumps(
        {
            "summary": _summary(results),
            "results": [asdict(result) for result in results],
        },
        indent=2,
        sort_keys=True,
    )


def _render_text_report(results: Sequence[TransformSmokeResult]) -> str:
    summary = _summary(results)
    lines = [
        "AlbumentationsX supported transform smoke",
        f"total: {summary['total']}",
        f"passed: {summary['passed']}",
        f"failed: {summary['failed']}",
        f"skipped: {summary['skipped']}",
    ]
    for result in results:
        if result.status == "passed":
            continue
        detail = f"{result.transform_name}: {result.status}"
        if result.reason_code:
            detail += f" ({result.reason_code})"
        if result.message:
            detail += f" - {result.message}"
        lines.append(detail)
    return "\n".join(lines)


def _summary(results: Sequence[TransformSmokeResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "passed": sum(1 for result in results if result.status == "passed"),
        "failed": sum(1 for result in results if result.status == "failed"),
        "skipped": sum(1 for result in results if result.status == "skipped"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
