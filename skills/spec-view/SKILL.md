---
name: spec-view
description: Render an apex SPEC-phase artifact (PRD, ADR set, or design doc) as a disposable, self-contained, offline rich HTML view a human can actually read — in COMPREHENSION mode (default; the artifact's own content: object model, worked example, interface surface, data model, invariants) or FREEZE-REVIEW mode (a readiness dashboard for approve-or-send-back). Inline-SVG diagrams, collapsible sections, severity badges, syntax-highlighted code. The Markdown stays canonical; this HTML is a throwaway VIEW (gitignored, never re-ingested, never the source of truth). Fires when someone says they don't understand a spec, asks to see/explain/render a design, or needs to approve a PRD, ADR, or design before freeze. Keywords: spec view, render spec, explain the design, show me the design, html review, prd view, adr view, design view, understand the design, human review, freeze dashboard, review html.
---

# Spec View — disposable rich HTML for humans

Renders a PRD, ADR set, or design doc into a single self-contained HTML page a human can actually read. Rich on purpose — inline SVG diagrams, collapsible sections, severity badges, highlighted code — because comprehension is the bottleneck this skill exists to relieve.

## The failure mode this skill has to avoid

**The commonest failure of this skill is rendering the REVIEW instead of the ARTIFACT.**

The apex review vocabulary — six passes, freeze-readiness, MVP-vs-deferred, overlap and OSS scans, findings by severity — is *process metadata about* a design. It is not the design. A reader who says "I don't understand this design" needs the object model, a worked example, the interface, and the data model. Handing them a freeze dashboard and a six-pass accordion answers a question they did not ask, and it is the single most likely way to waste this skill's output.

> **Render what the artifact IS, not what the review FOUND.**

Process/status content is legitimate — but in comprehension mode it is an appendix: **last, collapsed, and under ~15% of the page.**

## The disposable contract

This HTML is a **VIEW, never the source of truth.**

- The canonical artifact is always the **Markdown** file. Downstream apex steps (`impl-plan`, `impl-plan-review`, etc.) read the `.md`, never this `.html`.
- The HTML is **gitignored and throwaway.** Never commit it. Never re-ingest it. Never diff it.
- It is **regenerated on demand.** If the Markdown changes during review, re-run this skill — do not hand-edit the HTML.
- Every page carries a banner stating this (see scaffold).

If you find yourself wanting to treat the HTML as authoritative, stop — edit the Markdown and regenerate.

## The two modes — pick one before you write anything

| | **Comprehension** (default) | **Freeze review** |
|---|---|---|
| The ask sounds like | "I don't understand the design", "explain X", "show me the design", "render this so I can read it", or no qualifier at all | "is this ready to freeze?", "review this before I approve", invoked straight after `apex:*-review` |
| Leads with | what the thing IS — object model, worked example | the readiness dashboard |
| Ordered by | the artifact's own logic | the review's pass conditions |
| Process/status content | an appendix: last, collapsed, ≤15% of the page | the point of the page |
| Diagrams show | how the system works | where the risk is |

**When the ask is ambiguous, choose comprehension.** It is the more useful failure: a reader who wanted the gate can still find the appendix, whereas a reader who wanted the design cannot reconstruct it from a dashboard.

If a mode was chosen and the reader pushes back ("too much commentary", "this isn't the design"), you are in the wrong mode — switch, don't patch.

## When to invoke

- Someone says they **don't understand** a spec, or asks you to explain/show/walk through a design → comprehension mode.
- A non-engineer stakeholder must read a spec they wouldn't read as raw Markdown → comprehension mode.
- Right after `apex:prd-review` / `apex:adr-review` / `apex:design-review` runs its passes and a **human needs to approve before freeze** → freeze-review mode.
- On demand: "render the design", "give me an HTML view of the PRD".

Skip it when the only reader is an engineer reading in-editor — rendered Markdown is enough, and this costs tokens.

## Input & output

**Input:** the path to the canonical Markdown artifact. If not given, detect it from apex's standard layout — `docs/<feature-slug>/prd.md` or `design.md` (per-feature) or `docs/adr/*.md` (project-wide architecture) — preferring the most recently modified; ask only if ambiguous.

**Output:** a single self-contained file at:

```
tmp/apex-views/<type>-<slug>-<YYYY-MM-DD-HHMM>.html
```

- `<type>` ∈ `prd` | `adr` | `design`.
- Create `tmp/apex-views/` if absent. `tmp/` is gitignored in this repo by convention — verify; if it is not, fall back to `${TMPDIR:-/tmp}/apex-views/` and tell the user the absolute path.
- After writing, print the absolute path and a one-line "open with: `open <path>`" hint. Do not auto-open unless asked.

## Self-containment rules (zero-dependency, offline)

- **One file.** No external CSS, no CDN `<script>`, no web fonts, no network at view time. Must open by double-click on a plane with no internet.
- **CSS:** inline `<style>` only. Use the scaffold below.
- **JS:** inline, vanilla, minimal (tabs + slider-value copy only). Prefer `<details>`/`<summary>` for collapsibles — they need zero JS.
- **Diagrams:** hand-author **inline SVG**. Do NOT use Mermaid or any renderer. Inline SVG is crisp, themeable, and self-contained.
- **Syntax highlighting:** tokenize code yourself into `<span class="tok-*">` (classes in the scaffold). Do not pull a highlighter lib.
- **Images:** if the source references images, inline them as SVG or data-URIs; never hot-link.

## The scaffold (use verbatim, fill the body)

Emit this skeleton, then populate `<!-- DASHBOARD -->` and `<!-- BODY -->` per the artifact type. Keep the `<style>`/`<script>` as-is so every view is consistent.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TYPE} · {TITLE} — review view</title>
<style>
:root{
  --bg:#fbfbfd; --panel:#fff; --ink:#1c1c22; --muted:#6b6b76; --line:#e6e6ee;
  --accent:#5b4bdb; --ok:#1a7f4b; --ok-bg:#e6f4ec; --warn:#9a6700; --warn-bg:#fdf3da;
  --risk:#b42318; --risk-bg:#fdeceb; --info:#1257a6; --info-bg:#e8f0fb;
  --code-bg:#1e1e2a; --tok-kw:#c792ea; --tok-str:#c3e88d; --tok-num:#f78c6c;
  --tok-com:#7a8499; --tok-fn:#82aaff; --tok-punct:#bfc7d5; --tok-base:#e6e6ee;
  --radius:12px; --maxw:980px;
}
@media (prefers-color-scheme:dark){
  :root{--bg:#0f0f14;--panel:#17171f;--ink:#e9e9f0;--muted:#9a9aac;--line:#262633;
  --ok-bg:#10271b;--warn-bg:#2a2110;--risk-bg:#2a1413;--info-bg:#101f33;}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:var(--maxw);margin:0 auto;padding:32px 20px 80px}
.banner{background:var(--warn-bg);color:var(--warn);border:1px solid var(--line);
  border-radius:var(--radius);padding:10px 14px;font-size:13px;margin-bottom:24px}
h1{font-size:30px;margin:.2em 0 .1em;letter-spacing:-.02em}
h2{font-size:21px;margin:1.6em 0 .5em;letter-spacing:-.01em}
h3{font-size:16px;margin:1.2em 0 .4em}
.kicker{color:var(--accent);font-weight:700;text-transform:uppercase;
  letter-spacing:.08em;font-size:12px}
.meta{color:var(--muted);font-size:13px;margin-bottom:8px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:18px 20px;margin:14px 0}
.grid{display:grid;gap:14px}
.grid.cols-2{grid-template-columns:1fr 1fr}
.grid.cols-3{grid-template-columns:repeat(3,1fr)}
@media(max-width:720px){.grid.cols-2,.grid.cols-3{grid-template-columns:1fr}}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
  padding:3px 9px;border-radius:999px;border:1px solid transparent}
.badge.ok{color:var(--ok);background:var(--ok-bg)}
.badge.warn{color:var(--warn);background:var(--warn-bg)}
.badge.risk{color:var(--risk);background:var(--risk-bg)}
.badge.info{color:var(--info);background:var(--info-bg)}
.badge.todo{color:var(--muted);background:transparent;border-color:var(--line)}
.dash{list-style:none;padding:0;margin:0;display:grid;gap:8px}
.dash li{display:flex;align-items:center;gap:10px;padding:8px 12px;border:1px solid var(--line);
  border-radius:10px;background:var(--panel)}
.dash .dot{width:10px;height:10px;border-radius:50%;flex:0 0 auto}
.dot.ok{background:var(--ok)} .dot.warn{background:var(--warn)}
.dot.risk{background:var(--risk)} .dot.todo{background:var(--muted)}
.dash .note{color:var(--muted);font-size:13px;margin-left:auto}
details{border:1px solid var(--line);border-radius:10px;margin:10px 0;background:var(--panel)}
details>summary{cursor:pointer;padding:12px 16px;font-weight:600;list-style:none;
  display:flex;align-items:center;gap:10px}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"▸";color:var(--accent);transition:transform .15s}
