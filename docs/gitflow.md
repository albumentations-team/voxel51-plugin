# Gitflow

The project uses an integration-branch workflow for the MVP.

## Branch roles

`main`

Stable branch. Do not do direct feature work here. Merge into `main` only from
`dev`, `release/*`, or `hotfix/*` after checks and review.

`dev`

Integration branch for MVP implementation. Feature branches start from `dev`
and merge back into `dev` by pull request.

`feature/*`

Short-lived task branches. Each branch should map to one Linear issue and one
bounded pull request.

`release/*`

Release-preparation branch created from `main`. Use it only for release notes,
version updates, final documentation, capability reports, and final fixes found
during release validation.

`hotfix/*`

Urgent fix branch after a tagged release. Merge hotfixes back into both `main`
and `dev`.

## MVP branch sequence

```text
feature/* -> dev -> main -> release/v0.1.0 -> main + dev
```

## Start a task

```bash
git checkout dev
git pull --ff-only
git checkout -b feature/vox-issue-short-name
```

Examples:

```bash
git checkout -b feature/vox-6-plugin-metadata
git checkout -b feature/vox-7-empty-augment-operator
```

## Finish a task

Run the local gate before opening a pull request:

```bash
uv run pre-commit run --all-files
uv run pytest
uv run pyrefly check
```

Push the branch and open a PR into `dev`:

```bash
git push -u origin feature/vox-issue-short-name
```

## Promote to main

When `dev` contains a coherent tested milestone, open a PR:

```text
dev -> main
```

Before merging, rerun the complete local gate and have a review agent compare
the result with `DESIGN.md`.

## Prepare a release

Create the release branch from updated `main`:

```bash
git checkout main
git pull --ff-only
git checkout -b release/v0.1.0
```

After release validation, merge back:

```text
release/v0.1.0 -> main
release/v0.1.0 -> dev
```

Tag the accepted release commit on `main`:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Hotfixes

```bash
git checkout main
git pull --ff-only
git checkout -b hotfix/v0.1.1-short-description
```

After validation:

```text
hotfix/v0.1.1-short-description -> main
hotfix/v0.1.1-short-description -> dev
```
