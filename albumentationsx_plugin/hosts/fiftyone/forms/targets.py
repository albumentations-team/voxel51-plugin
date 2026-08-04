"""Shared target metadata for FiftyOne augmentation form guidance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class TargetKind(StrEnum):
    """Known transform targets rendered in the FiftyOne augmentation form."""

    IMAGE = "image"
    BBOXES = "bboxes"
    MASKS = "mask"
    KEYPOINTS = "keypoints"
    LABELS = "labels"


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """Display and Albumentations lookup metadata for a known target kind."""

    kind: TargetKind
    label: str
    albumentations_aliases: tuple[str, ...] = ()


TARGET_SPECS: Final[dict[TargetKind, TargetSpec]] = {
    TargetKind.IMAGE: TargetSpec(TargetKind.IMAGE, "image", ("image",)),
    TargetKind.BBOXES: TargetSpec(TargetKind.BBOXES, "bboxes", ("bboxes",)),
    TargetKind.MASKS: TargetSpec(TargetKind.MASKS, "masks", ("mask", "masks")),
    TargetKind.KEYPOINTS: TargetSpec(TargetKind.KEYPOINTS, "keypoints", ("keypoints",)),
    TargetKind.LABELS: TargetSpec(TargetKind.LABELS, "labels"),
}
TARGET_DISPLAY_ORDER: Final[tuple[TargetKind, ...]] = (
    TargetKind.IMAGE,
    TargetKind.BBOXES,
    TargetKind.MASKS,
    TargetKind.KEYPOINTS,
    TargetKind.LABELS,
)
FIFTYONE_LABEL_TARGETS: Final[dict[str, TargetKind]] = {
    "Classification": TargetKind.LABELS,
    "Classifications": TargetKind.LABELS,
    "Detections": TargetKind.BBOXES,
    "Keypoints": TargetKind.KEYPOINTS,
    "Segmentation": TargetKind.MASKS,
}


def target_label(target_kind: TargetKind) -> str:
    """Return the human-readable label for a known target kind."""

    return TARGET_SPECS[target_kind].label


def target_supported(target_kind: TargetKind, transform_targets: tuple[str, ...]) -> bool:
    """Return whether Albumentations metadata declares support for a target kind."""

    return any(alias in transform_targets for alias in TARGET_SPECS[target_kind].albumentations_aliases)
