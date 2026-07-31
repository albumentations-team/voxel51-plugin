from __future__ import annotations

import uuid

import fiftyone as fo
import pytest

from scripts.create_demo_dataset import (
    DEMO_SAMPLES,
    create_demo_dataset,
    delete_demo_dataset,
    describe_demo_dataset,
)


@pytest.mark.integration
def test_create_list_and_delete_demo_dataset(tmp_path) -> None:
    dataset_name = f"albumentationsx-demo-test-{uuid.uuid4().hex}"
    data_root = tmp_path / "demo-data"

    try:
        created = create_demo_dataset(dataset_name=dataset_name, data_root=data_root)
        listed = describe_demo_dataset(dataset_name=dataset_name, data_root=data_root)

        assert created.exists is True
        assert created.sample_count == len(DEMO_SAMPLES)
        assert created.image_count == len(DEMO_SAMPLES)
        assert listed == created

        dataset = fo.load_dataset(dataset_name)
        samples_by_demo_id: dict[str, fo.Sample] = {}
        for sample in dataset:
            demo_id = sample.get_field("demo_id")
            assert isinstance(demo_id, str)
            samples_by_demo_id[demo_id] = sample

        assert dataset.persistent is True
        assert sorted(samples_by_demo_id) == [spec.demo_id for spec in DEMO_SAMPLES]
        for spec in DEMO_SAMPLES:
            sample = samples_by_demo_id[spec.demo_id]
            assert "albumentationsx-demo" in sample.tags
            assert sample.metadata.width == spec.width
            assert sample.metadata.height == spec.height

        deleted = delete_demo_dataset(dataset_name=dataset_name, data_root=data_root, delete_files=True)

        assert deleted.exists is True
        assert dataset_name not in fo.list_datasets()
        assert not data_root.exists()
    finally:
        if dataset_name in fo.list_datasets():
            fo.delete_dataset(dataset_name)
