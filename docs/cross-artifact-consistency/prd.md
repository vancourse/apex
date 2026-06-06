# PRD — Cross-artifact consistency analysis

**Status:** frozen-candidate (post `prd-review`; awaiting user freeze) · **Slug:** `cross-artifact-consistency`
Dogfood: authored then cold-audited in a separate pass (`prd-review.md` beside this file). Source: `docs/research/sdlc-frameworks-survey.md` #1.

---

## 1. Problem

apex reviews each SDLC artifact **vertically** — `prd-review` audits the PRD against itself, `design-review` the design against itself, `impl-plan-review` the plan against itself. Each ends in a freeze. But **nothing audits the artifacts against *each other*.** Once the PRD is frozen and design begins, there is no gate that asserts the *design still satisfies the frozen PRD*, or the *impl-plan covers the frozen design*. A PRD scenario silently dropped from the design, a design decision with no implementing PR, or a success metric the plan never instruments — all pass every existing gate today. apex's freeze model is excellent vertically and blind horizontally.

This is the "do the frozen artifacts still agree?" gap — the single biggest structural hole found in the framework survey (it's GitHub Spec Kit's `/analyze`, generalized to apex's PRD/design/impl-plan chain).

## 2. Goal & acceptance criteria

A **read-only** analysis pass that cross-references the frozen artifacts of one feature (`docs/<slug>/prd.md` → `design.md` → `impl-plan.md`, plus the test set when present) and emits a **traceability matrix** with gaps and contradictions flagged. It authors *nothing* and freezes *nothing* — it produces a defect list that sends work back to the right upstream gate.

**Acceptance criteria (observable):**

- **AC1 — Forward coverage.** Every frozen PRD scenario (and use-case, per `prd-review` Pass 2) maps to ≥1 design element and ≥1 impl-plan layer. A scenario with no design or no plan owner is flagged **DROPPED**.
- **AC2 — Backward justification.** Every design element and every impl-plan layer traces back to ≥1 PRD scenario/requirement. An element/layer with no upstream anchor is flagged **ORPHAN** (gold-plating or undocumented scope).
- **AC3 — Contradiction detection.** Where two artifacts make incompatible claims about the same thing (PRD says "out of scope" but a design section builds it; design says one data shape, impl-plan another), it is flagged **CONFLICT** with both `file:line` citations.
- **AC4 — Read-only + actionable.** The pass writes no artifact other than its report; each finding names the **upstream gate to return to** (re-open PRD / design / impl-plan), never "fix it here."
- **AC5 — Freeze-state aware.** It runs only against artifacts marked **frozen**; an un-frozen upstream artifact is itself a finding ("cannot check consistency against a moving target — freeze the PRD first"), not a crash.

## 3. Testable scenarios (PRD owns the list; tests mirror 1:1)

> Verification layer: all **integration** (Layer 4 — drive the skill over fixture artifact-sets, assert the report). No **E2E** tag: this is a doc-analysis skill with no browser/UI surface (justified, not omitted).

- **S1 — Clean chain (happy path).** A feature whose frozen PRD/design/impl-plan fully agree → report shows a complete traceability matrix, **zero findings**, verdict CONSISTENT. *Edge:* a PRD scenario covered by *two* design elements is fine (1:many), not a finding.
- **S2 — Dropped scenario (AC1 failure path).** PRD has scenario S3 with no design element → flagged **DROPPED (S3)**, points back to `design-review`. *Edge:* an E2E-tagged scenario present in design but with no impl-plan spine-E2E owner is flagged as a *partial* drop (test-layer coverage gap, reusing `impl-plan-review` Pass 3's rule).
- **S3 — Orphan layer (AC2 failure path).** impl-plan layer "add export-to-CSV" with no PRD scenario → flagged **ORPHAN**, asks "amend the PRD or cut the layer?" *Edge:* a layer justified by a design *failure-mode* (not a scenario) is traced to that, not flagged.
- **S4 — Contradiction (AC3 failure path).** PRD §out-of-scope says "no bulk import"; a design section specs bulk import → **CONFLICT** with both citations. *Edge:* a *resolved* contradiction (design notes "PRD amended 2026-06-06 to include X") is not flagged — it checks the amendment lineage.
- **S5 — Un-frozen upstream (AC5 failure path).** design.md is still a frozen-*candidate* → report refuses the cross-check and emits one finding: "design not frozen; freeze before consistency analysis." *Edge:* PRD frozen but design absent entirely → "design phase not started," not an error.

**S1.x compound note:** S1 is compound (builds the matrix *and* asserts zero findings) → decomposes into use-cases **S1.1** (matrix renders every scenario→design→layer row) and **S1.2** (verdict = CONSISTENT only when no DROPPED/ORPHAN/CONFLICT). Each gets ≥1 assertion.

## 4. Out of scope

- **Authoring or fixing artifacts.** It reports; it never edits a PRD/design/plan. (Reason: apex's author/review separation — a review skill that also authors blurs the voices.)
- **Semantic NLP "do these paragraphs mean the same thing" inference beyond cited, structural mapping.** It maps numbered scenarios ↔ named design elements ↔ named layers; it does not attempt free-text equivalence proofs. (Reason: keep it deterministic and citation-backed, not a hallucination surface.)
- **Cross-*feature* consistency** (does feature A's design contradict feature B's). V2. (Reason: per-feature first; cross-feature is a different blast radius.)
- **Replacing the vertical reviews.** It runs *in addition to* `prd-review`/`design-review`/`impl-plan-review`, never instead. (Reason: it checks *between* artifacts; the vertical gates check *within*.)
- **A graph database / persistent index.** The matrix is regenerated each run from the frozen markdown (ephemeral, per apex's structural-ephemeral rule). (Reason: no ambient cost.)

## 5. Unknowns (design phase resolves)

- **U1 — Mapping anchor.** How do scenarios/elements/layers reference each other for a deterministic map? Options: the existing scenario IDs (S1, S2.1) + a "serves S2.1" convention already added to `impl-plan-review` Pass 3, vs. requiring explicit `<!-- maps: S3 -->` markers. Design must pick the lightest anchor that's already mostly present.
- **U2 — When it fires.** After design-freeze? Before impl? Both? And is it `[USER]`-invoked or an `[AUTO]` gate at a freeze boundary? (Leaning: an `[AUTO]` check at the impl-plan-freeze boundary + a `[USER]` command for on-demand.)
- **U3 — 1:many / many:1 tolerance.** AC1/AC2 must allow one scenario→many layers and many scenarios→one shared layer without false ORPHAN/DROPPED flags. Design must define the matrix cardinality rules (mirrors the same problem solved for bead coverage in `docs/execution-tiers`).

## 6. Success metric

- **Leading (1–2 weeks):** On features run through the full chain, the analyzer runs at the impl-plan-freeze boundary and its DROPPED/ORPHAN/CONFLICT counts are recorded; target = **0 un-analyzed freezes** on multi-artifact features.
- **Lagging (1–3 months):** Reduction in "spec drift" escapes — frozen-PRD scenarios that shipped missing, or shipped scope the PRD never asked for — caught at *review* time instead of in production/Copilot review.
- **Anti-metric (Goodhart):** "Zero findings" is gameable by mapping everything coarsely (one giant "covers all scenarios" layer). Paired guard: the matrix must show **per-scenario** rows (granularity ≥ scenario/use-case), so a coarse all-in-one mapping is itself visible as a smell.

## 7. Sequencing / dependencies

- **Upstream (must exist):** `prd-review` Pass 2 scenario IDs + use-case decomposition — **shipped (0.3.2)**; `impl-plan-review` Pass 3 layer→scenario lineage — **shipped (0.3.2)**. *This feature is only buildable because that traceability metadata now exists* — it consumes exactly what those passes produce.
- **Downstream:** could feed `spec-view` (render the matrix); shares the cardinality solution with the `docs/execution-tiers` bead-coverage audit (same shape — consider a shared rule).

## 8. Existing-product overlap scan

- **`test-coverage-audit` Pass 1** — checks PRD-scenario ↔ *test* 1:1. The closest overlap. **Distinct:** that maps spec→*tests*; this maps spec→*design*→*plan*. They're the same *mirror discipline* at different artifact pairs. Risk: don't duplicate — the analyzer should *reuse* Pass 1's scenario-enumeration logic and extend it one hop upstream (design/plan), not re-implement it. **Explicit reuse, not a parallel path.**
- **`impl-plan-review` Pass 3** — produces the layer→scenario lineage the analyzer reads. Producer/consumer, not overlap.
- **`spec-view`** — renders artifacts; could render this matrix later. No V1 overlap.

Verdict: one real adjacency (`test-coverage-audit`), addressed by reuse.

## 9. OSS-alternatives scan

- **GitHub Spec Kit `/analyze`** — **use as reference** (the direct inspiration); it cross-checks spec↔plan↔tasks. apex's version generalizes to its own chain and reuses existing scenario IDs. Not adoptable directly (it's a different plugin's command).
- **Requirements-traceability-matrix tooling** (classic RTM / DOORS) — **reference, reject adoption** — heavyweight enterprise RM tools; apex's matrix is an ephemeral markdown render, not a managed database.
- **OpenAPI/contract diff tools** — **reference** — relevant only for the API-shape slice; `api-surface-review` owns that.

Adversarial miss check: no widely-adopted lightweight "cross-artifact consistency" OSS exists for prose SDLC artifacts — the gap is real and Spec Kit is the only close prior art.

---

## Freeze marker

**Frozen as of:** _pending user sign-off._ Frozen-candidate: passed `prd-review` (`prd-review.md`); adversarial findings resolved here or recorded as U1–U3. Authored, not frozen, until the user marks it — then `apex:design-feature` may begin.
