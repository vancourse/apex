---
name: postgres-review
description: Generic PostgreSQL review rules — schema design, multi-tenant RLS, indexing, query performance, migrations, transactions + locking, observability. Routing table inside; load only the rule file matching the current task. Fires when designing or reviewing a Postgres schema change, RLS policy, migration, index addition, or hand-rolled SQL beyond ORM convenience methods. Pairs with apex:python-review/rules/db-and-sql.md (ORM/Python-side concerns) — load THIS skill for Postgres-internal topics. Keywords: postgres, postgresql, sql review, rls, row level security, multi-tenant, schema, index, migration, transaction, isolation, locking, explain, pg_stat_statements, vacuum.
---

# Postgres Review Rules

Generic, cross-project PostgreSQL rules. Read only the rule file(s) matching
the current task — do not load all of them.

This skill covers **Postgres-internal** concerns (schema, indexes, RLS
policies, migrations, transactions, locking, vacuum). For **ORM / Python-side**
concerns (N+1, connection pooling, cache deduplication, idempotency tests,
pagination), load `apex:python-review/rules/db-and-sql.md` instead. The two
skills are designed to be loaded together when a change crosses the boundary.

## Routing table

| Task touches…                                                                                                              | Read                                              |
| -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Column data types, constraints, generated columns, JSONB strategy, primary keys, composite-UNIQUE-as-FK-enforcer pattern   | `rules/schema-design.md`                          |
| RLS policies, non-privileged role pattern, `SET LOCAL app.tenant_id`, `FORCE ROW LEVEL SECURITY`, cross-tenant FK enforcement | `rules/multi-tenancy-rls.md`                      |
| **PR-time security audit** (secrets / authn+authz / input val + output enc / dep vuln + supply chain / audit log)          | invoke **`apex:security-review`**                 |
| **Design-phase threat modeling** (STRIDE against the feature's attack surface)                                             | invoke **`apex:threat-model`**                    |
| **Architecture-level persistence + tenancy decision** (which role model, which RLS strategy, which migration tool)         | invoke **`apex:architecture-design`** Pass 2      |

## Coming next (planned)

The skill is being expanded incrementally. Planned rule files, with the
topics they will cover:

- `rules/indexing.md` — B-tree / GIN / GiST / BRIN / partial / covering index choice, `EXPLAIN (ANALYZE, BUFFERS)` reading, join + CTE strategy.
- `rules/migrations.md` — migration ordering, expand/contract, online DDL, backfill discipline, idempotent SQL.
- `rules/transactions-locking.md` — isolation levels, advisory locks, `FOR UPDATE SKIP LOCKED`, deadlock patterns, statement timeouts.
- `rules/observability.md` — `pg_stat_statements`, `auto_explain`, slow-query log, vacuum + autovacuum tuning.

Until those land, defer to `apex:python-review/rules/db-and-sql.md` for the
Python-side patterns that touch the same topics (pagination, N+1, pooling),
and to `apex:architecture-design` Pass 2 for foundational decisions.

## When this fires

- Designing or reviewing a new table / column / constraint / index
- Authoring or reviewing an RLS policy
- Writing or reviewing a migration
- Investigating a slow query, deadlock, or vacuum issue
- Writing hand-rolled SQL beyond ORM convenience methods

## When this does NOT fire

- `session.query(Foo).filter_by(...)` and similar ORM helpers — load
  `apex:python-review/rules/db-and-sql.md` instead.
- Routine CRUD the ORM handles trivially.

## Project-specific overlays

Project-specific Postgres rules — tenant role names, GUC names, the canonical
session helper, the explicit RLS-protected table list, the composite-FK
patterns that are load-bearing in *your* schema — belong in a per-repo
overlay loaded **in addition** to this skill. In BookBridge:
`.claude/skills/bookbridge-pre-pr-check/rules/postgres-bb-specifics.md`
(see `bookbridge-pre-pr-check`).
