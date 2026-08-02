# ADR-00NN — <decision, stated as an outcome>

**Status:** Proposed | Accepted (FROZEN <date>) | **REJECTED at review <date>** | Superseded by [00NN](00NN-….md)
**Pass:** <architecture-design pass, or "amendment to 00NN">

Add the row to `docs/adr/README.md`'s index in the same commit. An ADR absent from the
index is one nobody will find.

## Context

The forces in play — constraints, prior decisions, what changed to make this a question
now. Enough that a reader in a year understands why this was live, without asking you.

## Decision

What is decided, in the active voice, as a rule the codebase can be checked against.
Number sub-decisions (D<NN>.1, D<NN>.2) so later amendments can correct one precisely
rather than rewriting the ADR — see 0017 → 0018.

## Alternatives considered

| Alternative | Why not |
| --- | --- |

An ADR with no alternatives is a record of a preference, not a decision.

## Consequences

What this makes easy, and what it makes hard. Include both:

- **Security.** What trust boundary this moves, and what inherits it.
- **Reversibility.** What it costs to undo once code depends on it.

## Enforcement

What makes this real rather than aspirational — an arch gate, a CI check, a test.
"By convention" is an honest answer, and names it as the weakest kind.

---

<!--
REJECTED ADRs stay in the tree, unedited, with a §0 post-mortem added at the top
explaining what the review found. Do not delete them. A rejected ADR is the only
durable record of an option the team has already priced — delete it and the next
author re-proposes it, and the review re-derives the same objection from scratch.
Kept rejections also make a repeated root cause visible across a decision thread.
-->
