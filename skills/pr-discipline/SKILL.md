---
name: pr-discipline
description: PR workflow discipline — draft-PR default, ask before push, full check suite before every commit, squash to one commit per PR, push once, slice non-trivial work into layered PR stacks (≤400 LOC per PR, tests with their layer), keep reviews scoped to the single PR diff. Fires when creating a PR, committing, pushing, reviewing a PR, or planning multi-layer work. Keywords: PR, pull request, draft, commit, push, squash, review, layered, stack, gh, git push.
---

# PR Discipline

Four rules that catch the most common PR-workflow failures: surprise pushes, push-then-fix-then-push cycles, oversized monolithic PRs, and review scope creep.

## 1. Always Create Draft PRs and Ask Before Pushing

Never push branches or create PRs without explicit user confirmation first. When asked to "create a PR", default to draft (`gh pr create --draft`) unless the user explicitly says to publish it.

**Why (cultural).** Users want the option to keep work local or review it before publishing. Surprise pushes / PR creation removes that control.

**Why (mechanical) — and this is the stronger reason.** **A conflicting PR gets no CI at all.** The forge cannot build a merge ref for a PR that conflicts with its base, so no workflow is dispatched — there is nothing to run the workflow *against*. The CLI then reports **"no checks reported"**, which is byte-identical to what a queue that has not started yet reports. The absence of a signal and the absence of a *result* look the same, and the second one is the one you assume.

*Measured:* a branch holding six issues for eleven hours was, at the moment its PR opened, **both behind by 23 commits and conflicted** — so it had **never once been built**. Eleven hours of work, zero CI runs, and nothing in the tooling said so. The branch looked exactly like a branch whose checks were pending.

**So: open the PR on commit one, as a draft.** The draft PR is not a publication — it is the instrument that tells you whether a merge ref can be built at all. Opening it early converts "am I conflicted?" from a question you discover at the end into a fact the forge tells you continuously.

**How to apply.**

- Before any `git push` or `gh pr create`, confirm with the user. If creating a PR is clearly requested, default to `--draft`. Mark ready-for-review only when the user says so.
- Open the draft at the **first** commit, not the last. Then read checks as a three-state signal, never two:

  ```bash
  gh pr checks --watch
  gh pr view --json mergeable,mergeStateStatus
  ```

  `mergeable: CONFLICTING` means **no CI has run or will run** — treat it as red, not as pending. Never read "no checks reported" as "checks are coming"; confirm which of the two it is before believing the branch is healthy.
- A draft that sits conflicted is not waiting for anything. Resolve first, or it accrues hours of unbuilt work.

## 2. Pre-Commit Checks + Minimal-Push Discipline

### Pre-commit checks (run before every `git commit`)

Run the project's full check suite locally before committing. The exact commands are repo-specific — look in `package.json` / `Makefile` / `pyproject.toml` / `CONTRIBUTING.md` for the canonical recipe — but the categories are universal:

- **Build** — strict-type errors that only surface during a full build, not in an editor
- **Lint** — ESLint, Ruff, golangci-lint, etc.
- **Format check** — Prettier, ruff format, gofmt, etc.
- **Type check** — pyright, tsc, mypy, etc.

If any fail, fix and re-run before committing. Never assume "it looks fine" — always verify.

Those four are cheap (seconds). **The test suite is not, and it is governed by the next rule.**

### Don't duplicate CI locally — run the scope your change can reach

**Rule.** Locally, run **the narrowed scope your change can actually reach**. Push, and let CI prove the rest. Reserve a full local run for when you have a *specific* reason to distrust the selector.

**Why.** The full suite locally is the most expensive habit that feels like diligence. *Measured:* a ~6,300-test suite was run locally **six times in one session at ~4 minutes each** — **~25 minutes of pure waiting** — mostly re-proving what CI would prove on push anyway. CI is the parallel, clean-checkout, shared machine; that is what it is for. The local run's job is the fast falsification of *your* change, not a second opinion on everyone else's.

This does **not** license skipping local verification. It scopes it: run the tests your diff can reach, then push. See `apex:verification-before-completion` for what "reach" means per change type.

**Corollary for tooling authors.** If a test selector falls back to **"run everything"** for a path it does not understand, check whether that path can *provably* not reach the rest. A frontend file cannot reach a backend package. Treating a provably-unreachable path as unknown is not a safe default — it is a **four-minute tax on every developer, on every invocation**, and it trains people to stop running the gate at all. Safe-by-default is correct only where reachability is genuinely unknown; where it is knowable, encode it. (`templates/gates/pre_pr_check.py` `TEST_SELECTOR` states this at the installation site.)

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

**Carve-out — this rule and §1's "open the draft on commit one" do not conflict.** They price two different costs, and the distinction is *who is watching*:

