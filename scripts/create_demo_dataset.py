"""Create a tiny deterministic FiftyOne dataset for local plugin demos."""

from __future__ import annotations

import argparse
import shutil
import struct
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import fiftyone as fo
import numpy as np

from albumentationsx_plugin.storage.images import write_mask_image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_NAME = "albumentationsx-demo"
GENERATED_DATA_ROOT = PROJECT_ROOT / "sample_data" / "generated"
DEFAULT_DATA_ROOT = GENERATED_DATA_ROOT / DEFAULT_DATASET_NAME
MARKER_FILENAME = ".albumentationsx-demo-data"
DEMO_TAG = "albumentationsx-demo"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_SUITE_KEY = "basic"
ALL_SUITE_KEY = "all"
SEGMENTATION_STORAGE_MEMORY = "memory"
SEGMENTATION_STORAGE_FILE = "file"
SEGMENTATION_STORAGE_MISSING_FILE = "missing_file"
SEGMENTATION_STORAGE_INVALID_SHAPE_FILE = "invalid_shape_file"
DETECTION_MASK_STORAGE_MEMORY = "memory"
DETECTION_MASK_STORAGE_FILE = "file"
HEATMAP_STORAGE_MEMORY = "memory"
HEATMAP_STORAGE_FILE = "file"
HEATMAP_STORAGE_MISSING_FILE = "missing_file"

RGB = tuple[int, int, int]
PixelFactory = Callable[[int, int], RGB]


class DemoDatasetError(Exception):
    """Raised when the demo dataset workflow cannot continue safely."""


@dataclass(frozen=True, slots=True)
class DemoSampleSpec:
    """Definition for one generated demo image and its FiftyOne fields."""

    demo_id: str
    filename: str
    label: str
    split: str
    scenario: str
    width: int = 96
    height: int = 64
    segmentation_storage: str = SEGMENTATION_STORAGE_MEMORY
    detection_mask_storage: str = DETECTION_MASK_STORAGE_MEMORY
    heatmap_storage: str = HEATMAP_STORAGE_MEMORY
    detection_count: int = 1
    keypoint_count: int = 1
    polyline_count: int = 1
    empty_supported_labels: bool = False
    boundary_geometry: bool = False
    include_unsupported_labels: bool = False
    missing_image: bool = False
    validation_case: str = ""


@dataclass(frozen=True, slots=True)
class DemoDatasetSpec:
    """Named demo dataset suite used by the CLI and integration checks."""

    suite_key: str
    dataset_name: str
    description: str
    samples: tuple[DemoSampleSpec, ...]


@dataclass(frozen=True, slots=True)
class DemoDatasetSummary:
    """Small serializable summary printed by the demo dataset commands."""

    dataset_name: str
    exists: bool
    sample_count: int
    data_root: Path
    image_count: int
    demo_ids: tuple[str, ...] = ()
    sample_ids: tuple[str, ...] = ()


DEMO_SAMPLES: tuple[DemoSampleSpec, ...] = (
    DemoSampleSpec(
        demo_id="demo-001",
        filename="demo-001-left-object.png",
        label="left-object",
        split="train",
        scenario="horizontal-flip",
    ),
    DemoSampleSpec(
        demo_id="demo-002",
        filename="demo-002-brightness-grid.png",
        label="brightness-grid",
        split="validation",
        scenario="brightness-contrast",
    ),
    DemoSampleSpec(
        demo_id="demo-003",
        filename="demo-003-center-target.png",
        label="center-target",
        split="test",
        scenario="crop",
    ),
)

