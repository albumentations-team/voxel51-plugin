# Install from release artifacts

The App-ready artifact is `albumentationsx-fiftyone-plugin-v<version>.zip`.
It contains the plugin manifest, entrypoint, runtime package, requirements, and
user documentation. The wheel and source distribution install the Python package;
use the plugin ZIP or FiftyOne download command to register the App integration.

The release also supplies installation notes, a dependency-specific capability
report, and `SHA256SUMS`. Choose an existing published release; a candidate
version in this branch does not mean that its release assets are available.

## Install from release ZIP

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
RELEASE_TAG="<release-tag>"
ARTIFACT_VERSION="${RELEASE_TAG#v}"
ARCHIVE="albumentationsx-fiftyone-plugin-v${ARTIFACT_VERSION}.zip"
curl -fLO "https://github.com/albumentations-team/voxel51-plugin/releases/download/${RELEASE_TAG}/${ARCHIVE}"
curl -fLO "https://github.com/albumentations-team/voxel51-plugin/releases/download/${RELEASE_TAG}/SHA256SUMS"
shasum -a 256 --check SHA256SUMS --ignore-missing

PLUGIN_ROOT="${FIFTYONE_PLUGINS_DIR:-$HOME/fiftyone/__plugins__}"
PLUGIN_DIR="$PLUGIN_ROOT/albumentationsx"
mkdir -p "$PLUGIN_DIR"
unzip -q "$ARCHIVE" -d "$PLUGIN_DIR"
fiftyone plugins requirements @albumentations/albumentationsx --install
fiftyone plugins list --enabled --names-only
```

The final command should list `@albumentations/albumentationsx`.

Restart FiftyOne after installation and check that **augment**, **pipelines**,
and **history** are available. Avoid enabling another copy of the plugin at the
same time. For the first preview, follow the
[integration quickstart](albumentationsx-fiftyone-integration.md#quickstart).

Bare and `v`-prefixed release tags use the same normalized artifact version in
filenames. Download URLs must retain the exact published tag.
