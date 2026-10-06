// @vitest-environment node
// Each local rule, fed a planted defect through the REAL eslint.config.js: proves
// the rule fires AND that the config wires it to the paths it is meant to guard
// (a rule defined but not wired catches nothing). The negative cases prove the
// scoping does not leak into the one file allowed to do the thing.
import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const eslint = new ESLint({ cwd: fileURLToPath(new URL("..", import.meta.url)) });

async function ruleIds(code, filePath) {
  const [result] = await eslint.lintText(code, { filePath });
  const fatal = result.messages.filter((m) => m.fatal);
  if (fatal.length) throw new Error(`fixture does not parse: ${fatal[0].message}`);
  return result.messages.map((m) => m.ruleId);
}

const SCREEN = "src/screens/planted/index.tsx";

const PLANTED = [
  ["local/no-nullish-default", SCREEN, "declare const xs: number[] | undefined;\nexport const v = xs ?? [];\n"],
  ["local/no-nullish-default", SCREEN, "declare const n: number | undefined;\nexport const v = n ?? 0;\n"],
  ["local/no-nullish-default", SCREEN, 'declare const s: string | undefined;\nexport const v = s ?? "";\n'],
  ["local/no-nullish-default", SCREEN, 'declare const s: string | undefined;\nexport const v = s ?? "ok";\n'],
  ["local/figure-only", SCREEN, "export const v = (1234.5).toFixed(2);\n"],
  ["local/figure-only", SCREEN, "export const v = (1234.5).toLocaleString();\n"],
  ["local/figure-only", SCREEN, 'export const f = new Intl.NumberFormat("en-US");\n'],
  ["local/require-data-control", SCREEN, "export const B = () => <button>Go</button>;\n"],
  ["local/require-data-control", SCREEN, "export const B = () => <div onClick={() => undefined}>Go</div>;\n"],
  ["local/require-data-control", SCREEN, 'export const B = () => <input value="" readOnly />;\n'],
  ["local/no-raw-fetch", SCREEN, 'export const r = fetch("/api/health");\n'],
  ["local/no-raw-fetch", "src/lib/load.ts", 'export const r = window.fetch("/api/health");\n'],
];

const ALLOWED = [
  ["local/no-nullish-default", "src/lib/elsewhere.ts", "declare const xs: number[] | undefined;\nexport const v = xs ?? [];\n"],
  ["local/figure-only", "src/lib/figure.tsx", "export const v = (1234.5).toFixed(2);\n"],
  ["local/require-data-control", SCREEN, 'export const B = () => <button data-control="planted.go">Go</button>;\n'],
  ["local/no-raw-fetch", "src/lib/client.ts", 'export const r = fetch("/api/health");\n'],
  ["local/no-raw-fetch", "src/gen/client.ts", 'export const r = fetch("/api/health");\n'],
];

describe("local eslint rules fire on planted defects", () => {
  it.each(PLANTED)("%s fires in %s", async (rule, file, code) => {
    expect(await ruleIds(code, file)).toContain(rule);
  });

  it.each(ALLOWED)("%s stays quiet where it is allowed (%s)", async (rule, file, code) => {
    expect(await ruleIds(code, file)).not.toContain(rule);
  });
});