ANNOTATION_DEMO_SAMPLES: tuple[DemoSampleSpec, ...] = DEMO_SAMPLES + (
    DemoSampleSpec(
        demo_id="annotations-004",
        filename="annotations-004-wide-object.png",
        label="wide-object",
        split="validation",
        scenario="annotation-wide",
        width=128,
        height=72,
    ),
    DemoSampleSpec(
        demo_id="annotations-005",
        filename="annotations-005-tall-object.png",
        label="tall-object",
        split="test",
        scenario="annotation-tall",
        width=72,
        height=128,
    ),
    DemoSampleSpec(
        demo_id="annotations-006",
        filename="annotations-006-multiple-spatial-labels.png",
        label="multiple-spatial-labels",
        split="validation",
        scenario="multiple-spatial-labels",
        detection_count=2,
        keypoint_count=2,
        polyline_count=2,
    ),
    DemoSampleSpec(
        demo_id="annotations-007",
        filename="annotations-007-boundary-geometry.png",
        label="boundary-geometry",
        split="validation",
        scenario="boundary-geometry",
        detection_count=2,
        keypoint_count=2,
        polyline_count=2,
        boundary_geometry=True,
    ),
    DemoSampleSpec(
        demo_id="annotations-008",
        filename="annotations-008-empty-label-containers.png",
        label="empty-label-containers",
        split="validation",
        scenario="empty-label-containers",
        detection_count=0,
        keypoint_count=0,
        polyline_count=0,
        empty_supported_labels=True,
    ),
)

MASK_DEMO_SAMPLES: tuple[DemoSampleSpec, ...] = (
    DemoSampleSpec(
        demo_id="masks-001",
        filename="masks-001-memory-segmentation.png",
        label="memory-segmentation",
        split="train",
        scenario="memory-segmentation",
    ),
    DemoSampleSpec(
        demo_id="masks-002",
        filename="masks-002-file-backed-segmentation.png",
        label="file-backed-segmentation",
        split="validation",
        scenario="file-backed-segmentation",
        segmentation_storage=SEGMENTATION_STORAGE_FILE,
    ),
    DemoSampleSpec(
        demo_id="masks-003",
        filename="masks-003-file-backed-detection-and-heatmap.png",
        label="file-backed-detection-and-heatmap",
        split="validation",
        scenario="file-backed-detection-and-heatmap",
        detection_mask_storage=DETECTION_MASK_STORAGE_FILE,
        heatmap_storage=HEATMAP_STORAGE_FILE,
    ),
)

VALIDATION_DEMO_SAMPLES: tuple[DemoSampleSpec, ...] = (
    DemoSampleSpec(
        demo_id="validation-001",
        filename="validation-001-heatmap-image-only-conflict.png",
        label="heatmap-image-only-conflict",
        split="validation",
        scenario="heatmap-image-only-conflict",
        validation_case="heatmap_with_image_only_transform",
    ),
    DemoSampleSpec(
        demo_id="validation-002",
        filename="validation-002-missing-source-image.png",
        label="missing-source-image",
        split="validation",
        scenario="missing-source-image",
        missing_image=True,
        validation_case="missing_source_image",
    ),
    DemoSampleSpec(
        demo_id="validation-003",
        filename="validation-003-missing-mask-file.png",
        label="missing-mask-file",
        split="validation",
        scenario="missing-mask-file",
        segmentation_storage=SEGMENTATION_STORAGE_MISSING_FILE,
        validation_case="missing_segmentation_mask_file",
    ),
    DemoSampleSpec(
        demo_id="validation-004",
        filename="validation-004-invalid-mask-shape.png",
        label="invalid-mask-shape",
        split="validation",
        scenario="invalid-mask-shape",
        segmentation_storage=SEGMENTATION_STORAGE_INVALID_SHAPE_FILE,
        validation_case="invalid_segmentation_mask_shape",
    ),
    DemoSampleSpec(
        demo_id="validation-005",
        filename="validation-005-unsupported-label.png",
        label="unsupported-label",
        split="validation",
        scenario="unsupported-label",
        include_unsupported_labels=True,
        validation_case="unsupported_label_field",
    ),
    DemoSampleSpec(
        demo_id="validation-006",
        filename="validation-006-crop-too-large.png",
        label="crop-too-large",
        split="validation",
        scenario="crop-too-large",
        width=20,
        height=16,
        validation_case="crop_larger_than_image",
    ),
    DemoSampleSpec(
        demo_id="validation-007",
        filename="validation-007-missing-heatmap-file.png",
        label="missing-heatmap-file",
        split="validation",
        scenario="missing-heatmap-file",
        heatmap_storage=HEATMAP_STORAGE_MISSING_FILE,
        validation_case="missing_heatmap_map_file",
    ),
)

