---
name: recon
description: Reconnaissance brief before design — promotes apex-flow §1a from an in-head checklist into a first-class, artifact-producing step. Scoped to the change's blast radius, it enumerates the authoritative primitives that already answer the design's questions, distills their CONTRACTS (not signatures), captures invariants + trust boundaries, runs the producer/consumer + first-affordance checks against that fact base, and persists durable semantic facts to domain-knowledge. Output is a short Recon Brief that feeds design. Pairs with apex:apex-flow §1a (the in-head quick version), apex:design-feature (downstream — consumes the brief), and apex:memory-note (persists the durable facts). Fires before designing a non-trivial change, especially one framed as "support a new scope/source/kind/variant" or "shrink/refactor bloated X". Keywords: reconnaissance, recon, facts brief, existing primitive, blast radius, contracts, invariants, before design, codebase recon, subtractive design.
---

# Recon

The step between "I have a requirement" and "I have a design." It puts the codebase's **authoritative primitives and invariants on the table as an artifact** — *before* the design commits — so the design uses what already exists instead of building machinery to reconstruct it.

`apex-flow` §1a already carries the reconnaissance questions, but as an *in-head* checklist run from memory. recon is the same discipline **promoted to a first-class, artifact-producing step**: it ends with a written **Recon Brief** that `apex:design-feature` (and the §1b adversarial checklist) consume.

## The failure it prevents

Designs go **additive** — new fields, enums, guards, tracking state — when the authoritative primitive that already answers the design's question is never surfaced. The canonical loss: a ~1000-LOC design that *stored and classified scope* on a record, when one existing context call already returned exactly that scope with authorization applied. The fix was subtractive (delete the machinery, query the primitive) — but you cannot reach a subtractive design if you never put the primitive on the table. recon puts it there, with evidence, first.

This is the **machinery-shape variant** of apex-flow §1a-Q1's cost-shape inversion: not *"can N operations become 1?"* but **"can stored-and-reconstructed become queried-from-context?"** Both are the same move — stop reconstructing what the system already hands you.

## When to invoke

- Before `apex:design-feature` or the apex-flow §1b adversarial checklist, on any **non-trivial, design-bearing** change.
- **Especially** when the task is framed as *"support a new scope / source / kind / variant"* or *"shrink / refactor bloated X"* — the two framings that most reliably hide an existing primitive. The first reads as "add machinery to represent the new thing"; the second anchors on the bloated artifact's shape (principles.md §2) instead of re-deriving the minimal design.
- In an unfamiliar or scope-heavy part of the tree, where the relevant primitives aren't already in your working memory.

**Skip** for trivial work (typo, one-line behavior change, obvious bug) — recon is for changes you'd *design*, not patch.

## Method — produce a Recon Brief

### Step 0 — Scope the blast radius (YAGNI guard)

Name the **specific question(s)** the design must answer: *"what files can a thread see?"*, *"how is X persisted and who reads it?"*, *"who emits event Y and in what shape?"*. recon is scoped to the code that answers **those** questions — **not** the whole subsystem. If you can't name the question, you're not ready to recon — clarify the requirement first. **Do not boil the ocean:** whole-codebase fact-gathering is expensive, mostly irrelevant, and rots before the next change.

### Step 1 — Enumerate the primitives + call sites

For each question, grep / Explore for the functions, types, and abstractions that already touch it. Look for **sibling abstractions** — per-dialect / per-connector / per-engine folders, similarly-named modules, similar return types (principles.md §3). List candidates with `file:line`.

