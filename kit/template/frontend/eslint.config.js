import tseslint from "typescript-eslint";
import local from "./eslint-rules/index.js";

// Local rules only: each one exists because a class of shipped defect did, and
// each has a planted fixture in eslint-rules/rules.test.js run through THIS config.
export default [
  { ignores: ["dist/**", "node_modules/**", "test-results/**"] },
  {
    files: ["**/*.{js,mjs,ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: { ecmaFeatures: { jsx: true }, sourceType: "module" },
    },
    plugins: { local },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: { "local/no-raw-fetch": "error", "local/figure-only": "error" },
  },
  {
    files: ["src/**/*.tsx"],
    ignores: ["src/**/*.test.tsx"],
    rules: { "local/require-data-control": "error" },
  },
  {
    files: ["src/screens/**/*.{ts,tsx}"],
    rules: { "local/no-nullish-default": "error" },
  },
  {
    files: ["src/lib/client.ts", "src/gen/**"],
    rules: { "local/no-raw-fetch": "off" },
  },
  {
    files: ["src/lib/figure.tsx"],
    rules: { "local/figure-only": "off" },
  },
];
