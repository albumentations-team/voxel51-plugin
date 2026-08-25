# FiftyOne operator debugging

Use this checklist when a FiftyOne App operator opens with an unexpected form,
fails during execution, or mutates the dataset without an immediate UI update.

## Local smoke checks

Run the plugin discovery smoke test first. It imports the plugin the same way
FiftyOne does and catches missing operator registrations or eager backend
imports:

```bash
uv run pytest tests/smoke/test_fiftyone_plugin_discovery.py
```

For operator form/output contracts, run the targeted unit tests:

```bash
uv run pytest \
  tests/unit/test_fiftyone_augment_operator.py \
  tests/unit/test_fiftyone_view_run_operator.py \
  tests/unit/test_fiftyone_delete_run_operator.py \
  tests/unit/test_fiftyone_manage_presets_operator.py
```

Before opening a PR, run the full local gate from
[Verification](verification.md).

## Debugging `Augment with AlbumentationsX`

When execution fails, the operator output should include structured diagnostic
fields instead of only a raw traceback:

- `errors_json`: normalized plugin errors with codes and context.
- `pipeline_config_json`: the parsed pipeline config, or why it could not be
  built.
- `operator_params_json`: the submitted FiftyOne operator params.

These fields are intentionally rendered as read-only JSON so a failing
pipeline can be copied into a unit test or used to reproduce the issue from a
local script.

## Debugging run and preset selectors

Run-key and preset selectors are dynamic. If a previously selected key was
deleted or became unavailable, the form should fall back to a currently
available key or show a read-only empty-state message.

The delete operator should not render the confirmation checkbox when there are
no deletable runs. This avoids asking the user to confirm an impossible action.

For tests that need isolated run or preset storage, pass `_storage_root` in
operator params and point it at a temporary directory.

## Debugging UI refresh actions

Dataset reload and generated-sample navigation are convenience actions after
successful mutation. Failures in those UI hooks must not fail the underlying
augmentation, cleanup, or inspection result.

The operators log these non-critical failures at debug level:

- dataset reload after augmentation;
- dataset reload after cleanup;
- generated-sample navigation from run inspection;
- preset storage listing during form rendering.

Use `caplog` in unit tests to verify that these failures remain traceable while
the user-facing operation still returns a useful result.