DEMO_DATASET_SPECS: dict[str, DemoDatasetSpec] = {
    DEFAULT_SUITE_KEY: DemoDatasetSpec(
        suite_key=DEFAULT_SUITE_KEY,
        dataset_name=DEFAULT_DATASET_NAME,
        description="Small stable dataset used by the existing MVP smoke workflow.",
        samples=DEMO_SAMPLES,
    ),
    "annotations": DemoDatasetSpec(
        suite_key="annotations",
        dataset_name="albumentationsx-demo-annotations",
        description="Broader supported-label dataset with different image shapes.",
        samples=ANNOTATION_DEMO_SAMPLES,
    ),
    "masks": DemoDatasetSpec(
        suite_key="masks",
        dataset_name="albumentationsx-demo-masks",
        description="Focused segmentation dataset with memory and file-backed masks.",
        samples=MASK_DEMO_SAMPLES,
    ),
    "validation": DemoDatasetSpec(
        suite_key="validation",
        dataset_name="albumentationsx-demo-validation",
        description="Intentional edge cases for validation and error-reporting checks.",
        samples=VALIDATION_DEMO_SAMPLES,
    ),
}
DEMO_DATASET_SUITE_KEYS: tuple[str, ...] = tuple(DEMO_DATASET_SPECS)


def write_demo_images(
    data_root: Path = DEFAULT_DATA_ROOT,
    samples: Sequence[DemoSampleSpec] = DEMO_SAMPLES,
) -> tuple[Path, ...]:
    """Write deterministic PNG images and return their paths."""

    image_root = data_root / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for spec in samples:
        if spec.missing_image:
            continue
        path = image_root / spec.filename
        path.write_bytes(_encode_png(spec.width, spec.height, lambda x, y, sample=spec: _pixel_color(sample, x, y)))
        written_paths.append(path)

    _write_demo_mask_assets(data_root, samples)
    _write_demo_detection_mask_assets(data_root, samples)
    _write_demo_heatmap_assets(data_root, samples)
    (data_root / MARKER_FILENAME).write_text(
        "Generated by scripts/create_demo_dataset.py. It is safe to delete this directory.\n",
        encoding="utf-8",
    )
    return tuple(written_paths)


def create_demo_dataset(
    dataset_name: str = DEFAULT_DATASET_NAME,
    data_root: Path = DEFAULT_DATA_ROOT,
    *,
    overwrite: bool = False,
    samples: Sequence[DemoSampleSpec] = DEMO_SAMPLES,
) -> DemoDatasetSummary:
    """Create the demo dataset and generated image files."""

    if dataset_name in fo.list_datasets():
        if not overwrite:
            raise DemoDatasetError(
                f"Dataset '{dataset_name}' already exists. Re-run with --overwrite or delete it first."
            )
        fo.delete_dataset(dataset_name)

    image_paths = write_demo_images(data_root, samples)
    dataset = fo.Dataset(dataset_name)
    dataset.persistent = True
    dataset.add_samples(_build_samples(data_root, samples))
    dataset.save()

    return _summarize_dataset(dataset, data_root, image_count=len(image_paths))


def create_demo_dataset_suite(
    suite_keys: Sequence[str] = DEMO_DATASET_SUITE_KEYS,
    data_root: Path = GENERATED_DATA_ROOT,
    *,
    overwrite: bool = False,
    dataset_name_prefix: str = "",
) -> tuple[DemoDatasetSummary, ...]:
    """Create one or more named demo dataset suites."""

    summaries: list[DemoDatasetSummary] = []
    for spec in _selected_dataset_specs(suite_keys):
        dataset_name = f"{dataset_name_prefix}{spec.dataset_name}"
        summaries.append(
            create_demo_dataset(
                dataset_name=dataset_name,
                data_root=data_root / dataset_name,
                overwrite=overwrite,
                samples=spec.samples,
            )
        )
    return tuple(summaries)


