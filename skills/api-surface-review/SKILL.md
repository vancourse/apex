---
name: api-surface-review
description: Reviews API endpoints and response payloads from the *consumer's* perspective — does each field earn its place, is the error shape actionable, is the function over-scoped, are timeouts justified. Complements python-review / typescript-review (which check producer-side correctness) by adding the "does this surface deserve to exist as designed" lens. Fires when reviewing a new endpoint, a new request/response Pydantic/Zod model, a new service handler, or a payload definition. Keywords: api review, endpoint review, payload shape, response model, request model, api design, rest, handler, service function.
---

# API Surface Review

Producer-side reviewers ask "is this code correct?" — this skill asks
"does this surface deserve to exist as designed, from the caller's seat?"

Run this lens **before** approving any PR that adds a new endpoint, a new
request/response model, or a new service-layer handler. It catches a
class of comment that mechanical rules (typing, async, naming) cannot.

## When this skill fires

Trigger if the diff contains any of:

- A new FastAPI route, Express handler, or RPC method
- A new Pydantic `BaseModel` / Zod schema for a request or response
- A new service-layer function called from a handler
- A change to an existing response envelope (new fields, restructured)

If the diff is purely internal (no new external surface), skip this
skill and use the language-specific review skill instead.

## The five passes

Run all five. Each pass takes one read of the diff. Do not skip passes
because the code "looks clean" — clean code with the wrong surface
shape is the exact failure mode this skill exists to catch.

---

### Pass 1 — Field-by-field necessity (response payloads)

For **each field** in every new response model, ask in order:

1. **Did the caller send this in the request?** If yes, deleting it.
   The caller already has it; echoing it back is noise.
   - Resource id in a `/resources/{id}/validate` response → delete.
   - Widget id in a `POST /widgets/{id}/...` response → delete (unless
     the endpoint *creates* a new id, e.g. POST /widgets).

2. **Can the caller compute this trivially themselves?** If yes,
   delete it.
   - `duration_ms` of the request → the caller already knows when it
     sent the request and got the response. Delete.
   - `request_id` echoed back when the caller chose it → delete.

3. **Does the caller take a different action based on this field's
   value?** If no, delete it.
   - A `summary` block that the UI doesn't render → delete.
   - A `version` field nobody branches on → delete.

4. **Is this field redundant with another field at a different
   nesting level?** If yes, collapse.
   - `connection_failures` array + `summary.connection_failure_count`
     → pick one; count is `len(array)`.
   - `is_drifted: bool` + `drift_count: int` → `drift_count > 0`
     answers both.

**Anti-pattern phrases to flag in your own response models:**

- "Echo the input back so the client can correlate" — caller is
  already correlating on the request promise/await.
- "Include a `summary` for convenience" — convenience whose? If the
  UI computes its own counts, the summary diverges.
- "Add `duration_ms` so the client can show perf" — the client has
  a clock.
- "Reflect `attachments` so the UI doesn't have to fetch them
  again" — separate endpoint, separate cache. Don't smuggle.

---

### Pass 2 — Error shape: human + machine, nothing else

The rule for any error/diagnostic payload:

- **One human-readable field** — what's wrong, in plain words the user
  can act on.
- **One machine-readable field** — a stable code/enum for client
  branching and i18n.
- **Optional location** — file:line, table.column, field name. Only if
  the caller can actually use it to navigate.

Anything else is over-normalization. Specifically reject:

- `kind` + `level` + `category` + `message` — pick one taxonomy field.
- `severity: Literal["error", "warning", "info"]` when every entry in
  practice is "error" — delete.
- `error_subtype` nested inside `error_type` — flatten.

**Test:** can the caller answer "what's wrong" and "how do I fix it"
from one read of one entry? If they need to cross-reference a `kind`
to a `level` to a `category`, the shape is over-engineered.

---

### Pass 3 — Timeouts and magic numbers

For any hardcoded timeout, retry count, page size, or limit in the new
code, ask:

