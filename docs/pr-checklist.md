# Pull request checklist

Use this checklist before handing a pull request to the project owner or a
review agent.

## Scope

- The PR maps to one Linear issue.
- The branch starts from the current `dev` branch.
- The diff does not include unrelated refactors or metadata churn.
- No code is copied from the previous community plugin.
- The root `__init__.py`, once created, stays limited to operator registration.

## Documentation

- Root `README.md` contains commands for user-visible behavior changed by the PR.
- `docs/` contains workflow, review, or release notes changed by the PR.
- `DESIGN.md` remains the implementation contract when documents disagree.

## Safety

- Source samples, source media files, and source annotations are not modified.
- Generated files are written only under plugin-owned run directories.
- Cleanup logic deletes only files listed in a saved manifest after path checks.
- User-facing errors explain what failed, where it failed, and what to do next.

## Checks

Run the complete local gate and relevant targeted tests from
[Verification](verification.md). Record skipped or not-yet-applicable checks in
the PR description.

## Manual verification

For PRs that change App behavior, record the manual scenario listed in
[Verification](verification.md#manual-app-checks).
