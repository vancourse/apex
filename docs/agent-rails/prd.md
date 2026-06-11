# PRD — `agent-rails` (machine-decidable pipeline state + freeze enforcement + gate registry)

**Status:** DRAFTED — awaiting user sign-off to freeze · **Slug:** `agent-rails`
Dogfood: authored then cold-audited (`prd-review.md` beside this file). Source: `docs/research/full-lifecycle-roadmap.md` agent-first audit, findings 1–3.

---

## 1. Problem

apex's purpose is to let a coding agent produce production-strength code **autonomously** — but its discipline is prose consumed by an attentive model. Three structural weaknesses follow, and all three bite hardest exactly when nobody is watching:

1. **Pipeline state lives in prose.** "Is this PRD frozen? What phase is this feature in? What gate is next?" is answered today by reading `❄️ FROZEN 2026-06-06` in a doc header. A fresh session (or a second agent) must re-derive pipeline position from conversation context it does not have. Resumability — the autonomy primitive — is undecidable.
2. **Freeze is advisory.** Nothing blocks writing `FROZEN` onto a PRD with no scenario IDs, no layer tags, no out-of-scope section. The gate skills *describe* the required shape; no decidable check *enforces* it at the transition. An agent under context pressure can (and eventually will) freeze a malformed artifact, and every downstream gate then builds on sand.
3. **Gate routing is keyword-regex + English.** The `suggest-skill-*` hooks pattern-match prompt/path strings; each skill's firing condition is prose. Wrong phrasing → silent gate miss. There is no machine-readable answer to "entering phase X with artifact Y — which gates MUST have run, and which fire now?"

One capability closes all three: **machine-decidable pipeline state, with enforcement at the freeze transitions, routed by a queryable gate registry.**

## 2. Goal & acceptance criteria

Three thin components, files-not-daemons, stdlib-only (the `detect-stack` precedent):

- **C1 — Feature state:** per-feature `docs/<slug>/state.json` — each artifact's status (`draft` / `in-review` / `frozen`), which gate set it, when, and a content hash of the artifact at freeze. Gates write it; sessions resume from it.
- **C2 — Freeze lint:** a decidable artifact-shape check that **gates the `frozen` transition** — PRD: scenario IDs + layer tags + out-of-scope + unknowns sections present; design: `realizes S#` tags; impl-plan: `serves S#` lineage per layer. Shape only — it never substitutes for the review skill's content judgment.
- **C3 — Gate registry:** `gates.json` — skill → phase → firing condition → blocking-or-advisory, the machine-readable twin of FLOW.md's Skill × Phase matrix, consumed by hooks and by the agent at phase transitions, with a CI conformance check against the matrix (the `autonomous-fix` lint pattern).

**Acceptance criteria (observable):**

