---
name: copilot-review-loop
description: PR review loop with the Copilot bot reviewer. Encodes how to trigger Copilot via the GraphQL requestReviews mutation (the REST API and gh CLI silently no-op on bot reviewers — both return success without actually requesting the bot), how to verify the request landed (direct GraphQL query, since gh pr view filters bots from reviewRequests), the wait-and-address cycle, and the stop conditions (NITs-only OR 5 rounds — whichever first). Pairs with apex:responding-to-review (per-comment discipline) and apex:pr-discipline. Fires when opening a PR ready for automated review, between iterations of Copilot review, or when capping out the review loop. Keywords: copilot, copilot-pull-request-reviewer, requestReviews mutation, botIds, BOT_kgDOCnlnWA, 5-round cap, NITs, automated review.
---

# Copilot Review Loop

The Copilot pull-request reviewer (`copilot-pull-request-reviewer`) provides automated cross-file review on every PR. This skill encodes the operational details:

- How to trigger Copilot correctly (REST API + `gh pr edit --add-reviewer` + `gh pr view --json reviewRequests` ALL silently no-op or filter when the reviewer is a bot — must use GraphQL throughout)
- How to verify the request actually landed (direct GraphQL query)
- The wait-and-address cycle
- How to bound the review loop so it terminates (NITs OR 5 rounds)

## When to invoke

- A PR is opened and ready for automated review (after `apex:ai-pre-review-checklist` passes)
- A round of Copilot review has produced findings and you've addressed them — time to re-request
- The loop is approaching the 5-round cap and you need to decide whether to stop

Pairs with:

- **`apex:responding-to-review`** — per-comment discipline (every blocker = artifact, every reply = diff, mechanically verify every flagged line is touched)
- **`apex:pr-discipline`** — the broader PR workflow context
- **`apex:ai-pre-review-checklist`** — runs once *before* the first Copilot round to make sure the PR is robust; runs again after capping out the loop as a sanity check

## Step 1 — Trigger Copilot via GraphQL

**Do NOT use** `gh pr edit --add-reviewer <bot>` or the REST `requested_reviewers` POST endpoint. Both return 200 success but silently no-op on bot reviewers. The change won't actually happen and you won't know unless you verify (Step 2).

**Use the GraphQL `requestReviews` mutation with `botIds`:**

```bash
PR_ID=$(gh pr view <PR-NUMBER> --repo <owner>/<repo> --json id -q .id)
gh api graphql -f query='mutation($prId: ID!) {
  requestReviews(input: { pullRequestId: $prId, botIds: ["BOT_kgDOCnlnWA"] }) {
    pullRequest { number }
  }
}' -f prId="$PR_ID"
```

`BOT_kgDOCnlnWA` is the GitHub Bot node ID for `copilot-pull-request-reviewer`. This is universal across all GitHub repos (not project-specific), and is stable across Copilot's deployment churn.

A successful response looks like:

```json
{"data": {"requestReviews": {"pullRequest": {"number": <N>}}}}
```

Anything else — fields with `errors`, HTTP 4xx/5xx — is a failed trigger. Retry with corrected arguments.

## Step 2 — Verify the request landed

`gh pr view --json reviewRequests` returns an EMPTY array when the only requested reviewer is a bot. Do not trust it. The empty array is the same "silently filters bots" trap as the REST API.

**To confirm Copilot was actually requested, query the GraphQL `reviewRequests` directly:**

```bash
gh api graphql -f query='query {
  repository(owner: "<owner>", name: "<repo>") {
    pullRequest(number: <PR-NUMBER>) {
      reviewRequests(first: 10) {
        nodes {
          requestedReviewer {
            __typename
            ... on Bot { login }
            ... on User { login }
          }
        }
      }
    }
  }
}'
```

Look for `{"__typename": "Bot", "login": "copilot-pull-request-reviewer"}` in the `nodes` array.

If the bot isn't in the list, the request didn't land — retry the mutation from Step 1 with the same PR_ID. Do NOT claim "Copilot is reviewing" without this verification step. (`apex:verification-before-completion` applies here: evidence before claims.)

## Step 3 — Wait

Copilot's review typically completes within ~15 minutes of the request landing. Sometimes faster (small PRs), sometimes longer (big PRs, queue backlog). Don't poll aggressively — set a timer for 15-20 min, work on something else, and come back.

**Polling pattern:** if you need to know when the review lands, query `gh pr view --json reviews` periodically — that DOES show bot reviews (only requests are filtered, not completed reviews). A non-empty `reviews` array with `author.login: copilot-pull-request-reviewer` is the signal.

