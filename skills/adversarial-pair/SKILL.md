---
name: adversarial-pair
description: Canonical dispatch mechanic for running any apex review skill (design, plan, implementation, PR) as two parallel worktree-isolated agents with opposite framings — cooperative steelman + adversarial attacker — then reconciling their findings. Promoted from prose in CLAUDE.md / design-feature into a first-class skill so every phase-routed review skill points to one source of truth for HOW to dispatch the pair. Pairs with apex:design-review, apex:impl-plan-review, apex:ai-pre-review-checklist, apex:threat-model (any of which can be the review skill the pair runs). Fires after design, plan, or implementation of a non-trivial change, before declaring the artifact frozen / ready / done. Keywords: adversarial pair, parallel review, cooperative agent, adversarial agent, steelman, attack pass, two-agent review, worktree review, cold pass.
---

# Adversarial Pair

The canonical "two-voice review" dispatch mechanic. Promotes the cooperative + adversarial pattern from prose-buried-in-CLAUDE.md (and inline sections in `apex:design-feature` / `apex:design-review`) into a **first-class skill** every phase-routed review can point to.

## The failure it prevents

A review run in the **same session as authoring** has its attack voice contaminated by the just-spent author voice. The reviewer is unconsciously protecting the design they just built — congratulating it, missing the very holes the author already half-rationalized. The cheap inline counter-passes that ship with `apex:design-feature` are the *one-agent* version of this problem; they catch the easy stuff and miss the load-bearing weaknesses.

The fix is **two cognitively-independent passes that cannot infect each other** — different agents, different framings, different worktrees, same input artifact. Reconcile their findings cold.

## When to invoke

Fire after a **non-trivial** change is authored, before it's frozen / merged / shipped:

| Phase | Pair runs | Review skill the pair invokes |
|---|---|---|
| Design freeze | After `apex:design-feature` | `apex:design-review` |
| Plan freeze | After `apex:impl-plan` | `apex:impl-plan-review` |
| Threat-modeling | When feature touches auth / payment / multi-tenant / admin / crypto | `apex:threat-model` |
| Pre-PR | After implementation, before opening PR | `apex:ai-pre-review-checklist` + language review (`apex:python-review` / `apex:typescript-review`) |

**The review skill is the *input* to this dispatch mechanic — not a substitute for it.** `apex:design-review` describes what to look for; `apex:adversarial-pair` describes how to run it twice with opposite framings.

### Skip cases

Don't dispatch the pair (single agent / inline pass is enough) when:

- **Pure-docs change** — no production code touched, no risk surface.
- **Pure-fixture change** — unless the fixture is customer-data-leak-prone.
- **Tiny one-file fix** — single function, no new contract, no new caller.
- **Already-frozen artifact unchanged since last pair pass** — re-running on unchanged input is waste.

Skip cases are about cost. The pair burns roughly 2× the tokens of a single review and dispatches two worktree agents. If the change can't justify that, run the inline counter-pass and move on.

## How to dispatch

The dispatch is three steps: spawn two agents in parallel, wait for both, reconcile.

### Step 1 — Spawn both agents in parallel

Send a **single message with two `Task` tool calls** so they run concurrently. Each call uses `isolation: "worktree"` so the agents work on isolated copies of the repo and can't step on each other's notes / scratch files.

```javascript
Task({
  description: "Cooperative review of <artifact>",
  subagent_type: "general-purpose",
  isolation: "worktree",
  prompt: COOPERATIVE_PROMPT,
})

Task({
  description: "Adversarial review of <artifact>",
  subagent_type: "general-purpose",
  isolation: "worktree",
  prompt: ADVERSARIAL_PROMPT,
})
```

(Some Claude Code versions surface this as the `Agent` tool — the parameter shape is identical; the rest of the apex repo standardizes on `Task` per `commands/review-pr.md`.)

### Step 2 — Prompt templates (fill in `{REVIEW_SKILL}` and `{ARTIFACT_PATH}`)

**Cooperative prompt** — steelman the artifact:

```
You are in an isolated git worktree. Use relative paths; do NOT cd to
absolute paths.

Treat the `{REVIEW_SKILL}` skill as your PASS CHECKLIST and OUTPUT SCHEMA
ONLY: read its SKILL.md to learn (a) what passes / conditions / checks to
run, and (b) what output format to use. IGNORE any framing the skill
prescribes — whether it says "attack mode", "adversarial lens", "cold
pass", or anything else. THIS skill's framing (steelman / cooperative)
overrides the review skill's own framing. (Many apex review skills like
`apex:design-review` are explicitly adversarial — that doesn't apply
here; you are the cooperative half of the pair.)

Run every pass in **steelman mode**: find what works, what reuses well,
what's clean. For each pass condition, cite the strongest evidence in the
artifact (`{ARTIFACT_PATH}`) and code (`file:line`) that it's met.

Default to "defensible" unless the evidence forces "unresolved." Your
job is to find what this artifact gets RIGHT — not to invent praise.

Output: follow the `{REVIEW_SKILL}`'s own output schema if it specifies
one (e.g., `apex:ai-pre-review-checklist` produces a step-by-step
checklist; `apex:design-review` produces per-pass verdicts; etc.).
Otherwise emit per-pass findings (defensible / unresolved / can't-tell),
each with `file:line` citations. No prose summary.
```

**Adversarial prompt** — attack the artifact:

