import assert from 'node:assert/strict';
import fs from 'node:fs';

const read = (name) => JSON.parse(fs.readFileSync(new URL(name, import.meta.url), 'utf8'));
const observations = read('browser-observations.json');
const configured = observations.find((item) => item.scenario === 'final-configured-two-stages');
assert.deepEqual(configured.inputs.filter((item) => item.type === 'number').map((item) => item.value), ['2', '2', '2', '1', '1', '0']);
assert.deepEqual(configured.inputs.filter((item) => item.type === 'checkbox').map((item) => item.checked), [true, true, true, true, false]);
const preview = observations.find((item) => item.scenario === 'preview-result-comparison-first');
assert.ok(preview.text.startsWith('Preview 1 annotated comparison'));
assert.ok(preview.text.indexOf('Back to editor') < preview.text.indexOf('Result details'));
assert.equal(preview.sections.find((item) => item.label === 'Result details').open, false);
assert.equal(preview.images.filter((item) => item.alt.includes('comparison')).length, 1);
const outputs = read('output-checks.json');
assert.equal(outputs.created_count, 2);
assert.equal(outputs.source_unchanged, true);
assert.equal(outputs.final_browser_continuation_verified, false);
assert.equal(outputs.checks.length, 2);
for (const output of outputs.checks) {
  assert.equal(output.pixels_match_config, true);
  assert.equal(output.bounding_boxes_match, true);
  assert.equal(output.excluded_keypoints_omitted, true);
}
console.log('Recorded browser layout/configuration and two Python-operator outputs verified. Final browser continuation remains pending.');