def describe_demo_dataset(
    dataset_name: str = DEFAULT_DATASET_NAME,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> DemoDatasetSummary:
    """Return a summary for an existing demo dataset."""

    if dataset_name not in fo.list_datasets():
        return DemoDatasetSummary(
            dataset_name=dataset_name,
            exists=False,
            sample_count=0,
            data_root=data_root,
            image_count=_count_existing_images(data_root),
        )

    dataset = fo.load_dataset(dataset_name)
    return _summarize_dataset(dataset, data_root, image_count=_count_existing_images(data_root))


def describe_demo_dataset_suite(
    suite_keys: Sequence[str] = DEMO_DATASET_SUITE_KEYS,
    data_root: Path = GENERATED_DATA_ROOT,
    *,
    dataset_name_prefix: str = "",
) -> tuple[DemoDatasetSummary, ...]:
    """Return summaries for one or more named demo dataset suites."""

    summaries: list[DemoDatasetSummary] = []
    for spec in _selected_dataset_specs(suite_keys):
        dataset_name = f"{dataset_name_prefix}{spec.dataset_name}"
        summaries.append(describe_demo_dataset(dataset_name=dataset_name, data_root=data_root / dataset_name))
    return tuple(summaries)


def delete_demo_dataset(
    dataset_name: str = DEFAULT_DATASET_NAME,
    data_root: Path = DEFAULT_DATA_ROOT,
    *,
    delete_files: bool = False,
) -> DemoDatasetSummary:
    """Delete the demo dataset and optionally the generated local files."""

    summary = describe_demo_dataset(dataset_name, data_root)
    if summary.exists:
        fo.delete_dataset(dataset_name)

    if delete_files:
        delete_generated_files(data_root)

    return summary


def delete_demo_dataset_suite(
    suite_keys: Sequence[str] = DEMO_DATASET_SUITE_KEYS,
    data_root: Path = GENERATED_DATA_ROOT,
    *,
    delete_files: bool = False,
    dataset_name_prefix: str = "",
) -> tuple[DemoDatasetSummary, ...]:
    """Delete one or more named demo dataset suites."""

    summaries: list[DemoDatasetSummary] = []
    for spec in _selected_dataset_specs(suite_keys):
        dataset_name = f"{dataset_name_prefix}{spec.dataset_name}"
        summaries.append(
            delete_demo_dataset(
                dataset_name=dataset_name, data_root=data_root / dataset_name, delete_files=delete_files
            )
        )
    return tuple(summaries)


def delete_generated_files(data_root: Path = DEFAULT_DATA_ROOT) -> None:
    """Delete generated demo files if the directory carries the script marker."""

    if not data_root.exists():
        return

    marker_path = data_root / MARKER_FILENAME
    if not data_root.is_dir() or not marker_path.exists():
        raise DemoDatasetError(
            f"Refusing to delete '{data_root}' because it was not created by the demo dataset script."
        )

    shutil.rmtree(data_root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.suite == ALL_SUITE_KEY and args.dataset_name:
            raise DemoDatasetError("--dataset-name can only be used when managing a single demo dataset suite.")

        suite_keys = _suite_keys_from_cli(args.suite)
        match args.command:
            case "create":
                if args.suite == ALL_SUITE_KEY:
                    summaries = create_demo_dataset_suite(
                        suite_keys=suite_keys,
                        data_root=_suite_data_root(args.data_root),
                        overwrite=args.overwrite,
                    )
                    _print_summaries("created", summaries)
                else:
                    spec = DEMO_DATASET_SPECS[args.suite]
                    dataset_name = args.dataset_name or spec.dataset_name
                    data_root = _single_dataset_data_root(args.data_root, dataset_name)
                    summary = create_demo_dataset(
                        dataset_name=dataset_name,
                        data_root=data_root,
                        overwrite=args.overwrite,
                        samples=spec.samples,
                    )
                    _print_summary("created", summary)
            case "list":
                if args.suite == ALL_SUITE_KEY:
                    summaries = describe_demo_dataset_suite(
                        suite_keys=suite_keys, data_root=_suite_data_root(args.data_root)
                    )
                    _print_summaries("found", summaries)
                else:
                    spec = DEMO_DATASET_SPECS[args.suite]
                    dataset_name = args.dataset_name or spec.dataset_name
                    data_root = _single_dataset_data_root(args.data_root, dataset_name)
                    summary = describe_demo_dataset(dataset_name, data_root)
                    _print_summary("found" if summary.exists else "missing", summary)
            case "delete":
                if args.suite == ALL_SUITE_KEY:
                    data_root = _suite_data_root(args.data_root)
                    summaries = delete_demo_dataset_suite(
                        suite_keys=suite_keys,
                        data_root=data_root,
                        delete_files=args.delete_files,
                    )
                    _print_summaries("deleted", summaries)
                    if args.delete_files:
                        print(f"generated files: deleted from {data_root}")
                else:
                    spec = DEMO_DATASET_SPECS[args.suite]
                    dataset_name = args.dataset_name or spec.dataset_name
                    data_root = _single_dataset_data_root(args.data_root, dataset_name)
                    summary = delete_demo_dataset(dataset_name, data_root, delete_files=args.delete_files)
                    _print_summary("deleted" if summary.exists else "missing", summary)
                    if args.delete_files:
                        print(f"generated files: deleted from {data_root}")
            case _:
                raise DemoDatasetError(f"Unsupported command: {args.command}")
    except DemoDatasetError as error:
        parser.exit(status=1, message=f"error: {error}\n")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="create",
        choices=("create", "list", "delete"),
        help="Workflow command to run. Defaults to create.",
    )
    parser.add_argument(
        "--suite",
        default=DEFAULT_SUITE_KEY,
        choices=(*DEMO_DATASET_SUITE_KEYS, ALL_SUITE_KEY),
        help=f"Demo dataset suite to manage. Defaults to {DEFAULT_SUITE_KEY}.",
    )
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="FiftyOne dataset name override for a single suite.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help=f"Generated data root. Defaults to {DEFAULT_DATA_ROOT} for the basic suite.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete and recreate an existing demo dataset.",
    )
    parser.add_argument(
        "--delete-files",
        action="store_true",
        help="Also delete generated image files when running the delete command.",
    )
    return parser