**On a large or unfamiliar tree, build/refresh a code graph first — then query it instead of grepping blind.** A structural index is the precondition for trustworthy enumeration here: without one you *will* miss sibling primitives and design additively. Resolve the index to one of three states before enumerating: **NONE** → install a tool once (`/apex:setup`) and build it; **STALE** (the working tree moved since the index was generated) → refresh it; **FRESH** → query it. Installing and maintaining are separate jobs — `/apex:setup` only *installs*; keeping the index fresh is the **tool's** job, not apex's (Graphify's post-commit hook rebuilds on commit, Serena is live by construction, Claude Context needs a re-index). Options: **Graphify** (`/graphify .`, a committed knowledge graph + PreToolUse hook), **Serena** (live LSP symbol navigation, never stale), or **Claude Context** (semantic vector search). See the README's *Large-codebase context tools* section. **Presence is not freshness:** a confidently-stale index is *worse* than none — it reads as authoritative while pointing at moved or deleted primitives. **If the index is absent, declined, or possibly stale, say so in the Recon Brief** — emit an explicit *"structural coverage: best-effort, sibling-miss risk"* caveat rather than a silent clean bill of health. **Two rules that bound how far to trust it:** (1) the graph answers Step 1 (*where it lives* + *what touches it*) — it does **not** answer Step 2 (the contract), so you still read the load-bearing functions. (2) Treat the graph as **ephemeral**: never trust a cached structural fact as stored truth — it rots exactly like a stale memory note. *(On a small/familiar tree, grep/Explore is fine — don't stand up an index for a handful of files.)*

### Step 2 — Read the load-bearing ones; distill the CONTRACT, not the signature

For the top candidates, **read them** and write down what they **guarantee** — not their type signature, their *semantics*: what they include / exclude, what authz / ordering / uniqueness they apply, what they return when empty, what they re-mint vs. preserve.

> A signature says `get_thread_files(thread, user) -> list[File]`.
> The **contract** says *"thread uploads ∪ agent-shared files, authz already applied."*
> The contract is what cracks the design. The signature isn't.

This is the step a code graph **cannot** do for you — it gets you to the right three functions; you still have to read them.

### Step 3 — Capture invariants + trust boundaries

- **Invariants** the design must not break: uniqueness constraints, ordering guarantees, wire-format symmetry (principles.md §4), "all writes go through service X."
- **Trust boundaries:** which stored fields are **authority** vs. **hints**? A field that can be stale, hand-edited, or re-minted on import/export is a *hint* — never reconstruct authorization or identity from it. Name the **source of truth** (`file:line`) for each fact.

### Step 4 — Run the §1a dual + affordance checks against the findings

- **Producer/consumer dual** (principles.md §1): if the obvious fix sits consumer-side, write down what the producer-side dual would be.
- **First plausible affordance** (principles.md §2): if an existing bloated artifact (a prior PR, a half-broken flag) is framing the work, set it aside and ask *"would I design this if it didn't exist?"*

Same checks as apex-flow §1a — recon just runs them against an **explicit fact base** instead of from memory.

### Step 5 — Diff against project memory; persist the durable facts

- Check `~/.claude/domain-knowledge/<project>.md` (and the project's CLAUDE.md) for facts **already known** — don't re-derive them.
- For **new semantic facts** (contracts, invariants, trust boundaries) that will matter again, offer to persist them via `apex:memory-note` → domain-knowledge.
- **Split rule (load-bearing):** *semantic* facts accrue — persist them. *Structural* facts (call graph, who-calls-whom) are **ephemeral** — regenerate next time, never persist; they rot.

## Output — the Recon Brief

A short, structured artifact (not prose) — the hand-off to design:

```
RECON BRIEF — <feature / change>

Questions the design must answer:
  1. <question>          verdict: answered by <primitive> @ file:line
  2. <question>          verdict: NO primitive — genuinely new (justify)

Authoritative primitives (CONTRACT, not signature):
  - <fn> @ file:line — guarantees: <includes / excludes / authz / ordering / empty-case>

Invariants / trust boundaries:
  - <invariant> — source of truth: file:line
  - <field> is a HINT, not authority (stale on <event>); authority = <primitive>

Producer/consumer dual + affordance note:
  - <one or two lines>

Memory:
  - already in domain-knowledge: <facts>
  - NEW (persist?): <facts>
```

## Pass condition / hand-off

recon is done when:

- Every question the design must answer has a **verdict**: an authoritative primitive (with contract) **or** a justified *"genuinely new."*
- Invariants + trust boundaries are named with their sources of truth.
- New durable semantic facts are persisted (or explicitly declined).

Hand off to **`apex:design-feature`** / apex-flow §1b. The design must now either **use** the named primitives or **justify** why each can't be extended — principles.md §3's pure-addition test, now answerable with evidence instead of hand-waving.

## Anti-goals

- **Don't boil the ocean** — blast-radius only (Step 0).
- **Don't stop at signatures** — the contract is the point (Step 2).
- **Don't persist structural facts** — they rot; only semantic facts accrue (Step 5).
- **Don't let recon become design** — it ends at *"here are the facts,"* not *"here's the solution."* The design decision belongs to `apex:design-feature` / §1b.

## Relationship to apex-flow §1a

recon **is** apex-flow §1a, promoted:

| | apex-flow §1a | recon |
|---|---|---|
| Form | in-head checklist | artifact (the Recon Brief) |
| When | quick, any planning | design-bearing work; unfamiliar / scope-heavy tree |
| Output | framing in your head | a written brief design consumes |
| Memory | — | diffs against + persists durable semantic facts |

For small work, §1a from memory is enough. For work you'd *design*, run recon and emit the brief.

**The flywheel:** recon front-loads what `apex:memory-note` back-loads. Each design's recon is cheaper because the previous one persisted its semantic facts to domain-knowledge.
