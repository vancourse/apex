# Schema Design — Postgres

Rules for column types, constraints, primary keys, generated columns, JSONB strategy, and the composite-UNIQUE-as-FK-enforcer pattern that multi-tenant schemas live or die by.

## Use `timestamptz`, never `timestamp without time zone`

**When:** Any column representing a moment in time.
**Rule:** Use `timestamptz` (alias of `timestamp with time zone`). Reserve `timestamp` for the rare case where you genuinely need a wall-clock value with no associated instant (e.g., a recurring 09:00 daily reminder independent of date).
**Why:** `timestamptz` stores UTC internally and converts on read using the session `timezone`. `timestamp` silently drops timezone information at write time, so the same wall-clock value entered from two clients in different zones lands as two different instants — invisibly. Every comparison across rows is then wrong by the timezone delta. The fix is one keyword and a re-run of the migration; the bug, once shipped, requires a backfill and is impossible to fully reverse for rows whose origin timezone was lost.

```sql
-- ❌ BAD: silently drops timezone, two clients write same value as different instants
created_at timestamp NOT NULL DEFAULT now()

-- ✅ GOOD: stores UTC, comparable across clients and sessions
created_at timestamptz NOT NULL DEFAULT now()
```

**Migration:** `ALTER TABLE t ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'UTC'`. Rewrites the column; size-significant tables need expand/contract (see `rules/migrations.md`).

## Use `text`, not `varchar(N)`

**When:** Any string column.
**Rule:** `text` (or `varchar` without length) by default. Reach for `varchar(N)` only when the length cap is a *business invariant* you intend to enforce — and in that case, prefer a `CHECK (length(col) <= N)` constraint, which is easier to relax later.
**Why:** Postgres stores `varchar(N)` and `text` identically; there is no performance difference. The length cap on `varchar(N)` is enforced as an error on insert, which means widening the cap requires a full table rewrite on some versions. A CHECK constraint can be dropped and added (and validated NOT VALID then VALIDATEd) without a rewrite. The Postgres docs explicitly recommend `text`.

```sql
-- ❌ BAD: length cap baked into the type; widening requires rewrite
name varchar(120) NOT NULL

-- ✅ GOOD: type is text; cap (if any) lives in a constraint you can change
name  text NOT NULL,
       CONSTRAINT name_length_ok CHECK (length(name) BETWEEN 1 AND 120)
```

## JSONB over JSON; columns over JSONB when accessed often

**When:** Choosing how to store semi-structured data.
**Rule:** `jsonb` over `json` always (binary form, supports GIN indexes, lossless transforms). But: any field you filter, sort, join, or aggregate on belongs in a real column, not a JSONB blob. Use JSONB for the genuinely-variable tail of a record (caller-supplied metadata, vendor-specific extension fields), not as a schema-design escape hatch.
**Why:** `json` stores the raw text and re-parses on every access; `jsonb` parses once. But even `jsonb` access of a field through `->>` is materially slower than a real column, and indexing it requires a GIN index (large, slow to maintain) or an expression index per accessed path (one index per access pattern). The "everything in JSONB" anti-pattern looks flexible at design time and produces N×slower queries plus an indexing nightmare six months later.

```sql
-- ❌ BAD: filter target stuffed in JSONB; needs GIN or expression index, slow scans
CREATE TABLE events (
  id bigserial PRIMARY KEY,
  payload jsonb NOT NULL  -- payload->>'event_type' is filtered on every query
);

-- ✅ GOOD: filter target promoted to a column; payload holds the variable tail
CREATE TABLE events (
  id          bigserial PRIMARY KEY,
  event_type  text NOT NULL,
  payload     jsonb NOT NULL,  -- holds only event-type-specific extra fields
  CONSTRAINT event_type_known CHECK (event_type IN ('click','view','purchase'))
);
CREATE INDEX events_event_type_idx ON events (event_type);
```

## CHECK constraints carry business invariants

