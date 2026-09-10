# Release Artifacts

VOX-45 adds a repeatable release artifact path for public tags. A release tag
should publish these files as GitHub Release assets:

- `fiftyone_albumentationsx_plugin-<version>-py3-none-any.whl`
- `fiftyone_albumentationsx_plugin-<version>.tar.gz`
- `albumentationsx-fiftyone-plugin-v<version>.zip`
- `albumentationsx-fiftyone-plugin-v<version>-install.md`
- `capability-report-v<version>.md`
- `SHA256SUMS`

The wheel and source distribution prove that the reusable Python package can be
built. The FiftyOne plugin zip is the App-ready artifact: it contains
`fiftyone.yml`, the root plugin entrypoint, runtime requirements, docs, sample
data notes, and the `albumentationsx_plugin` package.

## Build Locally

Run from a clean release branch or tag checkout:

```bash
uv sync --group dev
uv lock --check
uv run python scripts/verify_release_tag.py <release-tag>
uv build
uv run python scripts/report_transform_capabilities.py --output dist/capability-report-<release-tag>.md
uv run python scripts/build_release_artifacts.py --tag <release-tag>
```

`scripts/verify_release_tag.py` accepts both `0.1.2` and `v0.1.2`. The tag must
match `pyproject.toml`, `fiftyone.yml`, and `uv.lock` Python compatibility.

## Install From Release Zip

Prefer the normal FiftyOne GitHub download command for published tags:

```bash
python -m pip install "fiftyone>=1.19,<2"
fiftyone plugins download albumentations-team/voxel51-plugin/<release-tag>
fiftyone plugins requirements @albumentations/albumentationsx --install
```

If a workflow needs the attached zip artifact instead, download the zip and
`SHA256SUMS`, verify the checksum, and unpack into the configured FiftyOne
plugin directory:

```bash
curl -LO https://github.com/albumentations-team/voxel51-plugin/releases/download/<release-tag>/albumentationsx-fiftyone-plugin-<release-tag>.zip
curl -LO https://github.com/albumentations-team/voxel51-plugin/releases/download/<release-tag>/SHA256SUMS
shasum -a 256 --check SHA256SUMS --ignore-missing

PLUGIN_ROOT="${FIFTYONE_PLUGINS_DIR:-$HOME/fiftyone/__plugins__}"
PLUGIN_DIR="$PLUGIN_ROOT/albumentationsx"
mkdir -p "$PLUGIN_DIR"
unzip -q "albumentationsx-fiftyone-plugin-<release-tag>.zip" -d "$PLUGIN_DIR"
fiftyone plugins requirements @albumentations/albumentationsx --install
fiftyone plugins list --enabled --names-only
```

The final command should list `@albumentations/albumentationsx`.

## Release CI

The release workflow verifies every Python version claimed by `pyproject.toml`
across Linux, macOS, and Windows before publishing artifacts. The publishing job
then builds wheel, sdist, plugin zip, install notes, a capability report, and a
checksum manifest, and uploads them to the GitHub Release for the tag.

Manual FiftyOne App validation remains a release gate because CI cannot fully
prove the browser App interaction path.

## Distribution inventory

`scripts/plugin-files.txt` is the reviewed list of ZIP inputs. Add every new
runtime module or intended documentation asset to that list. The builder fails
if any listed file is absent or is a symlink. Files created locally under package,
documentation or sample-data directories cannot enter the archive implicitly.
Historical audits, generated demo images, caches and the upstream RST draft are
excluded. `DESIGN.md` is included so bundled documentation links resolve.

Both bare and `v`-prefixed tags are accepted. Artifact filenames use the normalized
version; install URLs retain the exact publication tag. Update all four version
sources together: project metadata, FiftyOne manifest, runtime `_version.py`, and
the root package entry in `uv.lock`. Extracted ZIP tests run with Python site
packages disabled so installed development metadata cannot mask a missing version.
