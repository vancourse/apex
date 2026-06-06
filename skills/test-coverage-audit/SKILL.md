---
name: test-coverage-audit
description: Pre-PR audit that verifies the test suite for this PR (or PR stack) actually covers the spec. 5 passes — PRD-scenario mirror, layer discipline, tier discipline, mock budget, failure-mode coverage. Distinct from apex:ai-pre-review-checklist Step 6 (which audits test QUALITY) and from apex:test-strategy (which is the methodology this audit verifies adherence to). Fires before opening a PR (or before declaring a PR stack complete). Keywords: test coverage, test audit, PRD mirror, layer discipline, mock budget, pre-PR test check.
---

# Test Coverage Audit

Pre-PR audit. Verifies the tests in this PR (or PR stack) match the methodology — PRD scenarios mirrored 1:1, tests at the right layer, the right CI tier, mock budget respected, failure modes covered.

Distinct from:

- **`apex:test-strategy`** — the methodology this audit verifies adherence to. Run that to learn / decide; run this to audit.
- **`apex:ai-pre-review-checklist`** Step 6 (test-quality review) — audits the *quality* of individual tests. This skill audits the *coverage* and *layer placement* of the test set as a whole.
- **`apex:python-review/rules/testing.md`** / **`apex:typescript-review/rules/testing.md`** — language tooling specifics.

## When to invoke

- About to open a PR (or the final PR in a layered stack)
- Auditing whether the stack's test coverage matches the PRD
- After `apex:ai-pre-review-checklist` Step 7 (consumer-tracing) — natural sequencing: consumers traced → coverage audited → PR opened

## The 5 audit passes

### Pass 1 — PRD ↔ Integration test 1:1 mirror

