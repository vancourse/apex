---
name: verification-before-completion
description: Phase 3 gate of the SDLC flow — verify that the change actually works before claiming done. Tests run, logs checked, UI exercised, type-check passes. Fires when about to declare a task complete, before opening a PR, when the user asks "is this done?", or when transitioning from implementing to closing out work. Keywords: done, complete, finished, ready, ship, verify, prove, validation, working, tested.
---

# Verification Before Completion

A task is never "done" until verified. Code that compiles is not code that works. Tests that pass are not features that work. This skill exists because the most common AI failure mode is declaring success based on code changes alone.

## The Rule

Before you say the task is done, prove it. The proof depends on the change type — but there is always proof.

| Change type | What "verified" looks like |
|---|---|
| Behavior change | Run the affected tests; they pass. Run a smoke test of the change end-to-end. |
| New endpoint / API | Hit it with the actual request shape (curl, Postman, or a test). Confirm the response matches the typed contract. |
| Bug fix | Reproduce the original bug first. Apply the fix. Re-run the reproduction; confirm the bug is gone. |
| UI change | Open the page in a browser. Exercise the change. Cover the golden path AND at least one edge case (empty state, error state). |
| Refactor with no behavior change | Run the full test suite. Compare type-check output before/after. |
| Performance fix | Measure before. Apply. Measure after. The number must move in the right direction. |
| Dependency bump | Run the build + test suite + type-check. Check for new warnings. |

## What does NOT count as verification

- "It looks right." Looking is not running.
- "The model says it should work." The model is not a runtime.
- "I made the change in the right file." File correctness is necessary, not sufficient.
- "I wrote tests but didn't run them." Untested code is unverified.
- "The lint passes." Lint is not behavior.
- "I checked the diff." Reviewing your own diff is not exercising the code.

## The verification checklist

Before declaring done, you should be able to answer:

1. **What was the smallest change that should have fixed this?** — and is that what you did, or did scope creep?
2. **What did you run to prove it works?** — name the command, name the test, name the URL.
3. **Did you cover the golden path AND an edge case?** — happy path success is not proof; one edge case is the minimum.
4. **Did you check the logs?** — most projects write logs to a known directory; find it and watch for new errors during your verification.
5. **What did you NOT verify?** — be explicit. "Tested handler locally; did not exercise the migration." This makes gaps visible.

If you can't answer 1-4, you have not verified — you have hoped.

## Repo-specific log patterns

Each repo writes logs somewhere project-specific. Find the pattern once and remember it:

- Look for `tmp/`, `logs/`, `.logs/` at repo root
- Check the dev-server start command for output redirection
- Check `docker compose logs <service>` if running via compose

When something isn't working, the logs almost always tell you why. The model's first move on "this isn't working" should be "show me the most recent log file," not "let me read the code again."

## When to invoke this skill

- About to say "the task is done"
- About to open a PR
- The user asks "is this working?" / "is this done?"
- Transitioning from Phase 2 (implementing) to Phase 4 (pre-PR gate) in the SDLC flow
- After a multi-file refactor or non-trivial change

## Relationship to other skills

- **`ai-pre-review-checklist`** — runs at Phase 4 (pre-PR). Verification (this skill) is Phase 3 — gates the transition from "implementation complete" to "ready to review." Pre-PR assumes verification already happened.
- **`pr-discipline` §5** — the self-review checklist mentions "all tests passing." This skill is the deep version of that bullet — *how* you verify, not just that you did.
- **Superpowers' `verification-before-completion`** — broader verification discipline. This skill adds the SDLC-flow-specific framing (Phase 3 gate) and the repo-log-finding pattern.
