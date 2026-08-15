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
- expected output samples or errors;
- whether source data remained unchanged;
- cleanup result, if cleanup behavior changed.
