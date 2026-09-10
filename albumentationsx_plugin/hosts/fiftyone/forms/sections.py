"""Keyboard-accessible sections supported by the FiftyOne 1.19 App."""

from __future__ import annotations

import fiftyone.operators.types as types


def add_collapsible_section(
    parent: types.Object, name: str, label: str, fields: types.Object, *, expanded: bool = False
) -> None:
    """Use native details/summary elements while keeping form controls mounted.

    ObjectView's collapsible option is absent from the released 1.19 frontend.
    GridView's public component props support native elements without custom JS.
    """
    section = types.Object()
    section.view(
        "_section_heading",
        types.Header(label=label, componentsProps={"item": {"component": "summary", "sx": {"cursor": "pointer"}}}),
    )
    for field_name, prop in fields.properties.items():
        section.add_property(field_name, prop)
    parent.define_property(
        name,
        section,
        view=types.GridView(
            componentsProps={
                "grid": {
                    "component": "details",
                    "open": expanded,
                    "sx": {"display": "block", "& > :not(summary)": {"mt": 2}},
                }
            }
        ),
    )
