from __future__ import annotations

import pytest

from albumentationsx_plugin.hosts.fiftyone.form_params import (
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
