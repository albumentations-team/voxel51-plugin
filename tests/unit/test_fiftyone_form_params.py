from __future__ import annotations

import pytest

from albumentationsx_plugin.hosts.fiftyone.form_params import (
    ANNOTATION_FIELD_GROUP_NAME,
    flatten_fiftyone_form_groups,
    flatten_stage_parameter_groups,
    stage_parameter_group_name,
)


@pytest.mark.unit
def test_stage_parameter_group_name_rejects_invalid_steps() -> None:
    assert stage_parameter_group_name(1) == "_stage_parameters_1"

    with pytest.raises(ValueError, match="at least 1"):
        stage_parameter_group_name(0)


@pytest.mark.unit
def test_flatten_stage_parameter_groups_preserves_execution_field_names() -> None:
    params = {
        "transform": "ElasticTransform",
        "p": 0.5,
        "_stage_parameters_1": {"alpha": 2.0, "p": 0.8},
        "_stage_parameters_2": {"step_2_height": 24, "step_2_width": 20},
    }

    assert flatten_stage_parameter_groups(params) == {
        "transform": "ElasticTransform",
        "alpha": 2.0,
        "p": 0.8,
        "step_2_height": 24,
        "step_2_width": 20,
    }


@pytest.mark.unit
def test_flatten_fiftyone_form_groups_preserves_annotation_checkbox_values() -> None:
    params = {
        "transform": "HorizontalFlip",
        stage_parameter_group_name(1): {"p": 0.8},
        ANNOTATION_FIELD_GROUP_NAME: {
            "annotation_field__ZGV0ZWN0aW9ucw": True,
            "annotation_field__aGVhdG1hcA": False,
        },
    }

    assert flatten_fiftyone_form_groups(params) == {
        "transform": "HorizontalFlip",
        "p": 0.8,
        "annotation_field__ZGV0ZWN0aW9ucw": True,
        "annotation_field__aGVhdG1hcA": False,
    }
