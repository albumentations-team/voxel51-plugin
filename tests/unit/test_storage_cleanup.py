from __future__ import annotations

import pytest

from albumentationsx_plugin.core import MediaIOError
from albumentationsx_plugin.storage import delete_manifest_output_files


@pytest.mark.unit
def test_delete_manifest_output_files_deletes_only_listed_files_and_skips_missing(tmp_path) -> None:
    run_dir = tmp_path / "dataset" / "run"
    output_path = run_dir / "images" / "output.png"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"generated")

    result = delete_manifest_output_files(run_dir, ("images/output.png", "images/missing.png"))

    assert result.deleted_count == 1
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert result.errors == ()
    assert not output_path.exists()


@pytest.mark.unit
def test_delete_manifest_output_files_rejects_traversal_before_deleting_anything(tmp_path) -> None:
    run_dir = tmp_path / "dataset" / "run"
    output_path = run_dir / "images" / "output.png"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"generated")
    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(b"outside")

    with pytest.raises(MediaIOError) as error:
        delete_manifest_output_files(run_dir, ("images/output.png", "../outside.png"))

    assert error.value.context["reason"] == "unsafe_manifest_output_path"
    assert output_path.exists()
    assert outside_path.exists()


@pytest.mark.unit
def test_delete_manifest_output_files_reports_non_file_paths(tmp_path) -> None:
    run_dir = tmp_path / "dataset" / "run"
    directory_path = run_dir / "images" / "not-a-file"
    directory_path.mkdir(parents=True)

    result = delete_manifest_output_files(run_dir, ("images/not-a-file",))

    assert result.deleted_count == 0
    assert result.skipped_count == 0
    assert result.failed_count == 1
    assert result.errors[0]["reason"] == "not_a_file"
    assert directory_path.exists()
