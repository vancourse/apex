# Testing — Python tooling specifics

The generic testing methodology — scenarios-first, the 8-layer model, mocking policy per layer, CI tiering, transaction-rollback isolation, recorded fixtures, the 17 language-agnostic test design rules — lives in **`apex:test-strategy`**.

This file holds only the **Python-specific tooling rules** that don't generalize to other languages.

## Stubs Over `MagicMock` for Internal Services

**When:** A service test needs to isolate an internal collaborator (not an external API).
**Rule:** Write a concrete stub class with typed async methods. No `MagicMock` + `patch` for internal services.
**Why:** Stubs are readable, typed, and fail explicitly. `MagicMock` hides wrong call signatures and creates false confidence — it returns truthy `MagicMock` objects for any attribute access, so test bugs go undetected.
**How to apply:**

```python
class _StubDraftService:
    async def classify(self, txn: Transaction) -> ClassificationResult:
        return ClassificationResult(None, None, None)
```

Reserve `MagicMock` for one or two true external boundaries (LLM SDK, Reducto, etc.). Inside the codebase, typed stubs win.

## Avoid `freezegun` / `monkeypatch.setattr` — Use Default-Argument Injection

**When:** A unit needs the wall clock, a UUID, a random source, or any non-deterministic input.
**Rule:** Accept it as an argument with a sensible default (Python lets you do this trivially via keyword argument with a default). Tests pass an explicit value; production keeps its default. Do not reach for `freezegun` / `monkeypatch.setattr(datetime, ...)` unless injection is genuinely impossible (i.e. the production signature is owned by a third party).
**Why:** Global-state patching is order-sensitive, leaks across tests, and obscures the production contract. The methodology rationale is in `apex:test-strategy` Rule 4; this file holds the Python idiom.
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

For async collaborators: pass `read_state`, `get_*`, `factory` callables as kwargs typed by `Protocol`. Production wires the real implementations at the single call site; the test passes fakes. Zero `patch.object` against sibling modules.

## Always Annotate Async Fixtures That Yield Tuples

**When:** An async pytest fixture yields a tuple.
**Rule:** Annotate the return as `AsyncGenerator[tuple[TypeA, TypeB], None]`. Without it, pyright can't infer element types and consumers cascade `# type: ignore`.

```python
@pytest_asyncio.fixture
async def service_with_fm(...) -> AsyncGenerator[tuple[DraftService, LocalFileManager], None]:
    ...
    yield service, fm
```

## Pydantic Domain-Object Test Data via `.model_dump()`

**When:** Testing HTTP endpoints or service methods that take/return Pydantic models.
**Rule:** Create request payloads by instantiating the domain object and calling `.model_dump(mode="json")`. Parse responses with `MyResponse.model_validate(response.json())`. Assert on the validated object, not on raw dicts.
**Why:** The model validates at construction; a typo in your test payload becomes a test-author error, not a hidden mismatch. Type checker catches refactors. The methodology rationale is in `apex:test-strategy` Rule 9; this is the Python/Pydantic idiom.

```python
# ✅ GOOD: validated domain object
payload = CreateTxnRequest(amount=Decimal("100.00"), account_id=uuid4()).model_dump(mode="json")
response = await client.post("/api/txn", json=payload)
parsed = CreateTxnResponse.model_validate(response.json())
assert parsed.status == "pending"

# ❌ BAD: raw dict
response = await client.post("/api/txn", json={"amount": 100, "account_id": "..."})
assert response.json()["status"] == "pending"
```

## Use `assert isinstance(...)` Not `typing.cast(...)`

**When:** Tempted to write `typing.cast(bytes, result)` in a test.
**Rule:** `assert isinstance(result, bytes)` — validates runtime behavior, narrows the type for pyright, and gives a better error message than a `cast` that silently lies. The methodology rationale is in `apex:test-strategy` Rule 10; this is the Python form.

## Transaction-Rollback Fixture Pattern (`pytest-asyncio` + `asyncpg`)

For per-test DB isolation against a real Postgres + RLS forced (the `apex:test-strategy` "Test isolation patterns" section in Python form):

```python
@pytest_asyncio.fixture
async def tenant_tx(pool: asyncpg.Pool, firm_id: UUID) -> AsyncGenerator[asyncpg.Connection, None]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET app.tenant_id = $1", str(firm_id))
            yield conn
            # transaction auto-rolls back on context exit
```

Use this fixture in service tests to run against real schema + real RLS + real FKs at ~50–100 tests/sec. Combined with `pytest-xdist` for parallel workers, PR tier stays under budget.

## `pytest-xdist` Parallelism — When and When Not

**Use `-n auto` for:**
- Unit tests (pure)
- Service tests with `tenant_tx` fixture (each worker has its own DB connection; transactions roll back independently)

**Do NOT use for:**
- Scenario tests that rely on time ordering or multi-step flows
- Tests that COMMIT and depend on cleanup ordering
- Tests against shared singleton state (e.g. an in-process queue)

Mark serial-only tests with `@pytest.mark.serial` and configure `pytest-xdist` to skip them in parallel runs.
