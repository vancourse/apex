// Money and counts are formatted in ONE place: <Figure> (src/lib/figure.tsx).
// An ad-hoc toFixed/toLocaleString/Intl.NumberFormat is a second definition of
// how a figure looks -- and of what it rounds to.
const METHODS = new Set(["toFixed", "toLocaleString", "toPrecision"]);

export default {
  meta: {
    type: "problem",
    docs: { description: "format numbers only through <Figure concept=...>" },
    messages: { adhoc: "`{{what}}` formats a figure ad hoc; render <Figure concept=\"...\" value={...} /> instead" },
    schema: [],
  },
  create(context) {
    function isIntlNumberFormat(callee) {
      return (
        callee.type === "MemberExpression" &&
        callee.object.type === "Identifier" &&
        callee.object.name === "Intl" &&
        callee.property.type === "Identifier" &&
        callee.property.name === "NumberFormat"
      );
    }
    return {
      CallExpression(node) {
        const callee = node.callee;
        if (callee.type === "MemberExpression" && callee.property.type === "Identifier" && METHODS.has(callee.property.name)) {
          context.report({ node, messageId: "adhoc", data: { what: `.${callee.property.name}()` } });
        } else if (isIntlNumberFormat(callee)) {
          context.report({ node, messageId: "adhoc", data: { what: "Intl.NumberFormat" } });
        }
      },
      NewExpression(node) {
        if (isIntlNumberFormat(node.callee)) {
          context.report({ node, messageId: "adhoc", data: { what: "new Intl.NumberFormat" } });
        }
      },
    };
  },
};
