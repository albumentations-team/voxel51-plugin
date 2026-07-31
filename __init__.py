"""FiftyOne plugin entrypoint."""

from typing import Protocol


class PluginRegistrar(Protocol):
    """Subset of the FiftyOne plugin registration context used here."""

    def register(self, cls: type[object]) -> None:
        """Register an operator or panel class."""


def register(plugin: PluginRegistrar) -> None:
    """Register plugin operators and panels.

    VOX-7 adds the first operator. This entrypoint intentionally stays small so
    import-time side effects do not grow with the implementation.
    """
