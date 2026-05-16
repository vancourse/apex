---
name: memory-note
description: Capture a high-signal lesson, reviewer correction, or durable project fact using the user's memory schema.
disable-model-invocation: true
---

# Memory Note

Create or update a memory/domain-knowledge note only if the lesson is surprising, non-obvious, and likely to matter again.

Do not save:

- facts already obvious from source code
- temporary task state
- secrets
- broad preferences with no example
- duplicate notes

Use this schema:

```md
# <Short title>

Type: feedback | project | reference | user
Scope: <repo/subsystem/person/tool>
Source: <PR/review/issue/command/conversation>
Last verified: YYYY-MM-DD
Rule: <what to do next time>
Why: <why this matters>
Invalidation: <when to re-check>
```

Prefer `~/.claude/domain-knowledge/<repo>.md` for durable project facts. Prefer Claude Code auto-memory for personal workflow patterns and recurring corrections.
