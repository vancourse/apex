# <Feature> — Recon brief

**For:** `design.md` · **Run before** the design commits to a shape.

Recon ends at *"here are the facts"*, never *"here is the solution."* The decision
belongs to the design. Scope this to the change's blast radius — whole-subsystem
fact-gathering is expensive, mostly irrelevant, and rots before the next change.

## Questions the design must answer

One row per question. Every question needs a **verdict**: an authoritative primitive,
or a justified "genuinely new". A question with no verdict means recon is not done.

| # | Question | Verdict |
| --- | --- | --- |
| 1 |  | answered by `<primitive>` @ `file:line` / NO primitive — genuinely new because … |

## Authoritative primitives — contract, not signature

The signature is not the point. Write what the primitive **guarantees**: what it
includes and excludes, what authorization or ordering it applies, what it returns when
empty, what it re-mints versus preserves.

> A signature says `get_thread_files(thread, user) -> list[File]`.
> The contract says *"thread uploads ∪ agent-shared files, authz already applied."*
> The contract is what cracks the design.

| Primitive (`file:line`) | Guarantees |
| --- | --- |

## Invariants and trust boundaries

Which stored fields are **authority** and which are **hints**? A field that can be stale,
hand-edited, or re-minted on import is a hint — never reconstruct authorization or
identity from one.

| Fact | Source of truth (`file:line`) | Authority or hint |
| --- | --- | --- |

## Producer/consumer dual

If the obvious fix sits consumer-side, write down what the producer-side version would
be. Then say which you are choosing.

## Affordance check

Is an existing artifact — a prior PR, a half-built flag, a bloated module — framing this
work? Set it aside and answer: *would I design it this way if that did not exist?*

## Memory

- Already known (CLAUDE.md / memory / domain knowledge):
- New and worth persisting:

Persist **semantic** facts (contracts, invariants, trust boundaries) — they accrue.
Never persist **structural** facts (who calls whom); regenerate those, they rot.
