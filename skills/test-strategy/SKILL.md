---
name: test-strategy
description: The methodology layer for how to test — what tests live at which layer (8-layer model), which CI tier runs them, what to mock (and where), how to isolate (transaction rollback / per-test budget), how to fixture (static / golden / per-test), how to record external services (VCR-style replay), what NOT to do (anti-goals), plus the 17 language-agnostic test design rules. Distinct from language-specific tooling rules (those live in apex:python-review/rules/testing.md and apex:typescript-review/rules/testing.md). Distinct from per-PR test audits (apex:test-coverage-audit). Fires when planning tests for a layer, auditing the test architecture for a feature, or routing test-design decisions. Keywords: test strategy, test architecture, test layers, test pyramid, mocking discipline, fixtures, CI tiering, transaction rollback, recorded fixtures, scenarios.
---

# Testing Strategy

The methodology layer for how to test. This skill answers:

- *Which layer should this test live at?* → 8-layer model
- *What can/can't I mock here?* → mocking policy per layer
- *Which CI tier runs this?* → tiering rules
- *How do I isolate it?* → transaction rollback + per-test budget
- *What fixture pattern?* → static / golden / per-test transactional
- *How do I handle real external services in CI?* → recorded fixtures (VCR-style)
- *What rules govern test shape?* → the 17 methodology rules

What this skill is **not**: language-specific tooling guidance. For Python tooling (pytest, MagicMock vs stubs, async fixture typing) → `apex:python-review/rules/testing.md`. For TS tooling (Vitest, MSW, RTL, TanStack Query test helpers) → `apex:typescript-review/rules/testing.md`. For Playwright specifics → `apex:typescript-review/rules/playwright-e2e.md`. For per-PR test coverage audit → `apex:test-coverage-audit`.

## When to invoke

- During **IMPL PLAN** phase — `apex:impl-plan-review` Pass 3 (test plan per layer) routes here for the layer model
- During **IMPLEMENT** phase — when about to write a test, this skill's routing table tells you which layer
- When auditing whether the test architecture for a feature is sound
- When mocked-test proliferation is suspected and you need the layer-discipline rules to push back

## Principles

1. **Each concern lives in exactly one layer.** No mocked-DB router test that "kind of" verifies tenancy. No service test that re-asserts what a unit test already proved. Push a concern up the pyramid only if the cheaper layer genuinely cannot exercise it.
2. **"Real" means real.** No DB mocks at the service layer. No `query_one` mocks. The only layer where mocks are acceptable for *internal* boundaries is the router-contract layer — and only for thin "the right service was called" checks.
3. **Catch each bug in the cheapest layer that can catch it.** RLS bugs need a real Postgres with the non-priv role. Render bugs need a browser. Pure math bugs need a unit test. Don't push correctness up the pyramid; you'll pay 10–100× the runtime for the same signal.
4. **Recorded fixtures over live external calls in CI.** A weekly drift suite re-validates the recordings against real upstream. PR-tier and cron-tier use the replay; only the weekly drift hits the network.
5. **Static reference data lives in migrations, not fixtures.** Per-test seed is transactional and rolled back.

## The 8-Layer Model

Each layer has exactly one concern, one mocking policy, one home in the repo, one CI tier.

| # | Layer | Tests | Mocking | Typical CI Tier |
|---|---|---|---|---|
| 1 | **Unit (pure logic)** | Pure functions: validators, parsers, math, deterministic rules, type narrowing | None — pure. If you need a mock, it's not a unit test. | PR |
| 2 | **Service (real DB)** | Service methods against real Postgres + RLS forced. Asserts: tenant isolation, transaction semantics, idempotency keys, audit-event emission, SQL constraint behavior. | External SDKs (LLM, payment, third-party HTTP) mocked at the SDK boundary. **No DB mocking.** | PR |
| 3 | **Router contract** | ≤3 tests per router: (a) auth required → 401, (b) happy path returns expected JSON shape + status, (c) the right service was called with the tenant id from the JWT. | Service layer mocked; router tests assert wiring only, not business behavior. | PR |
| 4 | **Backend API scenario** | One test per PRD scenario (`apex:prd-review` Pass 2). Drives the system through `/api/*` end-to-end with real DB + real services. | External SDKs use **recorded fixtures** (VCR-style replay). | 4h cron (or PR with `needs-heavy` opt-in label) |
| 5 | **Frontend component** | Components with non-trivial behavior — state, conditional rendering, user input | TanStack Query mocked (or MSW); API responses fixtured. | PR |
| 6 | **Spine E2E (browser)** | ~6 browser tests covering the critical user flow end-to-end (upload → process → review → approve → export, plus tenancy-via-UI). Real backend, real DB. | External SDKs fixtured at backend boundary. | 4h cron |
| 7 | **Visual scenario E2E** | ~15–20 browser tests where rendering specifically matters (drawer, override dialog, anomaly banner) | Same as spine. | Nightly cron |
| 8 | **Drift (real upstream)** | ~5 scenarios with real external SDKs on **pinned model snapshots / versions**. Detects upstream behavior change. | None — hits real upstream. | Weekly cron |

