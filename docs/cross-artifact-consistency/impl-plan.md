# Impl plan — Cross-artifact consistency analysis

**Status:** FROZEN as of 2026-06-06 · **Slug:** `cross-artifact-consistency`
**Design:** `design.md` (FROZEN). Built in `skills/cross-artifact-consistency/SKILL.md`.

apex skills are markdown procedures, not code — so this is a **single-layer**
build, and `impl-plan-review`'s heavier passes (migrations, rollout cohorts,
dependency sequencing) are N/A. Recorded tightly per apex's "skip gates for
small work."

## §1 Layered stack (single layer)

- **L1 — the skill** `skills/cross-artifact-consistency/SKILL.md` (frontmatter +
  the Pass-0…4 procedure). Registered automatically via its `description`
  frontmatter; surfaced in README skills table + FLOW.md matrix. No new slash
  command (ships as an `[AUTO]` skill — keeps the 13-command menu lean).

## §3 Test plan (scenario lineage)

This is a procedure skill (no runtime code), so "tests" = a manual exercise of
the SKILL against fixture artifact-sets. Validation owners by frozen-PRD scenario:

- **serves S1** (clean chain → CONSISTENT) · **serves S2** (DROPPED) · **serves
  S3** (ORPHAN) · **serves S4** (CONFLICT) · **serves S5 / Pass 0** (un-frozen
  refusal). First real exercise: run it against an actual frozen feature folder
  (`docs/execution-tiers/`) to confirm the `serves S#` lineage parses.
- No **E2E** owner — no UI surface (justified, per the PRD's no-E2E tag).

## §4 Rollout

Direct (a skill doc activates next session). No flag, no migration.

## §5 Reversibility

Fully reversible — `git revert` the SKILL.md + registry rows. No data, no state.

## Plan freeze

FROZEN. Build complete (`skills/cross-artifact-consistency/SKILL.md`). Residual:
validate the `serves S#` parse against a real impl-plan on first use.
