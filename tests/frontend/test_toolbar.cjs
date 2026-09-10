const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(
  path.join(__dirname, "../../albumentationsx_plugin/hosts/fiftyone/assets/toolbar.js"),
  "utf8",
);

function loadToolbar(datasetName = "images", mediaType = "image") {
  const operators = [];
  const prompts = [];
  let component;
  class Operator {
    constructor(pluginName) { this.pluginName = pluginName; }
    get uri() { return `${this.pluginName}/${this.config.name}`; }
  }
  class ComponentView {
    constructor(name, options) {
      this.name = "ComponentView";
      this.options = { ...options, component: name };
      this.label = options.label;
    }
  }
  const window = {
    React: {
      createElement: (type, props, ...children) => ({ type, props, children }),
      useRef: () => ({ current: null }),
      useLayoutEffect: () => {},
    },
    __mui__: { Button: "button", Tooltip: "tooltip" },
    __foc__: { useTheme: () => ({
      primary: { plainColor: "orange" },
      text: { primary: "black", secondary: "grey", buttonHighlight: "white" },
      background: { button: "grey" },
    }) },
    __fop__: {
      registerComponent: (definition) => { component = definition.component; },
      PluginComponentType: { Component: 3 },
      getAbsolutePluginPath: (_, asset) => `/proxy/plugins/albumentationsx/${asset}`,
    },
    __foo__: {
      Operator,
      OperatorConfig: class { constructor(options) { Object.assign(this, options); } },
      registerOperator: (Action, name) => operators.push(new Action(name)),
      usePromptOperatorInput: () => (uri) => prompts.push(uri),
      types: {
        ComponentView,
        Placement: class { constructor(place, view) { Object.assign(this, { place, view }); } },
        Places: { SAMPLES_GRID_ACTIONS: "samples-grid-actions" },
      },
    },
    __fos__: { datasetName: "datasetName", mediaType: "mediaType" },
    recoil: { useRecoilValue: (key) => ({ datasetName, mediaType })[key] },
  };
  vm.runInNewContext(source, { window });
  return { operators, prompts, component };
}

test("three typed placements open the existing Python prompts", () => {
  const { operators, prompts } = loadToolbar();
  assert.equal(operators.length, 3);
  assert.deepEqual(operators.map(op => op.resolvePlacement().view.options.action_label), ["augment", "pipelines", "history"]);
  for (const operator of operators) {
    assert.equal(operator.config.unlisted, true);
    assert.equal(operator.resolvePlacement().view.name, "ComponentView");
    assert.equal(operator.resolvePlacement().view.options.prompt, false);
    operator.execute({ hooks: operator.useHooks() });
  }
  assert.deepEqual(prompts, [
    "@albumentations/albumentationsx/augment_with_albumentationsx",
    "@albumentations/albumentationsx/manage_albumentationsx_presets",
    "@albumentations/albumentationsx/view_albumentationsx_run",
  ]);
});

for (const [dataset, media, expected] of [
  ["images", "image", [false, false, false]],
  ["videos", "video", [true, false, false]],
  [null, null, [true, false, true]],
]) {
  test(`button labels, icons and disabled actions for ${media || "no dataset"}`, () => {
    const { operators, component } = loadToolbar(dataset, media);
    operators.forEach((operator, index) => {
      const calls = [];
      const tree = component({
        operator,
        placement: operator.resolvePlacement(),
        canExecute: true,
        execute: () => calls.push("execute"),
        adaptiveMenuItemProps: { closeOverflow: () => calls.push("close") },
      });
      const button = tree.children[0].children[0];
      assert.equal(button.type, "button");
      assert.equal(button.props.disabled, expected[index]);
      assert.equal(button.props["aria-label"], operator.config.label);
      assert.equal(button.children[1], ["augment", "pipelines", "history"][index]);
      assert.match(button.children[0].props.src, /^\/proxy\/plugins\/albumentationsx\/.*\.svg$/);
      button.props.onClick();
      assert.deepEqual(calls, expected[index] ? [] : ["close", "execute"]);
    });
  });
}

test("operator permission disables the button even with an image dataset", () => {
  const { operators, component } = loadToolbar();
  const tree = component({ operator: operators[0], placement: operators[0].resolvePlacement(), canExecute: false });
  const button = tree.children[0].children[0];
  assert.equal(button.props.disabled, true);
  button.props.onClick();
});

test("Enter and Space activate without reaching the grid keyboard handlers", () => {
  const { operators, component } = loadToolbar();
  const calls = [];
  const tree = component({ operator: operators[0], placement: operators[0].resolvePlacement(), canExecute: true, execute: () => calls.push("execute") });
  const button = tree.children[0].children[0];
  for (const key of ["Enter", " "]) {
    button.props.onKeyDown({ key, preventDefault: () => calls.push("prevent"), stopPropagation: () => calls.push("stop") });
  }
  assert.deepEqual(calls, ["prevent", "stop", "execute", "prevent", "stop", "execute"]);
});