1. **Why this number?** If the PR description / comment / commit
   message doesn't say, the number is a guess.
2. **What happens at the boundary?** A 30s timeout on a request that
   *usually* takes 25s means flaky failures in production. A 30s
   timeout on a request that *usually* takes 2s means slow failures
   are masked.
3. **Is the timeout enforced or aspirational?** If the underlying
   call ignores it (e.g. a SQL driver without statement timeout
   configured), the timeout is theater.

**Default stance:** for a new endpoint with no measured latency
distribution, do not hardcode a timeout. Let the framework's default
apply, measure, then add a justified bound. Adding a number "to be
safe" is how silent hangs ship.

---

### Pass 4 — Service-function scope

For any new service-layer function, list the **verbs** it performs.
If there are more than two, it's an orchestrator masquerading as a
unit. Common bloat patterns:

- `check_X`: fetches input → validates → calls external → classifies
  results → formats response. That's 5 verbs. Split: fetch + validate
  in one layer, classification in another, response shaping in the
  handler.
- `process_Y`: load → transform → persist → notify → return. Same
  smell.

**Test:** can you write the function's docstring in one sentence
without `and`? If the sentence has an `and`, the function does too
much.

This pass is not about line count — a 12-line function can do four
things, and a 60-line function can do one thing well. Read intent,
not metrics.

---

### Pass 5 — Producer/consumer dual (applied to API shape)

For every new field, error class, or response branch, write down what
the producer-side fix would look like — the upstream emitting the right
shape — versus the consumer-side workaround (flag, lazy hook, hydration
map, `isExpanded`-gate). Flag any consumer-side fix where the
producer-side is plausible.

See [`rules/principles.md` §1](../../rules/principles.md#1-producerconsumer-dual)
for the canonical principle, the anti-pattern phrase list, and the
applied-lens table covering performance, API shape, error handling, and
polymorphic data. This pass applies that lens specifically to API
surface design.

---

## How to report findings

Group by pass. For each finding, state:

1. The exact field / function / number at issue (`file:line`).
2. Which pass it violates.
3. The one-line fix.

Example:

> **Pass 1 (necessity):** `ValidateResponse.resource_id` at
> `validate_payloads.py:23` — caller sent this in the path
> parameter. Delete the field.
>
> **Pass 2 (error shape):** `ValidationEntry` at `:61` has `kind` +
> `level` + `message`. Collapse `kind` and `level` into one enum;
> keep `message` for humans.
>
> **Pass 3 (timeout):** 30s hardcoded at
> `validate_service.py:18` with no justification. Remove or
> justify against measured p95.

Keep the review under ~10 findings per PR. If there are more, the
surface is wrong-shaped enough that the right action is "rework, then
re-review," not a line-by-line fix list.

## Relationship to other skills

- **`python-review` / `typescript-review`** — orthogonal. They review
  the implementation; this skill reviews the surface. Run both.
- **`ai-pre-review-checklist`** — overlaps with Pass 5 (minimum
  change, producer-side dual). Run this skill *in addition* because
  the checklist operates at diff level, not field level.
- **`pr-review-primer`** — a good PR description makes Passes 3 and 5
  cheaper to run (the "why this number" / "why consumer-side"
  answers should be in the description).

## Seed examples

This skill was distilled from a single PR review where five reviewer
comments were missed by `python-review` + `ai-pre-review-checklist`:

| Comment | Pass |
|---|---|
| "don't reflect resource id back" | Pass 1 (necessity, item 1) |
| "why reflect attachments / duration_ms / summary?" | Pass 1 (items 1–3) |
| "three levels: kind, level, message — too much" | Pass 2 (error shape) |
| "why 30s timeout?" | Pass 3 (timeouts) |
| "feels like a 'do everything' function" | Pass 4 (scope) |

If a future review surfaces a *new* category of API-shape comment
that doesn't fit one of the five passes, add a sixth — don't stretch
an existing pass to cover it.
