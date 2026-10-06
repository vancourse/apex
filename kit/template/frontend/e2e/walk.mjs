// The planted walk (instrument `walk:planted`).
//
//   BASE_URL=http://127.0.0.1:8000 MEMBER_TOKEN=planted-aroha node e2e/walk.mjs
//
// For every screen in controls.json: open it as the planted member, wait for it
// to leave `loading`, click every control, reload, and require it to settle
// again. Any 5xx fails the walk. Then every line of acceptance.json is read off
// the rendered text. Text, never pixels. The LAST stdout line is the receipt:
//   {"steps":[{"step","pass"}],"instrument":"walk:planted"}
// Acceptance steps keep their ids; structural checks are steps named walk:<check>.
import { readFileSync } from "node:fs";
import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL;
const TOKEN = process.env.MEMBER_TOKEN;
if (!BASE_URL || !TOKEN) {
  console.error("walk: BASE_URL and MEMBER_TOKEN are required");
  process.exit(2);
}
const SETTLE_MS = 10_000;
const read = (name) => JSON.parse(readFileSync(new URL(`../${name}`, import.meta.url), "utf8"));
const controls = read("controls.json");
const acceptance = read("e2e/acceptance.json");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
const serverErrors = [];
page.on("response", (response) => {
  if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`);
});

async function settle() {
  try {
    await page.waitForFunction(
      () => {
        const el = document.querySelector("[data-state]");
        return el !== null && el.getAttribute("data-state") !== "loading";
      },
      null,
      { timeout: SETTLE_MS },
    );
  } catch {
    return { ok: false, state: "loading (stuck)" };
  }
  return { ok: true, state: await page.getAttribute("[data-state]", "data-state") };
}

async function open(screen) {
  await page.goto(`${BASE_URL}/?member=${encodeURIComponent(TOKEN)}&screen=${encodeURIComponent(screen)}`);
  return settle();
}

const steps = [];
function record(step, pass, detail) {
  steps.push({ step, pass });
  console.log(`${pass ? "ok  " : "FAIL"} ${step}${detail ? ` -- ${detail}` : ""}`);
}

for (const screen of [...new Set(controls.map((c) => c.screen))]) {
  const first = await open(screen);
  record(`walk:${screen}:settles`, first.ok && first.state !== "failed", `state=${first.state}`);
  for (const control of controls.filter((c) => c.screen === screen)) {
    const locator = page.locator(`[data-control="${control.id}"]`);
    if ((await locator.count()) === 0) {
      record(`walk:${control.id}`, false, `not rendered (state=${(await settle()).state})`);
      continue;
    }
    const before = serverErrors.length;
    await locator.first().click({ timeout: 5_000 });
    await page.waitForLoadState("networkidle");
    const after = await settle();
    await page.reload();
    const reloaded = await settle();
    const pass = after.ok && reloaded.ok && serverErrors.length === before;
    record(`walk:${control.id}`, pass, `after click ${after.state}, after reload ${reloaded.state}`);
  }
}

for (const line of acceptance) {
  const opened = await open(line.screen);
  const text = await page.locator("body").innerText();
  const pass = opened.ok && text.includes(line.text_expected);
  record(line.step, pass, pass ? "" : `step ${line.step} on ${line.screen}: "${line.text_expected}" not on screen`);
}

record("walk:no-5xx", serverErrors.length === 0, serverErrors.join(", "));
await browser.close();

const failed = steps.filter((s) => !s.pass).map((s) => s.step);
if (failed.length) console.error(`walk: ${failed.length} step(s) failed: ${failed.join(", ")}`);
console.log(JSON.stringify({ steps, instrument: "walk:planted" }));
process.exit(failed.length ? 1 : 0);
