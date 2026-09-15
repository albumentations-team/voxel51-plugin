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
node --test tests/frontend/test_toolbar.cjs
```

For documentation-only changes, run pre-commit and check links. Run affected
behavior tests when examples or documented commands change.

## Targeted test groups

Run targeted tests when the changed area matches a pytest marker:

```bash
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m geometry
uv run pytest -m smoke
```

The smoke group covers local FiftyOne plugin discovery and headless user
scenarios over deterministic demo data: preview selected samples, materialize
outputs, inspect run summaries, reuse named presets and previous runs, process
current-view and whole-dataset scopes, clean up generated outputs, verify App
reload triggers, and confirm source samples/files remain unchanged.

## Release candidate checks

For release branches, run the complete local gate above and refresh the
capability report, then build the release artifacts:

```bash
uv run python scripts/report_transform_capabilities.py
uv run python scripts/smoke_supported_transforms.py
uv run python scripts/verify_release_tag.py <release-tag>
uv build
uv run python scripts/report_transform_capabilities.py --output dist/capability-report-<release-tag>.md
uv run python scripts/smoke_supported_transforms.py --output dist/transform-smoke-<release-tag>.md
uv run python scripts/build_release_artifacts.py --tag <release-tag>
```

`<release-tag>` may use either `0.1.2` or `v0.1.2`; it must match the versions
in `pyproject.toml`, `fiftyone.yml`, `albumentationsx_plugin/_version.py`, and
the root package entry in `uv.lock`. Python compatibility must also match. Attach or link the resulting capability snapshot,
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

## Headless User Scenario Smoke

Run this focused smoke group when a change touches operator behavior, presets,
run storage, cleanup, execution scope, preview output, or error UX:

```bash
uv run pytest tests/smoke/test_demo_operator_user_scenarios.py
```

These tests instantiate the same operator classes used by the FiftyOne App with
synthetic operator contexts. They do not replace manual visual checks, but they
catch regressions in the end-to-end parameter flow before opening the App.

## Annotation acceptance

Use this annotation-focused checklist when verifying supported label families. The automated
tests verify conversion and geometry, but this manual pass confirms that the
expanded label-family support is usable in the FiftyOne App.

1. Create a fresh demo dataset:

   ```bash
   uv run python scripts/create_demo_dataset.py create --overwrite
   uv run fiftyone app launch albumentationsx-demo
   ```

2. In the App, select at least one demo sample and run
   **Augment images**.
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
7. Run **Run history** for the new run key and confirm that the
   summary includes selected annotation fields, runtime target requirements,
   replay records, generated sample counts, and dropped annotation diagnostics.
8. Run **Augment images** again with a selected `Heatmap` field
   and a mixed geometry plus image-only color/intensity pipeline. Confirm the
   operator rejects the run before creating outputs.
9. Open **Run history → Review deletion of generated outputs**, inspect the preview,
   and confirm deletion. Confirm
   generated samples and plugin-owned output files are removed, while source
   samples, source images, and source annotation files remain unchanged.

Record the dataset name, transform names, created run key, cleanup result, and
any visual issues in the PR description or verification record.

## Demo Validation Dataset Suite

Use the validation suite when a change touches annotation-field validation,
media IO errors, crop parameter checks, or operator error UX.

1. Create the focused validation fixtures:

   ```bash
   uv run python scripts/create_demo_dataset.py create --suite validation --overwrite
   uv run fiftyone app launch albumentationsx-demo-validation
   ```

2. Filter by `validation_case` or matching tags in the App.
3. Confirm incompatible selected annotations fail before outputs are created.
4. Confirm media/file failures expose the relevant filepath or config context.
5. Delete the validation dataset and generated files:

   ```bash
   uv run python scripts/create_demo_dataset.py delete --suite validation --delete-files
   ```

Create all demo suites with `--suite all` when doing broader release checks.

## Supported Transform Smoke

Run this check before a public release or after dependency updates that affect
AlbumentationsX or `albu-spec`:

```bash
uv run python scripts/smoke_supported_transforms.py
```

The helper executes every transform exposed by the normal selector once against
a deterministic RGB image. It also provides deterministic reference-image
fixtures for the currently supported external-reference transforms. A clean run
must report `failed: 0` and `skipped: 0`.

Use `--transform` for a focused check while debugging one transform:

```bash
uv run python scripts/smoke_supported_transforms.py --transform RandomResizedCrop
```

## Release App acceptance

Use a fresh App session and the final candidate. Record the exact source commit,
plugin/dependency versions, OS/browser, dataset identity, commands, observed
results, and captures. Historical screenshots and headless contexts do not prove
the current App workflow.

1. Complete the standalone integration-guide quickstart in the installed-plugin
   environment, then preview, create, inspect history, and clean only its outputs.
2. Load a saved pipeline, change Probability from 1 to 0, and verify that the
   visible value controls preview and creation. Return through the continuation
   actions and verify draft parameters and annotations remain intact.
3. Check crop padding, multiple stages, current-view/dataset scope, advanced JSON
   validation, and incompatible heatmap pipelines. Known invalid source inputs
   must fail before materialization.
4. Save a new pipeline, update an explicitly selected ID, export/import full JSON,
   duplicate, and edit metadata. Verify that equal names do not silently overwrite.
5. Inspect completed/partial/failed/cancelled outcomes where reproducible; open
   outputs under active source filters; inspect cleanup scope and retained audits.
6. Run the annotation checklist above plus the small COCO acceptance scope in
   [Demo dataset](demo-dataset.md#coco-acceptance). Verify nonempty instance
   masks and actual person keypoints, including missing joints. Record fixed image
   IDs and any optional dependencies. Bbox-only imports do not establish mask or
   keypoint coverage.
7. Compare source-file hashes and source annotation values before and after
   execution and cleanup. Keep source datasets separate from acceptance outputs.
8. Review six current demo recordings and the rendered upstream page at desktop
   and narrow widths. Media must pass the repository asset policy.

Record local results and outstanding CI/publication work in
[Release preparation](release-preparation.md). Do not mark acceptance complete
for unexecuted scenarios or substitute the old 0.1.0 checklist.
