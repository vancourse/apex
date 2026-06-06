# PRD — `incident-retro` (post-release learning loop)

**Status:** FROZEN as of 2026-06-06 (user sign-off) · **Slug:** `incident-retro`
Dogfood: authored then cold-audited (`prd-review.md` beside this file). Source: `docs/research/sdlc-frameworks-survey.md` #3.

---

## 1. Problem

apex's self-improvement loop (`memory-note` → `domain-knowledge`) learns from **reviews and designs** — lessons surfaced while *building*. It never learns from **production incidents**. When something apex's gates *should* have caught reaches prod and breaks, there is no path that (a) runs a blameless retro, (b) identifies **which apex gate missed it**, and (c) feeds the lesson back so the next design/review catches the class. apex is a closed loop on the pre-merge side and an **open loop** on the post-release side — it cannot get better at the failures that actually escape.

This is the blameless-postmortem practice (Google SRE / Etsy) reduced to its *learning* half and pointed back at apex's own gates — explicitly **not** an incident-response tool.

## 2. Goal & acceptance criteria

A **user-invoked, zero-ambient-cost** skill that takes a *resolved* incident and produces a short retro whose payload is a **gate-miss diagnosis** + a durable lesson written via `memory-note`, optionally proposing a one-line amendment to the apex pass that should have caught it.

**Acceptance criteria (observable):**

- **AC1 — Blameless framing enforced.** The retro names **contributing causes** and system/gate conditions, never individuals or "should have been more careful." Output that attributes blame to a person fails its own check.
- **AC2 — Gate-miss mapping.** The retro names the **specific apex gate that should have caught this** (e.g. `design-feature` Pass 5 failure-modes, `threat-model`, `impl-plan-review` Pass 5 reversibility, observability gate) — or states explicitly "no existing gate covers this class" (which is itself a finding → a candidate new gate).
- **AC3 — Durable lesson emitted.** It produces a concrete `domain-knowledge` entry (via `memory-note`) capturing the non-obvious fact so the next session/design starts smarter. A retro that ends without a written lesson is incomplete.
- **AC4 — Corrective action is specific + owned.** Each action is specific, has an owner, and is split **mitigative** (stop the bleeding) vs **preventative** (a gate amendment or new check). Vague "improve testing" actions fail the check.
- **AC5 — Scope guard (not incident response).** It operates only on **already-resolved** incidents and produces only a *learning* artifact — no paging, no sev-levels, no live timelines. An attempt to use it mid-incident is redirected ("resolve first; this is the learning pass").

## 3. Testable scenarios (PRD owns the list; tests mirror 1:1)

> Verification layer: all **integration** (Layer 4 — drive the skill over fixture incident descriptions, assert the retro structure). No **E2E** (no UI surface; justified).

