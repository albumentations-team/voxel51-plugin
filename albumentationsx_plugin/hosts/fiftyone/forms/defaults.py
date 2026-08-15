"""Derive FiftyOne form defaults from host runtime context."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from albumentationsx_plugin.core import DEFAULT_CROP_SIZE
from albumentationsx_plugin.hosts.fiftyone.execution_scope import selected_sample_ids_from_context


@runtime_checkable
class _SupportsGetItem(Protocol):
    def __getitem__(self, key: str, /) -> object:
        """Return a sample-like object by ID."""


@dataclass(frozen=True, slots=True)
class RandomCropDefaults:
    """Runtime-aware UI defaults for `RandomCrop` dimensions."""

    width: int
    height: int
    help_text: str


@dataclass(frozen=True, slots=True)
class _ImageDimensions:
    width: int
    height: int


def build_random_crop_defaults(ctx: Any | None) -> RandomCropDefaults | None:
    """Build safe `RandomCrop` defaults from selected sample dimensions."""

    dimensions = _selected_sample_dimensions(ctx)
    if not dimensions:
        return None

    min_width = min(dimension.width for dimension in dimensions)
    min_height = min(dimension.height for dimension in dimensions)
    width = min(DEFAULT_CROP_SIZE, min_width)
    height = min(DEFAULT_CROP_SIZE, min_height)
    unique_sizes = {(dimension.width, dimension.height) for dimension in dimensions}
    if len(unique_sizes) == 1:
        help_text = "Default is limited by the selected image dimensions."
    else:
        help_text = "Selected images have mixed dimensions; default is limited by the smallest selected image."

    return RandomCropDefaults(width=width, height=height, help_text=help_text)


def _selected_sample_dimensions(ctx: Any | None) -> tuple[_ImageDimensions, ...]:
    samples = _selected_samples_from_context(ctx)
    if not samples:
        return ()

    dimensions = tuple(
        dimension for sample in samples if (dimension := _image_dimensions_from_sample(sample)) is not None
    )
    if len(dimensions) != len(samples):
        return ()

    return dimensions


def _selected_samples_from_context(ctx: Any | None) -> tuple[object, ...]:
    selected_samples = _ctx_selected_samples(ctx)
    if selected_samples:
        return selected_samples

    selected_sample_ids = selected_sample_ids_from_context(ctx)
    if not selected_sample_ids:
        return ()

    collection = _sample_collection(ctx)
    if collection is None:
        return ()

    samples = _samples_by_select(collection, selected_sample_ids)
    if not samples:
        samples = _samples_by_id_lookup(collection, selected_sample_ids)
    if len(samples) != len(selected_sample_ids):
        return ()

    return samples


def _ctx_selected_samples(ctx: Any | None) -> tuple[object, ...]:
    selected_samples = getattr(ctx, "selected_samples", ()) if ctx is not None else ()
    if isinstance(selected_samples, Iterable) and not isinstance(selected_samples, str | bytes | Mapping):
        return tuple(selected_samples)
    return ()


def _sample_collection(ctx: Any | None) -> object | None:
    if ctx is None:
        return None
    return getattr(ctx, "view", None) or getattr(ctx, "dataset", None)


def _samples_by_select(collection: object, selected_sample_ids: tuple[str, ...]) -> tuple[object, ...]:
    select = getattr(collection, "select", None)
    if not callable(select):
        return ()

    try:
        selected_collection = select(selected_sample_ids)
    except (AttributeError, LookupError, TypeError, ValueError):
        return ()

    return _iter_samples(selected_collection)


def _samples_by_id_lookup(collection: object, selected_sample_ids: tuple[str, ...]) -> tuple[object, ...]:
    samples: list[object] = []
    for sample_id in selected_sample_ids:
        sample = _sample_by_id(collection, sample_id)
        if sample is None:
            return ()
        samples.append(sample)
    return tuple(samples)


def _sample_by_id(collection: object, sample_id: str) -> object | None:
    get_sample = getattr(collection, "get_sample", None)
    if callable(get_sample):
        try:
            return get_sample(sample_id)
        except (AttributeError, LookupError, TypeError, ValueError):
            return None

    if not isinstance(collection, _SupportsGetItem):
        return None

    try:
        return collection[sample_id]
    except (AttributeError, LookupError, TypeError, ValueError):
        return None


def _iter_samples(collection: object) -> tuple[object, ...]:
    if not isinstance(collection, Iterable) or isinstance(collection, str | bytes | Mapping):
        return ()
    return tuple(collection)


def _image_dimensions_from_sample(sample: object) -> _ImageDimensions | None:
    metadata = _value_from(sample, "metadata")
    width = _positive_int(_value_from(metadata, "width"))
    height = _positive_int(_value_from(metadata, "height"))
    if width is None or height is None:
        return None
    return _ImageDimensions(width=width, height=height)


def _value_from(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, float) and not isinstance(value, bool) and value.is_integer() and value > 0:
        return int(value)
    return None