def _build_samples(data_root: Path, sample_specs: Sequence[DemoSampleSpec] = DEMO_SAMPLES) -> list[fo.Sample]:
    image_root = data_root / "images"
    samples: list[fo.Sample] = []
    for spec in sample_specs:
        fields: dict[str, object] = {
            "filepath": str((image_root / spec.filename).resolve()),
            "tags": _demo_tags(spec),
            "metadata": fo.ImageMetadata(width=spec.width, height=spec.height, mime_type="image/png"),
            "demo_id": spec.demo_id,
            "split": spec.split,
            "scenario": spec.scenario,
            "source": "generated",
            "ground_truth": fo.Classification(label=spec.label),
            "detections": _demo_detections(spec, data_root),
            "keypoints": _demo_keypoints(spec),
            "polylines": _demo_polylines(spec),
            "heatmap": _demo_heatmap_label(spec, data_root),
            "segmentation": _demo_segmentation(spec, data_root),
        }
        if spec.validation_case:
            fields["validation_case"] = spec.validation_case
        if spec.include_unsupported_labels:
            fields["unsupported_classifications"] = fo.Classifications(
                classifications=[
                    fo.Classification(label=f"{spec.label}-primary"),
                    fo.Classification(label=f"{spec.label}-secondary"),
                ]
            )

        samples.append(fo.Sample(**fields))
    return samples


def _selected_dataset_specs(suite_keys: Sequence[str]) -> tuple[DemoDatasetSpec, ...]:
    specs: list[DemoDatasetSpec] = []
    for suite_key in suite_keys:
        try:
            specs.append(DEMO_DATASET_SPECS[suite_key])
        except KeyError as error:
            supported = ", ".join((*DEMO_DATASET_SUITE_KEYS, ALL_SUITE_KEY))
            raise DemoDatasetError(
                f"Unsupported demo dataset suite '{suite_key}'. Supported suites: {supported}."
            ) from error
    return tuple(specs)


def _suite_keys_from_cli(suite: str) -> tuple[str, ...]:
    if suite == ALL_SUITE_KEY:
        return DEMO_DATASET_SUITE_KEYS
    return (suite,)


def _suite_data_root(data_root: Path | None) -> Path:
    if data_root is None:
        return GENERATED_DATA_ROOT.resolve()
    return data_root.expanduser().resolve()


def _single_dataset_data_root(data_root: Path | None, dataset_name: str) -> Path:
    if data_root is None:
        return (GENERATED_DATA_ROOT / dataset_name).resolve()
    return data_root.expanduser().resolve()


def _demo_tags(spec: DemoSampleSpec) -> list[str]:
    tags = [DEMO_TAG, spec.split, spec.scenario]
    if spec.validation_case:
        tags.extend(("validation-case", spec.validation_case))
    return tags


