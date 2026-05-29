---
name: spec-view
description: Render an apex SPEC-phase artifact (PRD, ADR set, or design doc) as a disposable, self-contained, offline rich HTML view for HUMAN review at the freeze gate — color-coded freeze-readiness dashboard, inline-SVG diagrams (data-flow, STRIDE grid, MVP-vs-deferred, scenario↔test traceability), collapsible/tabbed sections, severity badges, and syntax-highlighted code. The Markdown stays canonical; this HTML is a throwaway VIEW (gitignored, never re-ingested, never the source of truth). Pairs with apex:prd-review / apex:adr-review / apex:design-review (run the gate, then render the view for a human to approve). Fires when a human — especially a non-engineer reviewer — needs to read and approve a PRD, ADR, or design before freeze. Keywords: spec view, render spec, html review, prd view, adr view, design view, human review, freeze dashboard, review html.
---

# Spec View — disposable rich HTML for human review

Renders a PRD, ADR set, or design doc into a single self-contained HTML page so a human (often a non-engineer: product on a PRD, a staff eng on ADRs) can read, understand, and approve it at the freeze gate. The view is **rich on purpose** — color-coded freeze-readiness, inline SVG diagrams, collapsible passes, severity badges, highlighted code — because comprehension at the approval moment is the bottleneck this skill exists to relieve.

## The disposable contract — read this first

This HTML is a **VIEW, never the source of truth.**

- The canonical artifact is always the **Markdown** file. Downstream apex skills (`create-impl-plan`, `impl-plan-review`, etc.) read the `.md`, never this `.html`.
- The HTML is **gitignored and throwaway.** Never commit it. Never re-ingest it. Never diff it.
- It is **regenerated on demand.** If the Markdown changes during review, re-run this skill — do not hand-edit the HTML.
- Every page carries a banner stating this (see scaffold).

If you find yourself wanting to treat the HTML as authoritative, stop — edit the Markdown and regenerate.

## When to invoke

- Right after `apex:prd-review` / `apex:adr-review` / `apex:design-review` runs its passes and a **human needs to approve before freeze**.
- When a non-engineer stakeholder must read a spec they wouldn't read as raw Markdown.
- On demand: "render the design for review", "give me an HTML view of the PRD".

Skip it when the only reviewer is an engineer reading in-editor — rendered Markdown is enough, and this costs tokens. It's a nice-to-have for the human-review moment, not a pipeline step.

## Input & output

**Input:** the path to the canonical Markdown artifact. If not given, detect the most recent PRD / ADR / design doc in the working set (e.g. `docs/adr/*.md`, a `*-prd.md`, a design doc) or ask which one.

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

## Freeze-readiness dashboard

The dashboard is the highest-value element: it turns the view into the **freeze decision aid.** Render one `<li>` per pass condition of the matching review skill. Evaluate each against the artifact and pick a status dot + badge:

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

Use these to make the artifact *comprehensible at a glance* — not decoration. Every visual must carry review signal.

- **Inline SVG — data-flow** (design integration pass): boxes for services/stores, arrows for calls; color new components with `--accent`, existing ones neutral, broken invariants with `--risk`. Define one arrowhead `<marker>` and reuse.
- **Inline SVG — STRIDE grid** (design Pass 6): a 2×3 or 1×6 grid, one cell per category, cell tinted by residual risk (ok/warn/risk), mitigation text inside.
- **Inline SVG — MVP vs deferred** (design Pass 2/3): two stacked columns; MVP items solid, deferred items outlined with their re-eval trigger as a caption.
- **Table — scenario ↔ test traceability** (PRD/design): scenario # · description · edge case · (design) owning failure-mode/test. Flag any scenario with no coverage as `risk`.
- **Tabs** (`data-tabs`): one tab per ADR in an ADR set; or one tab per design pass if the doc is long. Use `<details>` accordions for everything else.
- **Severity badges**: on every finding, failure mode, and consequence — `ok`/`warn`/`risk`/`info`.
- **Syntax-highlighted code**: any schema/API/code snippet in the source → themed `<pre>` with `tok-*` spans you tokenize by hand (keywords, strings, numbers, comments, function names, punctuation).
- **Sliders / knobs** (`.knob`, optional): only for genuinely tunable values the reviewer might want to try — rollout cohort %, a threshold, a timeout. Wire the `output` to echo the value; add a `.copybtn` with `data-copy` so the reviewer can copy the chosen value back to you. Don't force a slider where there's no tunable.

## Type-specific body layout

- **PRD** → problem/goal panel · acceptance-criteria checklist (badges) · numbered scenario cards (each: action → response → edge case) · scenario↔test traceability table · success-metric callout panel · in/out-of-scope two-column grid · open-questions list · sequencing.
- **ADR set** → tabbed (one tab per ADR). Each: status badge · context · decision · alternatives **table** (option · pros · cons · why-not) · consequences with security + reversibility badges. A leading summary panel lists all ADRs with status dots.
- **Design** → freeze dashboard (above) · 6-pass accordion (`<details>`, open the ones with `risk`) · data-flow SVG in the integration pass · MVP-vs-deferred SVG · failure-mode table (mode → trigger → **user-visible behavior** → status) · STRIDE grid SVG · overlap + OSS scan results panel.

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
4. Proceed to `apex:create-impl-plan` against the frozen Markdown.
