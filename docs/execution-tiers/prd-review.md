# prd-review — Execution-tier handoff + optional bead lineage

Applied `apex:prd-review` (7 passes + adversarial counter-pass each + overlap + OSS scans) to `prd.md`, run as a separate cognitive pass from authoring. **Findings that bit are marked [FIXED]** (folded into the PRD before this record) or **[ACCEPTED]** (recorded as a named unknown / out-of-scope with reason). This is the gate biting on its own author — the point of the exercise.

## Pass-by-pass

**Pass 1 — Acceptance criteria observable.** PASS. AC1–AC5 are all observable (tier stated, bead graph emitted, gate fires, audit blocks, degrades-and-says-so).
- *Adversarial:* "Tier selected and stated" (AC1) could be satisfied while apex picks the *wrong* tier and still truthfully "states" it. **[FIXED]** — AC1 strengthened to require citing **both** signals (capability probe + work-size), so a wrong choice is visible in its own rationale rather than hidden behind a bare verdict.

**Pass 2 — Scenarios enumerated.** PASS (5 scenarios, each with an edge case).
- *Adversarial — happy path with no failure companion:* the first draft had S1 (large/happy) and S2 (small) but **no failure-path scenarios** for the gate or the audit. **[FIXED]** — added **S4** (coverage audit catches a lost layer, fails closed) and **S5** (gate-before-merge blocks a bead). Each AC now has a paired failure scenario.

**Pass 3 — Out-of-scope.** PASS (5 items, each with rationale).
- *Adversarial — obviously in-scope but missing:* the **Refinery-bypass risk** (fast execution skipping review) is the single most important thing the feature exists to prevent, yet the first draft only implied it. **[FIXED]** — promoted to a first-class acceptance criterion (AC3, "gate runs before Refinery merges") and a dedicated scenario (S5).
- *Adversarial — in-scope that should defer:* a bead-status dashboard was tempting to include. **[FIXED]** — explicitly deferred to V2 in §4.

**Pass 4 — Unknowns named.** PASS after fix. First draft named only the bead schema unknown.
- *Adversarial — unnamed assumption:* the draft silently assumed **one layer ↔ one bead**. A layer can decompose into several beads, which would break a naïve coverage audit. **[FIXED]** — added **U2** (layer↔bead cardinality) and **U4** (the concrete work-size threshold, which was an implicit "obviously" the freeze pass also flagged).

**Pass 5 — Success metric.** PASS after fix. Leading + lagging present.
- *Adversarial — Goodhart:* coverage-audit pass-rate is trivially gamed by **always choosing Tier 3** (no beads ⇒ no audit can fail). **[FIXED]** — added the paired **anti-metric** (Tier-1 adoption rate on eligible features) in §6.

**Pass 6 — Sequencing.** PASS. Upstream (frozen impl-plan, `/apex:setup` probe) named with status; downstream (INTEROP, `/apex:to-beads`, spec-view V2) named with the contract owed.
- *Adversarial — dependency assumed solved but isn't:* the draft leaned on "Gastown beads can carry our lineage" as if settled. It is **not** — it's a spike. **[FIXED]** — demoted from assumption to blocking unknown **U1/U3** in §5 and "blocked-on / not started" in §7.

**Pass 7 — Freeze readiness.**
- *Adversarial — two implementers build differently:* the **work-size threshold** (Tier 1 vs Tier 2 boundary) was undefined → S2 was ambiguous. **[FIXED]** — captured as **U4** with an explicit design-phase mandate to set a default + decide configurability, and S2 now references a documented tie-break. With U1–U4 named, no *silent* ambiguity remains; the open questions are explicit design inputs, not hidden re-interpretations.

## Overlap scan
PASS. The only adjacency is `/apex:setup`'s capability probe; the PRD explicitly makes tier-detection a **reuse/extension** of that pattern, not a parallel path. `impl-plan-review` is a clean upstream producer. **[no change needed]**

## OSS scan
PASS. Gastown = use (the executor), superpowers = use (Tier 2 + TDD), Temporal/Airflow = reference for the graph/recovery model, Linear/Jira = reference-but-avoid for tracking.
- *Adversarial — missed library:* the usual misses (retries, queueing, recovery) are **supplied by Gastown itself**, reinforcing "integrate, don't reinvent." **[no gap]**

## Verdict

**PASS — freeze-candidate.** All 7 passes meet their conditions; every adversarial finding is resolved in the PRD or recorded as a named unknown (U1–U4) / explicit out-of-scope. The review changed the PRD materially (2 new failure scenarios, the Refinery-gate AC, 2 new unknowns, the anti-metric) — it was not a rubber stamp.

**Not yet frozen.** Freeze timing is the user's call. The load-bearing residual risk is **U1/U3** (Gastown's bead schema + a Refinery pre-merge hook): if the design-phase spike finds beads can't carry lineage or the Refinery can't be gated pre-merge, AC2/AC3 need their fallback designs (sidecar lineage map; gate the resulting PRs post-Refinery, pre-human-merge) — both already noted as design inputs.
