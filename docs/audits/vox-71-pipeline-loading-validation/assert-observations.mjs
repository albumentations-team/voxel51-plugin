// Validate captured browser DOM values and independently checked output files.
// Capture the scenarios in README.md in FiftyOne before running this script.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const observations = JSON.parse(await readFile(new URL('./browser-observations.json', import.meta.url)));
const byScenario = new Map(observations.map((value) => [value.scenario, value]));
const observation = (name) => {
  assert.ok(byScenario.has(name), `Missing browser scenario: ${name}`);
  return byScenario.get(name);
};
const checked = (state, label) => state.checks.find((field) => field.label === label)?.checked;

for (const name of ['saved-pipeline-loaded', 'run-history-loaded', 'isolated-draft-opened-from-run-viewer']) {
  const state = observation(name);
  assert.equal(state.numbers.at(-1), '1');
  assert.equal(checked(state, 'detections'), true);
  assert.equal(checked(state, 'segmentations'), true);
  assert.equal(checked(state, 'keypoints'), false);
  assert.equal(checked(state, 'Enabled'), true);
}
for (const name of ['saved-pipeline-p0-preview-result', 'run-history-p0-preview-result', 'isolated-run-viewer-p0-preview-result']) {
  assert.equal(observation(name).identicalSourceAndOutput, true, name);
}
assert.equal(observation('isolated-draft-source-selection-keeps-p0').numbers.at(-1), '0');
const reloaded = observation('run-history-after-explicit-reload');
assert.equal(reloaded.numbers.at(-1), '1');
assert.equal(checked(reloaded, 'Preview only'), true);
assert.deepEqual(observation('run-history-edited-stage-count-order-transform-p0').numbers, ['2', '1', '2', '0', '1', '0']);
const mapped = observation('isolated-cross-dataset-loaded');
for (const label of ['detections', 'renamed_masks', 'new_keypoints']) assert.equal(checked(mapped, label), false);
assert.ok(mapped.text.includes('type changed: detections → classification'));
assert.ok(mapped.text.includes('segmentations (missing or unsupported)'));
assert.equal(checked(observation('cross-dataset-manual-field-replacement'), 'renamed_masks'), true);
assert.equal(checked(observation('cross-dataset-manual-field-replacement'), 'new_keypoints'), false);
const outputs = JSON.parse(await readFile(new URL('./output-checks.json', import.meta.url)));
assert.equal(outputs.source_unchanged, true);
assert.ok(outputs.runs.length >= 2);
for (const run of outputs.runs) {
  assert.equal(run.pixels_identical, true);
  assert.equal(run.bbox_matches, true);
  assert.equal(run.keypoints_omitted, true);
  assert.deepEqual(run.errors, []);
  assert.equal(run.pipeline.seed, null);
  for (const transform of run.pipeline.transforms) assert.equal(transform.params.p, 0);
}
assert.ok(outputs.runs.some((run) => run.pipeline.transforms.map((transform) => transform.name).join(',') === 'VerticalFlip,HorizontalFlip'));
console.log(`Verified ${observations.length} browser observations and ${outputs.runs.length} materialized outputs.`);
