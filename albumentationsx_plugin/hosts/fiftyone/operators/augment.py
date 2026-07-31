"""Placeholder augmentation operator for the FiftyOne App.

This operator establishes plugin discovery and registration. Real augmentation
logic is intentionally deferred until the image IO, sample adapter, and pipeline
tasks are implemented.
"""

from __future__ import annotations

from typing import Any

import fiftyone.operators as foo
import fiftyone.operators.types as types
from fiftyone.operators.operator import RiskLevel

OPERATOR_NAME = "augment_with_albumentationsx"
OPERATOR_LABEL = "Augment with AlbumentationsX"
PLACEHOLDER_MESSAGE = (
    "AlbumentationsX augmentation is not implemented yet. This operator is a "
    "registration placeholder for the MVP workflow."
)


class AugmentWithAlbumentationsX(foo.Operator):
    """Empty FiftyOne operator registered by the plugin scaffold."""

    @property
    def config(self) -> foo.OperatorConfig:
        return foo.OperatorConfig(
            name=OPERATOR_NAME,
            label=OPERATOR_LABEL,
            description="Build and preview AlbumentationsX augmentation pipelines.",
            dynamic=False,
            allow_immediate_execution=True,
            allow_delegated_execution=False,
            allow_distributed_execution=False,
            risk_level=RiskLevel.LOW,
        )

    # pyrefly: ignore[bad-override]
    def resolve_input(self, ctx: Any):
        inputs = types.Object()
        inputs.message(
            "status",
            label="Operator registered",
            description=PLACEHOLDER_MESSAGE,
        )
        return types.Property(
            inputs,
            view=types.View(label=OPERATOR_LABEL),
        )

    # pyrefly: ignore[bad-override]
    def resolve_output(self, ctx: Any):
        outputs = types.Object()
        outputs.bool(
            "ready",
            label="Registered",
            description="Whether the placeholder operator executed successfully.",
        )
        outputs.str(
            "message",
            label="Message",
            description="Current implementation status.",
        )
        return types.Property(outputs)

    # pyrefly: ignore[bad-override]
    def resolve_placement(self, ctx: Any):
        return types.Placement(
            types.Places.SAMPLES_GRID_ACTIONS,
            types.Button(label=OPERATOR_LABEL),
        )

    def execute(self, ctx: Any) -> dict[str, bool | str]:
        return {
            "ready": False,
            "message": PLACEHOLDER_MESSAGE,
        }
