"""Print the albu-spec backed transform capability catalog."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from albumentationsx_plugin.albumentations_backend.catalog import (
        build_albu_spec_catalog_snapshot,
        build_capability_report,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report format. Defaults to text.",
    )
    parser.add_argument(
        "--include-capabilities",
        action="store_true",
        help="Include every capability entry in JSON output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the report to.",
    )
    args = parser.parse_args(argv)

    if args.format == "json":
        report = json.dumps(
            build_albu_spec_catalog_snapshot(include_capabilities=args.include_capabilities),
            indent=2,
            sort_keys=True,
        )
    else:
        report = build_capability_report()

    if args.output is None:
        print(report)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{report}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
