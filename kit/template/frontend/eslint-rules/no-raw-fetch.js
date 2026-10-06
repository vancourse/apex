// HTTP goes through the generated client (src/gen/client.ts) over the one
// Transport (src/lib/client.ts), which maps every status to a LoadError. A raw
// fetch skips the timeout, the X-Member header and that mapping.
export default {
  meta: {
    type: "problem",
    docs: { description: "call fetch only from src/lib/client.ts" },
    messages: { raw: "raw fetch(): call the generated client (src/gen/client.ts) instead" },
    schema: [],
  },
  create(context) {
    return {
      CallExpression(node) {
        const callee = node.callee;
        const direct = callee.type === "Identifier" && callee.name === "fetch";
        const viaGlobal =
          callee.type === "MemberExpression" &&
          callee.object.type === "Identifier" &&
          ["window", "globalThis", "self"].includes(callee.object.name) &&
          callee.property.type === "Identifier" &&
          callee.property.name === "fetch";
        if (direct || viaGlobal) context.report({ node, messageId: "raw" });
      },
    };
  },
};