## Step 4 — Address findings

When Copilot's review appears:

1. Read all comments. Categorize each as: **blocker** (must fix), **nit** (cosmetic, optional), or **question** (needs a reply, may or may not need code change).
2. Run `apex:responding-to-review` for the per-comment discipline:
   - Every blocker needs a concrete artifact (code change, test, or approved deferral with reason)
   - Every reply maps to a diff (or an explicit "deferring because X" with ticket link)
   - Mechanically verify every flagged file:line is touched in the response commit before requesting re-review
   - Resolve threads after addressing (don't leave a thread open with "fixed" in the reply text)

## Step 5 — Re-request review

After pushing the addressing commit, re-request Copilot via the same mutation from Step 1. The bot will pick up where it left off, focusing on the new commit (Copilot is incremental — it reviews the delta from the previous round).

Verify the new request landed via Step 2's GraphQL query (the bot may have been auto-removed from `reviewRequests` after its previous review, which is normal — you're re-adding it).

## Step 6 — Decide whether to continue (the 5-round cap)

After each round, evaluate against **two stop conditions** (either / or — terminate at the first one to fire):

**Stop condition A — NITs only.** The only outstanding Copilot comments are cosmetic preferences:

- Naming preferences ("rename `x` to `xCount`") when the original is clear
- Comment / docstring suggestions when the code is self-evident
- Microoptimizations Copilot itself flags as minor ("could be a one-liner")
- Formatting / style the project's linter already accepts

If everything left is in this category, **stop and ship**. (The user owns the final "is this really a nit" judgment — Copilot often labels things as suggestions that are actually correctness issues. When in doubt, address it.)

**Stop condition B — 5 rounds completed.** Five full request-address-rerequest cycles have run. **Stop regardless of what's left.** Five rounds means either:

- Copilot is finding real issues that suggest the PR shape is wrong (consider closing the PR and going back to `apex:design-feature` or `apex:impl-plan-review`)
- Copilot is in a loop, finding cosmetic preferences that don't actually need addressing (the bot's training has a different style preference from your codebase)

Either way, more rounds aren't going to converge. After hitting either stop condition, do a final pass with `apex:ai-pre-review-checklist` (sanity check that nothing critical was lost in the iteration), then request human review for merge.

## What counts as a NIT (Stop condition A)

✅ **Is a nit (safe to ignore):**

- Variable / function naming preferences when the original is clear
- Comment-style preferences when the code is self-evident
- Microoptimizations the reviewer admits are minor
- Formatting / style the linter already accepts
- "Consider using <stylistic alternative>" when both work

❌ **Is NOT a nit (must address):**

- Correctness (off-by-one, edge case missed, race condition, wrong type)
- Security (injection vector, auth bypass, secret leak, SSRF)
- Performance (N+1 query, unbounded loop, memory leak, O(n²) on a hot path)
- Spec compliance (the PRD says X, the code does Y)
- Test coverage gap (a new code path with no direct test — see `apex:ai-pre-review-checklist` Step 7)
- API contract drift (request/response shape doesn't match what's specified)
- Concurrency / state-ownership issue (the code assumes single-instance / single-tenant)

When in doubt, address it. The 5-round cap exists for genuine NIT-loop termination, not as an excuse to skip real issues.

## When the loop terminates without converging

If you hit 5 rounds and there are still non-NIT comments outstanding, that's a signal — not "ship anyway":

1. **PR is too large.** Split into a layered stack per `apex:pr-discipline` §3 and `apex:impl-plan-review` Pass 1.
2. **Design issue, not implementation.** Return to `apex:design-feature` or `apex:apex-flow` §1b to rework the design before more implementation.
3. **Spec ambiguity.** Return to `apex:prd-review` and tighten the spec (Pass 2 scenarios, Pass 7 freeze readiness).

Don't merge-with-known-issues; iterate on the upstream gate. The 5-round cap is about loop termination, not about lowering the quality bar.

## Universality note

The `BOT_kgDOCnlnWA` node ID is GitHub's hosted Copilot reviewer — universal across repos. If you're using a different review bot (a custom Probot, a self-hosted reviewer, an enterprise variant), the bot ID will differ. Look it up with:

```bash
gh api graphql -f query='query { repository(owner: "<owner>", name: "<repo>") { id } }'
# then list available reviewers via the PR's reviewable suggestion API
```

The pattern (GraphQL mutation, GraphQL verification, NITs/5-rounds cap) is bot-agnostic; only the ID changes.
