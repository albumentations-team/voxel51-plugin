"""Build checksummed GitHub Release artifacts for the FiftyOne plugin."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify_release_tag import verify_release_tag

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "albumentations-team/voxel51-plugin"
PLUGIN_ARCHIVE_ROOTS = (
    "albumentationsx_plugin",
    "docs",
    "sample_data",
)
PLUGIN_ARCHIVE_FILES = (
    "__init__.py",
    "fiftyone.yml",
    "requirements.txt",
    "README.md",
    "LICENSE",
)
EXCLUDED_PARTS = frozenset(
    {
        "__pycache__",
        ".coverage",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "build",
        "dist",
        "htmlcov",
    }
)


@dataclass(frozen=True)
class ReleaseArtifacts:
    """Paths produced by the release artifact builder."""

    version: str
    plugin_zip: Path
    install_notes: Path
    checksums: Path
    checksummed_files: tuple[Path, ...]


def plugin_archive_name(version: str) -> str:
    """Return the FiftyOne plugin zip artifact name for *version*."""
    return f"albumentationsx-fiftyone-plugin-v{version}.zip"


def install_notes_name(version: str) -> str:
    """Return the install note artifact name for *version*."""
    return f"albumentationsx-fiftyone-plugin-v{version}-install.md"


def build_release_artifacts(
    tag: str,
    *,
    root: Path = ROOT,
    dist_dir: Path | None = None,
) -> ReleaseArtifacts:
    """Build the plugin zip, install notes, and SHA256SUMS file."""
    version = verify_release_tag(tag, root=root)
    output_dir = root / "dist" if dist_dir is None else dist_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    plugin_zip = output_dir / plugin_archive_name(version)
    _write_plugin_zip(plugin_zip, _iter_plugin_files(root), root=root)

    install_notes = output_dir / install_notes_name(version)
    install_notes.write_text(_build_install_notes(version), encoding="utf-8")

    checksums = output_dir / "SHA256SUMS"
    checksummed_files = _write_checksums(output_dir, checksums)

    return ReleaseArtifacts(
        version=version,
        plugin_zip=plugin_zip,
        install_notes=install_notes,
        checksums=checksums,
        checksummed_files=checksummed_files,
    )


def _iter_plugin_files(root: Path) -> Iterable[Path]:
    for relative_file in PLUGIN_ARCHIVE_FILES:
        path = root / relative_file
        if path.is_file():
            yield path

    for relative_root in PLUGIN_ARCHIVE_ROOTS:
        directory = root / relative_root
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not _is_excluded(path.relative_to(root)):
                yield path


def _is_excluded(relative_path: Path) -> bool:
    return relative_path.suffix == ".pyc" or any(part in EXCLUDED_PARTS for part in relative_path.parts)


def _write_plugin_zip(path: Path, files: Iterable[Path], *, root: Path) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, file_path.relative_to(root).as_posix())


def _build_install_notes(version: str) -> str:
    release_tag = f"v{version}"
    archive_name = plugin_archive_name(version)
    return f"""# AlbumentationsX for FiftyOne {release_tag} install artifact

Download the plugin zip and checksum manifest from the GitHub release:

```bash
curl -LO https://github.com/{REPOSITORY}/releases/download/{release_tag}/{archive_name}
curl -LO https://github.com/{REPOSITORY}/releases/download/{release_tag}/SHA256SUMS
shasum -a 256 --check SHA256SUMS --ignore-missing
```

Install the zip into the same Python environment and plugin directory used by
FiftyOne:

```bash
python -m pip install "fiftyone>=1.19,<2"
PLUGIN_ROOT="${{FIFTYONE_PLUGINS_DIR:-$HOME/fiftyone/__plugins__}}"
PLUGIN_DIR="$PLUGIN_ROOT/albumentationsx"
mkdir -p "$PLUGIN_DIR"
unzip -q {archive_name} -d "$PLUGIN_DIR"
fiftyone plugins requirements @albumentations/albumentationsx --install
fiftyone plugins list --enabled --names-only
```

The final command should list `@albumentations/albumentationsx`.
"""


def _write_checksums(dist_dir: Path, checksums_path: Path) -> tuple[Path, ...]:
    files = tuple(
        sorted(
            path
            for path in dist_dir.iterdir()
            if path.is_file()
            and path.name != checksums_path.name
            and not path.name.startswith(".")
            and not path.name.endswith(".tmp")
        )
    )
    lines = [f"{_sha256(path)}  {path.name}" for path in files]
    checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="release tag, with or without a leading 'v'")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist", help="directory that receives artifacts")
    args = parser.parse_args(argv)

    artifacts = build_release_artifacts(args.tag, dist_dir=args.dist_dir)
    print(f"Built {artifacts.plugin_zip}")
    print(f"Wrote {artifacts.install_notes}")
    print(f"Wrote {artifacts.checksums}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
