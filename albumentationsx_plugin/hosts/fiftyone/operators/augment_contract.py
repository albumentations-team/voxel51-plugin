"""Stable augmentation operator identifiers and error codes."""

from __future__ import annotations

import logging

OPERATOR_NAME = "augment_with_albumentationsx"
OPERATOR_LABEL = "AlbumentationsX · Augment images"
NO_SELECTION_ERROR_CODE = "no_selected_samples"
UNEXPECTED_RUNTIME_ERROR_CODE = "unexpected_runtime_error"
_LOGGER = logging.getLogger("albumentationsx_plugin.hosts.fiftyone.operators.augment")
