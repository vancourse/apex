# Testing & Quality Assurance

Rules for test design, fixture patterns, and mock discipline.

## Scenarios-First — List Use Cases Before Code

**When:** Starting work on any feature larger than a single helper.
**Rule:** Before writing code, enumerate the concrete user-flow scenarios the feature must handle. Each scenario becomes one integration test. If you can't articulate the scenarios, the design isn't concrete enough — replan, don't code.
**Why:** Tests written after the code echo the code's structure; tests written from scenarios echo the user's intent. Catches the "tests pass but the feature doesn't do what it should" failure mode at design time.
**How to apply:**

- Scenario format: "User does X, system shows Y, with edge case Z."
- One scenario per acceptance-criterion line in the design doc / PR description.
- Every PR ships BOTH unit tests (fast, pure logic, mocks OK for external boundaries) AND integration tests (one per scenario, real components).

## Integration Tests Use Real Components — Not Mocks

**When:** Writing a test that claims to cover end-to-end behavior.
**Rule:** Real DB (template-isolated per test, or fresh schema per test), real ORM, real validators, real external APIs where the feature actually touches them. Reserve mocks for true external boundaries (LLM providers, third-party APIs) and only at the unit layer below.
**Why:** Mocked integration tests have shipped real bugs because the mock confirmed the code-path while reality contradicted it. A test that mocks every collaborator verifies only that mocks were called, not that the system works.
**How to apply:**

- Per-test database isolation via template DBs (Postgres `CREATE DATABASE x TEMPLATE template_db`) or a fresh in-memory database per test.
- For LLM-touching features: use the real API with deterministic fixture inputs in CI; skip expensive runs as nightly-only when cost matters.
- Static analysis (mypy/pyright/eslint) is the cheap pre-check; integration tests are the load-bearing pre-check.
- If the test class mocks more than two collaborators, the production code's boundaries are wrong — fix those first, then the test.

## PRD ↔ Integration Test Mirror

**When:** Implementing a feature whose PRD was reviewed via `apex:prd-review` (which enumerates testable scenarios at Pass 2).

**Rule:** Integration tests mirror PRD scenarios **1:1**:

- Every PRD scenario has **≥1 integration test** that exercises it end-to-end.
- Every integration test names which PRD scenario it covers (in the test name, docstring, or a pytest marker — `@pytest.mark.scenario("prd-3")` is a fine pattern).
- A scenario without a test = the PRD is unverified at the implementation layer; that's a failing pre-PR check.
- A test without a PRD scenario = either the PRD is incomplete (amend it via a delta commit to the PRD) OR the test is gold-plating (delete it, or downgrade to a unit test).

**Why:** The PRD owns the scenario list. Integration tests are the verification artifact for those scenarios. Without this mirror invariant, scope drifts silently: the team builds features the PRD didn't ask for ("gold-plating"), or skips scenarios the PRD requires ("phantom coverage"). The mirror closes the spec-to-impl loop — `apex:prd-review` Pass 2 owns the list, `apex:impl-plan-review` Pass 3 owns the test plan per layer, and this rule is what makes those two upstream gates load-bearing rather than ceremonial.

**How to apply:**

- Name integration tests after PRD scenarios: `test_scenario_3_user_uploads_january_pdf_balance_check_blocks_categorization`.
- Pre-PR check: enumerate the PRD scenarios, grep for integration tests, verify 1:1 correspondence. Run this against the diff before opening the PR.
- If you need a test that doesn't fit any PRD scenario, ask: should this scenario be amended into the PRD? If yes, do that first; if no, the test is gold-plating — delete it or convert to a unit test (which doesn't claim end-to-end verification).
- For features where the PRD enumerates 8 scenarios but you only have 3 integration tests, that's not "we're partway done" — that's "the PRD says we shipped 8 things and we've actually shipped 3." Either ship the missing 5 or amend the PRD to reflect the actual scope.

## Explicit Collaborators With Stubs — Not `MagicMock` for Internal Services

**When:** A service test needs to isolate an internal collaborator (not an external API).
**Rule:** Write a concrete stub class with typed async methods. No `MagicMock` + `patch` for internal services.
**Why:** Stubs are readable, typed, and fail explicitly. Magic mocks hide wrong call signatures and create false confidence.
**How to apply:** `class _StubDraftService: async def classify(...) -> ClassificationResult: return ClassificationResult(None, None, None)`. Reserve `MagicMock` for one or two true external boundaries (LLM, Reducto).

## Inject the Dependency, Don't Patch the Global

