"""Host adapter interfaces.

Host adapters translate a specific application runtime into core DTOs. The
interface intentionally avoids accepting FiftyOne objects directly so the core
layer can be tested without a running host application.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from albumentationsx_plugin.core.contracts import AugmentationInput, AugmentationResult, RunManifest


@runtime_checkable
class HostSampleAdapter(Protocol):
    """Adapter between host-owned samples and core augmentation DTOs."""

    @property
    def host_name(self) -> str:
        """Return a short stable host name, for example `fiftyone`."""
        ...

    def iter_inputs(self) -> Iterable[AugmentationInput]:
        """Yield source items selected by the host."""
        ...

    def create_output_sample(self, result: AugmentationResult, manifest: RunManifest) -> str:
        """Create a host-owned output record and return its stable identifier."""
        ...