**Deletion implication.** Router tests that mock the DB and assert business behavior are doing the wrong job. They get folded into service tests with real DB. The router contract test gets ≤3 narrow assertions per router.

## Mocking policy per layer

| Layer | What can be mocked | What CANNOT |
|---|---|---|
| Unit | Nothing (pure logic) | If you reach for a mock, the test belongs at layer 2+ |
| Service (real DB) | True external SDKs at their boundary (LLM, Reducto, payment) | DB, ORM, internal services, validators, queue clients you implement |
| Router contract | The service layer (one mock per dependency) | Auth middleware, request validation, status-code propagation |
| Backend scenario | External SDKs via recorded fixtures | DB, services, the entire `/api/*` boundary |
| Frontend component | API responses (via MSW or `vi.mock` of the HTTP client) | React internals, child components (test through real composition), routing |
| Spine + Visual E2E | External SDKs fixtured at backend boundary | The browser, the framework, the API |
| Drift | None | Anything (the whole point is real upstream) |

**Mock budget per test:** more than 2 mocks in a single test = production code's boundaries are wrong. Fix the production seams first, then the test.

## CI Tiering

Six tiers (one with two trigger modes). PR is the only tier that blocks merge by default.

| Tier | When | Budget | Layers | External calls | Blocks merge |
|---|---|---|---|---|---|
| **PR** | Every PR + push to main | < 3 min | 1, 2, 3, 5 (Unit + Service + Router + FE Component) | Mocked at boundary | ✅ yes |
| **PR (path-triggered smoke)** | When LLM-prompt files or agent definitions change | < 30s added | 1–2 real-external smokes via free tier | Real (free tier, e.g. GitHub Models) | ✅ yes |
| **`needs-heavy` opt-in** | Per-PR by label | < 8 min | PR tier + 4h tier | Mocked + recorded fixtures | ✅ yes (when label set) |
| **4h cron** | Every 4h on main | < 10 min | All scenarios (layer 4) + spine E2E (layer 6) | Recorded fixtures | ❌ alerts |
| **Nightly cron** | Daily on main | < 25 min | 4h tier + visual scenarios (layer 7) + tenancy/concurrency stress | Recorded fixtures | ❌ alerts |
| **Weekly drift** | Weekly on main | < 5 min | ~5 drift scenarios (layer 8) | Real upstream, pinned snapshots | ❌ alerts |

**Why not gate merges on the 4h tier?** Merge-queue gating is ideal but requires GitHub merge-queue setup. The 4h cron is a lighter substitute that catches bugs within 4 hours of merge. Acceptable until you have paying users.

**PR runtime budget (target):** ~2–3 min total. Real DB at the service boundary adds ~10s vs mocks; the trade-off (more runtime, fewer bugs) is rejected because the bug class that real-DB tests catch (RLS / tenancy / idempotency) is the dominant class that reaches production.

## Test Isolation Patterns

- **Per-test transaction rollback.** Every service / scenario test runs inside a transaction that's rolled back at teardown (`BEGIN` on entry, `ROLLBACK` on exit). Service tests run at ~50–100/sec against a real DB.
- **One DB instance per CI run, not per test.** Service container stays. Migrations apply once at job start.
- **RLS forced for every test** (where applicable). Connect as the non-priv app role; tests fail loudly if RLS is misconfigured. Admin pool stays available for explicit DDL / cross-tenant setup but is greppable and rare.
- **Tenant fixture per test.** A fixture creates one tenant + minimal seed inside the rollback transaction, sets the tenant context var, yields. Cross-tenant tests use a `tenants(N)` factory.
- **Parallelism via test runners.** Service + unit tests run in parallel workers (e.g. `pytest-xdist`). Scenario tests run sequentially when multi-step flows rely on time ordering.
- **Per-test runtime budget.** Soft warn at 100ms, hard fail at 500ms. Drift gets caught immediately, not after the suite slows to 10 min.

