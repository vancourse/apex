# Multi-Tenancy & Row-Level Security — Postgres

Rules for tenant isolation via Postgres RLS. The single biggest source of multi-tenant correctness bugs is RLS that *looks* enabled but isn't actually enforcing. This file is the per-rule deep dive; for the system-level decision (RLS vs schema-per-tenant vs DB-per-tenant), see `apex:architecture-design` Pass 2.

## Two roles: schema owner + non-privileged app role

**When:** Setting up multi-tenant RLS on a Postgres database.
**Rule:** Two roles. `app_owner` creates schemas, tables, and policies — it owns everything. `app_user` (the role the application connects as) has only `SELECT / INSERT / UPDATE / DELETE` grants on tables; it owns nothing. RLS policies only constrain non-owner roles by default.
**Why:** Postgres exempts the table owner from RLS policies unless `FORCE ROW LEVEL SECURITY` is set. If your application connects as the role that owns the tables, RLS is *off* for it regardless of what `CREATE POLICY` statements you've written. Splitting owner and runtime roles is the structural defense; relying on `FORCE` alone is the override.

```sql
-- ✅ Two-role pattern.
-- Credentials are provisioned out-of-band (secret manager / infra tooling /
-- migration tool template variables) — do NOT commit plaintext passwords.
CREATE ROLE app_owner LOGIN;   -- owns tables, creates policies
CREATE ROLE app_user  LOGIN;   -- application connects as this

-- Schema-level USAGE is required before any per-table grant takes effect.
GRANT USAGE ON SCHEMA app TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_user;

-- `FOR ROLE app_owner` is load-bearing. `ALTER DEFAULT PRIVILEGES` applies
-- to the *current* role's future objects by default — so if this migration
-- is executed by a DBA / superuser session instead of `app_owner`, tables
-- later created by `app_owner` will NOT inherit the grants. Naming the role
-- explicitly makes the rule independent of whoever runs the migration.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

-- Note: IDENTITY columns (`GENERATED … AS IDENTITY`) do NOT require explicit
-- sequence grants — the table grant is sufficient. If you use legacy
-- `serial`/`bigserial`, also grant on the owned sequences:
--   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO app_user;
--   ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA app
--     GRANT USAGE, SELECT ON SEQUENCES TO app_user;
```

## Enable **and** `FORCE` Row Level Security per table

**When:** Adding RLS to a tenant-scoped table.
**Rule:** Both statements, every table, in the migration:

```sql
ALTER TABLE app.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.invoices FORCE  ROW LEVEL SECURITY;
```

**Why:** `ENABLE` turns RLS on for *non-owner* roles. `FORCE` extends enforcement to the table owner too. Without `FORCE`, any maintenance script or migration that runs as `app_owner` bypasses every policy — which means a backfill written to a single tenant can silently write across all tenants if the predicate has a typo. With `FORCE` on, the only ways to bypass RLS are (a) connect as a Postgres superuser, or (b) connect as a role that carries the `BYPASSRLS` attribute (`ALTER ROLE someone BYPASSRLS`). There is no per-table grant for this — `SET row_security = off` only takes effect for superusers or `BYPASSRLS` roles; for everyone else it's a no-op. Both bypass paths are exceptional maintenance affordances and neither should ever belong to the application's runtime role. The structural property is: **the application can never escape RLS, because the role it runs as has neither superuser nor `BYPASSRLS`.**

**Anti-pattern:** Enabling RLS on a table without `FORCE` and trusting that "the migration tool connects as a different role." The migration tool *is* the table owner in most setups.

## Every policy needs `USING`; every write policy needs `WITH CHECK`

**When:** Authoring an RLS policy.
**Rule:** `USING` controls which rows the policy *exposes* to reads (and what UPDATE/DELETE can target). `WITH CHECK` controls what new row values are *allowed* to be written. INSERT requires `WITH CHECK`; UPDATE requires both. Write them both, every time.

```sql
-- ❌ BAD: USING without WITH CHECK on UPDATE — can change rows out of the tenant
CREATE POLICY invoices_tenant_isolation ON app.invoices
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::bigint);
-- An UPDATE can read a row in tenant A and rewrite tenant_id to B; USING passes,
-- and without WITH CHECK the post-update row escapes the policy entirely.

-- ✅ GOOD: both clauses, symmetric on tenant_id
CREATE POLICY invoices_tenant_isolation ON app.invoices
  FOR ALL
  USING       (tenant_id = current_setting('app.tenant_id')::bigint)
  WITH CHECK  (tenant_id = current_setting('app.tenant_id')::bigint);
```

**Common subtle failure:** writing `FOR ALL` with only `USING` works for SELECT and DELETE, *appears* to work for UPDATE (you can't see another tenant's rows to update), and silently allows an UPDATE that *moves* a row out of your tenant by overwriting `tenant_id`. The bug is invisible to the application and to most tests; an integration test that writes as tenant A then reads as tenant B catches it.

## Propagate `app.tenant_id` via `SET LOCAL` inside a transaction

**When:** Telling Postgres which tenant the current request is for.
**Rule:** Inside a transaction, set the tenant GUC at the start. The exact statement depends on whether you're in psql/migration text or application code:

