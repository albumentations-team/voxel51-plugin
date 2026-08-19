"""Best-effort cancellation checks for FiftyOne operator contexts."""

from __future__ import annotations

import logging
from typing import Any, Final, Protocol

from albumentationsx_plugin.core import AugmentationCancelledError

_LOGGER = logging.getLogger(__name__)

_CANCELLATION_SIGNAL_NAMES: Final[tuple[str, ...]] = (
    "is_cancelled",
    "is_canceled",
    "cancelled",
    "canceled",
    "should_stop",
    "interrupted",
    "is_interrupted",
)


class CancellationChecker(Protocol):
    """Minimal cancellation interface used by augmentation executors."""

    def raise_if_cancelled(self) -> None:
        """Raise when a host or test harness has requested cancellation."""


class NoOpCancellationChecker:
    """Cancellation checker used when a host does not expose a signal."""

    def raise_if_cancelled(self) -> None:
        """Ignore cancellation checks."""


class FiftyOneCancellationChecker:
    """Best-effort bridge from a FiftyOne execution context to cancellation."""

    def __init__(self, ctx: Any | None) -> None:
        self._ctx = ctx

    def raise_if_cancelled(self) -> None:
        """Raise if the context exposes a truthy cancellation-like signal."""

        signal_name = _active_cancellation_signal(self._ctx)
        if not signal_name:
            return
        raise AugmentationCancelledError(
            context={
                "reason": "host_cancellation_requested",
                "host": "fiftyone",
                "signal": signal_name,
            }
        )


def _active_cancellation_signal(ctx: Any | None) -> str:
    if ctx is None:
        return ""

    for signal_name in _CANCELLATION_SIGNAL_NAMES:
        if _signal_is_active(ctx, signal_name):
            return signal_name
    return ""


def _signal_is_active(ctx: Any, signal_name: str) -> bool:
    try:
        signal = getattr(ctx, signal_name)
    except Exception:
        _LOGGER.debug("Failed to read FiftyOne cancellation signal", exc_info=True)
        return False

    if callable(signal):
        try:
            signal = signal()
        except Exception:
            _LOGGER.debug("Failed to call FiftyOne cancellation signal", exc_info=True)
            return False

    try:
        return bool(signal)
    except Exception:
        _LOGGER.debug("Failed to evaluate FiftyOne cancellation signal", exc_info=True)
        return False


__all__ = [
    "CancellationChecker",
    "FiftyOneCancellationChecker",
    "NoOpCancellationChecker",
]
