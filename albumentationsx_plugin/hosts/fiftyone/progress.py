"""Progress reporting helpers for FiftyOne augmentation operators."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final, Protocol

DELEGATED_EXECUTION_RECOMMENDED_SOURCE_COUNT: Final[int] = 50

_COMPLETE_STAGES: Final[frozenset[str]] = frozenset({"complete", "dry_run_complete"})
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AugmentationProgress:
    """Structured progress snapshot for one augmentation run."""

    stage: str
    total_sources: int
    processed_sources: int
    planned_outputs: int
    created_outputs: int
    skipped_sources: int
    errors: int
    dry_run: bool = False

    @property
    def fraction(self) -> float:
        """Return a FiftyOne-compatible progress fraction between 0 and 1."""

        if self.total_sources <= 0:
            return 1.0 if self.stage in _COMPLETE_STAGES else 0.0
        return _clamp(self.processed_sources / self.total_sources)

    @property
    def label(self) -> str:
        """Return a compact human-readable progress label."""

        mode = "Dry run" if self.dry_run else "Augmentation"
        return (
            f"{mode} {self.stage}: processed sources {self.processed_sources}/{self.total_sources}; "
            f"planned outputs {self.planned_outputs}; created outputs {self.created_outputs}; "
            f"skipped sources {self.skipped_sources}; errors {self.errors}"
        )


class ProgressReporter(Protocol):
    """Minimal reporter interface used by the augmentation executor."""

    def report(self, progress: AugmentationProgress) -> None:
        """Publish a progress snapshot."""


class NoOpProgressReporter:
    """Progress reporter used when no host-specific reporter is available."""

    def report(self, progress: AugmentationProgress) -> None:
        """Ignore progress updates."""


class FiftyOneProgressReporter:
    """Bridge structured augmentation progress into a FiftyOne context."""

    def __init__(self, ctx: Any | None) -> None:
        self._ctx = ctx

    def report(self, progress: AugmentationProgress) -> None:
        """Publish progress through the public FiftyOne execution context API."""

        ctx = self._ctx
        if ctx is None:
            return

        set_progress = getattr(ctx, "set_progress", None)
        if callable(set_progress):
            try:
                set_progress(progress=progress.fraction, label=progress.label)
                return
            except Exception:
                _LOGGER.debug("Failed to report FiftyOne delegated progress", exc_info=True)

        trigger = getattr(ctx, "trigger", None)
        if not callable(trigger):
            return
        try:
            trigger(
                "set_progress",
                params={
                    "progress": progress.fraction,
                    "label": progress.label,
                    "variant": "linear",
                },
            )
        except Exception:
            _LOGGER.debug("Failed to report FiftyOne App progress", exc_info=True)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "DELEGATED_EXECUTION_RECOMMENDED_SOURCE_COUNT",
    "AugmentationProgress",
    "FiftyOneProgressReporter",
    "NoOpProgressReporter",
    "ProgressReporter",
]
