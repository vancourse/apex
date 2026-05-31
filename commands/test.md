---
description: "[USER] Focus apex:test-strategy on ONE test layer — map an industry term (unit/integration/smoke/e2e/component/visual/drift) or an apex layer name to the 8-layer model, then surface what to test there, what to mock, and which CI tier. Advisory router; does NOT run the suite."
argument-hint: "[unit|integration|smoke|e2e|component|visual|drift|service|router|scenario | 1-8]"
---

Route the user to the right layer of the apex **8-layer test model**, then invoke `test-strategy` focused on that layer. This command **advises** — it never executes tests. (The test runner is project-specific; running the suite lives in your project's CLAUDE.md / Makefile, not in this shareable plugin.)

**Requested layer (optional argument):** "$ARGUMENTS"

## 1. Resolve the argument to apex layer(s)

Map the argument (case-insensitive) using the table below. It mirrors the "what people mean by X" mapping already inside `test-strategy` — don't invent a different one.

| Argument (industry term / alias) | apex layer(s) | Layer (what lives there) |
|---|---|---|
| `unit`, `1` | 1 | Unit (pure logic) — validators, parsers, math, type narrowing. **No mocks**; if you need one, it's not a unit test. |
| `service`, `service-db`, `2` | 2 | Service (real DB) — tenant isolation, transaction semantics, idempotency, audit events, constraint behavior. External SDKs mocked at the boundary; **no DB mocking**. |
| `router`, `contract`, `3` | 3 | Router contract — ≤3 tests: auth → 401, happy-path JSON shape + status, right service called with the tenant id from the JWT. Service mocked (wiring only). |
| `integration` | 2 (narrow) **or** 4 (broad / API) | Ambiguous on purpose: narrow = one service + its real collaborators (L2); broad / API-level system test = drive `/api/*` end-to-end (L4). Default to L4 when the user says "API"; otherwise ask which collaborators are in scope. |
| `scenario`, `api`, `api-scenario`, `4` | 4 | Backend API scenario — one test per PRD scenario, real DB + real services, external SDKs via **recorded fixtures**. |
| `component`, `fe`, `frontend`, `5` | 5 | Frontend component — state, conditional rendering, user input. TanStack Query / MSW mocked; API responses fixtured. |
| `e2e`, `spine`, `6` | 6 | Spine E2E (browser) — ~6 critical-flow tests, real backend + real DB, external SDKs fixtured at the backend boundary. |
| `visual`, `7` | 7 | Visual scenario E2E — ~15–20 browser tests where rendering specifically matters (drawer, dialog, banner). |
| `smoke` | path-triggered smoke (PR) **+** 8 | Fast real-external smoke on PR when prompt/agent files change; the real-upstream / canary sense of "smoke" = Drift (L8). State both. |
| `drift`, `canary`, `8` | 8 | Drift (real upstream) — ~5 scenarios on **pinned** model snapshots/versions; weekly cron. Detects upstream behavior change. |

If `$ARGUMENTS` is **empty**, skip the focusing step: present the full 8-layer menu (this table) so the user can pick, then continue.

If the argument is **ambiguous** (e.g. bare `integration`), state both candidate layers and ask which collaborators are in scope before proceeding — don't guess.

## 2. Invoke test-strategy, focused on the resolved layer

Invoke the `test-strategy` skill from the apex plugin. Read its SKILL.md and, for the resolved layer, surface:

- **What belongs at this layer — and what does NOT.** Each concern lives in exactly one layer; push it up the pyramid only if the cheaper layer genuinely can't catch the bug.
- **Mock policy for this layer** (the per-layer mock table). Mock budget **≤2** — if you need more, the test is at the wrong layer.
- **CI tier** for this layer (PR / 4h / nightly / weekly drift) and whether it gates merge.
- **PRD-scenario linkage** if this is Layer 4 — one integration test per PRD scenario, named to the scenario it covers (`test-strategy` Rules 1 + 3).

## 3. Hand off to tooling + the red-green loop

- **Language tooling** to actually write the test: Python → `apex:python-review/rules/testing.md`; TS/React → `apex:typescript-review/rules/testing.md`; Playwright (L6/L7) → `apex:typescript-review/rules/playwright-e2e.md`.
- **The red-green loop itself** (write the failing test first → watch it fail → minimal code to pass → refactor) lives in **`superpowers:test-driven-development`** — apex defers the loop and owns only the layer placement + mock budget *around* it.
- **Before the PR**: the `test-coverage-audit` skill (PRD↔test 1:1 mirror, layer discipline, CI tier discipline, mock budget, failure-mode coverage).

## Usage examples

- `/apex:test unit` — what a pure-logic unit test should / shouldn't cover (and why no mocks)
- `/apex:test smoke` — path-triggered PR smoke vs. real-upstream drift (L8)
- `/apex:test e2e` — the ~6 spine browser tests + what to fixture at the backend boundary
- `/apex:test integration` — disambiguates narrow (L2) vs API-level (L4) before answering
- `/apex:test` — print the 8-layer menu, then pick a layer

## Notes

- This is a **router**, not an executor. To actually run tests, use your project's own command (e.g. `make test-unit` from the repo root) — that belongs in the project CLAUDE.md, not in this shareable plugin.
- The full methodology (all 17 rules, isolation patterns, recorded fixtures, CI tiering, anti-goals) is the `test-strategy` skill. This command is the per-layer front door to it.
