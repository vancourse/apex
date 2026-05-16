# Review Risk Rules

Note: this file lives at user level (`~/.claude/rules/`) so `paths:` frontmatter is intentionally omitted — it serves as an invocable reference checklist, not an auto-triggered project rule.

Before calling a change ready, check whether it touches any high-risk area:

- auth, permissions, secrets, or data access
- persistence, migrations, or background jobs
- concurrency, retries, queues, or idempotency
- billing, payments, quotas, or limits
- external APIs, webhooks, or third-party formats
- public API contracts or generated types
- large dependency or lockfile changes

If yes, include a short risk note and the verification performed.
