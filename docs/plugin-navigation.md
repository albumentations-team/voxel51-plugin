# AlbumentationsX navigation

The sample grid exposes three primary actions as compact Albumentations logo
buttons labeled **augment**, **pipelines**, and **history**, with fully named
tooltips. The operator picker and prompt headings also
include the AlbumentationsX name. Each has a separate, focused
workflow; compatibility and discovery remain in the editor, and cleanup starts
from a selected run. No custom frontend build is required.

| Entry | Workflow |
| --- | --- |
| **AlbumentationsX · Augment images** | Select scope, edit stages, search Transform names, filter by target, inspect inline compatibility, preview, create, or save a pipeline. |
| **AlbumentationsX · Saved pipelines** | Inspect reusable configurations; load an editable copy, import/export, rename, or delete a saved pipeline. |
| **AlbumentationsX · Run history** | Search executions by label/date/status/transform, inspect results, open generated or failed source samples, reuse a pipeline, and review cleanup. |

The shorter action names are used below. The logo is bundled locally from the
[official Albumentations mark](https://albumentations.ai/icon.svg), so rendering
does not require an external image request. It is also included in plugin zip
and Python wheel distributions. Toolbar buttons use a white version for contrast
against FiftyOne's orange action background; operator icons use the red mark.
A small bundled `ComponentView` renders each logo and word together using
FiftyOne's shared React and MUI. It opens the existing operator prompt and
preserves disabled states, keyboard activation and overflow-menu navigation.
On narrower grids, FiftyOne moves actions that do not fit into its **More items**
menu; their logos and captions stay visible there.

## First and repeat runs

1. Select source images and open **Augment images**. Choose a transform and its
   parameters. A target filter narrows available choices while keeping the
   current transform, even if it does not match the filter. Filtering never
   replaces a stage. Target metadata describes Albumentations capabilities;
   selected annotation compatibility is checked separately.
2. Expand **Compatibility details** without leaving the editor. Preview retains
   stage values, annotation selection, and source scope. Use **Back to editor**
   or **Review and create samples** from the preview result.
3. After immediate creation, the grid opens only the available generated samples
   from that run. Existing source filters are cleared. The result remains open
   with counts, errors, draft continuation and **View in history**. Delegated
   execution retains its result payload and does not change the active grid.
4. **View in history** preselects the exact run. **Use pipeline from this run**
   opens an editable snapshot with fresh randomness. It neither mutates the old
   run nor replays its outputs. Save that configuration in the editor when it
   should appear in **Saved pipelines**.
5. **Review deletion of generated outputs** opens the existing cleanup operator
   with the selected run fixed. It shows label, UTC date, existing/missing sample
   and file counts, the run directory, and expandable manifest-listed paths.
   Confirmation is bound to this run. Missing, invalid or unsafe manifests block
   the form. Cleanup preserves sources and the audit manifest; **Back to Run
   history** returns to the selected record, now marked cleaned.

## Existing API compatibility

The plugin still registers all six existing operator names in `fiftyone.yml`.
Only placement and App labels change; Python callers retain their URIs and flat
parameters. Compatibility, capability reporting, and deletion are unlisted in
the general operator picker but remain executable by URI.

The bundled script supplies three unlisted App launchers (`open_augment`,
`open_pipelines`, `open_history`) whose only action is opening the corresponding
Python prompt. This keeps the custom placement type intact in FiftyOne 1.19;
remote placement deserialization otherwise loses `ComponentView`. The component
also forwards the adaptive-menu identity to its host wrapper and keeps that
wrapper from shrinking to zero width.

All URIs below are relative to `@albumentations/albumentationsx/`:

| URI suffix | App entry |
| --- | --- |
| `augment_with_albumentationsx` | Augment images |
| `manage_albumentationsx_presets` | Saved pipelines |
| `view_albumentationsx_run` | Run history |
| `analyze_albumentationsx_dataset_compatibility` | Compatibility details in the editor; detailed report remains available via API |
| `show_albumentationsx_capabilities` | Search/filter/help in the stage selector; full catalog remains available via API |
| `delete_albumentationsx_run` | Cleanup preview from Run history |

Direct cleanup callers retain `run_key` plus `confirm_delete=True`. App history
uses a separate run-bound confirmation field. The additional check does not
change the manifest allowlist or deletion implementation.

The history listing reuses VOX-56, merged from `dev` at `8ce5e21`; editable loading
and result presentation reuse VOX-71–74. VOX-49 extends the existing Saved
pipelines entry with explicit create/update modes, portable JSON/file import,
and metadata editing; see [the saved pipeline workflow](pipeline-presets.md).
Discovery recommendations (VOX-58) remain a separate task.