- **psql / hand-written migrations** (value is a literal): `SET LOCAL app.tenant_id = '<id>'`. Concise and ergonomic for human-typed SQL.
- **Application client code** (value comes from a request / bind variable): `SELECT set_config('app.tenant_id', $1, true)`. The `is_local=true` third argument gives identical transaction-scoped semantics to `SET LOCAL`, but unlike `SET` / `SET LOCAL` (which are utility commands), `set_config(...)` accepts bind parameters in prepared statements. Writing `SET LOCAL app.tenant_id = $1` against a prepared statement raises a syntax error at runtime — see the wrapper pattern below.

Never use `SET` (session-wide); never set it outside a transaction.

```sql
BEGIN;
SET LOCAL app.tenant_id = '42';
SELECT * FROM app.invoices;   -- RLS evaluates app.tenant_id = '42'
COMMIT;
```

**Why:** `SET LOCAL` scopes the GUC to the current transaction. The next checkout from the connection pool gets a clean session — no leakage of the previous request's tenant_id. `SET` (without `LOCAL`) sticks until the next `RESET` or pool checkout cleanup, which most pools do not do reliably. The leak is silent and tenant-crossing.

**Application wrapper pattern (language-agnostic):**

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def tenant_db(pool, tenant_id: int):
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Use set_config(..., is_local=true), NOT `SET LOCAL` — the latter
            # is a Postgres utility command and does NOT accept bind
            # parameters in prepared statements (would raise a syntax error).
            # set_config('app.tenant_id', $1, true) is semantically identical
            # to `SET LOCAL` (scoped to the current transaction) AND accepts
            # parameter binding, so the tenant_id value is safely cast/escaped.
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                str(tenant_id),
            )
            yield conn

# Usage at the request handler boundary:
# async with tenant_db(pool, tenant_id=42) as conn:
#     rows = await conn.fetch("SELECT * FROM app.invoices")
```

Two load-bearing details:

- **`@asynccontextmanager`** — without it, the bare `async def … yield` is an
  async generator and `async with` against it raises `TypeError:
  'async_generator' object does not support the asynchronous context manager
  protocol`.
- **`set_config(name, value, is_local)` over `SET LOCAL name = value`** —
  `SET` / `SET LOCAL` are Postgres utility commands and do not accept bind
  parameters in prepared statements. Writing
  `await conn.execute("SET LOCAL app.tenant_id = $1", ...)` raises a syntax
  error at runtime. `set_config(...)` is the parameterizable equivalent;
  with `is_local=true` it has identical transaction-scoped semantics. Use it
  in any client-driven setter; the bare `SET LOCAL` form remains correct
  inside hand-written psql sessions or migrations where the value is a
  literal, not a bind variable.

Every request handler opens a `tenant_db` block; no direct pool acquisition
outside it. Reviewers grep for `pool.acquire` and `conn.execute("SET …app.tenant_id…")` to confirm the discipline.

## RLS does not prevent cross-tenant foreign-key references — composite FKs do

**When:** Adding a foreign key on a tenant-scoped table.
**Rule:** Use a *composite* FK that includes `tenant_id` on both sides. The parent table needs a matching `UNIQUE (tenant_id, …)` (which is why the composite UNIQUE in `apex:postgres-review/rules/schema-design.md` is load-bearing).

```sql
-- ❌ BAD: child can reference any parent row regardless of tenant
CREATE TABLE app.line_items (
  tenant_id  bigint NOT NULL,
  id         bigserial PRIMARY KEY,
  invoice_id bigint NOT NULL REFERENCES app.invoices(id)
);

