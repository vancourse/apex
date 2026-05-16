---
name: pr-review-primer
description: Copy-paste PR description template that front-loads reviewer-facing intent — what the branch does, why this shape, high-level flow, state ownership, concurrency, transport choice, success/failure/fallback, test plan. Fires when writing a PR description or top-level PR comment. Keywords: pr description, pr primer, reviewer-facing, pr template.
---

# PR Review Primer Template

Use this as a copy/paste template in the PR description or in a reviewer
comment before the branch gets large.

```md
## What this branch does

<1-3 sentences on the user-visible or system-level change>

## Why this shape

- API layer: <what stays in endpoint / handler>
- Internal entry point: <service / orchestrator / facade>
- Why this split: <why workflow logic lives there>

## High-level flow

1. <step 1>
2. <step 2>
3. <step 3>
4. <step 4>

## State ownership

- Shared / artifact-scoped: <what is safe to share>
- Thread-scoped: <what must stay local to a thread>
- Temporary / ephemeral: <what is created and cleaned up>

## Concurrency model

- Racing callers: <who can collide>
- Assumption: <single instance / multi-instance / best-effort>
- Coordination approach: <none / filesystem / DB / optimistic isolation>

## Transport choice

- Transport: <REST / WS / background job / other>
- Why this is the right fit: <one or two bullets>
- Why not reuse a different existing transport: <brief reason>

## Success / failure / fallback

- Success means: <what must be true, not just "no exception">
- Failure means: <what user-visible or semantic failure looks like>
- Fallback: <when it triggers and what it preserves>

## Test plan

- Unit: <pure logic covered>
- Integration: <real storage / file I/O / service-layer coverage>
- Endpoint / transport: <wire-contract coverage>
```

## Minimal Version

If the change is smaller, use this compressed version:

```md
## Summary

- Problem: <one sentence>
- Shape: <endpoint -> service/orchestrator -> persistence>
- State: <artifact/thread/temp>
- Concurrency: <how collisions are prevented or tolerated>
- Transport: <why this transport>
- Success/fallback: <semantic success + fallback trigger>
- Tests: <unit/integration/endpoint split>
```