## Pre-Seeded Data Layers

| Layer | Lifecycle | Used by |
|---|---|---|
| **Static reference data** (rate schedules, taxonomies, COA templates, enums) | Loaded by migrations. Never edited per-test. | Everything. |
| **Golden seed** (one canonical tenant + realistic batch with documents) | Code-generated, versioned with the schema. CI fails if migrations changed without the seed regenerating. | Spine E2E + a subset of scenario tests where building the world imperatively each time would be wasteful. |
| **Per-test transactional seed** (default) | Built inside the test's transaction. Rolled back at teardown. | Service tests, most scenario tests, tenancy / concurrency tests. |

**Bright-line rule:** scenario and E2E tests may *assume* the golden seed exists, but assertions are on **state changes** (delta), not on absolute counts read from the seed. Service tests use only the per-test transactional seed.

## Recorded Fixtures (VCR-style replay)

A helper at `tests/_fixtures/recorded.py` (or equivalent) records and replays external-service responses by content hash:

- **Key:** SHA-256 of the request payload (prompt + model + parameters for LLM; URL + body for HTTP).
- **Storage:** JSON files in `tests/_fixtures/data/<service>/<hash>.json`, committed to the repo.
- **Record mode:** `RECORD_FIXTURES=1 <test-runner>` hits real service and writes the fixture. Manual, intentional, gated.
- **Replay mode:** the default. Missing fixture → test fails loud (no silent network calls in CI).
- **Pre-commit guard:** any test file that imports the real external SDK at module load fails the lint check.

The weekly drift suite is the smoke alarm against fixture rot.

## Anti-Goals

Things explicitly **not** in scope, with rationale:

- **No coverage gates** (`--cov-fail-under=80`). Coverage is an output metric, not a quality gate. High coverage with all-mocked tests is worse than 60% real-DB coverage.
- **No mutation testing.** Useful but expensive; revisit at scale.
- **No contract-testing tool** (Pact, Schemathesis) when shared types (TS types generated from the API) + scenario tests cover the contract.
- **No alternative browser tooling.** One browser tool, one harness. Pick Playwright OR Cypress, not both.
- **No `pytest-testmon` / test-impact-analysis** until the 4h tier breaks 10 min. Premature optimization.
- **No custom fixture-generation UI or seed-management tool.** Code in `tests/_seed/` is canonical.

## Failure Modes & Mitigations

| Failure mode | Mitigation |
|---|---|
| Real-DB tests slow over time | Per-test runtime budget (warn 100ms, fail 500ms). Slowest-10 reporter on every run. |
| Recorded fixtures rot silently | Content-addressed by request hash so prompt/payload changes invalidate. Weekly drift suite is the smoke alarm. |
| Golden seed becomes load-bearing reality | Bright-line: scenario / E2E tests assert on **state changes**, never on absolute seed counts. |
| Browser-test flake erodes trust | Retry disabled in CI for cron tier; spine tier 1 retry max with flake counter. Tests flaking 3× / 30 days quarantined. Lint-enforce no `waitForTimeout`. |
| Mocked tests proliferate at the wrong layer | Pre-push lint flagging new tests in `services/` or `routers/` that mock the DB. CLAUDE.md rule: "if it mocks the DB, it must be pure-logic unit." |
| CI minutes balloon | Per-tier `timeout-minutes` in workflow config. Breaking budget is the trigger to add path-based selectivity. |

## The Methodology Rules

These 17 rules are language-agnostic. Language-specific tooling (pytest, Vitest, RTL) lives in `apex:python-review/rules/testing.md` and `apex:typescript-review/rules/testing.md`. Language-specific frameworks (Playwright) live in `apex:typescript-review/rules/playwright-e2e.md`.

### 1. Scenarios-First — List Use Cases Before Code

**When:** Starting work on any feature larger than a single helper.
**Rule:** Before writing code, enumerate the concrete user-flow scenarios the feature must handle. Each scenario becomes one integration test. If you can't articulate the scenarios, the design isn't concrete enough — replan, don't code.
**Why:** Tests written after the code echo the code's structure; tests written from scenarios echo the user's intent. Catches the "tests pass but the feature doesn't do what it should" failure mode at design time.
**How to apply:**

