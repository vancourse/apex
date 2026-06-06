# prd-review — `incident-retro`

Applied `apex:prd-review` (7 passes + adversarial counter-pass each + overlap + OSS), cold, against `prd.md`. **[FIXED]** = folded in before this record; **[ACCEPTED]** = recorded unknown/out-of-scope.

**Pass 1 — Acceptance criteria observable.** PASS. AC1–AC5 each fail in an observable way (blame attribution fails AC1; no written lesson fails AC3; vague action fails AC4).
- *Adversarial:* AC2 ("name the gate that should have caught it") assumes a covering gate always exists. **[FIXED]** — AC2 explicitly handles the **"no gate covers this class"** path (itself a finding → candidate new gate), and S2 tests it.

**Pass 2 — Scenarios enumerated + tagged.** PASS (5, all integration-tagged with justified no-E2E; S1 decomposed into use-cases S1.1–S1.3).
- *Adversarial — happy path without failure companion:* draft had S1 + S2. **[FIXED]** — added **S3** (blame leak rejected), **S4** (vague action rejected), **S5** (mid-incident misuse redirected). Each AC paired.
- *Adversarial — a flow the list implies but misses:* near-misses (caught in staging). **[FIXED]** — added as an S5 edge ("near-miss IS in scope — a free lesson").

**Pass 3 — Out-of-scope.** PASS (5 items). Critically scopes out **incident response** (the kitchen-sink trap — this could balloon into an on-call tool).
- *Adversarial — in-scope that should defer:* technical root-causing. **[FIXED]** — explicitly handed to `superpowers:systematic-debugging`; this skill starts *after* the cause is known. Clean boundary prevents scope explosion.

**Pass 4 — Unknowns named.** PASS.
- *Adversarial — hidden assumption:* the skill assumes it knows the current gate list to map against. **[FIXED]** — **U1** (read `FLOW.md` at runtime vs. carry a drift-prone list). Plus **U2** (lesson dedup) and **U3** (how rigorous the "no gate" proposal is — bounded to avoid scope explosion).

**Pass 5 — Success metric.** PASS — leading (100% end with lesson + gate-miss) + lagging (repeat-class rate → 0) + anti-metric.
- *Adversarial — Goodhart:* repeat-class rate is gamed by labeling everything "novel." **[FIXED]** — paired guard: count **preventative gate amendments that actually land** ("learning without gate changes is just journaling").

**Pass 6 — Sequencing.** PASS. Upstream (`memory-note`, `FLOW.md`) named with status; downstream closes the loop (a preventative action becomes a normal apex PR). Notably the design phase's own output could be the first thing this skill ever consumes.

**Pass 7 — Freeze readiness.**
- *Adversarial — two implementers diverge:* the "no gate covers this" → new-gate-proposal could be built as anything from one line to a full PRD. **[FIXED]** — **U3** bounds it (one-line proposal that *feeds* a PRD if pursued), resolving the ambiguity.

**Overlap scan.** PASS. The real adjacency — `memory-note` — is **reuse, not duplication**: `incident-retro` is the structured *producer* of an incident-class lesson and *calls* `memory-note` to persist. `verification-before-completion` (pre-merge) and `systematic-debugging` (cause-finding) are opposite-end / upstream, no overlap.

**OSS scan.** PASS. Google SRE / Etsy blameless templates = reference discipline (lifted framing); incident.io / Rootly / Morgue = reject (full platforms). Adversarial: none of the platforms offer the standalone "map the miss to your own design gates" loop — that's the distinctive value.

## Verdict

**PASS — freeze-candidate.** All 7 passes meet conditions; adversarial findings resolved or recorded (U1–U3). The review materially sharpened the PRD (the "no gate" path as a first-class AC, 3 failure scenarios, the systematic-debugging boundary that prevents scope creep, the "amendments-that-land" anti-metric).

**Residual risk:** **U3** — the "no covering gate → propose a new one" path is the scope-explosion vector; the design must keep it a *one-line proposal that feeds a real PRD*, not an inline mini-spec, or `incident-retro` quietly becomes a feature-authoring tool.
