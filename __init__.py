"""FiftyOne plugin entrypoint."""

import sys
from pathlib import Path
from typing import Protocol

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))


class PluginRegistrar(Protocol):
    """Subset of the FiftyOne plugin registration context used here."""

    def register(self, cls: type[object]) -> None:
        """Register an operator or panel class."""


def register(plugin: PluginRegistrar) -> None:
    """Register plugin operators and panels.

    This entrypoint intentionally stays small so import-time side effects do not
    grow with the implementation.
    """

    from albumentationsx_plugin.hosts.fiftyone.operators import (
        AugmentWithAlbumentationsX,
        DeleteAlbumentationsXRun,
        ShowAlbumentationsXCapabilities,
        ViewAlbumentationsXRun,
    )

    plugin.register(AugmentWithAlbumentationsX)
    plugin.register(ShowAlbumentationsXCapabilities)
    plugin.register(ViewAlbumentationsXRun)
    plugin.register(DeleteAlbumentationsXRun)
