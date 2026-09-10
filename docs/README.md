# Project documentation

## User workflows

- [Installation and overview](../README.md)
- [Integration guide](albumentationsx-fiftyone-integration.md)
- [First run](first-run-onboarding.md) and [demo datasets](demo-dataset.md)
- [Navigation](plugin-navigation.md)
- [Pipeline loading, saving and management](pipeline-presets.md)
- [Preview](augmentation-preview.md) and [annotation-aware execution](annotation-aware-execution.md)
- [Dataset compatibility](dataset-compatibility-report.md) and [capability browser](capability-browser.md)
- [External-data transforms](external-data-transforms.md)
- [Run history](run-summary-operator.md), [cleanup](run-cleanup-operator.md), and [cancellation](cancellation.md)

## Contributor reference

- [Design and roadmap](../DESIGN.md)
- [Architecture and module ownership](architecture.md)
- [Catalog](albu-spec-catalog.md), [parameter schemas](parameter-schema.md), and [pipeline factory](pipeline-factory.md)
- [Dynamic forms](dynamic-fiftyone-forms.md) and [execution compatibility](fixed-transform-slice.md)
- [Manifest format](run-manifest.md)
- [Operator debugging](fiftyone-operator-debugging.md)
- [Verification](verification.md), [PR checklist](pr-checklist.md), and [Git workflow](gitflow.md)
- [Upstream integration draft](https://github.com/albumentations-team/voxel51-plugin/blob/dev/docs/voxel51-albumentationsx-integration-template.rst): contributor draft with placeholders, excluded from the plugin ZIP.

## Releases and historical reference

- [Artifact contents and release process](release-artifacts.md)
- [Release 0.1.2 changes](release-v0.1.2.md)
- [First-release notes](release-v0.1.0.md) and [versioned capability snapshot](capability-report-v0.1.0.md)
- [albu-spec integration assessment](albu-spec-integration-audit.md): dependency-specific reference, not a current release gate.

Historical App audit dumps and screenshots were removed from the current source
and release tree in VOX-79. They remain available in the
[reviewed source snapshot](https://github.com/albumentations-team/voxel51-plugin/tree/99b594bdcca16990f174d0bfa9f3a228f9f0a960/docs/audits).
The reusable preview DOM assertion is maintained in `tests/manual`; acceptance
requires a fresh App session and fresh captures for the release candidate.