details[open]>summary::before{transform:rotate(90deg)}
details .body{padding:0 16px 16px}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
pre{background:var(--code-bg);color:var(--tok-base);border-radius:10px;padding:14px 16px;
  overflow:auto;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.tok-kw{color:var(--tok-kw)} .tok-str{color:var(--tok-str)} .tok-num{color:var(--tok-num)}
.tok-com{color:var(--tok-com);font-style:italic} .tok-fn{color:var(--tok-fn)} .tok-punct{color:var(--tok-punct)}
figure{margin:14px 0;text-align:center} figcaption{color:var(--muted);font-size:12px;margin-top:6px}
svg{max-width:100%;height:auto}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.tab{padding:7px 14px;border:1px solid var(--line);border-radius:999px;background:var(--panel);
  cursor:pointer;font-size:14px;font-weight:600}
.tab[aria-selected="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
.tabpanel[hidden]{display:none}
.knob{display:flex;align-items:center;gap:12px;margin:10px 0}
.knob input{flex:1} .knob output{font-weight:700;min-width:3ch;text-align:right}
.copybtn{font-size:12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);
  color:var(--ink);padding:4px 10px;cursor:pointer}
/* comprehension mode: section nav + numbered walkthrough steps */
.toc{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 4px}
.toc a{font-size:13px;font-weight:600;text-decoration:none;color:var(--ink);border:1px solid var(--line);
  background:var(--panel);border-radius:999px;padding:6px 13px}
.toc a:hover{border-color:var(--accent);color:var(--accent)}
.step{display:flex;gap:14px;margin:16px 0;align-items:flex-start}
.step .n{flex:0 0 30px;height:30px;border-radius:50%;background:var(--accent);color:#fff;
  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px}
.step .c{flex:1;min-width:0}
.callout{border-left:4px solid var(--accent);padding:12px 16px;background:var(--panel);
  border-radius:0 10px 10px 0;margin:14px 0;border:1px solid var(--line);border-left-width:4px}
.callout.risk{border-left-color:var(--risk)} .callout.ok{border-left-color:var(--ok)}
@media print{details{break-inside:avoid} details:not([open])>.body{display:block}
  details>summary::before{content:""} body{background:#fff}}
</style>
</head>
<body>
<div class="wrap">
  <div class="banner">Generated review view — <strong>not</strong> the source of truth.
    Canonical: <code>{CANONICAL_PATH}</code>. Edit the Markdown and regenerate after any change.
    Generated {TIMESTAMP}.</div>
  <div class="kicker">{TYPE} · freeze review</div>
  <h1>{TITLE}</h1>
  <div class="meta">{SUBTITLE_OR_STATUS}</div>

  <!-- FREEZE-REVIEW MODE ONLY — in comprehension mode DELETE these two lines and
       put a nav of section links here instead (.toc in the stylesheet). -->
  <h2>Freeze readiness</h2>
  <ul class="dash"><!-- DASHBOARD --></ul>

  <!-- BODY -->
</div>
<script>
// tabs
document.querySelectorAll('[data-tabs]').forEach(g=>{
  const tabs=g.querySelectorAll('.tab'), panels=g.querySelectorAll('.tabpanel');
  tabs.forEach((t,i)=>t.addEventListener('click',()=>{
    tabs.forEach(x=>x.setAttribute('aria-selected','false'));
    panels.forEach(p=>p.hidden=true);
    t.setAttribute('aria-selected','true'); panels[i].hidden=false;
  }));
});
// slider value echo + copy
document.querySelectorAll('.knob input[type=range]').forEach(r=>{
  const out=r.nextElementSibling; const sync=()=>out.value=r.value; r.addEventListener('input',sync); sync();
});
document.querySelectorAll('.copybtn').forEach(b=>b.addEventListener('click',()=>{
  navigator.clipboard?.writeText(b.dataset.copy||'').then(()=>{const o=b.textContent;b.textContent='copied';setTimeout(()=>b.textContent=o,900)});
}));
</script>
</body>
</html>
```

## Freeze-readiness dashboard — **freeze-review mode only**

Do not render this in comprehension mode. It is the highest-value element *of a freeze decision aid*, and dead weight at the top of a page whose reader is trying to learn how the system works. In comprehension mode the same facts appear as a short collapsed appendix at the end.

In freeze-review mode, render one `<li>` per pass condition of the matching review skill. Evaluate each against the artifact and pick a status dot + badge:

- `ok` (green) — condition met.
- `warn` (amber) — partially met / accepted residual risk; note why.
- `risk` (red) — unmet; this blocks freeze.
- `todo` (grey) — can't determine from the artifact; reviewer must verify manually.

Put the shortfall in `.note`. Example `<li>`:

```html
<li><span class="dot risk"></span><strong>Failure modes</strong>
  — each has user-visible behavior <span class="note">2 modes say "logs and continues" (unresolved)</span></li>
```

Pass conditions to render, by type:

- **PRD** (mirror `apex:prd-review`): acceptance criteria present & testable · ≥3 concrete scenarios each with an edge case · scope in/out explicit · success metric defined & measurable · open questions/unknowns listed · sequencing stated.
- **ADR** (mirror `apex:adr-review`, per ADR): context · decision · ≥2 alternatives considered · consequences incl. **security + reversibility** · status set.
- **Design** (mirror `apex:design-review`): 3–5 scenarios w/ edge cases · MVP cut named (irreducible) · deferral list (≥3, each w/ re-eval trigger) · ≥2 existing primitives reused/extended + invariants named · failure modes each w/ user-visible behavior · STRIDE present (or "no attack surface" justified) · overlap scan addressed · ≥1 OSS alternative considered · adversarial pair dispatched if non-trivial.

End the dashboard with a one-line verdict badge: all-green → `<span class="badge ok">Ready to freeze</span>`; any red → `<span class="badge risk">Not ready — N blockers</span>`.

## Rich-content toolkit (what to render where)

Use these to make the artifact *comprehensible at a glance* — not decoration. Every visual must carry signal: **how the system works** in comprehension mode, **where the risk is** in freeze-review mode.

- **Inline SVG — data-flow** (design integration pass): boxes for services/stores, arrows for calls; color new components with `--accent`, existing ones neutral, broken invariants with `--risk`. Define one arrowhead `<marker>` and reuse.
- **Inline SVG — STRIDE grid** (design Pass 6): a 2×3 or 1×6 grid, one cell per category, cell tinted by residual risk (ok/warn/risk), mitigation text inside.
- **Inline SVG — MVP vs deferred** (design Pass 2/3): two stacked columns; MVP items solid, deferred items outlined with their re-eval trigger as a caption.
- **Table — scenario ↔ test traceability** (PRD/design): scenario # · description · edge case · (design) owning failure-mode/test. Flag any scenario with no coverage as `risk`.
- **Tabs** (`data-tabs`): one tab per ADR in an ADR set; or one tab per design pass if the doc is long. Use `<details>` accordions for everything else.
- **Severity badges**: on every finding, failure mode, and consequence — `ok`/`warn`/`risk`/`info`.
- **Syntax-highlighted code**: any schema/API/code snippet in the source → themed `<pre>` with `tok-*` spans you tokenize by hand (keywords, strings, numbers, comments, function names, punctuation).
- **Sliders / knobs** (`.knob`, optional): only for genuinely tunable values the reviewer might want to try — rollout cohort %, a threshold, a timeout. Wire the `output` to echo the value; add a `.copybtn` with `data-copy` so the reviewer can copy the chosen value back to you. Don't force a slider where there's no tunable.

## Body layout — comprehension mode (the default)

Order by the artifact's own logic, never by the review's pass structure. A design doc's six apex passes are how it was *authored*; they are not how it is *understood*.

**Design** — the layout below is the spine. Skip a section the artifact genuinely lacks; never invent one to fill a slot.

1. **What it is** — two or three sentences, then a section nav (`.toc`).
2. **Object model** — the entities, their relationships and cardinality, as an inline-SVG diagram plus a one-line "reading the diagram" caption. *If you render only one thing, render this.* Most design docs never draw it, so this is where the view adds the most.
3. **A worked example, end to end** — the highest-value element in this mode. Walk one real case through the whole system as numbered `.step` blocks with **real payloads at each step**, not placeholders. Abstract mechanism becomes concrete here or nowhere.
4. **The domain vocabulary** — every field/knob of the central type, in a table: what it controls, what happens if it is wrong.
5. **Interface surface** — actual signatures, verbs, error taxonomy. What a caller types.
6. **Data model / storage** — tables with key columns and, crucially, *the constraints that carry meaning* (which uniqueness rule enforces which rule of the domain).
7. **Invariants and what enforces each** — pair every guarantee with its mechanism. A guarantee with no named mechanism is the thing a reader most needs flagged.
8. **Failure modes** — mode → trigger → **user-visible behavior**.
9. **Threat model** — mechanism and residual per category.
10. **Appendix** (`<details>`, collapsed, last): status, open questions, deferrals, review history. All of it. This is the ≤15%.

**PRD** → problem/goal panel · what the user can do (scenario cards: action → response → edge case) · acceptance criteria as a checklist · in/out-of-scope grid · success metric · appendix: open questions, sequencing, review status.

**ADR set** → tabbed, one tab per ADR: context · decision · alternatives **table** (option · pros · cons · why-not) · consequences with security + reversibility badges. Leading summary panel lists all ADRs with status dots.

## Body layout — freeze-review mode

- **PRD** → dashboard · acceptance-criteria checklist · scenario↔test traceability table · success-metric callout · in/out-of-scope grid · open questions · sequencing.
- **ADR set** → dashboard · tabbed per ADR as above, each with its pass conditions scored.
- **Design** → dashboard · 6-pass accordion (`<details>`, open the ones with `risk`) · data-flow SVG in the integration pass · MVP-vs-deferred SVG · failure-mode table · STRIDE grid SVG · overlap + OSS scan panel.

## Before you emit — self-check

1. **Mode named?** If the ask was ambiguous, you chose comprehension.
2. **Comprehension mode: does an object model and a worked example with real values exist?** If not, the page is not yet a design view.
3. **Comprehension mode: measure the process/status content** — freeze readiness, findings, blockers, review log, cost-of-change, MVP-vs-deferred, what-changed-since-the-last-revision. Over ~15% of the page, or appearing before the artifact's own content? Cut and move to the appendix.
4. **Would a reader who has never seen this system be able to describe how it works after reading?** That is the only test comprehension mode has to pass.
5. **Offline?** No CDN, no web fonts, no network. Opens by double-click.
6. **Diagrams sane?** No text or box outside its `viewBox`; every `url(#id)` marker is defined. Verify by parsing the file, not by eye — a `file://` page often cannot be scripted or screenshotted from a preview pane.

## Quality bar

- Polished but **not** your application's design system — this is throwaway meta-tooling, not app UI. The scaffold's aesthetic is the standard; don't reinvent it per run.
- Accessible: color is never the only signal (badges/dots always have text labels); contrast meets WCAG AA; works light + dark via `prefers-color-scheme`.
- Print-friendly: `@media print` expands accordions so a PDF export shows everything.
- Faithful: render what the artifact says. If a section is missing, show it as a `risk`/`todo` in the dashboard — do not invent content to fill a template slot.

## Relationship to the freeze gates

Run the review skill first, then render:

1. `apex:prd-review` / `apex:adr-review` / `apex:design-review` — run the passes, surface findings.
2. `apex:spec-view` — render the (possibly still-failing) artifact so a human can see the freeze-readiness dashboard and approve or send back.
3. Human approves → freeze the **Markdown** (the freeze is a commit to the `.md`, never to the `.html`).
4. Proceed to `apex:impl-plan` against the frozen Markdown.
