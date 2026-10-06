// controls.json from the data-control attributes in src/**/*.tsx.
//
//   node scripts/gen-controls.mjs           write controls.json
//   node scripts/gen-controls.mjs --check   write nothing; exit 1 when stale
//
// Either way, exit 1 when controls.json would not contain every id in
// elements.json -- the screen of record's element list, written when the screen
// was specified. A control the design names but the code never rendered fails
// here, before the walk.
import { readdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
const ATTRIBUTE = /data-control="([a-z0-9_]+\.[a-z0-9_.]+)"/g;

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

/** [{screen, id}] for every data-control under src/screens/<screen>/. */
export function scanControls(root = FRONTEND) {
  const found = new Map();
  for (const path of walk(join(root, "src"))) {
    if (!path.endsWith(".tsx") || path.endsWith(".test.tsx")) continue;
    const parts = relative(join(root, "src"), path).split(sep);
    if (parts[0] !== "screens" || parts.length < 3) continue;
    const screen = parts[1];
    for (const match of readFileSync(path, "utf8").matchAll(ATTRIBUTE)) {
      found.set(match[1], { screen, id: match[1] });
    }
  }
  return [...found.values()].sort((a, b) => a.id.localeCompare(b.id));
}

/** Ids elements.json names that the code does not render. */
export function missingElements(controls, elements) {
  const have = new Set(controls.map((c) => `${c.screen}/${c.id}`));
  return elements.filter((e) => !have.has(`${e.screen}/${e.id}`));
}

export function render(controls) {
  return JSON.stringify(controls, null, 2) + "\n";
}

function main(argv) {
  const check = argv.includes("--check");
  const controls = scanControls();
  const elementsPath = join(FRONTEND, "elements.json");
  const elements = existsSync(elementsPath) ? JSON.parse(readFileSync(elementsPath, "utf8")) : [];
  const missing = missingElements(controls, elements);
  let failed = false;
  if (missing.length) {
    for (const e of missing) console.error(`elements.json names ${e.screen}/${e.id}, but no element carries data-control="${e.id}"`);
    failed = true;
  }
  const target = join(FRONTEND, "controls.json");
  const text = render(controls);
  const current = existsSync(target) ? readFileSync(target, "utf8").replace(/\r\n/g, "\n") : null;
  if (check) {
    if (current !== text) {
      console.error("stale: frontend/controls.json (run scripts/gen.py controls)");
      failed = true;
    }
  } else if (current !== text) {
    writeFileSync(target, text);
    console.log("wrote frontend/controls.json");
  }
  return failed ? 1 : 0;
}

const invoked = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : "";
if (invoked.toLowerCase() === import.meta.url.toLowerCase()) {
  process.exit(main(process.argv.slice(2)));
}
