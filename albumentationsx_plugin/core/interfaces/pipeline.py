"""Pipeline factory and runner interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from albumentationsx_plugin.core.contracts import AugmentationInput, AugmentationResult, PipelineConfig


@runtime_checkable
class PipelineRunner(Protocol):
    """Executable augmentation pipeline hidden behind a backend boundary."""

    def run(self, source: AugmentationInput) -> AugmentationResult:
        """Apply the prepared pipeline to one source item."""
        ...


@runtime_checkable
class PipelineFactory(Protocol):
    """Factory that validates configs and creates backend-specific runners."""

    def validate(self, config: PipelineConfig) -> None:
        """Raise a structured plugin error if the config cannot be executed."""
        ...

    def create_runner(self, config: PipelineConfig) -> PipelineRunner:
        """Create a runner for a previously validated pipeline config."""
        ...
