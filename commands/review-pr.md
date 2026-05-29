---
description: "[USER] Heavy multi-agent PR review — dispatches 6 cooperating specialist agents (code-reviewer, comment-analyzer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer, code-simplifier) from the pr-review-toolkit plugin in parallel. Optional pre-PR pass for non-trivial branches."
argument-hint: "[review-aspects]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task"]
---

Run a comprehensive PR review using specialized **cooperating** agents. This is a thin apex wrapper around the `pr-review-toolkit` plugin — it dispatches the same agents in parallel via the Task tool.

This is the **cooperating-agents** complement to apex's **adversarial pair pattern** (which uses `superpowers:dispatching-parallel-agents`):
- Adversarial pair = "what's wrong with this design / spec?"
- Cooperating specialists (this command) = "how does each lens see this diff?"

**Review aspects (optional argument):** "$ARGUMENTS"

## Workflow

### 1. Determine scope

- Parse `$ARGUMENTS` for specific aspects (default = `all`)
- Run `git diff --name-only` to identify changed files
- Check if a PR already exists: `gh pr view` (use `--json state,headRefName,baseRefName` for parseable output)

### 2. Map arguments to agents

| Argument | Agent (subagent_type) | When applicable |
|---|---|---|
| `comments` | `pr-review-toolkit:comment-analyzer` | Comments / docs added or modified |
| `tests` | `pr-review-toolkit:pr-test-analyzer` | Test files in diff, or new logic without test coverage |
| `errors` | `pr-review-toolkit:silent-failure-hunter` | Error handling, catch blocks, fallback paths |
| `types` | `pr-review-toolkit:type-design-analyzer` | New types / discriminated unions / dataclasses / Pydantic models |
| `code` | `pr-review-toolkit:code-reviewer` | Always — general quality + CLAUDE.md compliance |
| `simplify` | `pr-review-toolkit:code-simplifier` | After all other reviews pass — polish, not bug-finding |
| `all` | All of the above (applicability-filtered) | Default |

### 3. Dispatch agents IN PARALLEL

**Critical:** Use a single message with multiple `Task` tool calls so agents run concurrently. Don't sequence them — that misses the whole point of cooperating-agent review.

For each applicable agent, the prompt must include:
- Specific files / line ranges to focus on (from `git diff --name-only`)
- Whether to read the full files or just the diff
- What output format is expected (issues grouped by severity, with `file:line` citations)
- A length cap (e.g., "Report critical + important issues only, under 400 words")

Do **NOT** invoke `code-simplifier` in the same batch — it should run *after* the others' findings are addressed, as a final polish pass.

### 4. Aggregate findings

Once agents complete (each returns one message), produce a single consolidated report:

```markdown
# PR Review Summary

## Critical Issues (X found) — must fix before merge
- [<agent>] <issue description> — `<file>:<line>`

## Important Issues (X found) — should fix
- [<agent>] <issue description> — `<file>:<line>`

## Suggestions (X found) — nice to have
- [<agent>] <suggestion> — `<file>:<line>`

## Strengths
- <what's well-done>

## Recommended action plan
1. Fix critical issues first
2. Address important issues
3. Consider suggestions
4. Re-run review on changed files only after fixes
5. (optional) Run `/apex:review-pr simplify` for final polish
```

### 5. Stop conditions

- All applicable agents reported
- Critical issues are surfaced first in the summary
- Each finding has a `file:line` citation
- A clear action plan is presented

## Usage examples

- `/apex:review-pr` — all applicable agents in parallel
- `/apex:review-pr tests errors` — just `pr-test-analyzer` + `silent-failure-hunter`
- `/apex:review-pr simplify` — code-simplifier only (final polish pass)
- `/apex:review-pr comments types` — just comment-analyzer + type-design-analyzer

## Notes

- The underlying `/pr-review-toolkit:review-pr` command is also available — they call the same agents. This wrapper keeps the discovery consistent inside the `/apex:` namespace.
- Agents need git history to compare against — make sure the branch is committed (or staged) before running.
- For your own branch pre-PR: run on the working tree.
- For an open PR: use `gh pr checkout <num>` first, then run.
