from __future__ import annotations

from datetime import datetime, timezone

import pytest

from albumentationsx_plugin.storage.paths import (
    MAX_RUN_LABEL_SLUG_LENGTH,
    build_dataset_run_dir,
    build_run_key,
    default_storage_root,
    slugify_run_label,
)


@pytest.mark.unit
def test_build_run_key_is_readable_unique_and_safe() -> None:
    run_key = build_run_key(now=datetime(2026, 7, 31, 12, 30, 5, tzinfo=timezone.utc), suffix="VOX 10 / first")

    assert run_key == "albumentationsx-20260731T123005Z-VOX-10-first"


@pytest.mark.unit
def test_build_run_key_prefixes_sanitized_user_label() -> None:
    run_key = build_run_key(
        now=datetime(2026, 7, 31, 12, 30, 5, tzinfo=timezone.utc),
        suffix="a1b2c3d4",
        run_label="Cats crop test",
    )

    assert run_key == "cats-crop-test-albumentationsx-20260731T123005Z-a1b2c3d4"


@pytest.mark.unit
def test_build_run_key_ignores_empty_or_invalid_user_label() -> None:
    run_key = build_run_key(
        now=datetime(2026, 7, 31, 12, 30, 5, tzinfo=timezone.utc),
        suffix="a1b2c3d4",
        run_label="!!!",
    )

    assert run_key == "albumentationsx-20260731T123005Z-a1b2c3d4"


@pytest.mark.unit
def test_slugify_run_label_sanitizes_unsafe_characters_and_bounds_length() -> None:
    long_label = "Cats / Crop Test!!! " + ("VeryLong " * 12)
    label_slug = slugify_run_label(long_label)

    assert label_slug.startswith("cats-crop-test-verylong")
    assert len(label_slug) <= MAX_RUN_LABEL_SLUG_LENGTH
    assert slugify_run_label(None) == ""
    assert slugify_run_label("") == ""
    assert slugify_run_label("!!!") == ""


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
