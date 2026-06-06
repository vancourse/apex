# PRD — Execution-tier handoff + optional bead lineage

**Status:** frozen-candidate (post `prd-review`; awaiting user freeze) · **Slug:** `execution-tiers`
**Author role / Review role:** drafted then audited in a separate cognitive pass (see `prd-review.md` beside this file).

---

## 1. Problem

apex authors and freezes a per-feature artifact chain — `prd.md` → `design.md` → `impl-plan.md` — where the impl-plan is a **layered PR stack** (each layer ≤400 LOC, explicitly sequenced, with a per-layer test plan). But apex says **nothing about who executes that plan, or how it is handed off.** Today execution is implicit: a single Claude agent, or an ad-hoc call into `superpowers:dispatching-parallel-agents`.

Two gaps follow:

1. **No defined executor handoff.** As heavier orchestrators appear (notably [Gastown](https://github.com/steveyegge/gastown) — a multi-agent fleet with persistent work-items ("beads"), dependency graph, auto-merge "Refinery", and crash recovery), apex has no way to route a frozen plan to the *best available* executor without either (a) hard-depending on one, or (b) letting fast parallel execution **bypass apex's review gates** (the Refinery auto-merges; if it merges before `security-review` runs, apex's entire reason to exist is defeated).
2. **"Nothing lost" is not a checkable property.** apex's `impl-plan-review` guarantees the *plan* is complete (PRD scenario ↔ test 1:1). Once execution begins, nothing asserts that every planned layer actually became a unit of executed work. The plan→execution boundary is untracked.

## 2. Goal & acceptance criteria

Give apex a thin, executor-agnostic **handoff layer** that selects an execution tier by capability + work-size, hands the frozen plan to it, keeps the review gates tier-invariant, and (optionally) projects the plan into a bead lineage graph so "nothing lost" becomes auditable.

**Acceptance criteria (observable):**

- **AC1 — Tier selection is explicit and justified.** Given a frozen `impl-plan.md`, apex emits a one-line tier decision naming the chosen tier **and** citing both signals that produced it: the capability probe result and the work-size signal (layer count / parallelism). Not "apex picked a tier" — the *rationale is shown*.
- **AC2 — The executor receives an actionable form.** For Tier 1 (Gastown), apex emits a bead graph derived from the impl-plan: one bead per layer, dependency edges from the layer sequencing, each bead carrying its layer's per-layer test plan as done-criteria and a link back to its PRD scenario(s). For Tier 2/3, the plan is consumed as-is.
- **AC3 — Review gates are tier-invariant.** `security-review` and `verification-before-completion` fire identically in all three tiers. In Tier 1 specifically, the gate runs on each bead's output **before** the Refinery merges it — execution parallelizes, the gate does not get skipped.
- **AC4 — Bead-coverage audit (when beads are used).** A check asserts: every impl-plan layer ↔ exactly one bead; every PRD scenario is reachable from ≥1 bead via lineage; no bead lacks a plan ancestor. A failing audit blocks handoff.
- **AC5 — Graceful degradation, never hard-fail.** Gastown absent → fall to Tier 2 (superpowers). superpowers absent → fall to Tier 3 (baseline single-agent, sequential). The absence of any optional companion never errors; it degrades and says so.

## 3. Testable scenarios (PRD owns the list; impl tests mirror 1:1)

- **S1 — Large feature, Gastown present (happy path).** Frozen impl-plan with 6 independent layers; `gt`/`bd` on PATH. → apex selects **Tier 1**, emits a 6-bead graph with dependency edges, runs bead-coverage audit (passes), hands to Gastown. *Edge:* two layers are mutually independent → their beads have no edge between them (parallelizable).
- **S2 — Small feature (size gate).** Frozen impl-plan with 1 layer; Gastown present. → apex selects **Tier 2/3 anyway** (work below the parallelism threshold), citing "1 layer < threshold" as the rationale, even though Gastown is available. *Edge:* exactly-at-threshold case resolves deterministically (documented tie-break).
- **S3 — Degradation (failure path for AC5).** 4-layer plan; neither `gt` nor superpowers installed. → apex selects **Tier 3**, states "Gastown + superpowers absent → baseline sequential," and proceeds without error. *Edge:* superpowers present but Gastown absent → Tier 2.
- **S4 — Coverage audit catches a lost layer (failure path for AC4).** Bead emit drops a layer (e.g., emitter bug or a layer with no test plan). → bead-coverage audit **fails closed**, names the orphaned layer, blocks handoff to Gastown. *Edge:* a bead with no PRD-scenario ancestor is flagged as "execution work with no spec lineage."
- **S5 — Gate-before-merge (failure path for AC3).** Tier 1; a bead's output fails `security-review`. → the Refinery does **not** merge that bead; apex reports the blocking finding; sibling independent beads are unaffected. *Edge:* a bead passes review but its dependency was blocked → it waits, not merges.

## 4. Out of scope

- **Building or modifying Gastown / the Refinery itself.** We integrate with its `gt`/`bd` CLI surface as a consumer; we do not fork it. (Reason: it's an independent project; apex bundles nothing.)
- **Replacing superpowers' TDD loop / brainstorming / writing-plans.** Tier selection picks an *executor*; the within-bead methodology (red-green TDD) still defers to superpowers. (Reason: Gastown doesn't provide these; see overlap scan.)
- **Mandatory beads everywhere / a native work-tracking store inside apex.** Beads are an *optional projection*, off by default, on for large work or explicit handoff. (Reason: an always-on work-item DB contradicts apex's lean/no-ambient-cost thesis — the kitchen-sink smell apex exists to avoid.)
- **A general executor-abstraction framework / plugin-adapter SPI.** The handoff is a routing decision + an emitter, not a speculative abstraction layer. (Reason: YAGNI; only 3 concrete tiers exist.)
- **Real-time progress dashboards / bead status UI.** Out of scope for V1; `spec-view`-style rendering of a bead graph is a possible V2. (Reason: V2.)

## 5. Unknowns (the design phase must resolve)

- **U1 — Gastown bead schema fidelity.** Can a `bd` bead carry (a) non-execution **lineage** links to a PRD scenario / design decision, and (b) **acceptance criteria** as first-class fields? AC2/AC4 depend on this. The design phase must confirm against Gastown's actual `bd` schema before committing to the emitter shape; if beads can't carry lineage natively, design a sidecar lineage map.
- **U2 — Layer↔bead cardinality.** The PRD assumes one impl-plan layer ↔ one bead. A layer may legitimately decompose into multiple beads (e.g., parallel files within a layer). Design must decide whether the emitter is strictly 1:1 or 1:many, and how the coverage audit (AC4) handles 1:many without losing the "nothing orphaned" guarantee.
- **U3 — Refinery pre-merge gate hook.** AC3's "gate before merge" assumes the Refinery exposes a point to insert apex's review (a hook, a required check, or a manual barrier). If it does not, design must define the fallback (e.g., apex gates the resulting PRs *after* Refinery proposes them, before human merge).
- **U4 — The work-size threshold.** AC1/S2 need a concrete parallelism threshold. Design must set a default (and decide configurability) — the value that decides Tier 1 vs Tier 2 — resolving the S2 ambiguity so two implementers route identically.

## 6. Success metric

- **Leading (1–2 weeks):** On features run through the handoff, the bead-coverage audit (AC4) runs and its pass/fail is recorded; target = **100% of Tier-1 handoffs gated by a passing coverage audit** (no un-audited fleet executions). Plus: tier-selection rationale present in 100% of handoffs (AC1).
- **Lagging (1–3 months):** Reduction in **"lost scope" defects** — planned layers / PRD scenarios that shipped incomplete — on handoff-run features vs. baseline. Target: trend to zero lost-scope escapes attributable to the plan→execution boundary.
- **Anti-metric (Goodhart guard):** Coverage-audit pass-rate could be gamed by **always selecting Tier 3** (no beads → no audit to fail) or by emitting trivially-passing beads. Paired guard: track the **Tier-1 adoption rate on eligible (large) features**; if coverage-audit pass-rate is 100% only because Tier 1 is never selected, the metric is being gamed.

## 7. Sequencing / dependencies

- **Upstream (must be shipped/true):** apex's `impl-plan-review` + plan-freeze (the handoff consumes a *frozen* impl-plan) — **shipped**. The `/apex:setup` capability-probe pattern that tier detection reuses — **shipped**.
- **Blocked-on:** U1/U3 (Gastown bead schema + Refinery hook) must be answered before the Tier-1 emitter is buildable — **not started** (design-phase spike).
- **Downstream (owes a contract to):** `INTEROP.md` gains a "Gastown" section that points at this handoff; a possible `/apex:to-beads` command surface; `spec-view` V2 could render the bead graph. Each depends on the bead emit format this PRD's design fixes.

## 8. Existing-product overlap scan

- **`/apex:setup`** — already does **companion detection** (probes for superpowers, pr-review-toolkit, context tools). Tier selection's capability probe **reuses/extends this pattern**, it does not duplicate it. *Closest overlap; explicitly an extension, not a parallel path.*
- **`recon`** — produces a pre-design brief; unrelated to post-plan execution. No overlap.
- **`spec-view`** — renders frozen artifacts for human review; could *later* render a bead graph (V2, out of scope). No V1 overlap.
- **`impl-plan-review`** — produces the layered stack this handoff consumes; it is the *upstream producer*, not a competitor. No overlap (clean producer/consumer boundary).

Verdict: no parallel-path duplication. The one adjacency (`/apex:setup` probing) is an explicit reuse.

## 9. OSS-alternatives scan

- **Gastown** — **use** (it *is* the Tier-1 executor; we integrate as a consumer of `gt`/`bd`).
- **superpowers** — **use** (Tier-2 executor + TDD methodology; already an apex companion).
- **GitHub Spec Kit / BMAD** — **reference/avoid for this** — they author *upstream* artifacts (already covered by `INTEROP.md`); they are not executors, so not alternatives to the handoff.
- **Temporal / Airflow / Prefect** (workflow orchestrators) — **reference** — mature dependency-graph + retry + recovery designs; free education for the bead-graph + degradation model, but too heavy to adopt and not Claude-native.
- **Linear / Jira** (work-tracking) — **reference, explicitly avoid adopting** — beads overlap their "work item + dependency" model, but adopting an external tracker would re-introduce the ambient-cost apex avoids; the bead projection stays optional and local.

Adversarial OSS miss check: the commonly-missed categories (retries, queueing, recovery) are **provided by Gastown itself**, not something apex must build — confirming "integrate, don't reinvent."

---

## Freeze marker

**Frozen as of:** _pending user sign-off._ This PRD is a **frozen-candidate**: it has passed `prd-review` (see `prd-review.md`), and all adversarial findings are either resolved here or recorded as named unknowns (U1–U4) for the design phase. It is **authored, not frozen** until the user marks it frozen — at which point `apex:design-feature` may begin.