**When:** A column has a value range, an allowed-value list, a length cap, or a relationship to another column.
**Rule:** Encode it as a `CHECK` constraint. Don't trust the application to enforce it.
**Why:** Every constraint not at the database layer is a constraint waiting to be violated by a future code path (a script, a migration, a hand-edit, a parallel service). A `CHECK` is enforced for every writer, costs almost nothing, and shows up in the schema where the next engineer looks first.

```sql
-- ✅ GOOD: invariants visible in the schema, enforced for every writer
CREATE TABLE invoices (
  id            bigserial PRIMARY KEY,
  tenant_id     bigint NOT NULL,
  amount_cents  bigint NOT NULL CHECK (amount_cents >= 0),
  status        text   NOT NULL CHECK (status IN ('draft','open','paid','void')),
  paid_at       timestamptz,
  CONSTRAINT paid_implies_paid_at CHECK ((status = 'paid') = (paid_at IS NOT NULL))
);
```

Add new CHECKs to a populated table with `ALTER TABLE … ADD CONSTRAINT … NOT VALID;` (cheap, doesn't scan), then `ALTER TABLE … VALIDATE CONSTRAINT …;` (scans, but doesn't block writes). See `rules/migrations.md`.

## Native `enum` is rarely worth it

**When:** A column has a fixed set of allowed values.
**Rule:** Default to `text NOT NULL CHECK (col IN (…))`. Reach for native `CREATE TYPE … AS ENUM` only when you also need a sort order independent of alphabetical *and* the value set is genuinely stable.
**Why:** Adding a value to a native enum requires `ALTER TYPE … ADD VALUE`, which Postgres versions ≤11 require to run outside a transaction. Removing a value requires recreating the type and rewriting every dependent table. Renaming is similarly painful. CHECK constraints take the same query plan and can be edited freely. The "native enum is faster" intuition does not hold in benchmarks for typical schema sizes.

## Composite UNIQUEs that include the tenant column are load-bearing

**When:** Designing or reviewing a UNIQUE constraint on a multi-tenant table.
**Rule:** Treat every `UNIQUE (tenant_id, …)` as *load-bearing for cross-tenant integrity*. Do **not** drop it as "redundant" with a per-column UNIQUE — the composite is what makes downstream `FOREIGN KEY (tenant_id, x) REFERENCES … (tenant_id, x)` enforceable.
**Why:** A `UNIQUE (x)` on the parent table allows a child to FK on `x` alone — which means a row in tenant A can reference a parent row in tenant B. The composite `UNIQUE (tenant_id, x)` is what allows the child to FK on `(tenant_id, x)`, which is the only thing that prevents cross-tenant references at the schema layer. RLS keeps tenants from *reading* each other, but does **not** prevent cross-tenant FK references unless your FKs include the tenant column. (See `rules/multi-tenancy-rls.md`.) Drop the composite UNIQUE and you've silently turned off cross-tenant FK enforcement for every child of that parent — the breakage is invisible until a query joins across tenants and gets one too many rows.

```sql
-- ✅ GOOD: composite UNIQUE on parent + composite FK on child = cross-tenant integrity
CREATE TABLE accounts (
  tenant_id bigint NOT NULL,
  id        bigserial,
  code      text NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (tenant_id, code),    -- LOAD-BEARING: enables composite FK below
  UNIQUE (tenant_id, id)        -- LOAD-BEARING: enables (tenant_id, account_id) FKs
);

CREATE TABLE transactions (
  tenant_id  bigint NOT NULL,
  id         bigserial PRIMARY KEY,
  account_id bigint NOT NULL,
  FOREIGN KEY (tenant_id, account_id) REFERENCES accounts (tenant_id, id)
);
```

**Anti-pattern review check:** before dropping any UNIQUE that mentions a tenancy column, grep for `FOREIGN KEY (tenant_id` and `REFERENCES <this_table>` across the schema. If anything FK'd through the composite, the UNIQUE is load-bearing.

## Foreign keys: name ON DELETE explicitly

**When:** Declaring a foreign key.
**Rule:** Always specify `ON DELETE …` (and `ON UPDATE …` if relevant). Never accept the default by omission.
**Why:** The default is `NO ACTION` (deferred to commit), which gives different behavior from `RESTRICT` (immediate) and is easy to confuse with `CASCADE`. Reading a schema where every FK omits the clause means every reviewer has to remember the default. Naming it explicitly makes the intent reviewable.

