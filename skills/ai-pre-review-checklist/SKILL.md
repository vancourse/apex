---
name: ai-pre-review-checklist
description: 8-step pre-review robustness gate for any AI-assisted branch — force branch explanation, layering, state ownership, concurrency, success/failure/fallback, test quality, reviewer simulation, unvalidated gaps. Run this BEFORE you reach `git push`. The skill walks each step's full prompt against an assistant. Fires when a feature branch is ready for review and AI wrote or refactored code. Keywords: pre-review, ai-assisted, pr readiness, reviewer simulation, robustness gate, before push.
---

# AI-Assisted Pre-Review Checklist

Use this checklist before opening a PR when AI assistants helped implement,
refactor, or review the branch.

It is the final robustness gate between "the code exists" and "this branch is
ready for human review."

---

## Purpose

AI assistants produce locally coherent code but often miss branch-shaping
concerns unless asked directly:

- wrong layer, even if the code works
- new abstraction or transport without justification
- shared-state bugs hidden by happy-path tests
- excessive mocking in persistence-heavy tests
- incomplete explanation of success, failure, and fallback semantics
- unclear reviewer-facing narrative

This checklist forces those questions before a reviewer has to ask them.

---

## When To Use This

Run this checklist when any of the following are true:

- AI wrote or substantially refactored production code
- AI added or rewrote tests
- the branch introduces a new workflow, endpoint, service, or transport
- the branch changes persistence, concurrency, or state ownership
- the branch involves agentic behavior, retries, fallbacks, or streaming events

If the branch is non-trivial and AI touched it, use this checklist.

---

## The Required Inputs

Before starting, have these ready:

- the current diff
- the touched tests
- the relevant guideline docs (e.g. `python-review`, `typescript-review` skills)
- a short statement of what the branch is supposed to do

If the assistant cannot clearly restate the branch goal, stop there first.

---

## Non-Negotiable Instructions To The Assistant

When using an AI assistant for pre-review, explicitly ask for:

- findings first, not a summary
- severity ordering
- concrete risks and regressions
- assumptions called out explicitly
- what was not validated
- whether the tests actually prove the intended behavior

Recommended instruction:

```md
Review this branch as if you are preparing it for a strict reviewer.
Prioritize findings, risks, regressions, and missing tests.
Do not start with a summary.
State assumptions explicitly.
Say what you could not validate.
```

---

## Step 1: Force A Branch Explanation

Ask the assistant to explain the branch without hiding behind file names.

Prompt:

```md
Explain what this branch does at a high level in under two minutes.
Then answer:

- why it has this shape
- what state it introduces or changes
- what the user-visible flow is
- what the concurrency assumptions are
- why the transport choice is appropriate

If any of those are unclear from the code, say so explicitly.
```

Pass condition:

- the assistant can explain the branch clearly without reconstructing
  everything from low-level code
- the explanation sounds like a PR primer, not a code dump

If this fails, improve the design note or PR description before review.

---

## Step 2: Force A Layering Review

Ask the assistant whether the code is in the right place, not just whether it
works.

Prompt:

```md
Review the layering of this branch.
Identify any logic that belongs in a thinner API layer, service, orchestrator,
domain object, or helper.
Call out any abstractions that exist only because the code grew organically.
Flag any module or class that is doing too many jobs.
```

Pass condition:

- API modules remain terse
- orchestration is centralized
- helper modules are not acting as disguised service layers
- abstractions are justified by responsibility, not just by file size

---

## Step 3: Force A State-Ownership Review

Prompt:

```md
List every stateful artifact or persisted record this branch reads or writes.
For each one, classify it as:

- shared/global
- artifact-scoped
- thread-scoped
- request-scoped
- temporary/ephemeral

Then identify any ownership ambiguity, accidental sharing, stale-read risk, or
cleanup risk.
```

Pass condition:

- each persisted item has an explicit owner
- thread-local and shared state are not accidentally mixed
- stale-state risks are understood
- temp resources have cleanup paths

---

## Step 4: Force A Concurrency Review

Prompt:

```md
Review this branch for concurrency and multi-instance risks.
Who are the racing callers?
What happens if two requests touch the same underlying state?
Would this still behave correctly if multiple server instances were running?
Flag any in-memory coordination or hidden shared mutable state.
```

Pass condition:

- racing actors are named explicitly
- shared-state behavior is understood
- no process-local assumption exists by accident
- best-effort coordination is described as such, not treated as a hard
  guarantee