- Scenario format: "User does X, system shows Y, with edge case Z."
- One scenario per acceptance-criterion line in the PRD / design doc.
- Every PR ships BOTH unit tests (fast, pure logic, mocks OK for external boundaries) AND integration tests (one per scenario, real components).

### 2. Integration Tests Use Real Components — Not Mocks

**When:** Writing a test that claims to cover end-to-end behavior.
**Rule:** Real DB (template-isolated per test, or fresh schema per test), real ORM, real validators, real external APIs where the feature actually touches them. Reserve mocks for true external boundaries (LLM providers, third-party APIs) and only at the unit layer below.
**Why:** Mocked integration tests have shipped real bugs because the mock confirmed the code-path while reality contradicted it. A test that mocks every collaborator verifies only that mocks were called, not that the system works.
**How to apply:**

- Per-test database isolation via template DBs (`CREATE DATABASE x TEMPLATE template_db`) or a fresh in-memory database per test.
- For LLM-touching features: use the real API with deterministic fixture inputs in CI; skip expensive runs as nightly-only when cost matters.
- Static analysis (mypy/pyright/eslint/tsc) is the cheap pre-check; integration tests are the load-bearing pre-check.
- If the test class mocks more than two collaborators, the production code's boundaries are wrong — fix those first, then the test.

### 3. PRD ↔ Integration Test Mirror

**When:** Implementing a feature whose PRD was reviewed via `apex:prd-review` (which enumerates testable scenarios at Pass 2).

**Rule:** Integration tests mirror PRD scenarios **1:1**:

- Every PRD scenario has **≥1 integration test** that exercises it end-to-end.
- Every integration test names which PRD scenario it covers (in the test name, docstring, or test-runner marker).
- A scenario without a test = the PRD is unverified at the implementation layer; that's a failing pre-PR check.
- A test without a PRD scenario = either the PRD is incomplete (amend it via a delta commit to the PRD) OR the test is gold-plating (delete it, or downgrade to a unit test).

**Why:** The PRD owns the scenario list. Integration tests are the verification artifact for those scenarios. Without this mirror invariant, scope drifts silently: the team builds features the PRD didn't ask for ("gold-plating"), or skips scenarios the PRD requires ("phantom coverage"). The mirror closes the spec-to-impl loop — `apex:prd-review` Pass 2 owns the list, `apex:impl-plan-review` Pass 3 owns the test plan per layer, and this rule is what makes those two upstream gates load-bearing rather than ceremonial.

**How to apply:**

- Name integration tests after PRD scenarios.
- Pre-PR check (also covered by `apex:test-coverage-audit` Pass 1): enumerate the PRD scenarios, grep for integration tests, verify 1:1 correspondence.
- If you need a test that doesn't fit any PRD scenario, ask: should this scenario be amended into the PRD? If yes, do that first; if no, the test is gold-plating — delete it or convert to a unit test (which doesn't claim end-to-end verification).
- For features where the PRD enumerates 8 scenarios but you only have 3 integration tests: that's not "we're partway done" — that's "the PRD says we shipped 8 things and we've actually shipped 3." Either ship the missing 5 or amend the PRD to reflect the actual scope.

### 4. Inject the Dependency, Don't Patch the Global

**When:** A unit needs the wall clock, a UUID, a random source, or any non-deterministic input.
**Rule:** Accept it as an argument with a sensible default. Tests pass an explicit value; production keeps its default. Avoid global-state patching (`freezegun`, `monkeypatch.setattr`, `vi.useFakeTimers`) unless injection is genuinely impossible.
**Why:** Injection makes the seam visible in the production signature, gives the test a precise assertion site, and keeps the test free of global-state side effects. Global patching is order-sensitive, cross-test-leaks, and obscures the production contract.

For language-specific examples, see `apex:python-review/rules/testing.md` and `apex:typescript-review/rules/testing.md`.

### 5. One or Two Mocks Maximum — More Means the Production API Is Wrong

**When:** Counting mock / patch calls in a single test.
**Rule:** More than two is a design smell — fix the production code first (clearer service boundaries, injectable collaborators), then the test. Don't add more mocks to make a broken test pass.
**Why:** Heavy mocking verifies only that mocks were called, not that the system works.

### 6. Don't Mock Internal Storage / File / Thread / Queue Layers

**Rule:** Reject tests that mock internal storage, file managers, thread pools, or queue clients when an in-process fixture (in-memory DB, `tmp_path`, real executor, in-process queue) would work. Mock only at true external boundaries (LLM providers, third-party APIs).

