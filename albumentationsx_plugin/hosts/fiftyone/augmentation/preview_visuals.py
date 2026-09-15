"""Render annotation-aware preview visuals for FiftyOne operator outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from albumentationsx_plugin.core import JSONDict
from albumentationsx_plugin.core.serialization import normalize_json_mapping
from albumentationsx_plugin.hosts.fiftyone.annotations.fields import (
    FIELD_TYPE_CLASSIFICATION,
    FIELD_TYPE_DETECTIONS,
    FIELD_TYPE_HEATMAP,
    FIELD_TYPE_KEYPOINTS,
    FIELD_TYPE_POLYLINES,
    FIELD_TYPE_SEGMENTATION,
)
from albumentationsx_plugin.hosts.fiftyone.augmentation.preview_annotation_comparison import (
    build_preview_annotation_comparison,
    heatmap_array,
    mask_array,
    optional_bool,
    optional_text,
    payload_fields,
    payload_sequence,
    payload_type,
    polyline_shapes,
    relative_bbox,
    relative_points,
)
from albumentationsx_plugin.storage.images import RGBArray, validate_rgb_array

_PANEL_MAX_WIDTH: Final[int] = 420
_PANEL_MAX_HEIGHT: Final[int] = 320
_HEADER_HEIGHT: Final[int] = 30
_PANEL_GAP: Final[int] = 12
_PANEL_PADDING: Final[int] = 10
_POINT_RADIUS: Final[int] = 4
_FIELD_COLORS: Final[tuple[tuple[int, int, int, int], ...]] = (
    (31, 119, 180, 220),
    (44, 160, 44, 220),
    (214, 39, 40, 220),
    (148, 103, 189, 220),
    (255, 127, 14, 220),
    (23, 190, 207, 220),
)


@dataclass(frozen=True, slots=True)
class PreviewVisualComparison:
    """Annotation-aware image and JSON summary for one preview result."""

    image: RGBArray
    annotation_comparison: JSONDict


def build_preview_visual_comparison(
    *,
    source_image: object,
    output_image: object,
    source_labels: Mapping[str, object],
    output_labels: Mapping[str, object],
) -> PreviewVisualComparison:
    """Build a side-by-side before/after image with annotation overlays."""

    source_payload = normalize_json_mapping(source_labels)
    output_payload = normalize_json_mapping(output_labels)
    source_overlay = _overlay_image(source_image, source_payload)
    output_overlay = _overlay_image(output_image, output_payload)
    comparison_image = _side_by_side_image(source_overlay, output_overlay)
    return PreviewVisualComparison(
        image=_image_to_rgb_array(comparison_image),
        annotation_comparison=build_preview_annotation_comparison(source_payload, output_payload),
    )


def _overlay_image(image: object, payload: Mapping[str, object]) -> Image.Image:
    base = Image.fromarray(validate_rgb_array(image)).convert("RGBA")
    for field_index, (field_name, field_payload) in enumerate(payload_fields(payload).items()):
        color = _FIELD_COLORS[field_index % len(_FIELD_COLORS)]
        _draw_field(
            base,
            field_name=field_name,
            field_payload=field_payload,
            field_index=field_index,
            color=color,
        )
    return base


def _draw_field(
    image: Image.Image,
    *,
    field_name: str,
    field_payload: Mapping[str, object],
    field_index: int,
    color: tuple[int, int, int, int],
) -> None:
    label_type = payload_type(field_payload)
    if label_type == FIELD_TYPE_CLASSIFICATION:
        _draw_classification(
            image,
            field_name=field_name,
            field_payload=field_payload,
            field_index=field_index,
            color=color,
        )
    elif label_type == FIELD_TYPE_DETECTIONS:
        _draw_detections(image, field_name=field_name, field_payload=field_payload, color=color)
    elif label_type == FIELD_TYPE_HEATMAP:
        _draw_heatmap(image, field_payload=field_payload, color=color)
    elif label_type == FIELD_TYPE_KEYPOINTS:
        _draw_keypoints(image, field_name=field_name, field_payload=field_payload, color=color)
    elif label_type == FIELD_TYPE_POLYLINES:
        _draw_polylines(image, field_name=field_name, field_payload=field_payload, color=color)
    elif label_type == FIELD_TYPE_SEGMENTATION:
        _draw_segmentation(image, field_payload=field_payload, color=color)


def _draw_classification(
    image: Image.Image,
    *,
    field_name: str,
    field_payload: Mapping[str, object],
    field_index: int,
    color: tuple[int, int, int, int],
) -> None:
    label = optional_text(field_payload.get("label"))
    if not label:
        return
    y_offset = 6 + 18 * field_index
    _draw_text_badge(ImageDraw.Draw(image), (6, y_offset), f"{field_name}: {label}", color)


def _draw_detections(
    image: Image.Image,
    *,
    field_name: str,
    field_payload: Mapping[str, object],
    color: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for detection in payload_sequence(field_payload, "detections"):
        bbox = relative_bbox(detection)
        if bbox is None:
            continue
        rect = _bbox_rect(bbox, width=width, height=height)
        _draw_detection_mask(image, detection, rect, color=color)
        draw.rectangle(rect, outline=color, width=3)
        label = optional_text(detection.get("label")) or field_name
        _draw_text_badge(draw, (rect[0], max(0, rect[1] - 18)), label, color)


def _draw_keypoints(
    image: Image.Image,
    *,
    field_name: str,
    field_payload: Mapping[str, object],
    color: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for keypoint in payload_sequence(field_payload, "keypoints"):
        label = optional_text(keypoint.get("label")) or field_name
        for point in relative_points(keypoint):
            x, y = _relative_point(point, width=width, height=height)
            draw.ellipse(
                (x - _POINT_RADIUS, y - _POINT_RADIUS, x + _POINT_RADIUS, y + _POINT_RADIUS),
                fill=color,
                outline=(255, 255, 255, 230),
                width=1,
            )
            _draw_text_badge(draw, (x + _POINT_RADIUS + 2, y - _POINT_RADIUS), label, color)


def _draw_polylines(
    image: Image.Image,
    *,
    field_name: str,
    field_payload: Mapping[str, object],
    color: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for polyline in payload_sequence(field_payload, "polylines"):
        label = optional_text(polyline.get("label")) or field_name
        for shape in polyline_shapes(polyline):
            points = [_relative_point(point, width=width, height=height) for point in shape]
            if len(points) < 2:
                continue
            if optional_bool(polyline.get("filled"), default=False) and len(points) >= 3:
                fill = (color[0], color[1], color[2], 50)
                draw.polygon(points, fill=fill, outline=color)
            else:
                line_points = [*points, points[0]] if optional_bool(polyline.get("closed"), default=False) else points
                draw.line(line_points, fill=color, width=3)
            _draw_text_badge(draw, points[0], label, color)


def _draw_segmentation(
    image: Image.Image,
    *,
    field_payload: Mapping[str, object],
    color: tuple[int, int, int, int],
) -> None:
    mask = mask_array(field_payload.get("mask"))
    if mask is None:
        return
    overlay = _mask_overlay(mask, color=color, size=image.size)
    image.alpha_composite(overlay)


def _draw_detection_mask(
    image: Image.Image,
    detection: Mapping[str, object],
    rect: tuple[float, float, float, float],
    *,
    color: tuple[int, int, int, int],
) -> None:
    mask = mask_array(detection.get("mask"))
    if mask is None:
        return
    left, top, right, bottom = (int(round(value)) for value in rect)
    box_width = max(1, right - left)
    box_height = max(1, bottom - top)
    overlay = _mask_overlay(mask, color=color, size=(box_width, box_height))
    image.alpha_composite(overlay, dest=(left, top))


def _draw_heatmap(
    image: Image.Image,
    *,
    field_payload: Mapping[str, object],
    color: tuple[int, int, int, int],
) -> None:
    heatmap = heatmap_array(field_payload.get("map"))
    if heatmap is None:
        return
    overlay = _heatmap_overlay(heatmap, color=color, size=image.size)
    image.alpha_composite(overlay)


def _side_by_side_image(source: Image.Image, output: Image.Image) -> Image.Image:
    source_panel = _fit_panel(source)
    output_panel = _fit_panel(output)
    panel_width = max(source_panel.width, output_panel.width)
    panel_height = max(source_panel.height, output_panel.height)
    canvas_width = _PANEL_PADDING * 2 + panel_width * 2 + _PANEL_GAP
    canvas_height = _PANEL_PADDING * 2 + _HEADER_HEIGHT + panel_height
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (250, 250, 250, 255))
    draw = ImageDraw.Draw(canvas)
    source_origin = (_PANEL_PADDING, _PANEL_PADDING + _HEADER_HEIGHT)
    output_origin = (_PANEL_PADDING + panel_width + _PANEL_GAP, _PANEL_PADDING + _HEADER_HEIGHT)
    _draw_panel(canvas, draw, source_panel, origin=source_origin, label="Before")
    _draw_panel(canvas, draw, output_panel, origin=output_origin, label="After")
    return canvas


def _fit_panel(image: Image.Image) -> Image.Image:
    panel = image.copy()
    panel.thumbnail((_PANEL_MAX_WIDTH, _PANEL_MAX_HEIGHT), Image.Resampling.LANCZOS)
    return panel


def _draw_panel(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    *,
    origin: tuple[int, int],
    label: str,
) -> None:
    x, y = origin
    label_position = (x, max(0, y - _HEADER_HEIGHT + 6))
    _draw_text_badge(draw, label_position, label, (40, 40, 40, 230))
    border = (x - 1, y - 1, x + image.width + 1, y + image.height + 1)
    draw.rectangle(border, outline=(185, 185, 185, 255), width=1)
    canvas.alpha_composite(image, dest=origin)


def _draw_text_badge(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    color: tuple[int, int, int, int],
) -> None:
    label = _truncate_text(text)
    if not label:
        return
    x, y = xy
    bbox = draw.textbbox((x, y), label)
    background = (color[0], color[1], color[2], 190)
    draw.rectangle((bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2), fill=background)
    draw.text((x, y), label, fill=(255, 255, 255, 255))


def _bbox_rect(
    bbox: Sequence[float],
    *,
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    x, y, box_width, box_height = bbox
    left = _clamp(x) * width
    top = _clamp(y) * height
    right = _clamp(x + box_width) * width
    bottom = _clamp(y + box_height) * height
    return left, top, max(left + 1.0, right), max(top + 1.0, bottom)


def _relative_point(point: Sequence[float], *, width: int, height: int) -> tuple[float, float]:
    return _clamp(point[0]) * width, _clamp(point[1]) * height


def _mask_overlay(
    mask: npt.NDArray[np.bool_],
    *,
    color: tuple[int, int, int, int],
    size: tuple[int, int],
) -> Image.Image:
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[mask, 0] = color[0]
    rgba[mask, 1] = color[1]
    rgba[mask, 2] = color[2]
    rgba[mask, 3] = 70
    overlay = Image.fromarray(rgba, mode="RGBA")
    if overlay.size != size:
        overlay = overlay.resize(size, Image.Resampling.NEAREST)
    return overlay


def _heatmap_overlay(
    heatmap: npt.NDArray[np.float32],
    *,
    color: tuple[int, int, int, int],
    size: tuple[int, int],
) -> Image.Image:
    minimum = float(np.min(heatmap))
    maximum = float(np.max(heatmap))
    if maximum > minimum:
        normalized = (heatmap - minimum) / (maximum - minimum)
    else:
        normalized = np.where(heatmap != 0, 1.0, 0.0)
    alpha = np.asarray(normalized * 95, dtype=np.uint8)
    rgba = np.zeros((*heatmap.shape, 4), dtype=np.uint8)
    rgba[..., 0] = color[0]
    rgba[..., 1] = color[1]
    rgba[..., 2] = color[2]
    rgba[..., 3] = alpha
    overlay = Image.fromarray(rgba, mode="RGBA")
    if overlay.size != size:
        overlay = overlay.resize(size, Image.Resampling.BILINEAR)
    return overlay


def _image_to_rgb_array(image: Image.Image) -> RGBArray:
    return cast(RGBArray, np.asarray(image.convert("RGB"), dtype=np.uint8))


def _truncate_text(value: str, *, limit: int = 36) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}..."


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
