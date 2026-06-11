# impl-plan — `agent-rails`

**Status:** DRAFTED — awaiting `impl-plan-review` + user sign-off · **Upstream:** `design.md` (FROZEN, PR #28)
Carries D5 (1:1 test mirror incl. negative fixtures). Every layer names the scenario(s) it `serves`. Reversibility stated per layer.

---

## Layering principle

Five layers, each an independently revertible PR ≤ ~400 LOC, sequenced so **the tools exist before the skill amendments that call them** (a dangling `state_tool.py freeze` instruction in a skill, with no script behind it, is the failure to avoid). The feature dogfoods itself: `docs/agent-rails/state.json` already exists (written at design freeze) and its `design`/`impl-plan` entries advance as these layers land.

## Layer 1 — `state_tool.py`: the state record + reporting

**Serves S1 (S1.1–S1.3), S3.** The core CLI, no lint yet.

- `skills/agent-rails/reference/state_tool.py` (stdlib `json`/`hashlib`/`os`): subcommands `init <dir>` (all-`draft`, never frozen), `report <dir>` (status + computed flags + current phase + next gate — registry join stubbed to "registry not loaded" until L3), `freeze <dir> <artifact> --gate --signoff` (writes the transition; **lint call is a no-op stub** wired in L2).
- Atomic write: temp file in the same dir + `os.replace`.
- Flag computation (read-time, never stored): `DIVERGENCE` (prose vs state — stub until prose-scan, see note), `POST-FREEZE-DRIFT` (stored sha256 ≠ current file hash), `MALFORMED-TRANSITION` (status `frozen` missing any evidence field).
- **Tests (mirror 1:1):** S1.1 phase named · S1.2 statuses+hashes listed · S1.3 next-gate (against a fixture registry) · S1-edge UNMANAGED on missing state.json · S3 freeze writes gate/at/sha256 · S3-edge torn-write (kill between temp+replace → original intact, via a monkeypatched `os.replace` that raises).
- **Reversibility:** new files only; revert = delete the dir. No consumer yet.

## Layer 2 — `freeze_lint.py` + wire it into `freeze`

**Serves S2, S7.** The shape gate; makes `frozen` unreachable without passing shape.

- `reference/freeze_lint.py <artifact-type> <file>` → exit 0 | named-defect list. Anchor sets per the design §4 table (prd/design/impl-plan/adr); regexes **lifted from `cross-artifact-consistency`'s frozen design** (cite the file in a comment).
- `state_tool.py freeze` now calls the lint **before** writing — refusal leaves state unchanged (S2), names file+missing-anchor.
- **Tests:** S2 PRD missing scenario IDs + out-of-scope → refused, both defects named, state unchanged · S2-edge lint-clean but `--signoff` empty → still refused (independence of conditions) · S7 hand-edited `frozen` with missing evidence → MALFORMED-TRANSITION · S7-edge well-formed forgery (all fields present, hash matches) → **accepted by lint, asserted as documented boundary** (the test encodes the boundary, not a bug).
- **Reversibility:** revert restores the L1 no-op stub; freeze still works, minus shape enforcement.

## Layer 3 — `gates.json` + `registry_check.py` + report join

**Serves S5, S6.** The registry and its FLOW.md conformance.

- `gates.json` at repo root — authored from FLOW.md's current matrix (every ✓ row + side-path skill), schema per design §5 (`requires_frozen` the load-bearing field).
- `reference/registry_check.py`: parses FLOW.md's matrix block + side-path list, asserts set-equality with `gates.json` membership, **fails both directions naming the row**; a parse failure exits non-zero (fail-closed).
- `state_tool.py report` registry-join completed: next-gate + `requires_frozen`-unsatisfied = STOP (S5); no-entry pair → "no gate registered" (S5-edge).
- **Tests:** S5 "entering IMPL" → blocking+advisory listed · S5-edge unknown pair → explicit no-entry · S6 matrix row absent from gates.json (and reverse) → check fails naming row both ways · S6-edge FLOW.md matrix unparseable → non-zero (fail-closed).
- **Reversibility:** revert removes the registry; `report` falls back to the L1 "registry not loaded" line. Self-contained.

## Layer 4 — CI conformance workflow

**Serves S6 (enforcement), D5 (CI runs the suite).** Mirrors `.github/workflows/conformance-lint.yml`.

- `.github/workflows/agent-rails-conformance.yml`: on changes to `skills/agent-rails/**`, `gates.json`, `FLOW.md` — run the pytest suite (L1–L3 tests incl. negative fixtures) + `registry_check.py`. `permissions: contents: read`, pinned actions, job timeout (the `cicd-review` discipline this very repo now ships — dogfood it).
- **Tests:** the workflow IS the test runner; a meta-fixture asserts `registry_check.py` exits non-zero on a deliberately-drifted `gates.json` copy (so a green CI can't mask a broken check).
- **Reversibility:** revert removes the workflow; nothing else depends on it.

## Layer 5 — the seven skill amendments + SKILL.md + MAINTAINING.md

**Serves the design's §7 + F5 (state gets written, or it rots).** Pure prose/wiring; the tools all exist now (why it's last).

- `skills/agent-rails/SKILL.md` — the discipline: the STOP-on-`requires_frozen` rule at phase transitions/resume, the two lint contract lines, the per-type anchor table, JSON-not-TOML rationale.
- One-line freeze-record step appended to: `prd-review`, `design-review`, `impl-plan-review`, `adr-review`, `architecture-design`. `project-bootstrap` P3 gains `state_tool.py init`. `cross-artifact-consistency` gains the UNMANAGED check (defect-taxonomy extension).
- `MAINTAINING.md` — the same-commit rule (D3): a gate's phase/freeze change touches `gates.json` + FLOW.md matrix together (CI enforces).
- README skill table + FLOW.md matrix row for `agent-rails` itself; help.md (no new slash command — **menu stays 17**, grep-verified).
- **Tests:** S4 covered here once a real prose-scan exists — S4(a) prose FROZEN vs state draft → DIVERGENCE, canonical=state · S4(b) post-freeze edit → POST-FREEZE-DRIFT (this rides on L1's hash flag + the amendment that the skills re-hash on read). *(Note: S4's prose-scan is the one cross-layer scenario; its DIVERGENCE half needs the SKILL.md to define where prose markers are read — landed here, tested here.)*
- **Reversibility:** revert removes the wiring; the tools remain, inert (no skill calls them) — the safe direction.

## Test plan summary (D5 — 1:1, negatives explicit)

| Scenario | Layer | Negative/edge fixture |
|---|---|---|
| S1.1–S1.3, S1-edge | L1 | UNMANAGED (no state.json) |
| S3 | L1 | torn write (os.replace raises) |
| S2 | L2 | refused + state unchanged; lint-clean-no-signoff |
| S7 | L2 | MALFORMED-TRANSITION; well-formed-forgery boundary |
| S5 | L3 | no-entry pair |
| S6 | L3/L4 | unparseable matrix (fail-closed); drifted gates.json |
| S4(a)/S4(b) | L5 | DIVERGENCE; POST-FREEZE-DRIFT |

Every PRD scenario owns ≥1 named test; every negative path (forgery, torn write, drift, parse failure) is a fixture, not an assumption. No E2E (no UI — PRD §3 justification holds).

## Rollout / sequencing

Strictly L1→L5 (each consumes only earlier layers). Expand-only — no destructive migration (new files + append-only skill edits); `gates.json` and `state.json` are new artifacts, not schema changes over existing data. The dogfood `state.json` advances `design: frozen` / `impl-plan: in-review` as this plan freezes.

---

## Freeze marker

**Frozen as of 2026-06-11** (user sign-off = merge of PR #29). Passed `impl-plan-review` (`impl-plan-review.md`); P1–P2 resolved, P3 carried to L5. Scope changes now require an explicit amendment. Building (L1) may begin. Machine record: `state.json` beside this file.
