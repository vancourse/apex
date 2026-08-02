# <Feature> — PRD

**Status:** Draft | **Frozen <date>**
**Lives at:** `docs/<feature-slug>/prd.md` — first link in the chain, then `design.md`, then `impl-plan.md`.

## Problem

What is broken, missing, or costly today. Written from the user's or operator's
side, not the system's. If you cannot state the problem without naming a solution,
the problem is not understood yet.

## Scenarios

Numbered, concrete, and observable. **These are load-bearing** — the impl-plan mirrors
them 1:1 as integration tests, so a vague scenario becomes an untestable layer.

1. <actor> <does something> and <observable outcome>
2.

## In scope

## Out of scope

Name the tempting things you are deliberately not doing, and why. A deferral list that
is empty means the scope was never cut.

## Open questions

Number them (Q1, Q2, …) so the design can discharge them by reference. A PRD may freeze
with open questions — it may not freeze pretending it has none.

## Success metric

One measure that would tell you this worked, checkable after it ships. "Users are happy"
is not one.

## Sequencing

What must land first, and what it unblocks.

## Freeze record

Frozen at apex:prd-review Pass 7 on <date>. Scope changes after this point require an
explicit amendment recorded here, not a silent reinterpretation.

| Date | Change | Why |
| --- | --- | --- |