-- ✅ GOOD: child can only reference parent rows in the same tenant
CREATE TABLE app.line_items (
  tenant_id  bigint NOT NULL,
  id         bigserial PRIMARY KEY,
  invoice_id bigint NOT NULL,
  FOREIGN KEY (tenant_id, invoice_id) REFERENCES app.invoices (tenant_id, id)
);
```

**Why:** RLS filters which rows a *query* sees, but FK constraints are checked by the system without regard to the session role. A malicious or buggy INSERT into `line_items` that names an `invoice_id` from another tenant will succeed if the FK is on `invoice_id` alone, even with RLS enabled. The composite FK makes the cross-tenant reference structurally impossible. (Stripping a composite UNIQUE on `invoices(tenant_id, id)` as "redundant with PRIMARY KEY (id)" is the canonical way to silently turn this off — see `apex:postgres-review/rules/schema-design.md`.)

## Test RLS by connecting as `app_user` with a deliberately wrong tenant_id

**When:** Writing tests for RLS-protected tables.
**Rule:** The integration test:

1. Connects as `app_user` (not `app_owner` — the owner bypasses unless FORCE).
2. Opens a transaction and `SET LOCAL app.tenant_id = '1'`.
3. Inserts a row.
4. Commits.
5. Opens a new transaction, `SET LOCAL app.tenant_id = '2'`.
6. Asserts `SELECT COUNT(*) = 0` from the same table.
7. Asserts an attempted INSERT with `tenant_id = 1` either errors or is silently denied (depending on policy — usually errors via `WITH CHECK`).

**Why:** Unit tests of the application can't observe RLS — the application opens its own connection per test, often as a privileged role, and a stub `tenant_db` helper makes the test green even when RLS is misconfigured. The only test that proves the policy holds is one that runs against a real connection as `app_user`. This belongs at apex's test-strategy Layer 2 (DB-driven integration); see `apex:test-strategy`.

## Anti-pattern table — what you'll be tempted to say vs what's true

| You'll say…                                                                       | Reality                                                                                                                                          |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| "We enabled RLS, we're isolated."                                                 | Owner role bypasses RLS unless `FORCE` is on. Most migration tools run as owner. RLS is off for them.                                            |
| "The application sets `app.tenant_id` on every request — that's the defense."     | The application is the attacker's surface. RLS must enforce, not trust. Use `app_user` (no DDL grants) so the application *cannot* turn it off.  |
| "The composite UNIQUE on `(tenant_id, id)` is redundant with the PRIMARY KEY on `id`." | The composite UNIQUE is what allows child tables to FK on `(tenant_id, parent_id)`. Drop it and you silently lose cross-tenant FK enforcement.   |
| "We don't need WITH CHECK — USING covers it."                                     | USING gates which rows UPDATE can target; WITH CHECK gates what the row looks like *after* the UPDATE. An UPDATE can move a row out of the tenant. |
| "We `SET app.tenant_id` at the start of each handler — that's session-scoped."    | `SET` (without LOCAL) persists in the pooled connection until next `RESET`. The next checkout for a different tenant reuses the old value. Silent cross-tenant leak. |
| "RLS is on, FKs handle the rest."                                                 | FK checks ignore RLS. A non-composite FK on `parent_id` allows a child in tenant A to reference a parent in tenant B. RLS hides the reference from reads; it doesn't prevent the write. |
| "We tested RLS by writing as tenant A and reading as tenant A."                   | That tests nothing. The test must read as tenant B and assert zero rows of tenant A's data are visible.                                          |

## Worked example — minimal compliant migration

```sql
-- 1. Roles + schema (idempotent — usually one-time at DB setup).
--    Credentials provisioned out-of-band — never commit plaintext passwords.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_owner') THEN
    CREATE ROLE app_owner LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user LOGIN;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION app_owner;
-- `CREATE SCHEMA IF NOT EXISTS` is idempotent only for existence — if the
-- schema already exists with a different owner, the AUTHORIZATION clause
-- is silently ignored. Always follow up with an explicit ownership
-- correction so the owner / app-role split can't silently drift.
ALTER SCHEMA app OWNER TO app_owner;
GRANT USAGE ON SCHEMA app TO app_user;   -- required before per-table grants

-- 2. Table with tenant_id and composite UNIQUEs
CREATE TABLE app.invoices (
  tenant_id    bigint NOT NULL,
  id           bigint GENERATED ALWAYS AS IDENTITY,
  external_ref text   NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (tenant_id, external_ref),
  UNIQUE (tenant_id, id)  -- load-bearing for child composite FKs
);
ALTER TABLE app.invoices OWNER TO app_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.invoices TO app_user;
-- IDENTITY columns do not need explicit sequence grants; the table grant
-- covers ID generation. For legacy `serial`, also GRANT USAGE, SELECT on
-- the owned sequence.

-- 3. RLS enable + FORCE + policy with both clauses
ALTER TABLE app.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.invoices FORCE  ROW LEVEL SECURITY;

CREATE POLICY invoices_tenant_isolation ON app.invoices
  FOR ALL
  TO app_user
  USING       (tenant_id = current_setting('app.tenant_id')::bigint)
  WITH CHECK  (tenant_id = current_setting('app.tenant_id')::bigint);

-- 4. (Application code) — every query lives inside a `tenant_db` block that
--    calls `SELECT set_config('app.tenant_id', $1, true)` at transaction
--    start. Plain `SET LOCAL app.tenant_id = $1` does NOT work — `SET` /
--    `SET LOCAL` are utility commands and reject bind parameters. The
--    `set_config(..., true)` form is the parameterizable equivalent and has
--    identical transaction-local scoping. See the wrapper pattern above.
```

**Reviewer checklist** for any PR touching a tenant-scoped table:

1. `ENABLE ROW LEVEL SECURITY` present?
2. `FORCE ROW LEVEL SECURITY` present?
3. Policy has both `USING` and `WITH CHECK`?
4. Policy applies `TO app_user` explicitly (not the default `PUBLIC`, not the owner)?
5. Composite UNIQUEs on `(tenant_id, id)` and `(tenant_id, <natural_key>)` present?
6. Every FK on this table includes `tenant_id` on both sides?
7. Integration test connects as `app_user` and verifies cross-tenant isolation in both directions (read and write)?

Cross-references: schema-side details in `apex:postgres-review/rules/schema-design.md`; the architecture-level decision across multi-tenant strategies (RLS / schema-per-tenant / DB-per-tenant / app-layer filtering) in `apex:architecture-design` Pass 2; the security-audit version of these checks in `apex:security-review` Pass 2 (authn + authz).