**Check:** Enumerate scenarios from `apex:prd-review` Pass 2 (the PRD's testable scenarios list). For each:

- Is there at least one integration test that names this scenario?
- Does the test exercise the scenario end-to-end (real DB, real services, recorded external fixtures)?

Then the reverse: list every integration test in the PR / stack diff. For each:

- Does it name a PRD scenario?
- If not, is the scenario missing from the PRD (needs amendment) or is the test gold-plating (delete / downgrade to unit)?

**Pass condition:** 1:1 correspondence between PRD scenarios and integration tests (with the understanding that one scenario can have multiple tests for different edges, but every scenario has at least one).

**E2E-tag check:** For every scenario tagged **E2E** in `apex:prd-review` Pass 2, confirm a **spine-E2E browser test** (Playwright, Layer 6/7 — see `apex:typescript-review/rules/playwright-e2e.md`) exists and names the scenario — *in addition to* its integration test. An E2E-tagged scenario with only an integration test is a coverage gap: the PRD called for browser-layer proof of that flow and it isn't there.

**Use-case assertion check:** Where a scenario was decomposed into sub-numbered use-case one-liners (`apex:prd-review` Pass 2), confirm each use-case has **≥1 named assertion** inside the scenario's test(s) — a scenario test that exercises the flow but never asserts `S2.2`'s rejection path leaves that use-case unverified even though the scenario "has a test." This is the assertion-level floor of the mirror; it only applies to scenarios that were actually decomposed (simple atomic scenarios have nothing to check here).

**Adversarial counter-pass:** Find a PRD scenario that the test set "almost" covers — the test exists but exercises a slightly different path. That's phantom coverage; flag it. Also: find an **E2E-tagged scenario** whose browser test asserts the API result but never drives the actual UI flow — that's an integration test wearing an E2E costume; the user-visible path is still unverified.

### Pass 2 — Layer discipline

**Check:** Walk through changed files. For each new or changed test, ask:

- Is it at the right layer per `apex:test-strategy`'s 8-layer model?
- Pure logic → unit (no mocks). Service with DB → service test with REAL DB (no `tenant_db` mock). Router → thin contract test (≤3 per router, no business behavior asserted there). User-visible flow → component test + spine E2E.

Look for the canonical anti-patterns:

- Mocked-DB service test asserting business behavior → must rewrite as real-DB service test
- Router test that mocks the service AND asserts business behavior → split into router-contract (mock service) + service test (real DB)
- Unit test that needs a mock → move to layer 2
- Scenario test that only covers the happy path → add the edge case explicitly (per `apex:design-feature` Pass 5)

**Pass condition:** Every test is at its correct layer per the 8-layer model. No layer-confused tests.

**Adversarial counter-pass:** Find a test that "works" but is at the wrong layer. Push it up or down. If the work to move it is non-trivial, log it as tech debt with a ticket — don't ship with the layer confusion silent.

### Pass 3 — Tier discipline

**Check:** Every test in the PR diff explicitly belongs to a CI tier per `apex:test-strategy`'s tiering rules (PR / `needs-heavy` opt-in / 4h cron / nightly / weekly drift).

- Heavy tests (real LLM, browser-driven, fixture > 5MB, runtime > 500ms) don't block PR
- PR-tier tests respect the per-test runtime budget (warn >100ms, hard fail >500ms)
- Real-upstream tests live in the weekly drift tier only

**Pass condition:** PR-tier tests complete within budget. Heavy tests are tagged / pathed to the right cron tier.

**Adversarial counter-pass:** Find a PR-tier test whose runtime is already 200-400ms. That's the next test to push over budget — proactively move to `needs-heavy` opt-in or refactor.

### Pass 4 — Mock budget

**Check:** Scan the test classes / files. For each:

- More than 2 mocks in a single test? Production code's boundaries are wrong — flag for refactor.
- Real DB at the service layer (no `tenant_db` / `query` / `query_one` / `session` mock)?
- Mocks only at TRUE external boundaries (LLM SDK, third-party APIs, payment gateways)?

**Pass condition:** No test class violates the mock budget. No internal-collaborator mocks.

**Adversarial counter-pass:** Find a test where the production code shape suggests refactoring would let you delete a mock. That's a design smell surfaced by the test — capture it as a follow-up.

### Pass 5 — Failure-mode coverage

**Check:** For each non-trivial code path added in this PR, find the failure-path test(s):

- Cold start (empty data, first session)
- Empty data (the table / list returned 0 rows)
- Half-completed state (operation started, partial state written, user came back)
- Permission denied (RLS, role check, tenancy)
- External-dependency failure (upstream down, slow, malformed response)
- Concurrent access (two requests touching the same state)

Cross-reference `apex:design-feature` Pass 5 (failure modes named at design time).

**Pass condition:** Every named failure mode from the design has a test. Failure-path tests document expected user-visible behavior, not just "raises an exception."

**Adversarial counter-pass:** Find a failure mode where the test asserts "raises an error" or "logs and continues" without specifying *user-visible behavior*. That's an unresolved failure-mode definition — go fix the test (and probably the production code).

## Pass/fail summary

The audit passes if all 5 passes meet their conditions. Fail any → fix before opening the PR (or rebasing the stack). Common fix paths:

- Pass 1 fail → write the missing tests, OR amend the PRD to drop the missing scenarios, OR delete the gold-plated tests
- Pass 2 fail → rewrite the layer-confused tests; this often surfaces production-code refactor opportunities
- Pass 3 fail → tag heavy tests for cron tiers; refactor slow PR-tier tests
- Pass 4 fail → refactor production code's boundaries; then update the tests
- Pass 5 fail → add failure-path tests; surface design gaps to `apex:design-feature`

## Cross-references

- **`apex:test-strategy`** — the methodology being audited (8-layer model, mocking policy, tiering, principles, 17 rules)
- **`apex:prd-review`** Pass 2 — PRD owns the scenarios list (input to Pass 1 here)
- **`apex:impl-plan-review`** Pass 3 — impl plan owns the test plan per layer (input to Pass 2 here)
- **`apex:ai-pre-review-checklist`** Steps 6 (test quality) + 7 (consumer tracing) — pair with this skill at PRE-PR phase. ai-pre-review-checklist focuses on per-test quality; test-coverage-audit focuses on the test set's coverage and architecture
- **`apex:design-feature`** Pass 5 — failure modes named at design time (input to Pass 5 here)