def _write_demo_mask_assets(data_root: Path, sample_specs: Sequence[DemoSampleSpec]) -> None:
    for spec in sample_specs:
        match spec.segmentation_storage:
            case "memory" | "missing_file":
                continue
            case "file":
                _write_demo_mask_asset(data_root, spec, _demo_segmentation_mask(spec))
            case "invalid_shape_file":
                invalid_mask = _demo_segmentation_mask(
                    DemoSampleSpec(
                        demo_id=spec.demo_id,
                        filename=spec.filename,
                        label=spec.label,
                        split=spec.split,
                        scenario=spec.scenario,
                        width=max(1, spec.width - 5),
                        height=max(1, spec.height - 3),
                    )
                )
                _write_demo_mask_asset(data_root, spec, invalid_mask)
            case _:
                raise DemoDatasetError(
                    f"Unsupported segmentation storage '{spec.segmentation_storage}' for sample '{spec.demo_id}'."
                )


def _write_demo_mask_asset(data_root: Path, spec: DemoSampleSpec, mask: np.ndarray) -> Path:
    return write_mask_image(mask, data_root, _demo_mask_relative_path(spec), overwrite=True)


def _write_demo_detection_mask_assets(data_root: Path, sample_specs: Sequence[DemoSampleSpec]) -> None:
    for spec in sample_specs:
        match spec.detection_mask_storage:
            case "memory":
                continue
            case "file":
                for detection_index in range(spec.detection_count):
                    write_mask_image(
                        _demo_detection_instance_mask(detection_index),
                        data_root,
                        _demo_detection_mask_relative_path(spec, detection_index),
                        overwrite=True,
                    )
            case _:
                raise DemoDatasetError(
                    f"Unsupported detection mask storage '{spec.detection_mask_storage}' for sample '{spec.demo_id}'."
                )


def _write_demo_heatmap_assets(data_root: Path, sample_specs: Sequence[DemoSampleSpec]) -> None:
    for spec in sample_specs:
        match spec.heatmap_storage:
            case "memory" | "missing_file":
                continue
            case "file":
                write_mask_image(
                    _demo_heatmap_image(spec), data_root, _demo_heatmap_relative_path(spec), overwrite=True
                )
            case _:
                raise DemoDatasetError(
                    f"Unsupported heatmap storage '{spec.heatmap_storage}' for sample '{spec.demo_id}'."
                )


def _demo_segmentation(spec: DemoSampleSpec, data_root: Path) -> fo.Segmentation:
    if spec.empty_supported_labels:
        return fo.Segmentation(tags=["demo", "empty"])

    match spec.segmentation_storage:
        case "memory":
            return fo.Segmentation(mask=_demo_segmentation_mask(spec), tags=["demo", "memory-backed"])
        case "file" | "invalid_shape_file":
            return fo.Segmentation(
                mask_path=str((data_root / _demo_mask_relative_path(spec)).resolve()), tags=["demo", "file-backed"]
            )
        case "missing_file":
            return fo.Segmentation(
                mask_path=str((data_root / _demo_mask_relative_path(spec)).resolve()), tags=["demo", "missing-file"]
            )
        case _:
            raise DemoDatasetError(
                f"Unsupported segmentation storage '{spec.segmentation_storage}' for sample '{spec.demo_id}'."
            )


def _demo_mask_relative_path(spec: DemoSampleSpec) -> Path:
    return Path("masks") / f"{Path(spec.filename).stem}-segmentation.png"


def _demo_detection_mask_relative_path(spec: DemoSampleSpec, detection_index: int) -> Path:
    suffix = "" if spec.detection_count == 1 else f"-{detection_index + 1}"
    return Path("masks") / f"{Path(spec.filename).stem}-detection{suffix}.png"


def _demo_heatmap_relative_path(spec: DemoSampleSpec) -> Path:
    return Path("heatmaps") / f"{Path(spec.filename).stem}-heatmap.png"


