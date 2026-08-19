from __future__ import annotations

import logging

import pytest

import albumentationsx_plugin.hosts.fiftyone.augmentation.executor as executor_module
from albumentationsx_plugin.hosts.fiftyone.progress import (
    AugmentationProgress,
    FiftyOneProgressReporter,
    NoOpProgressReporter,
)


def _progress(
    *,
    stage: str = "running",
    total_sources: int = 4,
    processed_sources: int = 2,
    planned_outputs: int = 8,
    created_outputs: int = 3,
    skipped_sources: int = 1,
    errors: int = 1,
    dry_run: bool = False,
) -> AugmentationProgress:
    return AugmentationProgress(
        stage=stage,
        total_sources=total_sources,
        processed_sources=processed_sources,
        planned_outputs=planned_outputs,
        created_outputs=created_outputs,
        skipped_sources=skipped_sources,
        errors=errors,
        dry_run=dry_run,
    )


@pytest.mark.unit
def test_augmentation_progress_exposes_fraction_and_counter_label() -> None:
    progress = _progress()

    assert progress.fraction == 0.5
    assert "processed sources 2/4" in progress.label
    assert "planned outputs 8" in progress.label
    assert "created outputs 3" in progress.label
    assert "skipped sources 1" in progress.label
    assert "errors 1" in progress.label


@pytest.mark.unit
def test_augmentation_progress_marks_empty_complete_runs_done() -> None:
    progress = _progress(stage="complete", total_sources=0, processed_sources=0)

    assert progress.fraction == 1.0


@pytest.mark.unit
def test_fiftyone_progress_reporter_uses_context_set_progress() -> None:
    calls: list[dict[str, object]] = []

    class Context:
        def set_progress(self, *, progress: float | None = None, label: str | None = None) -> None:
            calls.append({"progress": progress, "label": label})

    FiftyOneProgressReporter(Context()).report(_progress())

    assert calls == [{"progress": 0.5, "label": _progress().label}]


@pytest.mark.unit
def test_fiftyone_progress_reporter_falls_back_to_trigger() -> None:
    calls: list[dict[str, object]] = []

    class Context:
        def trigger(self, operator_name: str, *, params: dict[str, object]) -> None:
            calls.append({"operator_name": operator_name, "params": params})

    FiftyOneProgressReporter(Context()).report(_progress())

    assert calls == [
        {
            "operator_name": "set_progress",
            "params": {
                "progress": 0.5,
                "label": _progress().label,
                "variant": "linear",
            },
        }
    ]


@pytest.mark.unit
def test_progress_reporters_do_not_raise_when_reporting_fails() -> None:
    class Context:
        def set_progress(self, *, progress: float | None = None, label: str | None = None) -> None:
            raise RuntimeError("progress backend unavailable")

        def trigger(self, operator_name: str, *, params: dict[str, object]) -> None:
            raise RuntimeError("app executor unavailable")

    FiftyOneProgressReporter(Context()).report(_progress())
    NoOpProgressReporter().report(_progress())


@pytest.mark.unit
def test_executor_progress_reporting_logs_reporter_failures(caplog) -> None:
    class Reporter:
        def report(self, progress: AugmentationProgress) -> None:
            raise RuntimeError("progress reporter misconfigured")

    caplog.set_level(logging.DEBUG, logger=executor_module.__name__)

    executor_module._report_progress(
        Reporter(),
        stage="running",
        total_sources=2,
        processed_sources=1,
        planned_outputs=2,
        created_outputs=1,
        skipped_sources=0,
        errors=0,
    )

    assert "Error while reporting augmentation progress" in caplog.text