- **AC1 — Resumability.** A fresh session with zero conversation context determines, by file reads alone: the feature's current phase, every artifact's freeze status, and the next required gate. No prose parsing, no inference.
- **AC2 — One canonical status.** `state.json` is canonical for status; prose headers (`❄️ FROZEN …`) become rendered display. Divergence (prose says frozen, state says draft — or the artifact's hash no longer matches its frozen hash) is **decidable and flagged**, never silently resolved.
- **AC3 — Freeze blocks on shape.** A `frozen` transition on an artifact failing its shape lint is **refused with named defects** (file + missing element), and state is unchanged. Lint-clean is necessary, not sufficient — user sign-off remains a second, independent condition.
- **AC4 — Tamper-evident, not tamper-proof.** A state entry hand-written without gate evidence (missing gate/timestamp/hash fields, or a hash that never matched the artifact) is detectable by the lint. (An agent with filesystem access can always edit a file; the rail is *evidence*, so `cross-artifact-consistency`/CI catches it — hard prevention stays with hooks and is out of scope.)
- **AC5 — Registry fidelity.** `gates.json` and FLOW.md's matrix cannot drift silently: a CI conformance check fails naming the divergent row. Adding a gate to one without the other is a red build, not a doc bug.
- **AC6 — Zero new ambient cost.** No daemon, no background watcher; scripts are stdlib-only Python (json/hashlib), atomic temp-file+rename writes; at most one new hook pattern-match.

## 3. Testable scenarios (PRD owns the list; tests mirror 1:1)

> Verification layer: all **integration** (Layer 4 — drive the reference scripts over fixture feature-directories, assert outputs). No **E2E** (no UI surface; justified).

- **S1 — Cold resume (happy path; compound → use-cases below).** A fixture feature with frozen PRD + drafted design; a fresh invocation reads `state.json` (+ `gates.json`) and reports phase, statuses, next gate. *Edge:* a feature directory with artifacts but NO `state.json` (pre-rails feature) → explicit "unmanaged — run the init" answer, never a fabricated status.
  - **S1.1** — current phase named (design, because PRD frozen + design unfrozen).
  - **S1.2** — every artifact's status + frozen-hash listed.
  - **S1.3** — next required gate named from the registry (`design-review`), not from prose.
- **S2 — Freeze refused on shape (AC3 failure path).** A PRD missing scenario IDs and the out-of-scope section → the freeze transition is refused; output names both defects with file+section; `state.json` unchanged. *Edge:* lint-clean PRD but no user sign-off recorded → still refused (the two conditions are independent; lint cannot manufacture sign-off).
- **S3 — Gate writes state atomically (AC6).** `prd-review` completes clean + sign-off → transition written via temp+rename with gate name, timestamp, artifact sha256. *Edge:* simulated crash between temp-write and rename → original `state.json` intact (no torn state).
- **S4 — Divergence flagged (AC2).** *(a)* prose header says FROZEN, state says `draft` → DIVERGENCE flagged, canonical (state) named, route = re-run the gate. *(b)* artifact edited after freeze (hash mismatch) → POST-FREEZE-DRIFT flagged, freeze marked stale, route = amendment per the freeze discipline. Neither auto-heals.
- **S5 — Registry routing (AC1/AC5).** Query "entering IMPL for feature X" → registry answers: blocking gates that must already be satisfied (`impl-plan-review` frozen) + advisory gates that fire in-phase. *Edge:* artifact/phase pair with no registry entry → explicit "no gate registered," never a guess.
- **S6 — Registry drift fails CI (AC5).** Fixture: a matrix row exists in FLOW.md with no `gates.json` entry (and the reverse) → the conformance check fails naming the row, both directions.
- **S7 — Tampered state detected (AC4).** `state.json` hand-edited to `frozen` with no gate evidence (missing fields / hash never matched any commit of the artifact) → lint flags MALFORMED-TRANSITION. *Edge:* a *well-formed forged* entry (all fields present, hash matches current file) is **accepted by the lint and acknowledged as such** — tamper-evidence has a stated boundary (see §4); the test asserts the boundary is documented behavior, not a silent hole.

## 4. Out of scope

- **Hard prevention of state self-edit.** Filesystem-level agents can always write files; we ship tamper-*evidence* (AC4), and the existing hard-block hooks keep owning destructive-action prevention. (Reason: honest rail — a fake lock is worse than a stated boundary.)
- **Multi-feature / executor orchestration state.** Which bead/agent is executing what is `docs/execution-tiers/` territory (status is executor-owned there; scope is apex-owned). `state.json` records **gate state**, not execution status. (Reason: the boundary that design already froze.)
- **A workflow engine / daemon / watcher.** State is files; gates update them when they run. (Reason: zero ambient cost — AC6.)
- **Backfilling history for existing features** (`docs/autonomous-fix/` etc.). Forward-only; an `init` for unmanaged features covers adoption (S1 edge). (Reason: no archaeology busywork.)
- **Replacing FLOW.md.** The prose + ASCII stays for humans; the registry is the machine twin, consistency-checked (U1 decides which is authored). (Reason: both consumers matter; CHANGELOG-style dual audience.)
- **Pass-level result storage in state.json.** Review findings stay in the prose review docs; state holds status + evidence only (U2 bounds the schema). (Reason: state file stays small enough to read every session.)

## 5. Unknowns (design phase resolves)

- **U1 — Registry authorship direction.** Hand-author `gates.json` and CI-check the FLOW.md matrix against it? Parse the matrix to generate the registry (ASCII parsing is fragile)? Author registry → render matrix? Leaning: **`gates.json` is authored, FLOW.md matrix is checked against it** (parse-for-verification is read-only and failure-tolerant; parse-for-generation is not).
- **U2 — State schema minimality.** Exact fields per artifact entry. Leaning: `{status, gate, at, sha256, signed_off_by}` and nothing else; everything richer lives in prose.
- **U3 — Sign-off representation.** Freezes require user sign-off; how is that recorded without the agent being able to fabricate it convincingly? (A `signed_off_by` field the agent types is weak evidence; a hook-mediated confirm is stronger.) Design must pick the honest option and state its strength.
- **U4 — Lint execution points.** Hook (fast shape check on state.json edits) vs in-skill (full lint before a gate proposes freeze) vs CI (conformance) — likely all three, thin; design must define what runs where so nothing is double-owned.
- **U5 — Hook consumption of the registry.** Do `suggest-skill-*` hooks read `gates.json` at fire time (jq dependency, per-edit cost) or stay regex with the registry as the agent-facing surface only? Design must measure the hook-latency budget.

## 6. Success metric

- **Leading (first dogfood cycle):** every new feature chain under `docs/` gets a `state.json` written by its gates, and the **cold-resume test passes**: a fresh session answers phase/next-gate for a live feature by file read alone (S1 run against real artifacts, not fixtures).
- **Lagging (1–3 months):** **zero advanced-past-unfrozen events** (no design started on an unfrozen PRD, no impl on an unfrozen plan) in dogfooded work — previously only detectable by humans reading prose; and ≥1 real freeze-refusal where the lint catches a genuinely malformed artifact (the rail earns its keep or it's ceremony).
- **Anti-metric (Goodhart):** shape-lint strictness is gameable by stub content (three one-word scenarios pass the ID check). Guard: the lint is **shape-only by contract** and `prd-review`'s content judgment remains the freeze's other half — a lint-clean artifact that fails review still doesn't freeze (AC3's "necessary, not sufficient").

## 7. Sequencing / dependencies

- **Upstream (shipped):** `cross-artifact-consistency` (already parses scenario IDs / `realizes` / `serves` tags — C2 reuses its extraction one level shallower) · `detect-stack` (stdlib + atomic-write + no-secrets file discipline) · `autonomous-fix` conformance-lint (the CI lint pattern C3 copies) · FLOW.md matrix (C3's content source).
- **Downstream:** `project-bootstrap` writes the initial `state.json` for new features · `council-review` / `adversarial-pair` read state to verify freeze preconditions before convening · the wave-2 model-routing table would live beside the registry if/when built.

## 8. Existing-product overlap scan

- **`cross-artifact-consistency`** — checks frozen artifacts still *agree*; `agent-rails` records/enforces what *is* frozen. The shape lint reuses its ID/tag parsing; divergence detection (S4) extends its defect taxonomy (DIVERGENCE / POST-FREEZE-DRIFT beside DROPPED / ORPHAN / CONFLICT). Producer/consumer, explicit reuse — not a second consistency engine.
- **`detect-stack` / `apex.profile.toml`** — project-level *tool routing*; `state.json` is feature-level *pipeline position*. Orthogonal axes, same file discipline.
- **`spec-view`** — renders artifacts for human freeze judgment; state is the machine record of that judgment. Complementary ends of the same gate.
- **Gastown beads** — execution status, executor-owned (frozen boundary in `docs/execution-tiers/`). Gate state ≠ execution status; stated in §4.

Verdict: no parallel path; both reuses are explicit.

## 9. OSS-alternatives scan

- **GitHub Spec Kit** (`spec.md` task tracking, `/analyze`) — **reference**: validates the spec-state instinct, but tracks authoring tasks, not freeze-gated state machine transitions with evidence. apex's freeze-as-contract has no Spec Kit equivalent.
- **beads (`bd`)** — **reference, reject for this**: dependency-aware *work-item* state, executor-side; adopting it here would re-cross the execution-tiers boundary deliberately frozen apart.
- **Workflow engines (Temporal, LangGraph checkpoints)** — **reject**: daemons/infra for runtime orchestration; apex state is three JSON files and a lint (AC6).
- **`git` itself (tags / notes as freeze markers)** — **considered, reject**: git notes don't survive normal clones/pushes by default and are invisible in review diffs; a committed `state.json` is reviewable, diffable, and travels with the repo.

Adversarial miss check: every surveyed tool stores either *task* state or *runtime* state; none stores **review-gate** state with tamper-evident freeze evidence — which is the load-bearing novelty here, and why this is built rather than adopted.

---

## Freeze marker

*Not yet frozen.* Awaiting: `prd-review` cold audit (beside this file) + user sign-off. Scope changes before freeze are normal edits; after freeze, explicit amendment.
