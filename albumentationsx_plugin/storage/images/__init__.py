"""Image IO helpers for plugin-owned augmentation outputs."""

from albumentationsx_plugin.storage.images.io import (
    LoadedImage,
    MaskArray,
    RGBArray,
    load_rgb_image,
    resolve_output_image_path,
    validate_mask_array,
    validate_rgb_array,
    write_mask_image,
    write_rgb_image,
)
from albumentationsx_plugin.storage.images.naming import (
    build_output_image_relative_path,
    build_output_mask_relative_path,
)

__all__ = [
    "LoadedImage",
    "MaskArray",
    "RGBArray",
    "build_output_image_relative_path",
    "build_output_mask_relative_path",
    "load_rgb_image",
    "resolve_output_image_path",
    "validate_mask_array",
    "validate_rgb_array",
    "write_mask_image",
    "write_rgb_image",
]
