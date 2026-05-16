---
name: responding-to-review
description: Discipline for responding to PR review comments — every blocker needs a concrete artifact, every reply maps to a diff, mechanically verify flagged lines are touched before requesting re-review. Fires when addressing review comments, responding to reviewer feedback, pushing a "fix review comments" commit, or preparing for re-review. Keywords: review comments, reviewer feedback, address comments, PR feedback, fix review comments, blocker, re-review, code review reply, address reviewer.
---

# Responding to PR Review Comments

A reviewer comment is only "addressed" when the PR contains a concrete artifact proving it. Never reply "addressed" without a corresponding diff.

This skill triggers when you're working through reviewer feedback. The canonical protocol lives in [`rules/responding-to-review.md`](../../rules/responding-to-review.md) — read that file when this skill fires.

## Quick reference

For each reviewer comment, your reply must include:

- **Status:** fixed / intentionally deferred / question
- **File path(s) changed**
- **Proof artifact:** diff snippet, new test name, or commit SHA
- If "fixed": one line describing the behavior change
- If "deferred": ticket link and reason

Before requesting re-review:

1. List every inline comment (file, line, issue)
2. For each: mechanically verify the diff touches that exact location
3. Confirm each blocker has a code-change or test artifact
4. Reply on individual threads (don't mass-resolve)
5. Run the verification command (`make check-pr`, `pytest`, `tsc`, `ruff`)

## Read the full protocol

When this skill fires, read [`rules/responding-to-review.md`](../../rules/responding-to-review.md). It covers:

- Blocker resolution protocol (artifact requirements)
- Reply-to-diff mapping rules
- Mechanical flagged-line verification
- Pre-re-review gate

## Why this matters

Mass-resolving threads with "addressed" without diff proof forces the reviewer to re-verify every comment themselves. That's slow, frustrating, and burns the reviewer's good will. The discipline costs ~30 seconds per comment; the savings is one re-review cycle per PR.

## Relationship to other skills

- **`pr-discipline` §7** — points to the same rule file. This skill is the trigger; `pr-discipline` is the broader PR-workflow umbrella.
- **`ai-pre-review-checklist`** — runs *before* opening the PR; this skill runs *after* opening, when comments come back.
