# Project documentation

This directory contains project documentation that is expected to grow with the
plugin implementation. The root `README.md` remains the user-facing entrypoint;
these files hold development workflow, review, and release notes.

## Documents

- [Gitflow](gitflow.md): branch model and merge flow for MVP work.
- [Architecture](architecture.md): layered code boundaries and extension points.
- [PR checklist](pr-checklist.md): required checks before review and merge.
- [Verification](verification.md): local gate, targeted tests, and manual checks.
- [Design document](../DESIGN.md): implementation contract for the plugin.

## Documentation rules

- Keep user-facing setup and demo commands in the root `README.md`.
- Keep implementation workflow, review notes, and release process in `docs/`.
- Update documentation in the same pull request as behavior changes.
- Prefer short, reproducible command blocks over prose-only instructions.
