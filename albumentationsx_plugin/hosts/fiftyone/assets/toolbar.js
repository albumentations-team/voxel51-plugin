/* FiftyOne exposes its shared React, MUI and plugin APIs to plugin scripts.
 * This small script is shipped directly; no frontend build is needed. */
(function () {
  "use strict";

  const React = window.React;
  const { Button, Tooltip } = window.__mui__;
  const { useTheme } = window.__foc__;
  const { registerComponent, PluginComponentType, getAbsolutePluginPath } =
    window.__fop__;
  const { Operator, OperatorConfig, registerOperator, types, usePromptOperatorInput } =
    window.__foo__;
  const PLUGIN_NAME = "@albumentations/albumentationsx";
  const ICON = "albumentationsx_plugin/hosts/fiftyone/assets/albumentations-white.svg";

  function AlbumentationsToolbarAction(props) {
    const { operator, placement, execute, canExecute, adaptiveMenuItemProps } =
      props;
    const root = React.useRef(null);
    const itemId = adaptiveMenuItemProps?.["data-item-id"] || operator.uri;
    React.useLayoutEffect(() => {
      // ComponentPlacement's host wrapper does not forward the adaptive-menu
      // identity and can shrink to zero. Set these on this placement only.
      const wrapper = root.current?.parentElement;
      if (!wrapper) return;
      const previousId = wrapper.getAttribute("data-item-id");
      const previousFlex = wrapper.style.flex;
      wrapper.setAttribute("data-item-id", itemId);
      wrapper.style.flex = "0 0 auto";
      adaptiveMenuItemProps?.refresh?.();
      return () => {
        if (previousId === null) wrapper.removeAttribute("data-item-id");
        else wrapper.setAttribute("data-item-id", previousId);
        wrapper.style.flex = previousFlex;
      };
    }, [itemId]);
    const theme = useTheme();
    const options = placement.view.options;
    const label = placement.view.label;
    const datasetName = window.recoil.useRecoilValue(window.__fos__.datasetName);
    const mediaType = window.recoil.useRecoilValue(window.__fos__.mediaType);
    const disabled = !canExecute ||
      (options.requires_dataset && !datasetName) ||
      (options.requires_image && mediaType !== "image");
    const title = disabled && options.requires_image
      ? "Open an image dataset before running augmentation."
      : label;
    const icon = getAbsolutePluginPath(operator.pluginName, ICON);
    const activate = () => {
      if (disabled) return;
      adaptiveMenuItemProps?.closeOverflow?.();
      execute();
    };

    return React.createElement(
      Tooltip,
      { title, placement: "bottom" },
      React.createElement(
        "span",
        { ref: root, style: { display: "inline-flex" } },
        React.createElement(
          Button,
          {
            type: "button",
            "aria-label": label,
            disabled,
            onClick: activate,
            onKeyDown: (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                event.stopPropagation();
                activate();
              }
            },
            onMouseDown: (event) => event.stopPropagation(),
            sx: {
              minWidth: 0,
              height: 28,
              padding: "4px 7px",
              gap: "4px",
              borderRadius: "16px",
              backgroundColor: theme.primary.plainColor,
              color: theme.text.buttonHighlight,
              fontSize: "12px",
              fontWeight: 600,
              lineHeight: "20px",
              textTransform: "none",
              whiteSpace: "nowrap",
              "&:hover": { backgroundColor: theme.primary.plainColor, filter: "brightness(0.9)" },
              "&.Mui-focusVisible": { outline: `2px solid ${theme.text.primary}`, outlineOffset: "-2px" },
              "&.Mui-disabled": { backgroundColor: theme.background.button, color: theme.text.secondary, opacity: 0.6 },
            },
          },
          React.createElement("img", {
            src: icon,
            alt: "",
            width: 18,
            height: 18,
            style: { flexShrink: 0 },
          }),
          options.action_label,
        ),
      ),
    );
  }

  registerComponent({
    name: "AlbumentationsXToolbarAction",
    label: "AlbumentationsX toolbar action",
    component: AlbumentationsToolbarAction,
    type: PluginComponentType.Component,
  });

  // Create placements in JavaScript: FiftyOne 1.19 deserializes remote views
  // as base View objects, losing the ComponentView type required by the toolbar.
  function registerAction(caption, target, label, requiresDataset, requiresImage) {
    class ToolbarAction extends Operator {
      get config() {
        return new OperatorConfig({
          name: `open_${caption}`,
          label,
          unlisted: true,
          skipInput: true,
          skipOutput: true,
        });
      }

      resolvePlacement() {
        return new types.Placement(
          types.Places.SAMPLES_GRID_ACTIONS,
          new types.ComponentView("AlbumentationsXToolbarAction", {
            label,
            action_label: caption,
            requires_dataset: requiresDataset,
            requires_image: requiresImage,
            prompt: false,
          }),
        );
      }

      useHooks() {
        return { prompt: usePromptOperatorInput() };
      }

      execute(ctx) {
        ctx.hooks.prompt(`${PLUGIN_NAME}/${target}`);
      }
    }
    registerOperator(ToolbarAction, PLUGIN_NAME);
  }

  registerAction("augment", "augment_with_albumentationsx", "AlbumentationsX · Augment images", true, true);
  registerAction("pipelines", "manage_albumentationsx_presets", "AlbumentationsX · Saved pipelines", false, false);
  registerAction("history", "view_albumentationsx_run", "AlbumentationsX · Run history", true, false);
})();
