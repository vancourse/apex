// `x ?? []`, `?? 0`, `?? ""`, `?? "ok"` in a screen turn a failed load into a
// plausible empty value, and the screen renders "nothing" instead of "failed".
// Screens read a Load<T> and switch on its kind (src/lib/load.ts).
export default {
  meta: {
    type: "problem",
    docs: { description: "forbid nullish-coalescing to an empty/default value in screens" },
    messages: {
      swallow:
        "`?? {{text}}` swallows a missing value; switch on the Load/Result kind and render the failed state instead",
    },
    schema: [],
  },
  create(context) {
    const source = context.sourceCode ?? context.getSourceCode();
    return {
      LogicalExpression(node) {
        if (node.operator !== "??") return;
        const right = node.right;
        const swallows =
          (right.type === "ArrayExpression" && right.elements.length === 0) ||
          (right.type === "ObjectExpression" && right.properties.length === 0) ||
          (right.type === "Literal" && (typeof right.value === "number" || typeof right.value === "string")) ||
          (right.type === "TemplateLiteral" && right.expressions.length === 0);
        if (swallows) context.report({ node, messageId: "swallow", data: { text: source.getText(right) } });
      },
    };
  },
};
