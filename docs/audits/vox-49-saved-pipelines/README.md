# VOX-49: saved pipeline import, editing, and identity

Date: 2026-09-09. Branch: `feature/vox-49-preset-import-editing`, created from
`feature/vox-67-coco-ux-audit` at `a65830f` (includes VOX-75).

## Behavior verified

- New saves and duplicates allocate UUID-based IDs. Unicode, repeated names,
  case, punctuation, whitespace and 96-character-prefix collisions keep separate
  configurations. Load and update selectors include the ID.
- Updates require an explicit target and confirmation bound to that ID.
  Loading a draft never selects the replacement target. Changing targets cannot
  reuse another target's confirmation; returning to the editor clears it.
- Legacy slug filenames and references remain in place. Rename and metadata
  edits retain identity and creation time; new portable JSON imports retain the
  supplied ID without deriving it from the name. Schema version remains 1.
- Export presents an overview table and one **Importable pipeline JSON** field.
  Both pasted JSON and local UTF-8 JSON files use the same parser and executable
  pipeline validation. Import replacement still requires explicit overwrite.
- Missing, malformed, non-JSON, non-regular, oversized and unsafe import files,
  summary JSON, invalid schemas and unsupported pipelines return structured
  errors before a write. Failed and unconfirmed updates preserve file bytes.
- Atomic new-file publication prevents simultaneous writers from replacing
  each other. Confirmed replacement is atomic; simulated write failures keep
  the previous bytes and clean temporary files.

## FiftyOne App check

FiftyOne 1.19.0 / AlbumentationsX 2.3.8 / albu-spec 0.0.6, Chrome,
`http://localhost:5162`, temporary dataset `vox-49-pipeline-app` with one
deterministic 20×12 RGB source image. A temporary plugin entrypoint redirects
default preset storage to `/tmp/vox-49-validation/app-storage`; no personal
saved pipelines are used.

1. Seed **Поворот** (`HorizontalFlip(p=1)`) and **Яркость** (`p=0`). Confirm both
   names and distinct IDs appear in Saved pipelines and the replacement picker.
2. Use **Edit saved pipeline details** to set description `Проверка VOX-49` and
   add tag `обучение` with the native editable list. Submit and verify the
   named success result, overview table and full importable JSON. The initial
   display-only TagsView was replaced after this visual check exposed it.
3. Open **Augment images → Save pipeline → Update existing pipeline**. Enter
   a name, choose Поворот, and confirm replacement. Switch to Яркость: its
   checkbox is empty and Save pipeline is disabled. Cancel. Verify both file
   SHA-256 values are unchanged.
4. Paste `[{"key":"preset","path":"/tmp/preset.json"}]` into JSON import.
   Verify `summary_json_not_importable` and guidance to copy **Importable
   pipeline JSON**. Both original file hashes remain unchanged.
5. Choose **Local JSON file**, enter
   `/tmp/vox-49-validation/portable-app.json`, and submit. Verify the named
   success result for **Импорт из файла**, its retained `manual-file-import`
   ID, and three pipelines in the overview. Original pipelines remain intact.
6. Verify the source image pixels are unchanged and the dataset still contains
   one sample. Close the test tab and stop the temporary App; the launcher's
   cleanup removes its dataset. Preset fixtures and logs remain under `/tmp`.

The final file/pixel assertions are recorded in [app-check.json](app-check.json).
Actual save/update/export/import through real datasets, including a named
**Pipeline updated** result, is also covered by
`tests/integration/test_fiftyone_saved_pipeline_lifecycle.py`.

## Automated checks

- Full suite: **519 collected**, **516 passed** initially. Three existing tests
  still expected IDs derived from display names. Their assertions now load
  the returned ID and verify the preserved display name/configuration/path;
  all **3 passed** on rerun (`legacy-scenarios-final.log`). No implementation
  change was needed for those failures. The complete 17-minute suite was not
  repeated after these test-only corrections.
- Coverage: **90.95%**, exceeding the required 85%.
- Final lifecycle delta after App fixes: **41 passed**, including the
  real-dataset integration scenario and collision/import/storage regressions.
- Frontend toolbar navigation: **6 passed**.
- `uv sync --frozen --group dev` and `uv lock --check`: passed.
- `pre-commit run --all-files`, hooks over every changed/untracked file, and
  `pyrefly check`: passed.
- `git diff --check`: passed.

Logs remain in `/tmp/vox-49-validation/`: `full.log`, `delta.log`,
`legacy-scenarios-final.log`, `pre-commit.log`, `pre-commit-final.log`,
`frontend.log`, `app.log`, `app-final.log`.

Changes are uncommitted for review. Linear VOX-49 is In Progress.