| | Draft PR, no reviewers | Published PR, reviewers assigned |
|---|---|---|
| Cost of an extra push | ~0 — no notifications, no force-push noise in a review timeline | High — the cost §2 exists to prevent |
| Value of an extra push | High — it is the only way to learn the merge ref builds (§1) | Low — you already know |

So: **push freely to a draft; squash before marking ready-for-review.** The squash-to-one-commit discipline attaches to the *ready* transition, not to the first push. What §2 forbids is the push→fix→push cycle *in front of an audience*, and a draft has none. If your forge charges for CI minutes, a draft with `[skip ci]` on intermediate pushes preserves both rules — you still get the mergeability signal, which is the part §1 actually needs.

## 3. Layered PR Stack Discipline

When planning non-trivial work (new feature, cross-cutting change, multi-layer refactor), default to a **layered PR stack** rather than one large PR.

**Core rules.**

1. **Slice by architectural layer, not by feature completeness.** Foundation (types + storage + migrations) → service/domain logic → API surface → frontend renderer. Each PR lands a complete, testable layer even if the feature isn't user-visible yet. Never mix layers in one commit.

2. **Cap hand-written LOC per PR.** Target ≤400 hand-written lines; hard ceiling ~600. Generated code (migrations, lockfiles) doesn't count. If a layer exceeds the ceiling, split it further (e.g., types-only PR + storage-only PR).

3. **Tests live with their layer.** Storage tests in the foundation PR, service tests in the service PR, HTTP tests in the API PR, UI tests in the frontend PR. Don't back-fill tests into an earlier PR.

4. **One commit per PR.** Squash before opening. The commit message is one line explaining *why*, plus a short body if needed. No tooling trailers.

5. **No speculative abstractions.** Three similar lines beats a premature helper. Don't introduce a base class, mixin, or config option for a hypothetical second caller.

6. **Route changes to the correct branch while coding, not at PR time.** If you notice uncommitted changes spanning multiple layers, stash and route per-layer *before* committing. Don't commit across layers and try to split later — that path leads to painful rebases.

7. **Cap branch *lifetime*, not only branch size.** A PR under 400 LOC that stays open for a day against a moving base is not a small PR. See `apex:impl-plan-review` Pass 1 for the measured cost and the budget.

8. **After any replay, verify the changed-file set.** Re-cutting a stack after its parent squash-merged is where the base goes wrong silently — a clean `git apply --3way` is not evidence the patch was built from the right base. Canonical statement: [`rules/merge-hygiene.md` §1](../../rules/merge-hygiene.md#1-a-clean-apply-is-not-evidence-of-correctness). Generated artifacts caught in that resolution are regenerated, never hand-merged ([§2](../../rules/merge-hygiene.md#2-generated-artifacts-that-are-committed-must-never-be-hand-merged)) — which is the other half of why "generated code doesn't count" in rule 2 above.

**Why.** A clean 3-PR stack (foundation → service → API → UI, each one thing at one layer) reads as joyful to review. Each PR is small enough to hold in your head, has tests scoped to it, and reviewers can approve layer-by-layer with confidence. Mixing layers forces a painful re-routing + rebase-with-conflicts before the stack is reviewable.

**How to apply.** When the user asks to implement a non-trivial feature, or when you're about to write code that touches more than one of {core types, storage, service, API, frontend}: pause and propose a PR-stack slicing plan in plan mode *before* writing code. Name each PR, list its files, estimate its LOC, and name its test scope. If approved, create the branch per layer as you go — not all at once at the end. When rebasing an existing stack, use `git rebase --onto <new-base> <old-base> <branch>` to replay *only* the layer's own commits, never the ancestor layers' — then **read the resulting changed-file set against the integration branch before doing anything else** (rule 8). Getting `<old-base>` wrong is silent: the replay still applies cleanly, and what it drops is somebody else's merged work.

## 4. Code Review Scope — Single PR Only

When asked to review a PR, focus on that PR's diff and the directly affected files. Do **not** crawl prior merged PRs, review threads on related PRs, or git blame across long histories — those passes are slow and rarely worth their cost.

**How to apply.** For PR review requests, run at most: (1) repo-conventions compliance, (2) shallow bug scan on the diff, (3) light git blame only when re-enabling/reverting code raises a specific question. Skip the prior-PR-comments crawl unless the user explicitly asks for it. Aim to finish a review in 2–3 minutes of agent work, not 10+.

**Why.** Multi-PR archaeology is disproportionate to the value for most reviews. The diff in front of you carries enough signal; reach back only when something in the diff demands it.

## 5. Self-Review Checklist Before Submitting

Before requesting a human reviewer, confirm:

- [ ] **`git diff --name-status origin/<base> HEAD` lists exactly the files you meant to change — and nothing you did not delete** (run it after your last sync; any unintended `D` is a replay that dropped someone else's merged work, and it will still report as mergeable — see [`rules/merge-hygiene.md` §1](../../rules/merge-hygiene.md#1-a-clean-apply-is-not-evidence-of-correctness))
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
