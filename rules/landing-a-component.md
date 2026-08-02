# Landing a Component Rules

Three rules for getting a component from *sliced* to *merged*, each stated as the rule that would have prevented a measured failure. Throughput is rarely the constraint: one repo ran 661 commits and 200+ merged PRs in fourteen days and the component still was not done. What cost the days was slicing that never touched the package, a design reviewed to rev 7 before the package existed, and two sessions building one slice on two branches. These are the mechanics that decide whether throughput lands.

## 1. A Slice That Does Not Touch the Target Package Is Not a Slice of That Component

**Rule.** A slice counts toward a component only if it creates or changes files **inside that component's package**. Everything else is a dependency, not a slice. **Land prerequisites before the branch that consumes them exists, or land them in the same PR.**

**Why.** A component was cut into twelve slices; the five that closed all landed in *other* packages — a neighbouring service, a shared contracts module, docs. None of them created the package, so the completion bar never moved. Worse, merging them is what moved a dependency underneath the long-lived branch that *did* hold the real work, and one conflicted test file then blocked **9,085 green, fully-tested lines for a day**. A branch that must live for days while other sessions merge into its dependencies has one ending. There is a second bill: a prerequisite built for a slice that never merged is now an unwired orphan — infrastructure for a package that could not land. Prerequisite work inherits the fate of the thing it preceded.

**How to apply.**

- Before counting a slice as progress, name the file it creates or changes in the target package. If there is none, retitle it a dependency and re-count what is actually left.
- Sequence prerequisites to merge **before** the consuming branch is cut, or ship them in the same PR. Never leave both open at once.
- If a consuming branch must live longer than a day, treat every merge into its dependencies as a scheduled conflict — rebase on each one, or shrink the branch until it no longer needs to.
- A stack whose bottom PRs all sit in other packages is not a stack for this component. `apex:impl-plan-review` Pass 2 requires each PR to state what it depends on and what it unblocks; a slice with no target-package file fails that pass by construction.

## 2. A Design May Be at Most One Revision Ahead of Code

**Rule.** If a design is on rev 3 and the package it describes does not exist in the tree, **that is the finding** — stop reviewing and build the thinnest vertical slice that tests the contested decision. This is the corollary stated in [`apex:apex-flow` §12](../skills/apex-flow/SKILL.md#12-bounded-review-loops--every-gate-that-can-send-an-artifact-back-needs-a-cap), which owns the two-round cap, the escalation exception, and the measured cost. Read it there rather than restating it here.

**Why.** Adversarial review terminates against code and does not terminate against prose. A test can falsify a claim; a document cannot, so every pass can always invent another plausible blocker and the loop has no fixed point. The git shape §12 measures — rev 7 across 71 commits, 24 review rounds and **22 reversal/correction commits**, none of it against a package that existed — is what "no fixed point" looks like in a log. When that code was finally written it took about a day and passed every gate on the first run.

**How to apply.** One authoring pass, one adversarial pass, then build. Surviving objections become issues that implementation settles — recorded as known-open, never dropped. The check is cheap and mechanical: count the design's revisions, then look for the package in the tree. If the design is more than one revision ahead, route the work to code, not to another review round.

## 3. Branch Name Matches Worktree Name, and One Slice Means One Branch

**Rule.** One slice, one branch, one worktree — and **the branch's name is the worktree's name**. Claim the slice before you cut the branch.

**Why.** Two sessions independently claimed the same slice: one built the entire package on the obvious branch name, the other sat on a hash-suffixed variant of that same name holding zero package files. The duplicated work is the visible half of the cost. The invisible half is that when worktrees run branches they are not named for, "which tree am I in?" stops being answerable at a glance — and every routing decision after that is made from memory instead of from the prompt.

**How to apply.**

- Claim first: take ownership of the issue, then create the branch and the worktree with the identical name. A start-of-session collision notice is advisory; the claim is what actually prevents the duplicate.
- Never disambiguate a collision by appending a hash to the branch name. Two branches for one slice means two sessions think they own it — resolve the ownership rather than renaming around it.
- Route changes to the correct branch while coding, not at PR time (`apex:pr-discipline` §3).
- A worktree whose branch no longer matches its name is stale state: land or abandon that branch before starting new work in that tree.

## Where these rules are applied

| Rule | Applied in |
|---|---|
| 1. Slices touch the target package | `apex:impl-plan-review` Pass 2 (sequencing / dependency order), `apex:pr-discipline` §3 (layered PR stack, route per-layer while coding), `apex:cross-artifact-consistency` (ORPHAN layers — plan layers with no upstream anchor) |
| 2. At most one revision ahead of code | `apex:apex-flow` §12 (owns the round cap and the escalation exception), `apex:design-review` (design-freeze readiness), `apex:prd-review` / `apex:adr-review` (same cap on their own artifacts), `apex:architecture-design` (caps the ADR set) |
| 3. Branch matches worktree, one slice one branch | `apex:pr-discipline` §1–§3 (branch per layer, one commit per PR, push once), `apex:adversarial-pair` (worktree-isolation rules for dispatched agents) |

Skills should reference this file by section rather than restating the rule. Apply it in the skill's own context; let the canonical statement live here.
