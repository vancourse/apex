# Contributing to apex

apex is a personal Claude Code plugin that encodes an opinionated SDLC methodology. Changes to apex itself follow the same discipline apex prescribes for other projects — **eat your own dog food**.

## The rules apex itself follows

### 1. PR loop (not direct-to-main)

Every change opens a draft PR. No direct push to `main`, regardless of how trivial the change feels.

- Branch off `main`: `feat/<topic>`, `chore/<topic>`, `docs/<topic>`, `fix/<topic>`, `refactor/<topic>`
- Open as **draft PR** (`gh pr create --draft`) — see `apex:pr-discipline` §1
- **Squash-merge** to `main`; one commit per PR — `apex:pr-discipline` §2
- Tests / new content live with their change, not back-filled
- See `apex:pr-discipline` for the full rule set

### 2. Copilot review loop

After opening the PR, request Copilot via the **GraphQL `requestReviews` mutation**. The REST API and `gh pr edit --add-reviewer <bot>` both silently no-op on bot reviewers — must use GraphQL throughout.

```bash
PR_ID=$(gh pr view <PR-NUMBER> --json id -q .id)
gh api graphql -f query='mutation($prId: ID!) {
  requestReviews(input: { pullRequestId: $prId, botIds: ["BOT_kgDOCnlnWA"] }) {
    pullRequest { number }
  }
}' -f prId="$PR_ID"
```

**Verify the request landed** via direct GraphQL query (`gh pr view --json reviewRequests` filters bots from output, so you'd be flying blind):

```bash
gh api graphql -f query='query {
  repository(owner: "vancourse", name: "apex") {
    pullRequest(number: <PR-NUMBER>) {
      reviewRequests(first: 10) {
        nodes { requestedReviewer { __typename ... on Bot { login } } }
      }
    }
  }
}'
```

Look for `{"__typename": "Bot", "login": "copilot-pull-request-reviewer"}` in the response.

Then address findings via `apex:responding-to-review` (every blocker → concrete artifact; every reply → diff). **Stop at NITs-only OR 5 rounds**, whichever first. See `apex:copilot-review-loop` for the full loop including the NIT taxonomy and what counts as "stop".

### 3. PR description front-loads reviewer-facing intent

Use the `apex:pr-review-primer` template:

- **What** — what the branch does
- **Why this shape** — design rationale
- **High-level flow** — request lifecycle / control flow (when applicable)
- **State ownership** — what state moves where
- **Concurrency** — racing actors, locking, idempotency (when applicable)
- **Transport choice** — sync vs async, HTTP vs queue, etc. (when applicable)
- **Success / failure / fallback** — observable behavior in each
- **Test plan** — checkboxes for verification

For pure-docs PRs, most of those collapse to N/A — but the **what** and **why this shape** still apply, and the **test plan** lists how to verify cross-references resolve.

### 4. Architecture changes go through ADRs

If a change crosses an architecture boundary — the methodology's own load-bearing decisions (skills lifecycle, dependency model, packaging / distribution, hook event model) — write an ADR first. Use `apex:adr-review` (5-element audit) before committing.

apex itself doesn't have a `docs/adr/` directory yet because the architecture *is* the plugin's content — captured in `FLOW.md`, `README.md`, skill descriptions, and `rules/` shared files. If apex grows enough infrastructure (build pipeline, distribution mechanism, CI test harness across multiple environments) to warrant its own ADRs, this CONTRIBUTING file's PR-loop rule still applies to them.

### 5. The hooks fire on apex's own working tree

apex's hooks (`scan-secrets-on-edit`, `guard-destructive`, `format-on-save`, etc.) apply to *every* edit in *any* worktree where apex is loaded — including this one. That means:

- A real-shaped secret in a skill example or rule file → blocked by `scan-secrets-on-edit`. Use `EXAMPLE_AWS_KEY_AKIA...` or similar fixture markers; `FAKE` / `EXAMPLE` / `TEST` / `DUMMY` / `FIXTURE` / `REPLACE` / `YOUR_` in the same line exempts the match.
- `rm -rf` on root/home/parent / force-push to main / `--no-verify` commits / `.env` writes → blocked by `guard-destructive`.
- Edited Markdown files get auto-formatted by `format-on-save` (Prettier if installed).

## Commit message convention

apex doesn't use the status-doc trailer ritual (that's a BookBridge-specific convention in that repo's `CLAUDE.md`). For apex commits, use a short imperative subject line + body explaining *why*. Examples:

- `Add apex:foo skill`
- `Strengthen api-surface-review with consumer-tracing pass`
- `Extract testing methodology into apex:test-strategy`
- `Fix typo in FLOW.md side-paths section`

Keep subject under 70 characters; body wrapped at 72 columns.

## Acknowledgment of past commits

The first 11 commits on `main` (`9fa9b55` Initial commit through `b547f6b` Architecture + security) were pushed directly without this loop, during the initial setup + comprehensive methodology build-out. The discipline applies from PR #1 forward; the existing `main` history stays as-is.

## When you don't need a PR

There aren't any carve-outs. Even a typo fix opens a PR.

The argument against carve-outs:

- Carve-outs require deciding "is this trivial?" — moving the decision to a per-change human judgment that drifts over time
- Trivial-feeling changes have shipped real bugs (apex's own `bookbridge-pre-pr-check` was promoted *because* "trivial-looking" diffs missed RLS / idempotency / FK violations)
- The PR ceremony cost on a typo is ~30 seconds; the cost of one missed regression is hours

The argument for carve-outs (rejected here):

- Speed
- Founder-mode pre-pilot

If you change your mind on this later, this file is the right place to document the carve-out.

## How a typical apex PR flows

1. Identify the change (new skill, rule update, FLOW.md amendment, etc.)
2. Branch off `main`: `git switch -c <type>/<topic>`
3. Make the change locally; let `format-on-save` and `scan-secrets-on-edit` fire as you edit
4. Commit with a clear imperative subject + body
5. Push: `git push -u origin <type>/<topic>`
6. Open draft PR: `gh pr create --draft --title "<subject>" --body "<reviewer-facing intent>"`
7. Request Copilot via the GraphQL mutation above
8. Verify Copilot landed via direct GraphQL
9. Wait ~15 min for the first round
10. Address findings; push fix-up commits; re-request Copilot
11. Stop at NITs-only OR 5 rounds
12. Mark ready-for-review (yourself, in the role of "the second cognitive pass")
13. Squash-merge to `main`
14. Pull `main` into the marketplace clone (`git -C ~/.claude/plugins/marketplaces/apex pull`)
15. Resync the plugin cache (`rsync -a --delete --exclude='.git' --exclude='.in_use' ~/.claude/plugins/marketplaces/apex/ ~/.claude/plugins/cache/apex/apex/0.1.0/`)
16. Bump `gitCommitSha` in `~/.claude/plugins/installed_plugins.json`
17. Restart Claude.app to surface skill changes

Steps 14–17 are the local-install sync; they're separate from the merge itself and can be batched after multiple merges.
