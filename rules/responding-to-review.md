# Responding to PR Review Comments

How to address reviewer comments with rigor — every blocker resolved with a concrete artifact, every reply mapped to a diff.

## The Rule

A reviewer comment is only "addressed" when the PR contains a concrete artifact proving it. Never reply "addressed" without a corresponding diff.

## Blocker Resolution Protocol

A blocker is only resolved when the PR contains one of:

- A code change in the referenced file, OR
- A new or updated test file, OR
- An explicit reviewer-approved rationale for deferral (with ticket link)

**Before posting "addressed" or "fixed", include in your reply:**

1. The blocker text (quoted)
2. The changed file path(s)
3. Proof artifact: diff snippet, new test name, or commit SHA
4. The verification command run (e.g., `make check-pr`, targeted `pytest`, `ruff`, `pyright`, `tsc`)

## Every Reply Must Map to a Diff

For each reviewer comment, your reply must include:

- **Status:** fixed / intentionally deferred / question
- **File path(s) changed**
- If "fixed": one line describing the behavior change
- If "deferred": ticket link and reason

## Verify Every Flagged Line Has a Corresponding Diff

**When:** Pushing a "fix review comments" commit.

**Rule:** Mechanically verify that every specific `file:line` the reviewer cited appears in the diff. A commit titled "address review comments" that leaves flagged code untouched is worse than no commit — it signals diligence while delivering none.

**Checklist:**

1. List every inline comment (file, line, issue)
2. For each: confirm the diff touches that exact location
3. If intentionally not addressed, reply on GitHub explaining why before requesting re-review
4. Run `git diff --stat` and cross-reference the reviewer's file list

## Pre-Submit Blocker Gate

**Before requesting re-review:**

1. Re-read the reviewer's summary; list all blockers
2. Confirm each blocker has a merged code/test artifact
3. If any blocker lacks an artifact, do NOT ask for re-review
4. Reply to each individual comment with the artifact pointer (don't just mass-resolve)

## Why this matters

Mass-resolving threads with "addressed" or "done" without diff proof:

- Forces the reviewer to re-read every comment and verify the change themselves (slow, frustrating)
- Hides cases where you missed a comment or addressed only part of it
- Creates downstream confusion when the same issue resurfaces and the resolved thread suggests it was already fixed

The discipline costs ~30 seconds per comment. The savings is one re-review cycle per PR.
