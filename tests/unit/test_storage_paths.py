from __future__ import annotations

from datetime import UTC, datetime

import pytest

from albumentationsx_plugin.storage.paths import build_dataset_run_dir, build_run_key, default_storage_root


@pytest.mark.unit
def test_build_run_key_is_readable_unique_and_safe() -> None:
    run_key = build_run_key(now=datetime(2026, 7, 31, 12, 30, 5, tzinfo=UTC), suffix="VOX 10 / first")

    assert run_key == "albumentationsx-20260731T123005Z-VOX-10-first"


@pytest.mark.unit
def test_default_storage_root_lives_under_fiftyone_home(tmp_path) -> None:
    assert default_storage_root(home=tmp_path) == tmp_path / ".fiftyone" / "albumentationsx-plugin"


@pytest.mark.unit
def test_dataset_run_dir_sanitizes_dataset_and_run_components(tmp_path) -> None:
    run_dir = build_dataset_run_dir(
        "dataset with / odd chars",
        "run:key",
        storage_root=tmp_path,
    )

    assert run_dir.parent.parent == tmp_path
    assert run_dir.parent.name.startswith("dataset-with-odd-chars-")
    assert len(run_dir.parent.name.rsplit("-", maxsplit=1)[-1]) == 10
    assert run_dir.name == "run-key"


@pytest.mark.unit
def test_dataset_run_dir_avoids_collisions_between_similar_dataset_names(tmp_path) -> None:
    slash_name = build_dataset_run_dir("dataset/a", "run-key", storage_root=tmp_path)
    space_name = build_dataset_run_dir("dataset a", "run-key", storage_root=tmp_path)

    assert slash_name.parent.name.startswith("dataset-a-")
    assert space_name.parent.name.startswith("dataset-a-")
    assert slash_name.parent != space_name.parent
