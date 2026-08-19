# Project documentation

This directory contains project documentation that is expected to grow with the
plugin implementation. The root `README.md` remains the user-facing entrypoint;
these files hold development workflow, review, and release notes.

## Documents

- [Design and roadmap](../DESIGN.md): current MVP boundary, durable design
  decisions, completed work, and the remaining plan.
- [Gitflow](gitflow.md): branch model and merge flow for MVP work.
- [Architecture](architecture.md): layered code boundaries and extension points.
- [Demo dataset](demo-dataset.md): deterministic local dataset workflow.
- [Fixed transform slice](fixed-transform-slice.md): executable
  catalog-backed transform choices and output behavior.
- [Annotation-aware execution](annotation-aware-execution.md): supported
  FiftyOne label conversion through Albumentations targets.
- [Augmentation preview](augmentation-preview.md): non-persistent selected-sample
  preview path and verification checklist.
- [Cancellation semantics](cancellation.md): interrupted-run checkpointing,
  retained partial outputs, and cleanup guarantees.
- [albu-spec catalog](albu-spec-catalog.md): version-aware transform capability
  registry and review report.
- [Capability browser](capability-browser.md): read-only FiftyOne operator for
  searching and filtering transform support metadata.
- [albu-spec integration audit](albu-spec-integration-audit.md): integration
  contract, upstream escalation policy, and current metadata findings.
- [Parameter schema](parameter-schema.md): host-neutral parameter field
  generation from albu-spec metadata.
- [Dynamic FiftyOne forms](dynamic-fiftyone-forms.md): rendering catalog-backed
  transform schemas in the FiftyOne operator.
- [Pipeline factory](pipeline-factory.md): catalog-driven transform construction,
  optional target execution, and replay extraction.
- [Run manifest](run-manifest.md): saved run metadata, relative output paths,
  replay records, and FiftyOne custom run registration.
- [Run summary operator](run-summary-operator.md): read-only FiftyOne run
  inspection and stale manifest handling.
- [Run cleanup operator](run-cleanup-operator.md): confirmed cleanup for
  generated samples, manifest-listed files, and custom runs.
- [Release v0.1.0](release-v0.1.0.md): historic first-release scope,
  verification checklist, known limitations, and tag flow.
- [Release artifacts](release-artifacts.md): checksummed GitHub Release
  artifact build, publication, and install flow.
- [Capability report v0.1.0](capability-report-v0.1.0.md): final albu-spec
  transform capability snapshot for the first public release.
- [PR checklist](pr-checklist.md): required checks before review and merge.
- [Verification](verification.md): local gate, targeted tests, and manual checks.

## Documentation rules

- Keep user-facing setup and demo commands in the root `README.md`.
- Keep implementation workflow, review notes, and release process in `docs/`.
- Update documentation in the same pull request as behavior changes.
- Prefer short, reproducible command blocks over prose-only instructions.
