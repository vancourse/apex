# Database & SQL

Rules for SQL queries, ORM usage, migrations, and connection management.

## Move Computation to the Data (SQL > Python)

**When:** Filtering, sorting, aggregating, or sampling rows.
**Rule:** Do it in SQL. Fetching 10k rows to filter them in a Python loop is the anti-pattern.
**How to apply:** `WHERE`, `LIMIT`, `DISTINCT`, `SAMPLE`, and aggregates in the query — not in list comprehensions.

## One Correct Query — No Retry Loops

**When:** Tempted to "try to get 10, if only 5, try again."
**Rule:** Write one query that returns the needed data. Retry loops hide the fact that the query is wrong.

## Connection Pooling

**When:** Opening DB or HTTP connections.
**Rule:** Use a pool. Never create per-request connections.
**Why:** Per-request connects exhaust file descriptors and introduce latency.

## Cache Deduplication Must Check All Dimensions

**When:** Implementing a cache-hit check.
**Rule:** Include every parameter that affects the output — not just the content hash.
**Why:** A hash match with different processing params is a false cache hit. Silent wrong-data bug.

## Idempotency Tests Must Read Between Calls

**When:** Testing that `ensure_*` or `upsert_*` is idempotent.
**Rule:** Read state after the first call, compare to state after the second call. Assert the same record ID.
**Why:** Checking only the final state doesn't prove idempotency — it only proves the second call didn't crash.

## Two-Pass Scan + Fetch

**When:** Iterating a collection to find items to modify.
**Rule:** Pass 1 collects affected IDs (scan only). Pass 2 fetches/modifies/writes.
**Why:** Interleaving reads with scans causes N+1 and tangles concerns.

## Paginate All List Queries

**When:** Writing a query that returns a list of rows.
**Rule:** Use `LIMIT` and a bounded default. Never return unbounded results.

## Return Sorted Data if You Sorted for Storage

**When:** Sorting data for deterministic persistence.
**Rule:** Return the same sorted version to the caller. Don't sort for the write path and return the unsorted original.
