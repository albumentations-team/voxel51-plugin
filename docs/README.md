# Documentation

## User guide

Start with the [integration guide](albumentationsx-fiftyone-integration.md).
It covers installation, a first preview on your dataset, the three App actions,
supported annotations, execution, error recovery, and migration from the older
community plugin. A standalone dataset example is available when needed.

Detailed references:

- [Pipeline loading, saving, import, and management](pipeline-presets.md)
- [Preview behavior and display](augmentation-preview.md)
- [Annotation support and output metadata](annotation-aware-execution.md)
- [Navigation and operator compatibility](plugin-navigation.md)
- [Dataset compatibility](dataset-compatibility-report.md)
- [Transform capabilities](capability-browser.md)
- [Reference-image inputs and resource limits](external-data-transforms.md)
- [Run history](run-summary-operator.md), [cleanup](run-cleanup-operator.md),
  and [cancellation](cancellation.md)
- [Release ZIP installation](release-artifacts.md)

## Contributors

Contributor files are maintained in the
[repository docs directory](https://github.com/albumentations-team/voxel51-plugin/tree/2f8aa79c4acad7d5efa41e8554161b15828ec9ee/docs).
Use a checkout of the release tag for release-specific source and commands.

- `architecture.md`: implementation ownership and dependency boundaries
- `dynamic-fiftyone-forms.md` and `operator-api.md`: forms and Python callers
- `albu-spec-catalog.md`, `parameter-schema.md`, `pipeline-factory.md`: backend contracts
- `run-manifest.md`: persisted run format
- `demo-dataset.md`: generated annotation/validation suites
- `recording-guide.md`: COCO video/GIF storyboards, editing, and updates to both draft PRs
- `verification.md`: canonical checks and fresh App acceptance
- `gitflow.md`, `pr-checklist.md`: contribution and release workflow
- `fiftyone-integration.rst`: maintained source for the upstream integration page
- `release-v0.1.2.md`: current candidate release notes
- `release-preparation.md`: file disposition, evidence, and publication handoff

The original `release-v0.1.0.md` and `capability-report-v0.1.0.md` are historical
records. They are not current installation instructions or release gates.
