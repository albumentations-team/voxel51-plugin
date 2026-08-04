# Verification

Use this page as the single source of truth for local checks. Other documents
should link here instead of repeating command lists.

## Complete local gate

Run the complete gate before opening a pull request that includes Python code or
changes user-visible behavior:

```bash
uv sync --group dev
uv run pre-commit run --all-files
uv run pytest
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

## Manual App checks

For pull requests that change FiftyOne App behavior, record the manual scenario
in the PR description:

- dataset used;
- operator opened;
- input parameters;
- expected output samples or errors;
- whether source data remained unchanged;
- cleanup result, if cleanup behavior changed.