**When:** A unit needs the wall clock, a UUID, a random source, or any non-deterministic input.
**Rule:** Accept it as an argument with a sensible default. Tests pass an explicit value; production keeps its default. Do not reach for `freezegun` / `monkeypatch.setattr(datetime, ...)` unless injection is genuinely impossible.
**Why:** Injection makes the seam visible in the production signature, gives the test a precise assertion site, and keeps the test free of global-state side effects.
**How to apply:**

```python
def should_commit(self, tool_call_id: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    ...

# In tests, no patching:
now = datetime(2026, 1, 1, tzinfo=UTC)
assert throttler.should_commit("call-1", now=now) is True
assert throttler.should_commit("call-1", now=now + timedelta(milliseconds=100)) is False
```

The same shape applies to async collaborators — pass `read_state`, `get_*`, `factory` callables as kwargs typed by `Protocol`. Production wires the real implementations at the single call site; the test passes fakes. Zero `patch.object` against sibling modules.

## One or Two Mocks Maximum — More Means the Production API Is Wrong

**When:** Counting `MagicMock` / `patch()` calls in a single test.
**Rule:** More than two is a design smell — fix the production code first (clearer service boundaries, injectable collaborators), then the test. Don't add more mocks to make a broken test pass.
**Why:** Heavy mocking verifies only that mocks were called, not that the system works.

## Don't Mock Internal Storage / File / Thread Layers

**Rule:** Reject tests that mock internal storage, file managers, or thread pools when an in-process fixture (in-memory SQLite, `tmp_path`, real executor) would work. Mock only at true external boundaries (LLM providers, third-party APIs).

## Don't Test Orchestration Through the REST Layer

**When:** Tempted to write an HTTP-level test for a pure function with a mocked state.
**Rule:** Test the unit directly. Trust that the framework propagates exceptions to HTTP status codes — verify that once at the framework boundary, not per route.

## Meaningful Tests — Assert Side Effects or Return Values

**When:** Writing any test.
**Rule:** Every test must assert a side effect (persisted state, emitted event) or a return value. Instantiating a class without asserting anything is banned.

## Write Tests in Terms of Domain Objects

**When:** Testing HTTP endpoints or service methods.
**Rule:** Create request payloads by instantiating domain objects and calling `.model_dump(mode="json")`. Parse responses with `MyResponse.model_validate(response.json())`. Assert on domain objects, not raw dicts.

## Use Explicit Assertions — Not Type Casts

**When:** Tempted to write `typing.cast(bytes, result)` in a test.
**Rule:** `assert isinstance(result, bytes)` — validates runtime behavior, narrows the type, and gives a better error message.

## Test Failure Modes Explicitly

**When:** Writing tests for a multi-step operation.
**Rule:** Ask "What if the DB drops?", "What if the task crashes?", "What if we get invalid input?" — add at least one failure-path test per operation.

## Generate Test Data Programmatically

**When:** A test needs large or structured data (CSV, DataFrames, JSON).
**Rule:** Generate it in code. Only use files when absolutely necessary; keep them under 1 MB. Ask "Can we generate this instead?" for anything over that.

## Test Conciseness — Quality Over Coverage Quantity

**Rule:** A few curated, high-quality tests beat a large block of boilerplate. Avoid 10–15 "do everything" tests that are hard to understand.

## Fixture Consolidation — One Fixture per Logical Unit

**When:** Two fixtures share 90% of their setup.
**Rule:** Collapse into one tuple fixture. Let callers destructure what they need: `service, _ = service_with_fm`.

## Always Annotate Async Fixtures That Yield Tuples

**When:** An async pytest fixture yields a tuple.
**Rule:** Annotate return as `AsyncGenerator[tuple[TypeA, TypeB], None]`. Without it, pyright can't infer element types and consumers cascade `# type: ignore`.

## Update Mocks When Contracts Change

**When:** A code change makes a previously-optional artifact mandatory.
**Rule:** Update test mocks to provide the artifact. A mock that returns empty where production now raises makes tests lie.

## Idempotency Tests Must Read State Between Calls

**When:** Testing that `ensure_*` or `upsert_*` is idempotent.
**Rule:** Read state after the first call, then after the second. Assert the returned ID/identity is the same across both.
**Why:** Only checking the final state proves the second call didn't crash — not that it didn't create a duplicate.

## Don't Assert on Log Strings — Assert on Behavior

**When:** Tempted to check `assert "Fast parse complete" in captured_logs`.
**Rule:** Assert on observable outcomes instead: return values, state changes, side effects. Log-string assertions break on copy edits with no functional change.