def _demo_detections(spec: DemoSampleSpec, data_root: Path) -> fo.Detections:
    detections = []
    for detection_index in range(spec.detection_count):
        detection_kwargs: dict[str, object] = {
            "label": _indexed_label(spec.label, detection_index, spec.detection_count),
            "bounding_box": _demo_bounding_boxes(spec)[detection_index % len(_demo_bounding_boxes(spec))],
            "confidence": 0.9 - min(detection_index, 4) * 0.05,
            "attributes": {"scenario": fo.CategoricalAttribute(value=spec.scenario)},
        }
        match spec.detection_mask_storage:
            case "memory":
                detection_kwargs["mask"] = _demo_detection_instance_mask(detection_index)
            case "file":
                detection_kwargs["mask_path"] = str(
                    (data_root / _demo_detection_mask_relative_path(spec, detection_index)).resolve()
                )
            case _:
                raise DemoDatasetError(
                    f"Unsupported detection mask storage '{spec.detection_mask_storage}' for sample '{spec.demo_id}'."
                )
        detections.append(fo.Detection(**detection_kwargs))

    return fo.Detections(detections=detections)


def _demo_keypoints(spec: DemoSampleSpec) -> fo.Keypoints:
    return fo.Keypoints(
        keypoints=[
            fo.Keypoint(
                label=_indexed_label(f"{spec.label}-anchor", keypoint_index, spec.keypoint_count),
                points=_demo_keypoint_points(spec)[keypoint_index % len(_demo_keypoint_points(spec))],
                confidence=[0.95, 0.85],
            )
            for keypoint_index in range(spec.keypoint_count)
        ]
    )


def _demo_polylines(spec: DemoSampleSpec) -> fo.Polylines:
    return fo.Polylines(
        polylines=[
            fo.Polyline(
                label=_indexed_label(f"{spec.label}-outline", polyline_index, spec.polyline_count),
                points=[_demo_polyline_points(spec)[polyline_index % len(_demo_polyline_points(spec))]],
                confidence=0.8,
                closed=False,
                filled=False,
            )
            for polyline_index in range(spec.polyline_count)
        ]
    )


def _demo_heatmap_label(spec: DemoSampleSpec, data_root: Path) -> fo.Heatmap:
    if spec.empty_supported_labels:
        return fo.Heatmap(tags=["demo", "empty"])

    match spec.heatmap_storage:
        case "memory":
            return fo.Heatmap(map=_demo_heatmap(spec), range=[0.0, 1.0], tags=["demo", "memory-backed"])
        case "file":
            return fo.Heatmap(
                map_path=str((data_root / _demo_heatmap_relative_path(spec)).resolve()),
                range=[0.0, 255.0],
                tags=["demo", "file-backed"],
            )
        case "missing_file":
            return fo.Heatmap(
                map_path=str((data_root / _demo_heatmap_relative_path(spec)).resolve()),
                range=[0.0, 255.0],
                tags=["demo", "missing-file"],
            )
        case _:
            raise DemoDatasetError(f"Unsupported heatmap storage '{spec.heatmap_storage}' for sample '{spec.demo_id}'.")


def _demo_bounding_boxes(spec: DemoSampleSpec) -> tuple[list[float], ...]:
    if spec.boundary_geometry:
        return ([0.0, 0.0, 0.2, 0.28], [0.78, 0.7, 0.22, 0.3])
    return ([0.12, 0.25, 0.32, 0.5], [0.58, 0.18, 0.26, 0.32])


def _demo_keypoint_points(spec: DemoSampleSpec) -> tuple[list[list[float]], ...]:
    if spec.boundary_geometry:
        return (
            [[0.02, 0.02], [0.18, 0.26]],
            [[0.98, 0.96], [0.82, 0.74]],
        )
    return (
        [[0.25, 0.5], [0.42, 0.38]],
        [[0.62, 0.28], [0.76, 0.44]],
    )


def _demo_polyline_points(spec: DemoSampleSpec) -> tuple[list[list[float]], ...]:
    if spec.boundary_geometry:
        return (
            [[0.0, 0.08], [0.18, 0.18], [0.28, 0.0]],
            [[0.72, 1.0], [0.86, 0.82], [1.0, 0.92]],
        )
    return (
        [[0.16, 0.32], [0.28, 0.24], [0.44, 0.44], [0.58, 0.55]],
        [[0.58, 0.26], [0.66, 0.34], [0.78, 0.48], [0.84, 0.6]],
    )


def _indexed_label(label: str, index: int, count: int) -> str:
    if count <= 1:
        return label
    return f"{label}-{index + 1}"


