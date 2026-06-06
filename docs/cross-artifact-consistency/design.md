# Design — Cross-artifact consistency analysis

**Status:** drafted (awaiting `design-review` → freeze) · **Slug:** `cross-artifact-consistency`
**PRD:** `prd.md` (FROZEN 2026-06-06). Adversarial re-pass in `design-review.md`.

## Shape (one paragraph)

A read-only **`consistency-analysis` skill** (SKILL.md, no new slash command — fired like other review gates + invokable by name). It loads a feature's frozen `prd.md` / `design.md` / `impl-plan.md`, extracts three node sets — **PRD scenarios/use-cases** (IDs `S1`, `S2.1`), **design elements** (section headings + their `realizes S#` tags), **impl-plan layers** (their `serves S#` lineage from `impl-plan-review` Pass 3) — builds a **traceability matrix** over them, and emits findings: **DROPPED** (scenario with no design/plan owner), **ORPHAN** (element/layer with no scenario ancestor), **CONFLICT** (incompatible claims, cited). It writes only its report and routes each finding to the upstream gate to re-open.

## Pass 1 — Scenarios

Reuses the PRD's S1–S5 (the operator running the analyzer over a feature's artifact set). The load-bearing addition design-side: the **matrix is the primary artifact**, findings are derived from it. *Adversarial (answered in review):* a scenario covered by a *design failure-mode* rather than a numbered scenario — handled by treating design failure-modes and threat-model entries as valid ancestors, not just scenarios.

## Pass 2 — MVP cut

1. **Loader + freeze-check** — read the three frozen artifacts; if any is a frozen-*candidate* or absent, emit the AC5 finding and stop (no partial matrix).
2. **Node extraction** — scenarios/use-cases from `prd.md` (the `S#`/`S#.#` IDs), design elements from `design.md` headings + `realizes S#` tags, layers from `impl-plan.md` `serves S#` lines.
3. **Matrix + three checks** — forward (DROPPED), backward (ORPHAN), and **structural CONFLICT** scoped to the one deterministic case: a node the PRD marks *out-of-scope* that a design/plan node realizes.
4. **Report + routing** — a markdown matrix (scenario → design → layer rows) + a findings list, each naming the gate to re-open.

That's MVP. Everything else defers.

## Pass 3 — Deferral list

- **Free-text CONFLICT detection** beyond the out-of-scope case (V2) — *trigger:* false-negatives where two artifacts disagree on a data shape in prose. MVP catches the highest-value contradiction (scope) deterministically; broader semantic conflict risks the hallucination surface the PRD scoped out.
- **`spec-view` rendering of the matrix** (V2) — *trigger:* operators wanting the visual.
- **Cross-feature consistency** (V2) — *trigger:* features sharing a contract.
- **Auto-suggesting the fix** (rejected, maybe never) — it routes to a gate; it never proposes the edit (preserves read-only).

*Adversarial check:* none of these hot-fix-bite — MVP is correct, just narrower on CONFLICT.

## Pass 4 — Integration with existing surface

Reuses, does not duplicate:
- **`test-coverage-audit` Pass 1** scenario-enumeration logic — the analyzer extends it one hop upstream (spec→design→plan) instead of re-implementing scenario parsing (≥2-primitive reuse #1).
- **`impl-plan-review` Pass 3** `serves S#` lineage — consumed directly as the layer→scenario edges (reuse #2).
- **`prd-review` Pass 2** scenario IDs / use-case decomposition — the node namespace.
- **`FLOW.md` docs convention** — where to find the three artifacts (`docs/<slug>/`).

**Mapping anchor (resolves U1):** **reuse the IDs that 0.3.2 already produces** — `S#` in the PRD, `serves S#` in layers — and add **one light convention**: a design.md section may carry a `realizes S#` tag (heading suffix or inline). A design element with *no* `realizes` tag and no failure-mode/threat-model anchor is an ORPHAN finding — which is the intended signal, so the convention is self-enforcing (you're not required to tag; untagged = flagged). No new marker syntax, no `<!-- maps -->` comments.

**Invariants preserved:** read-only (never edits an artifact); **ephemeral** (matrix regenerated each run from frozen markdown, never stored as truth — apex's structural-ephemeral rule). **Invariant not broken:** it runs *in addition to* the vertical reviews, never replacing them.

## Pass 5 — Failure modes (user-visible behavior)

- **An artifact absent** (design not started) → "design phase not started for <slug>" — not an error, a status.
- **Un-frozen upstream** → AC5 finding: "freeze <artifact> before consistency analysis"; no partial matrix.
- **Old PRD with no scenario IDs** (pre-0.3.2 authoring) → "no scenario IDs found — re-run `prd-review` Pass 2 to enumerate/number scenarios"; degrade, don't crash.
- **Malformed `serves S#` lineage** (cites a scenario that doesn't exist) → flagged as a CONFLICT ("layer serves S9 but PRD has no S9").
- **Huge feature** (dozens of scenarios) → matrix paginates by scenario; per-scenario rows preserved (the anti-metric guard).

## Pass 6 — Attack surface (STRIDE-lite)

Minimal but non-zero: the skill **reads files by feature slug**. *Tampering/Info-disclosure:* a malicious slug could attempt path traversal (`../../etc`). *Mitigation:* resolve only within `docs/<slug>/`, reject slugs with path separators. No external input, no network, no PII (operates on the repo's own design docs). No auth surface. Heavier threat-model not warranted (stated, not silent).

## Overlap + OSS
Audited from PRD §8/§9: the one adjacency (`test-coverage-audit`) is reuse; Spec Kit `/analyze` is the reference. No synonym-grade internal duplicate; no missed lightweight OSS.

## U-resolutions
- **U1 — RESOLVED:** reuse existing `S#` + `serves S#`; add only an optional `realizes S#` design tag; untagged design elements self-flag as ORPHAN (no required new syntax).
- **U2 — RESOLVED:** ships as a SKILL (no new slash command); fires `[AUTO]` at the **impl-plan-freeze boundary** and is invokable by name on demand. Menu stays lean.
- **U3 — RESOLVED:** matrix is **1:many / many:1 tolerant** — DROPPED = scenario with 0 owners; ORPHAN = node with 0 ancestors; coverage needs ≥1 each. Same cardinality model as the `docs/execution-tiers` bead-coverage audit (candidate shared rule).

## Hand-off
On `design-review` freeze → `impl-plan` (the skill is small: a parser + matrix + report; likely a 1–2 layer stack). Run `api-surface-review` on the report format if it becomes a consumed artifact (e.g. by `spec-view`).
