# prd-review — `agent-rails` (cold audit)

**Artifact:** `docs/agent-rails/prd.md` (DRAFTED) · **Reviewer stance:** adversarial, run cold after authoring.
**Verdict:** PASS WITH FINDINGS — freeze-ready once F1–F3 are resolved in the PRD (resolved inline; see notes) and user sign-off lands. F4–F5 recorded as accepted risks.

---

## Pass 1 — Acceptance criteria are observable

AC1 (file-reads-only resume), AC3 (refusal with named defects), AC5 (CI fails naming the row), AC6 (no daemon; atomic writes) — all decidable. AC2 is decidable given the hash. **AC4 is honest about its boundary** (tamper-evident, not -proof) — and S7's edge case turns the boundary itself into a tested, documented behavior rather than a hole. Good.

**F1 (resolved):** AC3 originally implied lint-clean ⇒ freezable; the sign-off condition was implicit. Fixed: "necessary, not sufficient" is now explicit in AC3 and re-asserted by S2's edge and §6's anti-metric guard.

## Pass 2 — Scenarios enumerated, tagged, decomposed

Seven scenarios, each with an edge; S1 correctly decomposed (S1.1–S1.3, compound). All tagged integration with an explicit no-E2E justification (no UI) — consistent with `incident-retro`/`stack-adapters` precedent. Scenarios map onto ACs with no orphan AC: AC1←S1/S5, AC2←S4, AC3←S2, AC4←S7, AC5←S6, AC6←S3.

**F2 (resolved):** S4 initially conflated two distinct defects; now split into S4(a) status-divergence and S4(b) post-freeze-drift with distinct flags (DIVERGENCE / POST-FREEZE-DRIFT) and distinct routes (re-run gate / amendment). The taxonomy extension of `cross-artifact-consistency` is named in §8.

## Pass 3 — Out-of-scope is load-bearing

The §4 list rejects the four expensive temptations (hard locks, orchestration state, daemons, backfill) each with a reason. The "honest rail" framing on the first is the right call — **adversarial probe:** could a reviewer read AC4 + §4 and believe the system is more secure than it is? No: S7's edge documents the forgeable case explicitly. Held.

## Pass 4 — Unknowns are genuinely open + design-resolvable

U1–U5 are real decisions with stated leanings, none of which secretly change scope. **F3 (resolved):** U3 (sign-off representation) was originally listed as a leaning; it is genuinely the riskiest unknown (a fabricatable `signed_off_by` undermines AC4's spirit) — now flagged as *must pick the honest option and state its strength*, making weak-evidence-acknowledged an acceptable design outcome but silent weakness not.

## Pass 5 — Success metric + anti-metric

Leading metric is testable in the first dogfood cycle (cold-resume on a live feature). Lagging metric ("zero advanced-past-unfrozen") measures the actual failure class. The Goodhart guard (shape-only by contract; review remains the other half) is the same shape as `incident-retro`'s repeat-class guard. Held.

## Pass 6 — Sequencing

Upstream dependencies all shipped; the three reuse claims (`cross-artifact-consistency` parsing, `detect-stack` file discipline, `autonomous-fix` lint pattern) are each verifiable in-repo. Downstream consumers named without creating coupling (bootstrap/council read state; nothing blocks on them). Held.

## Pass 7 — Freeze readiness

Overlap scan: 4 products, all distinct-with-stated-boundary; the Gastown boundary correctly defers to the frozen `execution-tiers` design. OSS scan: 4 alternatives, each adopt/reference/reject with a reason; the adversarial miss check identifies the actual novelty (review-gate state with freeze evidence). **Freeze blocked only on:** user sign-off.

## Adversarial counter-pass (attack the whole PRD)

1. **"Three components is a bundle, not a feature"** — attack: C1/C2/C3 could be three PRDs. Defense holds: C2 without C1 has nothing to gate (the lint guards a *transition* in state); C3 without C1 routes against state that doesn't exist; S1 needs all three. One capability, layered delivery (impl-plan's problem).
2. **"The lint will ossify the artifact format"** — attack: shape checks freeze today's PRD template; future skill evolution fights the lint. Partially held: mitigated by U2's minimality + the lint checking *presence of anchors* (IDs, tags, sections) not layout. Residual risk accepted, noted here. **(F4 — accepted risk, revisit at design.)**
3. **"state.json will rot like all status files"** — attack: gates forget to write it; state silently diverges from reality. Defense: that's exactly what S4(a) detects, and the leading metric makes write-through observable in the first cycle. But the *enforcement* that gates write state belongs in the gate skills' own text — design must amend the freeze-performing skills, or rot is guaranteed. **(F5 — design requirement, carried forward.)**
4. **"Why JSON when apex chose TOML for the profile?"** — attack: file-format inconsistency. Defense: `apex.profile.toml` is human-edited config (TOML's niche); `state.json` is machine-written evidence (stdlib `json`, no comments needed, hash-friendly). Distinction is real; one line in design should state it.

---

**Findings ledger:** F1 resolved (AC3 wording) · F2 resolved (S4 split) · F3 resolved (U3 hardened) · F4 accepted risk (anchor-not-layout linting; revisit at design) · F5 carried to design (freeze-performing skills must be amended to write state — without this the feature rots).
