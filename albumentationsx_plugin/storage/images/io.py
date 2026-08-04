"""Host-neutral image loading, validation, and output writing."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import TypeAlias, cast

import numpy as np
import numpy.typing as npt
from PIL import Image, UnidentifiedImageError

from albumentationsx_plugin.core import MediaIOError
from albumentationsx_plugin.storage.images.constants import SUPPORTED_OUTPUT_EXTENSIONS

RGBArray: TypeAlias = npt.NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class LoadedImage:
    """Validated RGB image loaded from disk."""

    filepath: Path
    data: RGBArray
    width: int
    height: int


def load_rgb_image(filepath: str | PathLike[str]) -> LoadedImage:
    """Load an image from disk and return a validated RGB uint8 array."""

    path = Path(filepath).expanduser()
    if not path.exists():
        raise _media_error(path, "Image file does not exist.", reason="missing_file")
    if not path.is_file():
        raise _media_error(path, "Image path is not a file.", reason="not_a_file")

    try:
        with Image.open(path) as image:
            array = np.array(image.convert("RGB"), dtype=np.uint8, copy=True)
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise _media_error(
            path,
            "Image file could not be read as a supported image.",
            reason="unreadable_image",
            exception_type=type(error).__name__,
        ) from error

    rgb_array = validate_rgb_array(array, filepath=path)
    height, width, _channels = rgb_array.shape
    return LoadedImage(
        filepath=path.resolve(),
        data=rgb_array,
        width=int(width),
        height=int(height),
    )


def validate_rgb_array(image: object, *, filepath: str | PathLike[str] | None = None) -> RGBArray:
    """Return a `uint8` RGB array or raise a structured media IO error."""

    error_filepath = "<memory>" if filepath is None else str(filepath)
    if not isinstance(image, np.ndarray):
        raise _media_error(
            error_filepath,
            "Image data must be a NumPy array.",
            reason="invalid_array_type",
            actual_type=type(image).__name__,
        )

    if image.dtype != np.uint8:
        raise _media_error(
            error_filepath,
            "Image data must use uint8 dtype.",
            reason="invalid_dtype",
            dtype=str(image.dtype),
            shape=_shape_context(image),
        )

    if image.ndim != 3:
        raise _media_error(
            error_filepath,
            "Image data must have shape (height, width, 3).",
            reason="invalid_shape",
            shape=_shape_context(image),
        )

    height, width, channels = image.shape
    if height <= 0 or width <= 0:
        raise _media_error(
            error_filepath,
            "Image data must have positive width and height.",
            reason="invalid_shape",
            shape=_shape_context(image),
        )

    if channels != 3:
        raise _media_error(
            error_filepath,
            "Image data must have exactly three RGB channels.",
            reason="invalid_channel_count",
            shape=_shape_context(image),
            channels=int(channels),
        )

    return cast(RGBArray, image)


def write_rgb_image(
    image: object,
    output_root: str | PathLike[str],
    relative_path: str | PathLike[str],
    *,
    overwrite: bool = False,
) -> Path:
    """Validate and write an RGB image under `output_root`.

    `relative_path` must stay inside `output_root`; absolute paths and parent
    traversal are rejected before any file is written.
    """

    array = validate_rgb_array(image)
    output_path = resolve_output_image_path(output_root, relative_path)
    if output_path.exists() and not overwrite:
        raise _media_error(
            output_path,
            "Output image already exists.",
            reason="output_exists",
            relative_path=str(relative_path),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _write_temporary_image(array, output_path)
    try:
        temporary_path.replace(output_path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise _media_error(
            output_path,
            "Output image could not be moved into place.",
            reason="write_failed",
            exception_type=type(error).__name__,
        ) from error

    return output_path


def resolve_output_image_path(output_root: str | PathLike[str], relative_path: str | PathLike[str]) -> Path:
    """Resolve a manifest-relative image path inside an output root."""

    root = Path(output_root).expanduser().resolve()
    raw_relative_path = Path(relative_path)
    if raw_relative_path.is_absolute():
        raise _media_error(
            raw_relative_path,
            "Output image path must be relative to the run directory.",
            reason="absolute_output_path",
        )
    if not raw_relative_path.parts or ".." in raw_relative_path.parts:
        raise _media_error(
            root / raw_relative_path,
            "Output image path must not contain parent traversal.",
            reason="unsafe_output_path",
            relative_path=str(relative_path),
        )

    output_path = (root / raw_relative_path).resolve()
    try:
        output_path.relative_to(root)
    except ValueError as error:
        raise _media_error(
            output_path,
            "Output image path escapes the run directory.",
            reason="unsafe_output_path",
            relative_path=str(relative_path),
        ) from error

    if output_path.suffix.lower() not in SUPPORTED_OUTPUT_EXTENSIONS:
        raise _media_error(
            output_path,
            "Output image extension is not supported.",
            reason="unsupported_extension",
            extension=output_path.suffix.lower(),
        )

    return output_path


def _write_temporary_image(array: RGBArray, output_path: Path) -> Path:
    suffix = output_path.suffix.lower()
    image_format = "JPEG" if suffix in {".jpg", ".jpeg"} else "PNG"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.stem}.",
            suffix=suffix,
            dir=output_path.parent,
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
        Image.fromarray(array).save(temporary_path, format=image_format)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise _media_error(
            output_path,
            "Output image could not be written.",
            reason="write_failed",
            exception_type=type(error).__name__,
        ) from error

    return temporary_path


def _shape_context(image: np.ndarray) -> list[int]:
    return [int(part) for part in image.shape]


def _media_error(
    filepath: str | PathLike[str],
    message: str,
    *,
    reason: str,
    **context: object,
) -> MediaIOError:
    return MediaIOError(
        filepath=str(filepath),
        message=message,
        context={"reason": reason, **context},
    )
