---
name: apex-flow
description: Opinionated SDLC framework — plan before coding, reconnaissance before design, adversarial design checklist with alternatives and critiques, phase-routed skill gates for planning/implementing/reviewing, port-verification discipline. Fires when planning a non-trivial change, designing a new endpoint or service, refactoring across files, shrinking a bloated PR or design, adding support for a new scope/source/kind/variant, opening a PR, or reviewing changes. Keywords: plan, design, refactor, endpoint, payload, review, PR, implement, ship, shrink, bloated, minimal diff, support a new, subtractive design, reconnaissance, recon.
---

# SDLC Methodology

A small set of rules that catch the most common AI-assisted-coding failure modes: jumping to implementation without a plan, taking the first plausible affordance, shipping pure-addition designs, declaring "done" without verification.

## 1. Plan Before Coding

Before modifying any code, enter plan mode and write a plan. If an issue arises mid-task, stop and replan rather than pushing through with a broken approach.

### 1a. Reconnaissance before design

Before naming a fix to a non-trivial problem (especially perf, refactor, or anything where cost shape matters), run these four questions. They fire at the *diagnosis-to-design boundary* — earlier than the adversarial checklist below — because that's where the framing usually goes wrong:

1. **Cost-shape inversion.** "It does N×M operations" — is there a single operation that returns the same data? SQL → INFORMATION_SCHEMA / system catalogs / vendor stats views. HTTP → batch or list endpoints. File system → directory listing. The first instinct on N-record loops should be "can N become 1?", not "can N get smaller?"
2. **Codebase reconnaissance.** Grep for sibling per-dialect / per-connector / per-engine abstractions in the tree the slow code lives in. If sibling bulk methods exist (e.g. `get_foreign_keys` in a `dialect/` folder), the missing piece (`get_columns`, `get_row_counts`) likely belongs in the same place. Look before designing. **On a large or unfamiliar repo, this look should go through a code graph, not blind grep — ensure a structural index exists first** (Graphify / Serena / Claude Context; run `/apex:setup` if none, see README → *Large-codebase context tools*). Promote to `apex:recon` (below) when the work is design-bearing; the index is its Step 1 substrate. Treat the index as ephemeral, never as the source of truth — you still read the actual functions for their contracts. **Presence is not freshness** — a stale index is worse than none; if it's absent or possibly stale, flag the sibling-miss risk rather than assuming full coverage (apex queries the index; the tool maintains it).
3. **Producer/consumer dual.** Force the dual question: if the proposed fix is on the consumer (caller, frontend, downstream), write down what the producer-side fix would look like. See [`rules/principles.md` §1](../../rules/principles.md#1-producerconsumer-dual) for the canonical statement, the anti-pattern phrase list, and the applied-lens table.
4. **Beware the first plausible affordance.** An existing flag/option/path that looks "broken but fixable" creates unwarranted gravity. Treat it as one candidate among 2–3, not the default. See [`rules/principles.md` §2](../../rules/principles.md#2-beware-the-first-plausible-affordance).

**Why this matters.** A common failure pattern: a slow-data fix anchors on "fix this broken flag" and grows into a several-hundred-LOC consumer-side workaround (lazy loads, UX guards, hydration maps), when the producer-side fix was a single batch query that already had siblings in the dialect/connector folder — visible from a `grep` away. The diagnosis-to-design handoff skipped reconnaissance and let the first plausible affordance lock the framing.

**Promote §1a to an artifact when the work is design-bearing.** For a non-trivial change, or in an unfamiliar / scope-heavy part of the tree, run **`apex:recon`** to emit these four questions as a written *Recon Brief* — enumerate the authoritative primitives, distill their **contracts (not signatures)**, capture invariants + trust boundaries, then diff against and persist to `~/.claude/domain-knowledge/`. recon **is** §1a, promoted from an in-head checklist to a hand-off artifact that `apex:design-feature` / §1b consume. Keep §1a in-head only for small work.

### 1b. Adversarial design checklist

For any non-trivial design task (new endpoint, new service, multi-file refactor, anything you'd "design" rather than just patch), run this 5-step adversarial checklist *before* presenting a design:

1. **Minimum change.** State the smallest possible diff that satisfies the requirement. If you propose anything richer, justify the deviation.
2. **Verify assumptions with citations.** List every load-bearing assumption your design depends on, each with a `file:line` citation that proves it. No "I think X is true" — read the code.
3. **Enumerate 2–3 alternatives with tradeoffs.** Don't present "here's a design." Present "here are 2–3 designs; here's why I'd pick this one."
4. **Adversarial critique pass.** Write 3 critiques a senior engineer would raise against your favorite. Address each, or revise.
5. **Justify additions over reuse.** Pure-addition designs are a smell — if your design only adds code (no deletions, no consolidation), explain why no existing path can be extended. See [`rules/principles.md` §3](../../rules/principles.md#3-pure-addition-designs-are-a-smell).

Skip this checklist only for trivial fixes (typo, single-line behavior change, obvious bug). When in doubt, run it — the cost is one extra paragraph in the response, the saving is multiple round-trips of "you should have asked X first."

**Adversarial pair (DEFAULT for non-trivial shape decisions).** The "is this the minimal design?" call is where the subtractive design surfaces — and a single agent grading its own §1b is the contaminated-voice problem. For non-trivial work (auth / payment / multi-tenant / cryptography / any trust-boundary crossing, or anything you'd dispatch `apex:design-review` for), run §1a+§1b as a **2-agent cooperative+adversarial pair** via `apex:adversarial-pair` (apex's canonical dispatch mechanic) — one steelman, one attack, reconciled — **before** `apex:impl-plan-review`. Running the pair only at impl-plan-review is too late: by then the shape is already chosen. Skipping the pair on non-trivial work is a deviation to justify explicitly, not a silent default.

### 1c. Verify the ask against raw quotes, not writeups

When re-auditing what was actually asked for — "did we close X?", "is Y done?", "what's left from the customer's ask?" — trust the verbatim quote in the source (meeting note, ticket, customer email) and the actual code (grep, Read). Both common shortcuts drift from the source:

- **Status-row symbols / status doc cells** lag the code and frequently summarize only one edge case per feature.
- **"What they're asking for" / "Open questions" interpretation blocks in writeups** mix the literal ask with engineering scope-creep added during analysis.

**4-column audit table.** For every "did we ship X" question, produce a row:

| Raw quote | Writeup interpretation (if any) | Actual code (file:line) | Visible to user? |
|---|---|---|---|

The "visible to user" column is separate from "shipped" because code can be live without being exposed by demo seeds, UI rendering, or docs. A feature can be done in code but invisible in the demo, and the reviewer reasonably concludes "not shipped" from what they see.

**When this fires:** any question that matches "audit existing work against an ask" — not "design a fix." For fix design, §1a (reconnaissance) and §1b (adversarial checklist) own the gates.

## 2. Break Down Hard Problems

For complex work, offload independent subtasks to sub-agents. Keep the main context clean and focused. Use parallel agents when subtasks are independent.

## 3. Self-Improvement Loop

After completing a task, document any non-obvious lessons learned (gotchas, surprising behaviors, approaches that worked well) in memory. Read and apply these lessons at the start of future sessions.

## 4. Prove It Works

A task is never "done" until it has been verified. Run tests, check logs, or use the browser to confirm the change works as expected. Do not declare completion based on code changes alone.

## 5. Autonomous Bug Fixing

When a bug is identified, immediately investigate logs and error output to find the root cause. Attempt to solve it autonomously before asking for help. Check log files proactively when something isn't working — most projects write logs to a known directory; find it once and remember the pattern.

## 6. Phase-Routed Skill Gates

Invoke the relevant skill(s) at the matching phase. **Some skills fire at multiple phases** — `api-surface-review` is the canonical example: it belongs in *planning*, *implementing*, AND *reviewing*, not just review.

### 6a. Phase routing

The canonical phase × skill routing matrix lives in [`FLOW.md`](../../FLOW.md). Refer to that diagram when deciding which skill to invoke at which phase — single source of truth.

### 6b. The multi-phase rule

When a skill is listed at multiple phases (e.g. `api-surface-review` at planning + implementing + pre-PR + reviewing), **invoke it at every matching phase, not just the first.** Invoking it once during planning does not discharge the implementing gate — design intent and code reality diverge, and the implementing pass catches that divergence.

### 6c. Why this exists

Past sessions that skipped these gates produced missed violations (wrong generic names, `function` declarations instead of arrows, un-exported dead symbols, echo-back response fields, hardcoded timeouts) that required a full second review pass. The cost of invoking a skill is one read; the cost of skipping it is multiple review cycles.

## 7. Verify Ports — Don't Trust Them

When porting code from another repository, treat the source's assumptions as stale by default. Invoke the **`verify-ports`** skill for the 5-point checklist (schema / product state / UX / external format / defensive code) and the assumptions-table reporting pattern.

## 8. Domain-Specific Knowledge Files

Long-lived, project-specific knowledge that doesn't belong in any repo lives in `~/.claude/domain-knowledge/<project>.md`. **Read the relevant file at the start of any session that touches that project.**

These files capture facts learned during reviews — things that aren't in the source code or any committed doc but matter for design decisions (which features are dead, which were recently added, which third-party formats users actually paste). When a reviewer corrects an assumption in a PR, log it there so the next session doesn't repeat the mistake.

## 9. Executing Actions with Care

Read, search, and investigate freely — looking is not acting. For actions that are hard to reverse, affect shared systems, or are otherwise risky (deleting data, force-pushing, sending messages, modifying shared infrastructure), confirm before proceeding unless durably authorized. Approval in one context doesn't extend to the next.

## 10. Review-Risk Checklist

Before calling a change ready, check whether it touches any high-risk area:

- auth, permissions, secrets, or data access
- persistence, migrations, or background jobs
- concurrency, retries, queues, or idempotency
- billing, payments, quotas, or limits
- external APIs, webhooks, or third-party formats
- public API contracts or generated types
- large dependency or lockfile changes

If yes, include a short risk note and the verification performed.

## 11. Frontend Hygiene

- Inspect existing design-system components before creating new UI primitives.
- Reuse existing layout, spacing, typography, and interaction patterns.
- Verify important UI changes in a browser when possible.
- Consider keyboard navigation, focus states, loading states, empty states, and error states.
- Avoid broad visual refactors in feature PRs unless requested.
- Do not hardcode copy, colors, spacing, or breakpoints if the repo has tokens or helpers.
- If using a motion library (Framer Motion / Motion, etc.), gate animations behind `prefers-reduced-motion` and reuse the existing animation pattern — don't introduce a second one alongside it.