```sql
-- ❌ BAD: defaults invisible to the reader
FOREIGN KEY (user_id) REFERENCES users (id)

-- ✅ GOOD: intent stated
FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT
```

## Soft deletes are an anti-pattern; prefer archive tables or partitioning

**When:** Tempted to add `deleted_at timestamptz` and filter `WHERE deleted_at IS NULL` everywhere.
**Rule:** Don't, by default. Prefer (a) moving the row to an `<table>_archive` table on delete, or (b) range-partitioning the table and dropping old partitions.
**Why:** Every query against a soft-delete table needs the predicate, every index needs to include or be partial on it, and forgetting the predicate produces a silent correctness bug (deleted rows appearing in lists). The "one column" cost compounds across every consumer of the table. Archive tables and partitioning keep the hot path clean and make the "deleted vs visible" boundary structural, not predicated. When you genuinely need soft delete (regulatory, undo within N days), encapsulate it in a `<table>_visible` view and force consumers to query the view, never the base table.

## Generated columns: stored for derived values queried often, virtual otherwise

**When:** A column's value is fully determined by other columns in the same row (e.g., `full_name = first_name || ' ' || last_name`).
**Rule:** Use `GENERATED ALWAYS AS (…) STORED` when the derived value is filtered, sorted, indexed, or returned often. Use a view or compute-in-query for values touched rarely. Postgres does not yet support virtual generated columns — `STORED` is the only on-table option.
**Why:** Stored generated columns are recomputed only on write, indexed like any other column, and impossible to write to directly (so they can't drift). The cost is disk space proportional to the column width. The trade is worth it when you'd otherwise reach for a trigger.

```sql
-- ✅ GOOD: full_name indexed and queryable, can never drift
ALTER TABLE users
  ADD COLUMN full_name text
    GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED;
CREATE INDEX users_full_name_idx ON users (full_name);
```

## Primary keys: identity > serial > UUID; pick UUIDv7 if you need ordering

**When:** Choosing the type of a primary key.
**Rule:** Default to `bigint GENERATED BY DEFAULT AS IDENTITY` (or `GENERATED ALWAYS AS IDENTITY` if you want to forbid manual writes). Use `serial`/`bigserial` only for backwards compat with old code; the IDENTITY syntax is SQL-standard and avoids the sequence-ownership quirks of `serial`. Use `uuid` (v7 if available) when keys must be generated client-side or you need globally unique identifiers across systems.
**Why:** Sequential bigints are smallest, fastest to index, and friendly to range scans. UUIDv4 is random — every insert hits a different B-tree leaf, which causes write amplification and cache misses at scale. UUIDv7 (and v6) are time-ordered, which restores locality. `serial` works but uses a sequence-owned-by-table mechanism that surprises people during table renames and partitioning.

```sql
-- ✅ GOOD: SQL-standard identity column, sequence is internal to the table
CREATE TABLE users (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ...
);
```

## Anti-pattern review checklist

Before approving a schema change, the reviewer asks:

1. Is every timestamp column `timestamptz`?
2. Is every string column `text` (unless a length cap is a deliberate business invariant)?
3. Is every JSONB field a column you filter, sort, or join on?
4. Does every column with a fixed value range have a `CHECK` constraint?
5. On every multi-tenant table, is there `UNIQUE (tenant_id, <natural_key>)` *and* `UNIQUE (tenant_id, id)` for child-FK use?
6. Does every FK name `ON DELETE` explicitly?
7. If a new soft-delete predicate appears, is there a reason an archive table or partition won't work?
8. Are generated columns used instead of triggers where possible?
9. Is the primary key an identity column (or UUIDv7 with a stated reason)?

Cross-references: see `rules/multi-tenancy-rls.md` for RLS-policy-side enforcement, `rules/migrations.md` (coming PR2) for the safe-change recipes, and `apex:architecture-design` Pass 2 for the foundational persistence + tenancy decision.
