from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_NAME = "@albumentations/albumentationsx"
EXPECTED_OPERATOR_URIS = {
    f"{PLUGIN_NAME}/augment_with_albumentationsx",
    f"{PLUGIN_NAME}/view_albumentationsx_run",
    f"{PLUGIN_NAME}/delete_albumentationsx_run",
}


@pytest.mark.smoke
def test_fiftyone_discovers_local_plugin_from_plugins_dir() -> None:
    env = os.environ.copy()
    env["FIFTYONE_PLUGINS_DIR"] = str(ROOT)
    env["PYTHONPATH"] = _prepend_pythonpath(ROOT, env.get("PYTHONPATH"))

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json
import fiftyone.operators as foo
import fiftyone.plugins as fop

print(json.dumps({
    "plugins": sorted(plugin.name for plugin in fop.list_plugins(enabled=True, builtin=False)),
    "operators": sorted(operator.uri for operator in foo.list_operators(enabled=True, builtin=False)),
}))
""",
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert PLUGIN_NAME in payload["plugins"]
    assert EXPECTED_OPERATOR_URIS.issubset(set(payload["operators"]))


def _prepend_pythonpath(path: Path, current_pythonpath: str | None) -> str:
    if not current_pythonpath:
        return str(path)
    return os.pathsep.join((str(path), current_pythonpath))
