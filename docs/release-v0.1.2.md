# Release 0.1.2 candidate

This is a preparation record, not a publication or acceptance announcement.

- Preserve supported transform parameters through the editor, including padded crops and brightness options.
- Reuse prepared pipelines across outputs while validating each input image's dimensions.
- Query selected samples within the active view before converting them.
- Ship the runtime version in Python distributions and plugin ZIPs.
- Build ZIPs from an explicit file inventory and retain the exact release tag in install URLs.
- Remove historical audit dumps from the source distribution and replace Russian fixture text while preserving Unicode input support.
- Separate editor compilation, annotation codecs/geometry, form layout, and operator presentation responsibilities.

Use the [complete verification gate](verification.md) and [artifact process](release-artifacts.md).
Final App acceptance is tracked in VOX-77; automated or historical evidence alone
is insufficient to declare this candidate ready for publication.

## Resource limits

Selected-sample execution queries the selected subset before decoding it. Whole
view/dataset preparation still materializes and validates the complete scope
before output progress/cancellation checkpoints. Reference-image transforms load
the full source pool and prepare per-source reference lists and provenance. Those
lists grow quadratically; no large-dataset resource guarantee is made for this
candidate. Use small selected scopes for reference-image workflows until the
[bounded-resource follow-up](https://linear.app/albumentations/issue/VOX-80) defines
and verifies a resource policy and cancellable preflight.