---

## Step 5: Force A Success / Failure / Fallback Review

Especially important for agentic or multi-stage flows.

Prompt:

```md
Review the success, failure, cancellation, and fallback semantics of this branch.
Do not limit yourself to exceptions.
Identify cases where the code can "complete" without actually achieving the
intended user outcome.
Flag any fallback whose trigger condition is vague or whose state handoff is
risky.
```

Pass condition:

- success means more than "no exception was raised"
- semantic failure cases are identified
- fallback triggers are concrete
- cancellation and partial-state behavior are understood

---

## Step 6: Force A Test-Quality Review

Prompt:

```md
Review the tests for this branch by layer:

- pure unit tests
- service/integration tests
- endpoint/transport tests

Tell me where mocks are appropriate, where real storage/file-manager should be
used, and what user-visible behavior is still unproven.
Flag any test that mostly verifies mocks rather than behavior.
```

Pass condition:

- tests match the layer they claim to validate
- persistence-heavy tests use real implementations where appropriate
- endpoint contracts are covered when wire shape matters
- remaining gaps are explicitly known

---

## Step 7: Force A Consumer-Tracing Pass

Prompt:

```md
For every contract this branch changes — a table column, a function
signature, a payload field, an SQL gate, a status transition — list the
consumers that read or depend on the contract.

For each consumer, answer:

- does the change break it, or is it correctly accounted for?
- is the consumer covered by a test in this branch, or only by indirect
  coverage of the legacy path?

For every new code path introduced (a new branch, a new variant, a new
status):

- is there at least one test that exercises it directly, not via fallback
  to the legacy path?

For every "mirrors X" claim in the PR description:

- paste X next to the new code, line-by-line, and confirm 1:1 parity.
```

Pass condition:

- consumers are named explicitly, not waved off as "the code that uses this"
- new code paths have at least one direct test, not just fallback coverage
- "mirrors X" claims are backed by line-by-line diff, not approximate
  similarity

If you cannot list 3+ consumers in 5 minutes, the change has more reach
than the diff suggests — replan or split the PR.

---

## Step 8: Force A Reviewer Simulation

Prompt:

```md
Simulate a strict reviewer reading this branch cold.
What are the first 5 questions they will ask?
What design choices are likely to trigger pushback?
What should be explained proactively in the PR description?
```

Pass condition:

- the likely reviewer objections are known in advance
- the PR description addresses non-obvious choices
- the branch no longer depends on the reviewer reverse-engineering intent

---

## Step 9: Force A "What Did You Not Validate?" Answer

Prompt:

```md
What did you not validate in this review?
Separate:

- validated by tests
- validated by code inspection only
- not validated
```

Pass condition:

- unvalidated areas are visible before review
- you know what still needs testing, documentation, or explanation

If the assistant cannot answer this clearly, the review is not trustworthy.

---

## Red Flags Specific To AI-Assisted Branches

Treat these as high-risk until proven otherwise:

- the assistant says "looks good" without listing findings or gaps
- the assistant reviews only the latest file edit instead of the whole branch
- the branch has architecture changes but no high-level explainer
- tests pass, but no one has checked transport contracts or state ownership
- mocks dominate tests that claim to validate storage/file behavior
- new abstractions exist, but nobody can explain why they are the right ones
- a workflow "works" only because happy-path tests were overly constrained

---

## Definition Of Ready For Human Review

Before posting the branch, make sure all of the following are true:

- the assistant can explain the branch at a high level
- the API/layering story is coherent
- state ownership is explicit
- concurrency assumptions are defensible
- success/failure/fallback semantics are clear
- tests match the actual layer and behavior being exercised
- consumers of changed contracts are traced; new code paths have direct tests
- "mirrors X" claims in the PR description are backed by line-by-line diff
- you know what was only inspected and what remains unvalidated
- the PR description is ready (see `pr-review-primer` skill)

If any of those are missing, the branch is not ready for external review.

---

## Recommended Workflow

Use these skills in this order:

1. `python-review` or `typescript-review` — code-level patterns and
   anti-patterns while implementing.
2. `protocol-first-workflow` — architecture shaping before implementation
   grows (Python).
3. `ai-pre-review-checklist` — this skill, the robustness gate before asking
   humans to review AI-assisted code.
4. `pr-review-primer` — reviewer-facing explanation for the PR body.
