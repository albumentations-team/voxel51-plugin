# Gitflow

The project uses an integration-branch workflow. The first milestone is the MVP
release, but the same branch pattern applies to later releases.

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

## Branch sequence

```text
feature/* -> dev -> main -> release/vX.Y.Z -> main + dev
```

For the first MVP release, `vX.Y.Z` is `v0.1.0`.

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

Run the required checks from [Verification](verification.md) before opening a
pull request.

Push the branch and open a PR into `dev`:

```bash
git push -u origin feature/vox-issue-short-name
```

## Promote to main

When `dev` contains a coherent tested milestone, open a PR:

```text
dev -> main
```

Before merging, rerun the complete local gate from
[Verification](verification.md) and have a review agent compare the result with
`DESIGN.md`.

## Prepare a release

Create each release branch from updated `main`:

```bash
git checkout main
git pull --ff-only
git checkout -b release/vX.Y.Z
```

After release validation, merge back:

```text
release/vX.Y.Z -> main
release/vX.Y.Z -> dev
```

Tag the accepted release commit on `main` with an annotated tag:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

Examples:

- `release/v0.1.0` for the first MVP release;
- `release/v0.2.0` for the next feature release after new work has moved from
  `dev` to `main`;
- `release/v0.1.1` for a planned patch release prepared through the normal
  release process.

## Hotfixes

Use a hotfix branch for urgent fixes to the latest released version. Start from
`main` or from the release tag that needs the fix:

```bash
git checkout main
git pull --ff-only
git checkout -b hotfix/vX.Y.Z-short-description
```

After validation:

```text
hotfix/vX.Y.Z-short-description -> main
hotfix/vX.Y.Z-short-description -> dev
```

Tag the hotfix commit on `main` with the matching patch version, for example
`v0.1.1`.
