---
name: pr-discipline
description: PR workflow discipline — draft-PR default, ask before push, full check suite before every commit, squash to one commit per PR, push once, slice non-trivial work into layered PR stacks (≤400 LOC per PR, tests with their layer), keep reviews scoped to the single PR diff. Fires when creating a PR, committing, pushing, reviewing a PR, or planning multi-layer work. Keywords: PR, pull request, draft, commit, push, squash, review, layered, stack, gh, git push.
---

# PR Discipline

Four rules that catch the most common PR-workflow failures: surprise pushes, push-then-fix-then-push cycles, oversized monolithic PRs, and review scope creep.

## 1. Always Create Draft PRs and Ask Before Pushing

Never push branches or create PRs without explicit user confirmation first. When asked to "create a PR", default to draft (`gh pr create --draft`) unless the user explicitly says to publish it.

**Why.** Users want the option to keep work local or review it before publishing. Surprise pushes / PR creation removes that control.

**How to apply.** Before any `git push` or `gh pr create`, confirm. If creating a PR is clearly requested, default to `--draft`. Mark ready-for-review only when the user says so.

## 2. Pre-Commit Checks + Minimal-Push Discipline

### Pre-commit checks (run before every `git commit`)

Run the project's full check suite locally before committing. The exact commands are repo-specific — look in `package.json` / `Makefile` / `pyproject.toml` / `CONTRIBUTING.md` for the canonical recipe — but the categories are universal:

- **Build** — strict-type errors that only surface during a full build, not in an editor
- **Lint** — ESLint, Ruff, golangci-lint, etc.
- **Format check** — Prettier, ruff format, gofmt, etc.
- **Type check** — pyright, tsc, mypy, etc.

If any fail, fix and re-run before committing. Never assume "it looks fine" — always verify.

### Push cadence — minimize pushes

**Rule.** Iterate locally until the change is fully tested and known-good. Then squash to **one** commit per PR. Then push **once**. Do not push-then-fix-then-push.

**How to apply.**
- During iteration, commit freely on a local branch (many small WIP commits are fine).
- Before pushing, squash all WIPs into one clean commit per PR (`git rebase -i` or `git reset --soft <base> && git commit`).
- Run the full pre-commit check suite on the squashed commit before pushing.
- Exercise the change end-to-end locally — run the relevant tests, hit the endpoint, load the UI — before pushing.
- Only then `git push`. Confirm with the user first (see §1).

**Why.**
- CI is a shared resource. Repeated pushes spam reviewers with notifications, force-push noise on already-opened PRs, and burn CI minutes. Readers of the PR timeline can't tell which push is "the real one."
- The push → fix → push → fix cycle is the symptom of skipping pre-commit checks. The preferred workflow is: build locally, test locally, squash, push once.

**Anti-pattern to avoid.** Committing, pushing, watching CI, fixing a lint error, pushing again, watching CI, fixing a typecheck error, pushing again. Every intermediate push should have been a local commit that got squashed away before the first push.

## 3. Layered PR Stack Discipline

When planning non-trivial work (new feature, cross-cutting change, multi-layer refactor), default to a **layered PR stack** rather than one large PR.

**Core rules.**

1. **Slice by architectural layer, not by feature completeness.** Foundation (types + storage + migrations) → service/domain logic → API surface → frontend renderer. Each PR lands a complete, testable layer even if the feature isn't user-visible yet. Never mix layers in one commit.

2. **Cap hand-written LOC per PR.** Target ≤400 hand-written lines; hard ceiling ~600. Generated code (migrations, lockfiles) doesn't count. If a layer exceeds the ceiling, split it further (e.g., types-only PR + storage-only PR).

3. **Tests live with their layer.** Storage tests in the foundation PR, service tests in the service PR, HTTP tests in the API PR, UI tests in the frontend PR. Don't back-fill tests into an earlier PR.

4. **One commit per PR.** Squash before opening. The commit message is one line explaining *why*, plus a short body if needed. No tooling trailers.

5. **No speculative abstractions.** Three similar lines beats a premature helper. Don't introduce a base class, mixin, or config option for a hypothetical second caller.

6. **Route changes to the correct branch while coding, not at PR time.** If you notice uncommitted changes spanning multiple layers, stash and route per-layer *before* committing. Don't commit across layers and try to split later — that path leads to painful rebases.

**Why.** A clean 3-PR stack (foundation → service → API → UI, each one thing at one layer) reads as joyful to review. Each PR is small enough to hold in your head, has tests scoped to it, and reviewers can approve layer-by-layer with confidence. Mixing layers forces a painful re-routing + rebase-with-conflicts before the stack is reviewable.

**How to apply.** When the user asks to implement a non-trivial feature, or when you're about to write code that touches more than one of {core types, storage, service, API, frontend}: pause and propose a PR-stack slicing plan in plan mode *before* writing code. Name each PR, list its files, estimate its LOC, and name its test scope. If approved, create the branch per layer as you go — not all at once at the end. When rebasing an existing stack, use `git rebase --onto <new-base> <old-base> <branch>` to replay *only* the layer's own commits, never the ancestor layers'.

## 4. Code Review Scope — Single PR Only

When asked to review a PR, focus on that PR's diff and the directly affected files. Do **not** crawl prior merged PRs, review threads on related PRs, or git blame across long histories — those passes are slow and rarely worth their cost.

**How to apply.** For PR review requests, run at most: (1) repo-conventions compliance, (2) shallow bug scan on the diff, (3) light git blame only when re-enabling/reverting code raises a specific question. Skip the prior-PR-comments crawl unless the user explicitly asks for it. Aim to finish a review in 2–3 minutes of agent work, not 10+.

**Why.** Multi-PR archaeology is disproportionate to the value for most reviews. The diff in front of you carries enough signal; reach back only when something in the diff demands it.

## 5. Self-Review Checklist Before Submitting

Before requesting a human reviewer, confirm:

- [ ] All tests passing; linting and formatting applied
- [ ] No commented-out code or personal IDs/UUIDs in shared files
- [ ] Meaningful test coverage (not just coverage numbers — does each test prove a behavior?)
- [ ] No untyped escape hatches (`Any`, `any`, `unknown` cast, `as` cast) without a one-line justification
- [ ] Error handling and logging added for key operations
- [ ] No magic numbers — use named constants
- [ ] Documentation updated where the change affects it (docstrings, READMEs, API references)
- [ ] One thing per PR — if you noticed an unrelated improvement, deferred it to its own PR

## 6. Business Logic Changes Require Tests in the Same PR

**When:** Introducing or modifying business-logic helpers (status transitions, update/merge helpers, schema transforms, payload validation).

**Rule:** Add tests in the same PR. Minimum cases:

- Happy path
- Invalid / no-op path
- Edge case (nested, concurrent, boundary)
- Regression scenario from any prior review comment

Back-filling tests in a follow-up PR is not acceptable for business-logic changes — the implementation and its proof must land together.

## 7. Responding to Reviewer Comments

When addressing review comments on your PR, follow the blocker-resolution protocol: every blocker needs a concrete artifact (code change, new test, or approved deferral), and every reply maps to a diff.

Invoke the **`responding-to-review`** skill when actively addressing comments. The canonical protocol lives in [`rules/responding-to-review.md`](../../rules/responding-to-review.md) — blocker artifact requirements, reply structure, mechanical verification that every flagged line was touched, and the pre-re-review gate.
