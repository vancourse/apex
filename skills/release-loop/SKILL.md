---
name: release-loop
description: The milestone-demo release loop — use when starting, resuming, or closing any versioned unit of shippable work (a platform capability, an app, a feature, v1..vn). A release is a milestone whose done is a numbered, operator-runnable demo; issues map 1:1 to demo steps; the first PR is the demo's walking skeleton failing honestly; exit gates (milestone_completion_gate, acceptance_check) close the loop mechanically. Trigger on "new release", "start R<n>", "ship <feature>", "v2 of <app>". Complements apex-flow (which governs plan→design→implement within a slice); this governs the release around the slices. Bug fixes route to investigate-bug + the defect form instead.
---

# The release loop

The finding this skill carries, measured on a real 33-day repo: every gate the
project had guarded an *entry* condition (may this work start, is it declared)
and none guarded an *exit* — so it reached **47 milestones open, 0 closed, 11 of
them finished-but-abandoned**, and the operator experienced total failure while
four of five releases of the "failing" component were complete. A process that
cannot say *done* converts finished work into felt failure.

The loop below is the exit discipline. It assumes the project has the
companion machinery installed: the milestone template, falsifiable `Done when`
on issue forms, the acceptance hook, and the completion gate on a scheduled
lane.

## The loop

1. **Claim the release.** One active front; a second front needs the operator.

2. **Spec.** v1 → the project's discovery lifecycle (recon → PRD → design,
   with review stops — apex-flow's territory). vn → a **dated amendment to
   the living design**, never a second dossier or `design-v2.md`: measured,
   per-version snapshots die unread; living documents survive.

3. **Milestone from the template** ([`templates/milestone.md`](../../templates/milestone.md)): title is an
   outcome a person can watch; description is **DONE = THIS DEMO** — numbered
   observable steps, real input named, and the scope valve written in advance
   ("a further issue is R<n+1> scope unless it makes a numbered step false").

4. **Issues, one per demo step**, each with a falsifiable `Done when` — an
   observation that could come out the other way. "The golden test compares
   both lanes and asserts the rows match" can fail; "a decision is recorded"
   cannot, and unfalsifiable acceptance is how design work gets counted as
   delivery.

5. **First PR = the demo's walking skeleton, failing honestly — and the walls
   before the rooms.** Every boundary the design declares lands here as a
   contract artifact plus the test that pins it, before either side's
   internals. Three wall kinds, in order of preference: **frozen wire DTOs**
   for process/app boundaries (additive-only snapshot, a planted-break test);
   **seam contracts** for a package whose consumers should trust it without
   running its suite (with a coverage check that re-derives the consumed
   surface from the tree, so the contract cannot go quietly incomplete); and
   **typed Protocols** for in-process plug points, conformance checked by the
   type checker's signatures, never by `isinstance` name-matching. A wall no
   test pins is a drawing. Contract-first is what makes the sides
   independently developable and separately testable from day two — and the
   operator can run the skeleton from day one, so building-the-wrong-thing
   surfaces on day one.

6. **Build, slice by slice.** PR carries `Closes #N`; the acceptance hook
   injects #N's `Done when` as tick-boxes; tick honestly — a criterion that
   turned out wrong is stated in the body, not ticked.

7. **Close on the demo.** The operator runs it; all steps true → close. The
   completion gate fails the scheduled lane if a finished milestone sits open
   past its grace period — done is mechanical, not a feeling.

## Refusals

- A milestone whose description holds no demo.
- `Done when` that cannot be false.
- A second dossier for a vn.
- Session narrative (handoffs, sweeps, completion logs) filed into `docs/` —
  it belongs in the PR body, attached to the work that produced it.
- Reopening a closed release to append work — that is the next version.

## The machinery this skill assumes

apex ships the companion pieces; a target repo installs them via
`apex:install-gates`. Nothing here is theory the operator has to build.

| Piece | Where it lives | Tier |
| --- | --- | --- |
| [`templates/milestone.md`](../../templates/milestone.md) | the milestone *description* shape | authoring |
| [`templates/github/work-item.yml`](../../templates/github/work-item.yml) — `Done when`, falsifiable | issue form | authoring |
| [`templates/github/defect.yml`](../../templates/github/defect.yml) — repro, regression guard, consecutive runs | issue form | authoring |
| `hooks/acceptance_checklist.py` | PreToolUse (Bash) — injects #N's criteria at `gh pr create` | advisory |
| `hooks/issue_cap.py` | PreToolUse (Bash) — the second `gh issue create` of a session | advisory |
| `hooks/session_output_gate.py` | PreToolUse (Write) — narrative `.md` into `docs/` | advisory |
| [`templates/gates/acceptance_check.py`](../../templates/gates/acceptance_check.py) | CI — the PR ticked what its issue asked | blocking |
| [`templates/gates/milestone_completion_gate.py`](../../templates/gates/milestone_completion_gate.py) | CI, **scheduled lane** — finished milestones are closed | blocking |

The completion gate is the one that closes the loop, and it belongs on a
**scheduled** lane rather than a PR lane: the condition it watches (a finished
milestone left open) becomes true *after* the last PR merges, when no PR lane
is running. See [`apex:install-gates`](../install-gates/SKILL.md) for the
copy-pasteable step.

## What these gates cannot do

Stated here rather than discovered later, because a gate that is believed to
check more than it does is worse than no gate:

- `acceptance_check.py` cannot tell whether a ticked box is **true**, and it
  cannot make an unfalsifiable criterion good. It buys a forced re-read of the
  issue at close time. That is all it buys.
- `milestone_completion_gate.py` cannot tell whether a milestone *should* be
  finished — only that every issue filed under it is closed. A release missing
  an issue nobody filed reads as finished, which is why step 3's numbered demo
  is the actual definition of done and the gate is only its backstop.
- The three hooks are advisory and fire only inside Claude Code. A blocking
  body-gate that fires on correct work teaches the reader to reach for
  `--admin`, which skips every *other* check too.

## Boundaries with the neighbouring skills

`release-loop` sits **around** these, at release granularity — it owns no step
any of them owns:

| Skill | Owns | Where the boundary is |
| --- | --- | --- |
| [`apex:apex-flow`](../apex-flow/SKILL.md) | plan → design → implement | *within* a slice. Step 2 hands v1 specs to it and takes back a frozen design. |
| [`apex:pr-discipline`](../pr-discipline/SKILL.md) | PR hygiene, layered stacks | *within* a PR. Step 6 files PRs under its rules. |
| [`apex:release-readiness`](../release-readiness/SKILL.md) | semver, changelog, tag, bake | *after* the PRs merge. Step 7 closes the milestone; that gate ships the artifact. |
| [`apex:investigate-bug`](../investigate-bug/SKILL.md) | diagnosis of a defect | this skill touches only the defect *form*. A bug routes there, not through step 3. |
