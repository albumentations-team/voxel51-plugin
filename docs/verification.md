# Verification

Use this page as the single source of truth for local checks. Other documents
should link here instead of repeating command lists.

## Complete local gate

Run the complete gate before opening a pull request that includes Python code or
changes user-visible behavior:

```bash
uv sync --group dev
uv lock --check
uv run pre-commit run --all-files
uv run pytest --cov-fail-under=85
uv run pyrefly check
```

For early documentation-only pull requests before the Python package exists,
run `uv run pre-commit run --all-files` and record any test or type-check
commands that are not applicable yet.

## Targeted test groups

Run targeted tests when the changed area matches a pytest marker:

```bash
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m geometry
uv run pytest -m smoke
```

The smoke group covers local FiftyOne plugin discovery and the headless MVP demo
path: create demo data, augment one sample, inspect the run summary, clean up the
run, and verify source samples/files remain.

## Release candidate checks

For release branches, run the complete local gate above and refresh the
capability report, then build the release artifacts:

```bash
uv run python scripts/report_transform_capabilities.py
uv run python scripts/verify_release_tag.py <release-tag>
uv build
uv run python scripts/report_transform_capabilities.py --output dist/capability-report-<release-tag>.md
uv run python scripts/build_release_artifacts.py --tag <release-tag>
```

`<release-tag>` may use either `0.1.2` or `v0.1.2`; it must match the versions
in `pyproject.toml` and `fiftyone.yml`, and `uv.lock` must match the declared
Python compatibility. Attach or link the resulting capability snapshot,
install notes, and `SHA256SUMS` from the release notes. The historic
[Release v0.1.0](release-v0.1.0.md) records the first release's scope and
manual App checks. The reusable artifact process is documented in
[Release artifacts](release-artifacts.md).

## Manual App checks

For pull requests that change FiftyOne App behavior, record the manual scenario
in the PR description:

- dataset used;
- operator opened;
- input parameters;
- preview result, if preview behavior changed;
- expected output samples or errors;
- whether source data remained unchanged;
- cleanup result, if cleanup behavior changed.

## VOX-41 Annotation Acceptance

Use this checklist before closing VOX-41 or GitHub issue #40. The automated
tests verify conversion and geometry, but this manual pass confirms that the
expanded label-family support is usable in the FiftyOne App.

1. Create a fresh demo dataset:

   ```bash
   uv run python scripts/create_demo_dataset.py create --overwrite
   uv run fiftyone app launch albumentationsx-demo
   ```

2. In the App, select at least one demo sample and run
   **Augment with AlbumentationsX**.
3. Keep annotation fields enabled for `Classification`, `Detections`,
   `Keypoints`, `Polylines`, `Heatmap`, and `Segmentation`.
4. Run a non-dry geometry-only pipeline, for example `HorizontalFlip` with
   `p=1.0`.
5. Confirm generated samples appear after the automatic App refresh.
6. Confirm visual alignment:
   - detections move with the image;
   - detection instance masks stay attached to their boxes;
   - keypoints and polyline vertices move with the image;
   - heatmap values stay spatially aligned;
   - segmentation masks preserve discrete regions.
7. Run **View AlbumentationsX Run** for the new run key and confirm that the
   summary includes selected annotation fields, runtime target requirements,
   replay records, generated sample counts, and dropped annotation diagnostics.
8. Run **Augment with AlbumentationsX** again with a selected `Heatmap` field
   and a mixed geometry plus image-only color/intensity pipeline. Confirm the
   operator rejects the run before creating outputs.
9. Run **Delete AlbumentationsX Run** with confirmation checked. Confirm
   generated samples and plugin-owned output files are removed, while source
   samples, source images, and source annotation files remain unchanged.

Record the dataset name, transform names, created run key, cleanup result, and
any visual issues in the PR description or Linear comment.
