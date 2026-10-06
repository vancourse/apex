// Every interactive element carries data-control="<screen>.<name>".
// scripts/gen-controls.mjs collects them into controls.json, and the walk
// (e2e/walk.mjs) clicks every one -- so a control without the attribute is a
// control nobody clicks.
const INTERACTIVE = new Set(["button", "a", "input", "select", "textarea"]);

export default {
  meta: {
    type: "problem",
    docs: { description: "interactive JSX elements must carry data-control" },
    messages: { missing: "<{{name}}> is interactive but has no data-control=\"<screen>.<name>\" attribute" },
    schema: [],
  },
  create(context) {
    return {
      JSXOpeningElement(node) {
        const name = node.name.type === "JSXIdentifier" ? node.name.name : null;
        const attrs = node.attributes.filter((a) => a.type === "JSXAttribute" && a.name.type === "JSXIdentifier");
        const has = (attr) => attrs.some((a) => a.name.name === attr);
        const interactive = (name !== null && INTERACTIVE.has(name)) || has("onClick");
        if (interactive && !has("data-control")) {
          context.report({ node, messageId: "missing", data: { name: name === null ? "element" : name } });
        }
      },
    };
  },
};