```
You are in an isolated git worktree. Use relative paths; do NOT cd to
absolute paths.

Treat the `{REVIEW_SKILL}` skill as your PASS CHECKLIST and OUTPUT SCHEMA
ONLY: read its SKILL.md to learn (a) what passes / conditions / checks to
run, and (b) what output format to use. IGNORE any framing the skill
prescribes — whether it says "steelman", "cooperative", "defensible", or
anything else. THIS skill's framing (attack / adversarial) overrides the
review skill's own framing. (For review skills whose default framing is
already adversarial — like `apex:design-review` — just use their passes
as-is in attack mode.)

Run every pass in **attack mode**: find what's wrong, missing, hand-waved,
or what the author got away with. For each pass condition, name the
specific thing that's unresolved — flow not covered, primitive duplicated
instead of extended, failure mode without user-visible behavior, invariant
quietly broken.

Default to "refuted" unless the evidence forces "defensible." Your job is
to find what this artifact gets WRONG — not to invent gotchas, but to
read the artifact and the code (`file:line`) like a senior engineer
trying to merge the smallest possible diff.

Output: follow the `{REVIEW_SKILL}`'s own output schema if it specifies
one (run the same passes, but in attack mode). Otherwise emit per-pass
findings (refuted / accepted-residual-risk / ok), each with `file:line`
citations. No prose summary.
```

### Step 3 — Reconcile

Read both reports cold. Categorize each finding:

| Category | Action |
|---|---|
| Both agents flag the same issue | Real blocker. Fix before freeze / merge. |
| Adversarial flags, cooperative doesn't address | Real blocker (cooperative missed it). Fix before freeze / merge. |
| Cooperative defends, adversarial accepts as residual risk | Defensible. Document the rationale in the artifact. |
| Adversarial flags, cooperative defends with citation | Open conflict. You (the human / main loop) adjudicate. |
| Only cooperative flags | Rare — usually means cooperative slipped into critique mode. Verify against the adversarial output before acting. |

The reconciliation is **your** job, not a third agent's. A third reconciler would just re-introduce the single-voice contamination this whole skill exists to prevent.

## Worktree isolation rules (load-bearing)

Three rules every dispatched agent must honor — state them inline in the prompt (agents reliably honor inline statements; reliably forget buried-in-system ones):

- **Relative paths only.** A worktree-isolated agent that `cd`s to an absolute path leaves the worktree silently.
- **No writes outside the worktree.** Agents producing artifacts should write them to relative paths inside the worktree; the main loop collects from each worktree after both finish.
- **No git operations that affect main.** No `git push`, no `git rebase --onto main`, no `git checkout main`. The agent's worktree is read-bystander for the rest of the repo.

The cooperative + adversarial prompt templates above already include the first rule verbatim ("Use relative paths; do NOT cd to absolute paths"). Append the other two if your dispatched agents will write artifacts or run git commands.

## Pass condition

The pair is "done" when:

1. Both agents returned (or one returned and one explicitly errored — investigate the error before proceeding).
2. Every finding is categorized per the reconciliation table.
3. Every "real blocker" is either fixed in the artifact or explicitly accepted with a one-line rationale.
4. Every "open conflict" has a recorded adjudication.

Then the artifact can be frozen / merged / shipped per its phase's gate (`apex:design-review` freeze, `apex:impl-plan-review` plan-freeze, PR-open, etc.).

## Project-specific chains

Projects with their own pre-PR rituals can layer the pair into a longer chain. Example pattern (the BookBridge variant lives in the user's CLAUDE.md):

```
1. apex:adversarial-pair (cooperative + adversarial agents in parallel,
                          input = apex:ai-pre-review-checklist)
2. <project-specific pre-PR catalogue> (single agent — project leaks/RLS/
                                        idempotency rules)
3. <bot reviewer> (Copilot, etc.)
4. Optional heavy review on high-risk PRs.
```

The pair is step 1 — the canonical "two independent views" pass. Project-specific catalogues (BookBridge's `bookbridge-pre-pr-check`, etc.) and bot reviewers run *after* the pair has consolidated the cheap, generic findings.

## Anti-goals

- **Don't dispatch the pair for trivial work.** The skip cases exist. Token cost is real.
- **Don't let the reconciler become a third agent.** That re-introduces the single-voice contamination.
- **Don't combine the two prompts into one "balanced" agent.** That's the same one-agent-does-both pattern this skill replaces. The voices have to be cognitively separate.
- **Don't skip the worktree isolation.** Two agents writing to the same working tree corrupt each other's scratch notes within seconds.

## Relationship to other skills

- **`apex:design-feature`** — owns the design-time checklist. The pair runs *that* checklist twice. design-feature's inline "Adversarial pair pattern" section now points here.
- **`apex:design-review`** — the cold-pass adversarial gate for design. The pair dispatches *this* skill twice with opposite framings.
- **`apex:impl-plan-review`** — analogous for the implementation plan.
- **`apex:ai-pre-review-checklist`** — analogous for pre-PR robustness. The pair is the canonical way to run this checklist twice.
- **`apex:threat-model`** — the heavier two-agent variant referenced in its "when to invoke heavier" criteria. The pair *is* that heavier dispatch.
- **`superpowers:dispatching-parallel-agents`** (external) — generic parallel dispatch from the superpowers plugin. apex's pair is the **opinionated** version: hardcoded cooperative/adversarial framings, worktree-isolation default, reconciliation table. Use this skill, not the generic one, for review-shaped work.
