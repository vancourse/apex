# Async & Concurrency

asyncio discipline — task lifecycle, locks, timeouts, thread safety.

## Never Fire-and-Forget a Task

**When:** Calling `asyncio.create_task(...)`.
**Rule:** Track every task in a set. Implement explicit cancellation and cleanup.
**How to apply:** `task.add_done_callback(self._tasks.discard)`; on shutdown, cancel all and `asyncio.wait(tasks, timeout=...)`.

## Every Async Loop Needs a try/except

**When:** Writing a `while True:` worker loop.
**Rule:** Wrap the body in try/except. Handle `CancelledError` separately. Log and back off on other exceptions; never silently ignore.

## Explicit Context Passing

**When:** A function needs context (IDs, config, user).
**Rule:** Pass it down the stack. Don't rely on "guessing" or fuzzy matching to reconstruct state.

## Fan-Out: Return Values From `gather`, Don't Write Into a Shared Dict

**When:** Multiple coroutines need to contribute entries to a shared collection.
**Rule:** Each coroutine returns its value; the caller builds the map from `asyncio.gather` results. Don't have N writers mutate a shared `dict`.
**Why:** Shared-mutable-state fan-out is fragile even when the GIL makes it safe today — future refactors (threads, process pools) silently break it.

```python
# ❌ BAD
results: dict[str, Value] = {}
async def worker(key: str) -> None:
    results[key] = await fetch(key)
await asyncio.gather(*(worker(k) for k in keys))

# ✅ GOOD
async def worker(key: str) -> tuple[str, Value]:
    return key, await fetch(key)
results = dict(await asyncio.gather(*(worker(k) for k in keys)))
```

## Group Timeout: `wait_for(gather(...), timeout=...)`

**When:** Applying a single cumulative deadline to a group of concurrent tasks.
**Rule:** `asyncio.wait_for(asyncio.gather(...), timeout=...)` is the preferred shape. Avoid manual `asyncio.wait` + cancellation bookkeeping for the common case.

## Every External Call Has an Explicit Timeout

**When:** Calling an external service (HTTP, LLM, DB).
**Rule:** Pass an explicit `timeout=` argument. Never rely on the library default.
**How to apply:** DB 30s, external API 10–30s, LLM 120s. Hitting the default is a code smell.

## asyncio.Lock — Unconditional Release in finally

**When:** Using `asyncio.Lock` with manual acquire/release.
**Rule:** Release unconditionally inside a `try/except RuntimeError: pass`. Never gate release on `lock.locked()`.
**Why:** `lock.locked()` can return `False` under `CancelledError` propagation even when you hold it, leaving the lock acquired forever.

## Prefer `async with lock:`

**When:** Simple acquire-do-work-release flows.
**Rule:** Use the context manager. The async-with form guarantees release.
**How to apply:** For "reject if already held," use `if lock.locked(): raise AlreadyRunningError()` then `await lock.acquire()`. In asyncio's single-threaded model, an uncontested acquire completes without yielding — the check+acquire is effectively atomic.

## Never `asyncio.wait_for(lock.acquire(), timeout=0)`

**When:** Trying to implement a non-blocking try-lock.
**Rule:** Don't. `wait_for` with `timeout=0` always raises `TimeoutError`, even on a free lock.
**How to apply:** Use `lock.locked()` as a pre-check instead.

## Never Call Sync Transport from Async Handlers

**When:** An async FastAPI endpoint calls a helper that uses a sync HTTP client or sync DB driver.
**Rule:** Wrap the sync helper in `asyncio.to_thread` or convert it to use an async transport.
**Why:** Sync I/O blocks the event loop; the whole service stalls under concurrent load.

## Race Conditions in SSE Streaming

**When:** An SSE endpoint streams events while performing async work.
**Rule:** Wrap the generator in try/finally for cleanup. Don't read state → stream → write state without handling mid-stream mutation. Use thread-level locking or conflict detection for concurrent same-thread requests.

## Partial Success Needs Explicit Response Shapes

**When:** An endpoint can partially succeed (primary op completes, side effect fails).
**Rule:** Define discriminated response shapes for each outcome. No ambiguous `status: "success" | "error"`.
