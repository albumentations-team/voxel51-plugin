"""Human-readable capability report helpers."""

from __future__ import annotations

from collections import Counter, defaultdict

from albumentationsx_plugin.albumentations_backend.catalog.classification import is_mvp_supported_status
from albumentationsx_plugin.albumentations_backend.catalog.provider import AlbuSpecCatalogProvider


def build_capability_report(provider: AlbuSpecCatalogProvider | None = None) -> str:
    """Return a compact text report for manual catalog review."""

    catalog = provider or AlbuSpecCatalogProvider()
    capabilities = catalog.list_transform_capabilities()
    status_counts = Counter(capability.status.value for capability in capabilities)
    supported_transform_names = [
        capability.name for capability in capabilities if is_mvp_supported_status(capability.status)
    ]
    names_by_status: dict[str, list[str]] = defaultdict(list)
    for capability in capabilities:
        names_by_status[capability.status.value].append(capability.name)

    version_key = (
        f"albumentationsx-{catalog.version_info['albumentationsx']}__albu-spec-{catalog.version_info['albu_spec']}"
    )
    lines = [
        "AlbumentationsX capability catalog",
        f"version key: {version_key}",
        f"total transforms: {len(capabilities)}",
        f"supported choices: {len(supported_transform_names)}",
        "",
        "Status counts:",
    ]
    for status_name, count in sorted(status_counts.items()):
        lines.append(f"- {status_name}: {count}")

    lines.extend(["", "Supported transform names:"])
    for name in supported_transform_names:
        lines.append(f"- {name}")

    lines.extend(["", "Excluded transform names by status:"])
    for status_name, names in sorted(names_by_status.items()):
        if status_name in {"supported", "supported_with_defaults"}:
            continue
        lines.append(f"- {status_name}: {', '.join(sorted(names))}")

    return "\n".join(lines)