def _demo_detection_instance_mask(index: int = 0) -> np.ndarray:
    if index % 2:
        return np.asarray(
            [
                [0, 0, 1, 1],
                [0, 1, 1, 1],
                [1, 1, 1, 0],
                [1, 1, 0, 0],
            ],
            dtype=np.uint8,
        )
    return np.asarray(
        [
            [1, 1, 0, 0],
            [1, 1, 1, 0],
            [0, 1, 1, 1],
            [0, 0, 1, 1],
        ],
        dtype=np.uint8,
    )


def _demo_heatmap(spec: DemoSampleSpec) -> np.ndarray:
    y_indices, x_indices = np.indices((spec.height, spec.width), dtype=np.float32)
    return (x_indices + y_indices) / float(spec.width + spec.height - 2)


def _demo_heatmap_image(spec: DemoSampleSpec) -> np.ndarray:
    return np.asarray(np.rint(_demo_heatmap(spec) * 255.0), dtype=np.uint8)


def _demo_segmentation_mask(spec: DemoSampleSpec) -> np.ndarray:
    mask = np.zeros((spec.height, spec.width), dtype=np.uint8)
    mask[spec.height // 4 : (spec.height * 3) // 4, spec.width // 8 : spec.width // 3] = 1
    mask[spec.height // 3 : (spec.height * 2) // 3, spec.width // 2 : (spec.width * 3) // 4] = 2
    return mask


def _summarize_dataset(dataset: fo.Dataset, data_root: Path, *, image_count: int) -> DemoDatasetSummary:
    demo_ids: list[str] = []
    sample_ids: list[str] = []
    for sample in dataset:
        demo_id = sample.get_field("demo_id")
        if isinstance(demo_id, str):
            demo_ids.append(demo_id)
        sample_ids.append(str(sample.id))

    return DemoDatasetSummary(
        dataset_name=dataset.name,
        exists=True,
        sample_count=len(dataset),
        data_root=data_root,
        image_count=image_count,
        demo_ids=tuple(sorted(demo_ids)),
        sample_ids=tuple(sorted(sample_ids)),
    )


def _print_summary(action: str, summary: DemoDatasetSummary) -> None:
    status = "exists" if summary.exists else "not found"
    print(f"dataset: {summary.dataset_name} ({status}, {action})")
    print(f"samples: {summary.sample_count}")
    print(f"images: {summary.image_count}")
    print(f"data root: {summary.data_root}")
    if summary.demo_ids:
        print(f"demo ids: {', '.join(summary.demo_ids)}")
    if summary.sample_ids:
        print(f"fiftyone sample ids: {', '.join(summary.sample_ids)}")


def _print_summaries(action: str, summaries: Sequence[DemoDatasetSummary]) -> None:
    for index, summary in enumerate(summaries):
        if index:
            print()
        summary_action = action if summary.exists else "missing"
        _print_summary(summary_action, summary)


def _count_existing_images(data_root: Path) -> int:
    image_root = data_root / "images"
    if not image_root.exists():
        return 0
    return sum(1 for path in image_root.iterdir() if path.suffix.lower() == ".png")


def _encode_png(width: int, height: int, pixel_factory: PixelFactory) -> bytes:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel_factory(x, y))

    return b"".join(
        (
            PNG_SIGNATURE,
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
            _png_chunk(b"IEND", b""),
        )
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _pixel_color(spec: DemoSampleSpec, x: int, y: int) -> RGB:
    if spec.demo_id == "demo-001":
        if 8 <= x < 36 and 16 <= y < 48:
            return (236, 82, 82)
        if abs(y - round((x / spec.width) * spec.height)) <= 1:
            return (64, 192, 128)
        return (25, 34, 46)

    if spec.demo_id == "demo-002":
        if (x // 8 + y // 8) % 2 == 0:
            return (246, 210, 96)
        return (39, 119, 184)

    center_x = spec.width // 2
    center_y = spec.height // 2
    if (x - center_x) ** 2 + (y - center_y) ** 2 <= 18**2:
        return (132, 96, 246)
    if 24 <= x < 72 and 24 <= y < 40:
        return (245, 245, 245)
    return (33, 38, 48)


if __name__ == "__main__":
    raise SystemExit(main())
