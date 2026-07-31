from __future__ import annotations

import importlib
import sys

import numpy as np
import pytest
from PIL import Image

from albumentationsx_plugin.core import MediaIOError
from albumentationsx_plugin.storage.images import (
    build_output_image_relative_path,
    load_rgb_image,
    resolve_output_image_path,
    validate_rgb_array,
    write_rgb_image,
)


def _rgb_array(width: int = 5, height: int = 4) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 0] = 255
    image[:, :, 1] = np.arange(width, dtype=np.uint8)
    return image


@pytest.mark.unit
def test_load_rgb_image_returns_uint8_rgb_array(tmp_path) -> None:
    original = _rgb_array()
    image_path = write_rgb_image(original, tmp_path, "inputs/source.png")

    loaded = load_rgb_image(image_path)

    assert loaded.filepath == image_path
    assert loaded.width == 5
    assert loaded.height == 4
    assert loaded.data.dtype == np.uint8
    assert loaded.data.shape == (4, 5, 3)
    np.testing.assert_array_equal(loaded.data, original)


@pytest.mark.unit
def test_load_rgb_image_converts_supported_modes_to_rgb(tmp_path) -> None:
    rgba_array = np.zeros((3, 4, 4), dtype=np.uint8)
    rgba_array[..., 0] = 12
    rgba_array[..., 1] = 34
    rgba_array[..., 2] = 56
    rgba_array[..., 3] = 128
    rgba_path = tmp_path / "rgba.png"
    Image.fromarray(rgba_array).save(rgba_path)

    loaded = load_rgb_image(rgba_path)

    assert loaded.data.shape == (3, 4, 3)
    assert loaded.data.dtype == np.uint8
    np.testing.assert_array_equal(loaded.data[..., 0], np.full((3, 4), 12, dtype=np.uint8))


@pytest.mark.unit
def test_load_rgb_image_reports_missing_file_with_structured_error(tmp_path) -> None:
    missing_path = tmp_path / "missing.png"

    with pytest.raises(MediaIOError) as error:
        load_rgb_image(missing_path)

    assert error.value.reason_code == "io_error"
    assert error.value.context == {
        "filepath": str(missing_path),
        "reason": "missing_file",
    }


@pytest.mark.unit
def test_load_rgb_image_reports_unreadable_files(tmp_path) -> None:
    unreadable_path = tmp_path / "not-an-image.png"
    unreadable_path.write_text("not image bytes", encoding="utf-8")

    with pytest.raises(MediaIOError) as error:
        load_rgb_image(unreadable_path)

    assert error.value.context["reason"] == "unreadable_image"
    assert error.value.context["filepath"] == str(unreadable_path)


@pytest.mark.unit
def test_validate_rgb_array_reports_invalid_shape_and_channels() -> None:
    with pytest.raises(MediaIOError) as shape_error:
        validate_rgb_array(np.zeros((4, 5), dtype=np.uint8))

    with pytest.raises(MediaIOError) as channel_error:
        validate_rgb_array(np.zeros((4, 5, 4), dtype=np.uint8))

    assert shape_error.value.context["reason"] == "invalid_shape"
    assert shape_error.value.context["shape"] == [4, 5]
    assert channel_error.value.context["reason"] == "invalid_channel_count"
    assert channel_error.value.context["channels"] == 4


@pytest.mark.unit
def test_validate_rgb_array_reports_invalid_dtype() -> None:
    with pytest.raises(MediaIOError) as error:
        validate_rgb_array(np.zeros((4, 5, 3), dtype=np.float32))

    assert error.value.context["reason"] == "invalid_dtype"
    assert error.value.context["dtype"] == "float32"


@pytest.mark.unit
def test_write_rgb_image_refuses_to_overwrite_existing_outputs(tmp_path) -> None:
    image = _rgb_array()

    output_path = write_rgb_image(image, tmp_path, "images/result.png")

    with pytest.raises(MediaIOError) as error:
        write_rgb_image(image, tmp_path, "images/result.png")

    assert output_path.exists()
    assert error.value.context["reason"] == "output_exists"


@pytest.mark.unit
def test_resolve_output_image_path_rejects_unsafe_relative_paths(tmp_path) -> None:
    with pytest.raises(MediaIOError) as traversal_error:
        resolve_output_image_path(tmp_path, "../escape.png")

    with pytest.raises(MediaIOError) as absolute_error:
        resolve_output_image_path(tmp_path, tmp_path / "absolute.png")

    assert traversal_error.value.context["reason"] == "unsafe_output_path"
    assert absolute_error.value.context["reason"] == "absolute_output_path"


@pytest.mark.unit
def test_resolve_output_image_path_rejects_unsupported_extensions(tmp_path) -> None:
    with pytest.raises(MediaIOError) as error:
        resolve_output_image_path(tmp_path, "images/result.bmp")

    assert error.value.context["reason"] == "unsupported_extension"
    assert error.value.context["extension"] == ".bmp"


@pytest.mark.unit
def test_output_image_relative_path_is_deterministic_and_manifest_safe() -> None:
    relative_path = build_output_image_relative_path(
        "/source data/My Image.JPG",
        sample_id="sample/id:1",
        output_index=7,
    )

    assert relative_path.as_posix() == "images/My-Image-sample-id-1-0007.png"


@pytest.mark.unit
def test_storage_image_import_does_not_import_fiftyone() -> None:
    sys.modules.pop("fiftyone", None)

    importlib.import_module("albumentationsx_plugin.storage.images")

    assert "fiftyone" not in sys.modules