### 7. Don't Test Orchestration Through the REST Layer

**When:** Tempted to write an HTTP-level test for a pure function with mocked state.
**Rule:** Test the unit directly. Trust that the framework propagates exceptions to HTTP status codes — verify that once at the framework boundary, not per route.

### 8. Meaningful Tests — Assert Side Effects or Return Values

**When:** Writing any test.
**Rule:** Every test must assert a side effect (persisted state, emitted event) or a return value. Instantiating a class without asserting anything is banned. "It didn't throw" is not an assertion.

### 9. Write Tests in Terms of Domain Objects

**When:** Testing HTTP endpoints or service methods.
**Rule:** Create request payloads by instantiating validated domain objects (Pydantic in Python, Zod in TS) and serializing them. Parse responses by validating against the schema. Assert on domain objects, not raw dicts.
**Why:** Schema-validated payloads catch test-author typos at construction time. Type checkers / linters catch refactors. Raw-dict tests silently drift from the production contract.

For language-specific examples, see the language-review testing rule files.

### 10. Use Explicit Assertions — Not Type Casts

**When:** Tempted to write `typing.cast(bytes, result)` (Python) or `result as Buffer` (TS) in a test.
**Rule:** Use a runtime check that narrows the type: `assert isinstance(result, bytes)` / `if (!(result instanceof Buffer)) throw new Error(...)`. Validates runtime behavior, narrows the type for the type checker, and gives a better error message than a cast that silently lies.

### 11. Test Failure Modes Explicitly

**When:** Writing tests for a multi-step operation.
**Rule:** Ask "What if the DB drops?", "What if the task crashes?", "What if we get invalid input?", "What if the user lacks permission?", "What if the external API times out?" — add at least one failure-path test per operation. Map to `apex:design-feature` Pass 5 failure modes.

### 12. Generate Test Data Programmatically

**When:** A test needs large or structured data (CSV, JSON, time series).
**Rule:** Generate it in code. Only use fixture files when absolutely necessary; keep them under 1 MB. Ask "Can we generate this instead?" for anything larger.
**Why:** Generated data is grep-able, refactor-safe, and stays in sync with the schema. Files drift.

### 13. Test Conciseness — Quality Over Coverage Quantity

**Rule:** A few curated, high-quality tests beat a large block of boilerplate. Avoid 10–15 "do everything" tests that are hard to understand. Each test should have one or two clear assertions.

### 14. Fixture Consolidation — One Fixture per Logical Unit

**When:** Two fixtures share 90% of their setup.
**Rule:** Collapse into one tuple/object fixture. Let callers destructure what they need.

### 15. Update Mocks When Contracts Change

**When:** A code change makes a previously-optional artifact mandatory.
**Rule:** Update test mocks to provide the artifact. A mock that returns empty where production now raises makes tests lie. Same for the inverse: a mock that provides what production no longer returns hides regressions.

### 16. Idempotency Tests Must Read State Between Calls

**When:** Testing that `ensure_*` or `upsert_*` is idempotent.
**Rule:** Read state after the first call, then after the second. Assert the returned ID/identity is the same across both.
**Why:** Only checking the final state proves the second call didn't crash — not that it didn't create a duplicate.

### 17. Don't Assert on Log Strings — Assert on Behavior

**When:** Tempted to check `assert "Fast parse complete" in captured_logs`.
**Rule:** Assert on observable outcomes instead: return values, state changes, side effects. Log-string assertions break on copy edits with no functional change.

## Cross-references

- `apex:prd-review` Pass 2 — PRD owns the testable scenarios list (input to Rule 3)
- `apex:impl-plan-review` Pass 3 — test plan per layer (uses the 8-layer model from this skill)
- `apex:test-coverage-audit` — per-PR audit that this strategy's rules are met
- `apex:ai-pre-review-checklist` Step 6 (test quality) + Step 7 (consumer tracing) — pairs with this skill at PRE-PR phase
- `apex:python-review/rules/testing.md` — Python-specific tooling (pytest, MagicMock, async fixtures)
- `apex:typescript-review/rules/testing.md` — TypeScript-specific tooling (Vitest, MSW, RTL)
- `apex:typescript-review/rules/playwright-e2e.md` — Playwright-specific (selectors, state-based waits)
- Project-specific operational details (specific paths, role names, CI workflow names, real PR refs, custom layers) live in `<repo>/docs/testing.md` or equivalent.
