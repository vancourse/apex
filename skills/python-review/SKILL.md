---
name: python-review
description: Generic Python code review rules — architecture, types, SQL, async, testing, error handling, logging, security, APIs, hygiene, PR discipline, AI code smells. Routing table inside; load only the rule file matching the current task. Fires when investigating a specific Python anti-pattern, auditing a diff for review, or planning a refactor — NOT for every Python edit. In BookBridge, prefer `bookbridge-pre-pr-check` as the entry point; it cross-references rule files here. Keywords: python anti-pattern, python review, code review, refactor, pytest, pyright, asyncio, pydantic, fastapi, sqlalchemy.
---

# Python Review Rules

Generic, cross-project Python rules. Read only the rule file(s) matching
the current task — do not load all of them.

## Routing table

| Task touches...                                                              | Read                                        |
| ---------------------------------------------------------------------------- | ------------------------------------------- |
| Class/module layering, SOLID, GoF patterns, service-class signal             | `rules/architecture.md`                     |
| Pydantic models, dataclasses, typing, generics, state transitions            | `rules/types-and-models.md`                 |
| SQL queries, ORM, N+1, pagination, caching, connection pools, idempotency    | `rules/db-and-sql.md`                       |
| asyncio tasks, locks, timeouts, sync-in-async, SSE streaming                 | `rules/async-concurrency.md`                |
| pytest, fixtures, stubs vs MagicMock, integration tests, mock discipline     | `rules/testing.md`                          |
| Exception specificity, fail-fast, silent data loss, `assert` in production   | `rules/error-handling.md`                   |
| `structlog`, log levels, PII redaction, error IDs, docstring contracts       | `rules/logging-observability.md`            |
| Auth, secrets, SQLi, path traversal, prompt injection, parsing bounds        | `rules/security.md`                         |
| FastAPI routes, request validation, partial success, pagination envelopes    | `rules/api-design.md`                       |
| Imports, layer placement, dead code, docstring drift, dependency management  | `rules/code-hygiene.md`                     |
| AI-assisted code (`getattr`/`hasattr`/`isinstance` speculation, SDK guards)  | `rules/ai-code-smells.md`                   |

For PR sizing, the blocker-artifact protocol, and review-reply discipline, see the top-level `pr-discipline` skill — it covers all languages, and its companion [`rules/responding-to-review.md`](../../rules/responding-to-review.md) holds the canonical review-comment protocol.

## When multiple topics apply

Pick the dominant one. Don't load everything. If a rule lives in two
topics, the dominant file owns it and others cross-reference by name.

## Project-specific overlays

Project-specific rules (layering conventions, package bans, internal API
names, canonical wrapper tables) live in each repo's own
`.claude/my-guidelines/python-review.md`. Load that IN ADDITION when
working in that project.