- **S1 — Gate existed and missed it (happy path).** A NULL-handling bug that a `design-feature` Pass 5 failure-mode would have caught → retro names Pass 5 as the miss, emits a `domain-knowledge` lesson, proposes a preventative action. *Edge:* the incident maps to **two** gates (design + test-coverage) → both named, not just the first.
- **S2 — No gate covers this class (AC2 "no gate" path).** An incident from a class apex has no gate for (e.g. a third-party API silently changing a field's semantics) → retro flags "no covering gate," proposes a *candidate new gate/check* as the preventative action. *Edge:* the proposed gate overlaps an existing one → retro says "extend X," not "add new."
- **S3 — Blame leak (AC1 failure path).** A draft retro says "the engineer forgot to add the index" → the blameless check **rejects** it and rewrites to the contributing condition ("no gate required a query-plan check on new hot-path reads"). *Edge:* blameless-but-vague ("the team should be careful") is also rejected (fails AC4 specificity).
- **S4 — Vague action (AC4 failure path).** Action "improve test coverage" → flagged as non-specific/unowned; pushed to "add a failure-path test for the empty-feed case to `test-coverage-audit` Pass 5, owner: <name>." *Edge:* a specific-but-only-mitigative action with no preventative companion is flagged (every escape needs a prevention).
- **S5 — Mid-incident misuse (AC5 failure path).** Invoked while the incident is still firing → redirected to resolve first; emits nothing. *Edge:* a "near-miss" (caught in staging, never hit prod) IS in scope — it's a free lesson.

**S1 compound note:** S1 is compound (diagnose + emit lesson + propose action) → use-cases **S1.1** (gate-miss named), **S1.2** (`domain-knowledge` entry written), **S1.3** (preventative action proposed). Each gets ≥1 assertion.

## 4. Out of scope

- **Incident *response* / on-call tooling** — paging, sev classification, live timelines, status pages. (Reason: runtime/ops infra apex deliberately doesn't own; this is the *learning* half only.)
- **Auto-amending apex's skills.** It *proposes* a gate amendment; a human applies it (through apex's normal PR gates). (Reason: apex doesn't self-mutate without review — eat our own dogfood.)
- **Metrics / MTTR / incident dashboards.** (Reason: measurement infra; out of thesis — see survey's DORA reject.)
- **A persistent incident database.** Output is a markdown retro + a `domain-knowledge` append; no managed store. (Reason: zero ambient cost.)
- **Root-causing the incident technically** (that's debugging — `superpowers:systematic-debugging` owns it). This skill starts *after* the cause is known and asks "which gate should have caught it?" (Reason: clean boundary with the debugging side-path.)

## 5. Unknowns (design phase resolves)

- **U1 — Gate catalog reference.** To map an incident to "the gate that should have caught it," the skill needs the current list of gates/passes. Does it read `FLOW.md` (the canonical matrix) at runtime, or carry its own list (drift risk)? Design must pick (leaning: reference `FLOW.md`).
- **U2 — Lesson dedup.** `domain-knowledge` could accumulate near-duplicate lessons across retros. Design must define whether the skill checks for an existing similar lesson before appending (reuses `memory-note`'s existing behavior?).
- **U3 — "No gate covers this" → new-gate proposal rigor.** When AC2 hits the "no gate" path, how much does the retro specify the proposed gate (one line vs. a mini-PRD)? Risk of either too-vague or scope-exploding. Design must bound it (leaning: one-line proposal that *feeds* a real PRD if pursued).

## 6. Success metric

- **Leading (1–2 weeks):** Of incidents run through the skill, **100% end with a written `domain-knowledge` lesson + a named gate-miss** (or an explicit "no gate" finding). Retros that end with neither = the skill failed its job.
- **Lagging (1–3 months):** **Repeat-class rate** — incidents whose class was previously retro'd and lessoned should trend toward zero. The loop works iff the same class doesn't escape twice.
- **Anti-metric (Goodhart):** Repeat-class rate is gameable by classifying every incident as "novel" (so nothing is ever a repeat). Paired guard: track **how many retros propose a *preventative* gate amendment that actually lands** — learning without gate changes is just journaling.

## 7. Sequencing / dependencies

- **Upstream (must exist):** `memory-note` / `domain-knowledge` (the persistence target) — **shipped**; `FLOW.md` gate matrix (the mapping reference) — **shipped**. `superpowers:systematic-debugging` (finds the cause this skill reacts to) — companion, side-path.
- **Downstream:** preventative actions feed apex's *own* PR gates (a proposed amendment becomes a normal `prd`/`design`/skill-edit PR). Closes the loop back to the start of the SDLC.

## 8. Existing-product overlap scan

- **`memory-note`** — captures lessons. **Distinct:** `memory-note` captures a lesson from *any* source (a review, a gotcha); `incident-retro` is the *structured producer* of an incident-class lesson + gate-miss, which then *calls* `memory-note` to persist. Producer/consumer, explicit reuse — the retro is not a second memory store.
- **`verification-before-completion`** — proves a change works *pre-merge*; `incident-retro` learns from what broke *post-release*. Opposite ends of the loop, no overlap.
- **`superpowers:systematic-debugging`** — finds the technical cause; this starts after. Clean boundary (stated in §4).

Verdict: no parallel path; `memory-note` reuse is explicit.

## 9. OSS-alternatives scan

- **Google SRE / Etsy blameless postmortem templates** — **use as reference** (the blameless framing, contributing-causes, mitigative-vs-preventative action split are lifted directly). Not a tool to adopt — a discipline to encode.
- **incident.io / FireHydrant / Rootly** — **reference, reject adoption** — full incident-management platforms (paging, timelines, retros-as-a-feature); apex wants only the learning-loop atom, locally, zero-infra.
- **Morgue (Etsy's postmortem tool)** — **reference** — confirms the lightweight, markdown-ish retro shape; not adopted.

Adversarial miss check: the heavy platforms all bundle the learning retro *with* response tooling — none offer the standalone "map the miss back to your own design gates" loop apex wants, which is the distinctive value.

---

## Freeze marker

**Frozen as of 2026-06-06** (user sign-off). Passed `prd-review` (`prd-review.md`); adversarial findings resolved or recorded as U1–U3. Scope changes now require an explicit amendment. `apex:design-feature` may begin (see `design.md`).
