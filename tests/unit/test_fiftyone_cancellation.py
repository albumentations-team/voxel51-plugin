from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from albumentationsx_plugin.core import AugmentationCancelledError
from albumentationsx_plugin.hosts.fiftyone.cancellation import FiftyOneCancellationChecker, NoOpCancellationChecker


@pytest.mark.unit
def test_fiftyone_cancellation_checker_ignores_missing_signal() -> None:
    FiftyOneCancellationChecker(SimpleNamespace()).raise_if_cancelled()
    NoOpCancellationChecker().raise_if_cancelled()


@pytest.mark.unit
def test_fiftyone_cancellation_checker_raises_for_truthy_signal_attribute() -> None:
    with pytest.raises(AugmentationCancelledError) as error:
        FiftyOneCancellationChecker(SimpleNamespace(cancelled=True)).raise_if_cancelled()

    assert error.value.reason_code == "augmentation_cancelled"
    assert error.value.context["signal"] == "cancelled"


@pytest.mark.unit
def test_fiftyone_cancellation_checker_raises_for_truthy_signal_method() -> None:
    class Context:
        def is_cancelled(self) -> bool:
            return True

    with pytest.raises(AugmentationCancelledError) as error:
        FiftyOneCancellationChecker(Context()).raise_if_cancelled()

    assert error.value.context["reason"] == "host_cancellation_requested"
    assert error.value.context["host"] == "fiftyone"
    assert error.value.context["signal"] == "is_cancelled"


@pytest.mark.unit
def test_fiftyone_cancellation_checker_swallows_signal_errors(caplog) -> None:
    class Context:
        def is_cancelled(self) -> bool:
            raise RuntimeError("backend unavailable")

    caplog.set_level(logging.DEBUG, logger="albumentationsx_plugin.hosts.fiftyone.cancellation")

    FiftyOneCancellationChecker(Context()).raise_if_cancelled()
    assert "Failed to call FiftyOne cancellation signal" in caplog.text
