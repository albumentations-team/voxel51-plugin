# Project documentation

This directory contains project documentation that is expected to grow with the
plugin implementation. The root `README.md` remains the user-facing entrypoint;
these files hold development workflow, review, and release notes.

## Documents

- [Gitflow](gitflow.md): branch model and merge flow for MVP work.
- [Architecture](architecture.md): layered code boundaries and extension points.
- [Demo dataset](demo-dataset.md): deterministic local dataset workflow.
- [Fixed transform slice](fixed-transform-slice.md): executable
  catalog-backed transform choices and output behavior.
- [albu-spec catalog](albu-spec-catalog.md): version-aware transform capability
  registry and review report.
- [Parameter schema](parameter-schema.md): host-neutral parameter field
  generation from albu-spec metadata.
- [Dynamic FiftyOne forms](dynamic-fiftyone-forms.md): rendering catalog-backed
  transform schemas in the FiftyOne operator.
- [Pipeline factory](pipeline-factory.md): catalog-driven transform construction,
  image-only execution, and replay extraction.
- [Run manifest](run-manifest.md): saved run metadata, relative output paths,
  replay records, and FiftyOne custom run registration.
- [Run summary operator](run-summary-operator.md): read-only FiftyOne run
  inspection and stale manifest handling.
- [Run cleanup operator](run-cleanup-operator.md): confirmed cleanup for
  generated samples, manifest-listed files, and custom runs.
- [PR checklist](pr-checklist.md): required checks before review and merge.
- [Verification](verification.md): local gate, targeted tests, and manual checks.
- [Design document](../DESIGN.md): implementation contract for the plugin.

## Documentation rules

- Keep user-facing setup and demo commands in the root `README.md`.
- Keep implementation workflow, review notes, and release process in `docs/`.
- Update documentation in the same pull request as behavior changes.
- Prefer short, reproducible command blocks over prose-only instructions.
